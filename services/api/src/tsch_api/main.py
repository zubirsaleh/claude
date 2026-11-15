import secrets
from collections.abc import Callable, Iterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from tsch_contracts import (
    AccountMode,
    BrokerAdapter,
    IllegalTransition,
    OrderProposal,
    ReceiptStatus,
)
from tsch_risk import RiskPolicy
from tsch_risk.policy import EXECUTABLE_MODES

from .brokers import LIVE_EXECUTION_COMPILED_IN, SimBroker
from .config import Settings, get_settings
from .db import (
    Account,
    AuditLog,
    Base,
    FillRecord,
    OrderCommand,
    Strategy,
    append_audit,
    get_state,
    make_engine,
    make_sessionmaker,
    verify_audit_chain,
)
from .orders import KILL_SWITCH_KEY, CommandConflict, CommandNotFound, OrderService
from .schemas import (
    AccountOut,
    AuditOut,
    AuditVerifyOut,
    ClosePositionIn,
    ConnectionStatus,
    FillOut,
    KillSwitchIn,
    KillSwitchOut,
    ModesOut,
    OrderOut,
    ProposalIn,
    StrategyOut,
)
from .seed import seed

API_VERSION = "0.1.0"


def _policy(settings: Settings) -> RiskPolicy:
    return RiskPolicy(
        max_risk_pct=settings.risk_max_risk_pct,
        max_daily_loss_pct=settings.risk_max_daily_loss_pct,
        max_drawdown_pct=settings.risk_max_drawdown_pct,
        max_open_positions=settings.risk_max_open_positions,
        max_volume=settings.risk_max_volume,
        max_spread_points=settings.risk_max_spread_points,
        max_quote_age_s=settings.risk_max_quote_age_s,
    )


def create_app(
    settings: Settings | None = None,
    *,
    engine: Engine | None = None,
    sim: SimBroker | None = None,
    clock: Callable[[], datetime] | None = None,
    create_schema: bool = False,
) -> FastAPI:
    settings = settings or get_settings()
    engine = engine or make_engine(settings.database_url)
    sessions = make_sessionmaker(engine)
    clock = clock or (lambda: datetime.now(UTC))
    sim = sim or SimBroker(clock=clock)
    adapters: dict[AccountMode, BrokerAdapter] = {AccountMode.SIM: sim}
    policy = _policy(settings)
    operator_token = settings.resolved_operator_token()

    @asynccontextmanager
    async def lifespan(_: FastAPI):  # type: ignore[no-untyped-def]
        if create_schema:
            Base.metadata.create_all(engine)
        with sessions() as s:
            seed(s, sim.get_identity())
        yield

    app = FastAPI(
        title="Trading Strategy Control Hub API",
        version=API_VERSION,
        description="SIM + MT5 DEMO control plane. Live execution is not available.",
        lifespan=lifespan,
    )
    app.state.sim = sim
    app.state.engine = engine

    def db() -> Iterator[Session]:
        with sessions() as s:
            yield s

    def operator(authorization: Annotated[str | None, Header()] = None) -> str:
        if operator_token is None:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                                "operator auth not configured; write actions disabled")
        scheme, _, token = (authorization or "").partition(" ")
        if scheme.lower() != "bearer" or not secrets.compare_digest(token, operator_token):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid operator credentials",
                                headers={"WWW-Authenticate": "Bearer"})
        return "operator"

    DB = Annotated[Session, Depends(db)]
    Operator = Annotated[str, Depends(operator)]

    def service(s: Session, mode: AccountMode) -> OrderService:
        adapter = adapters.get(mode)
        if adapter is None:
            raise HTTPException(status.HTTP_409_CONFLICT, f"mode {mode} is not connected")
        return OrderService(s, adapter, policy, timedelta(seconds=settings.approval_ttl_seconds),
                            clock)

    def service_for(s: Session, command_id: str) -> OrderService:
        cmd = s.get(OrderCommand, command_id)
        if cmd is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "command not found")
        return service(s, AccountMode(cmd.mode))

    @app.exception_handler(CommandConflict)
    async def _conflict(_: Request, exc: CommandConflict):  # type: ignore[no-untyped-def]
        from fastapi.responses import JSONResponse
        return JSONResponse({"detail": str(exc)}, status_code=409)

    @app.exception_handler(IllegalTransition)
    async def _illegal(_: Request, exc: IllegalTransition):  # type: ignore[no-untyped-def]
        from fastapi.responses import JSONResponse
        return JSONResponse({"detail": str(exc)}, status_code=409)

    @app.exception_handler(CommandNotFound)
    async def _nf(_: Request, exc: CommandNotFound):  # type: ignore[no-untyped-def]
        from fastapi.responses import JSONResponse
        return JSONResponse({"detail": "command not found"}, status_code=404)

    # --- read endpoints ----------------------------------------------------------------
    @app.get("/health", tags=["system"])
    def health() -> dict[str, str]:
        return {"status": "ok", "version": API_VERSION}

    @app.get("/api/v1/system/modes", response_model=ModesOut, tags=["system"])
    def modes() -> ModesOut:
        return ModesOut(
            default_mode=AccountMode(settings.default_mode),
            executable_modes=sorted(EXECUTABLE_MODES),
            live_execution_available=LIVE_EXECUTION_COMPILED_IN,
            notes={
                "SIM": "Internal simulated broker. All prices are synthetic.",
                "MT5_DEMO": "Not connected. Host-side mt5-agent arrives in Phase 4.",
                "TRADINGVIEW_PAPER_MANUAL": "Manual journal only. No TradingView order API.",
                "LIVE_DISABLED": "Live execution is not compiled into this release.",
            },
        )

    @app.get("/api/v1/connections", response_model=list[ConnectionStatus], tags=["system"])
    def connections() -> list[ConnectionStatus]:
        h = sim.get_health()
        return [
            ConnectionStatus(name="SIM broker", mode=AccountMode.SIM,
                             status="CONNECTED" if h.connected else "DISCONNECTED",
                             detail=h.detail, last_heartbeat_utc=h.last_heartbeat_utc),
            ConnectionStatus(name="MT5 terminal (native MCP)", mode=AccountMode.MT5_DEMO,
                             status="NOT CONNECTED",
                             detail="No verified MT5 terminal / mt5-agent registered."),
            ConnectionStatus(name="TradingView", mode=AccountMode.TRADINGVIEW_PAPER_MANUAL,
                             status="MANUAL ONLY",
                             detail="Personal research in your own Claude session. No data "
                                    "enters this app; no order integration exists."),
        ]

    @app.get("/api/v1/accounts", response_model=list[AccountOut], tags=["accounts"])
    def accounts(s: DB) -> list[Account]:
        return list(s.scalars(select(Account).order_by(Account.created_utc)))

    @app.get("/api/v1/strategies", response_model=list[StrategyOut], tags=["strategies"])
    def strategies(s: DB) -> list[Strategy]:
        return list(s.scalars(select(Strategy).order_by(Strategy.key)))

    @app.get("/api/v1/orders", response_model=list[OrderOut], tags=["orders"])
    def list_orders(s: DB, state: str | None = None,
                    limit: Annotated[int, Query(ge=1, le=500)] = 100) -> list[OrderCommand]:
        q = select(OrderCommand).order_by(OrderCommand.created_utc.desc()).limit(limit)
        if state:
            q = q.where(OrderCommand.state == state)
        return list(s.scalars(q))

    @app.get("/api/v1/orders/{command_id}", response_model=OrderOut, tags=["orders"])
    def get_order(command_id: str, s: DB) -> OrderCommand:
        cmd = s.get(OrderCommand, command_id)
        if cmd is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "command not found")
        return cmd

    @app.get("/api/v1/fills", response_model=list[FillOut], tags=["fills"])
    def fills(s: DB, limit: Annotated[int, Query(ge=1, le=1000)] = 200) -> list[FillRecord]:
        return list(s.scalars(select(FillRecord).order_by(FillRecord.ts_utc.desc()).limit(limit)))

    @app.get("/api/v1/audit", response_model=list[AuditOut], tags=["audit"])
    def audit(s: DB, limit: Annotated[int, Query(ge=1, le=1000)] = 200) -> list[AuditLog]:
        return list(s.scalars(select(AuditLog).order_by(AuditLog.id.desc()).limit(limit)))

    @app.get("/api/v1/audit/verify", response_model=AuditVerifyOut, tags=["audit"])
    def audit_verify(s: DB) -> AuditVerifyOut:
        ok, bad = verify_audit_chain(s)
        return AuditVerifyOut(ok=ok, first_bad_id=bad)

    @app.get("/api/v1/risk/kill-switch", response_model=KillSwitchOut, tags=["risk"])
    def get_kill(s: DB) -> KillSwitchOut:
        return KillSwitchOut(engaged=bool(get_state(s, KILL_SWITCH_KEY, False)))

    # --- write endpoints (operator only) -----------------------------------------------
    @app.post("/api/v1/orders/proposals", response_model=OrderOut, status_code=201,
              tags=["orders"])
    def propose(body: ProposalIn, s: DB, actor: Operator) -> OrderCommand:
        if body.account_mode not in EXECUTABLE_MODES:
            raise HTTPException(status.HTTP_409_CONFLICT,
                                f"mode {body.account_mode} cannot take order proposals")
        proposal = OrderProposal(**body.model_dump())
        return service(s, body.account_mode).propose(proposal, actor)

    @app.post("/api/v1/orders/{command_id}/approve", response_model=OrderOut, tags=["orders"])
    def approve(command_id: str, s: DB, actor: Operator) -> OrderCommand:
        return service_for(s, command_id).approve(command_id, actor)

    @app.post("/api/v1/orders/{command_id}/submit", response_model=OrderOut, tags=["orders"])
    def submit(command_id: str, s: DB, actor: Operator) -> OrderCommand:
        return service_for(s, command_id).submit(command_id, actor)

    @app.post("/api/v1/orders/{command_id}/reconcile", response_model=OrderOut,
              tags=["orders"])
    def reconcile(command_id: str, s: DB, actor: Operator) -> OrderCommand:
        return service_for(s, command_id).reconcile(command_id, actor)

    @app.post("/api/v1/sim/positions/{position_id}/close", tags=["sim"])
    def close_sim_position(
        position_id: str, body: ClosePositionIn, s: DB, actor: Operator,
        idempotency_key: Annotated[str, Header(min_length=16, max_length=64)],
    ) -> dict[str, str | None]:
        if not body.confirm:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "close requires confirm=true")
        receipt = sim.close_demo_position(position_id, idempotency_key)
        append_audit(s, actor, "position.close",
                     {"position_id": position_id, "status": receipt.status.value,
                      "message": receipt.message}, ts=clock())
        s.commit()
        acct = s.scalars(select(Account).where(Account.mode == AccountMode.SIM.value)).one()
        service(s, AccountMode.SIM).ingest_fills(acct.id)
        if receipt.status != ReceiptStatus.ACKED:
            raise HTTPException(status.HTTP_409_CONFLICT, receipt.message)
        return {"status": receipt.status.value, "deal_id": receipt.deal_id}

    @app.put("/api/v1/risk/kill-switch", response_model=KillSwitchOut, tags=["risk"])
    def put_kill(body: KillSwitchIn, s: DB, actor: Operator) -> KillSwitchOut:
        service(s, AccountMode.SIM).set_kill_switch(body.engaged, actor)
        return KillSwitchOut(engaged=body.engaged)

    return app
