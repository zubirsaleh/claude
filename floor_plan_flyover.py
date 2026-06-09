#!/usr/bin/env python3
"""
Cinematic 4K floor plan flyover animation.

Generates a 20-second 3840×2160 MP4 that simulates a drone flying over
the architectural floor plan with perspective tilt, slow pan, zoom,
cinematic colour grading, vignette, and film grain.
"""

import math, os, sys
import cv2
import numpy as np
from PIL import Image, ImageEnhance

# ── paths ────────────────────────────────────────────────────────────────────
FLOOR_PLAN = "/root/.claude/uploads/086f69bc-84b1-5447-8ed7-19c6527b039f/26531fd3-202250.png"
OUTPUT_MP4  = "/home/user/claude/floor_plan_flyover.mp4"

# ── video settings ───────────────────────────────────────────────────────────
OUT_W, OUT_H = 3840, 2160   # 4K UHD
FPS          = 30
DURATION_S   = 20
TOTAL_FRAMES = FPS * DURATION_S

# ── canvas size (must be larger than output for smooth panning) ───────────────
CANVAS_W = 7680
CANVAS_H = 5760


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def ease_sine(t: float) -> float:
    """Smooth sinusoidal ease-in/out (0→0, 0.5→1, 1→0 style not needed)."""
    return 0.5 - 0.5 * math.cos(math.pi * t)


def lerp(a, b, t):
    return a + (b - a) * t


def interpolate_keyframes(kfs: list[dict], t: float) -> dict:
    """Interpolate numerical keys across keyframes using sine ease."""
    if t <= kfs[0]["t"]:
        return {k: v for k, v in kfs[0].items() if k != "t"}
    if t >= kfs[-1]["t"]:
        return {k: v for k, v in kfs[-1].items() if k != "t"}
    for i in range(len(kfs) - 1):
        k1, k2 = kfs[i], kfs[i + 1]
        if k1["t"] <= t <= k2["t"]:
            lt = ease_sine((t - k1["t"]) / (k2["t"] - k1["t"]))
            return {k: lerp(k1[k], k2[k], lt) for k in k1 if k != "t"}
    return {k: v for k, v in kfs[-1].items() if k != "t"}


def perspective_tilt(frame: np.ndarray, tilt_v: float, tilt_h: float) -> np.ndarray:
    """
    Apply a keystone / perspective warp.
    tilt_v  – vertical tilt (0 = top-down, 1 = strong forward lean)
    tilt_h  – horizontal lean (-1…+1)
    """
    h, w = frame.shape[:2]
    v  = tilt_v * 0.13
    hs = tilt_h * w * 0.04
    src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    dst = np.float32([
        [w * v + hs,       h * v],
        [w * (1 - v) + hs, h * v],
        [w + hs,           h],
        [hs,               h],
    ])
    M = cv2.getPerspectiveTransform(src, dst)
    return cv2.warpPerspective(frame, M, (w, h), borderMode=cv2.BORDER_REFLECT)


def make_vignette(w: int, h: int, strength: float = 0.60) -> np.ndarray:
    cx, cy = w / 2, h / 2
    Y, X   = np.ogrid[:h, :w]
    dist   = np.sqrt(((X - cx) / cx) ** 2 + ((Y - cy) / cy) ** 2)
    vig    = np.clip(1.0 - (dist * strength) ** 1.6, 0.0, 1.0).astype(np.float32)
    return np.stack([vig, vig, vig], axis=-1)


def dof_blur(frame: np.ndarray, tilt_v: float) -> np.ndarray:
    """
    Blur the top rows more when tilt is high (near horizon = soft focus).
    """
    if tilt_v < 0.15:
        return frame
    blur_rows = int(frame.shape[0] * tilt_v * 0.20)
    if blur_rows < 2:
        return frame
    ks = max(1, blur_rows // 8) * 2 + 1   # odd kernel
    ks = min(ks, 31)
    top = frame[:blur_rows]
    top_blurred = cv2.GaussianBlur(top, (ks, ks), 0)
    # fade blend
    alpha = np.linspace(0.8, 0.0, blur_rows, dtype=np.float32).reshape(-1, 1, 1)
    blended = (top_blurred * alpha + top * (1 - alpha)).astype(np.uint8)
    out = frame.copy()
    out[:blur_rows] = blended
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    print("── Loading floor plan …")
    pil = Image.open(FLOOR_PLAN).convert("RGB")

    print("── Upscaling to 8K canvas …")
    pil_big = pil.resize((CANVAS_W, CANVAS_H), Image.LANCZOS)

    # Subtle pre-processing: sharpen + contrast + saturation
    pil_big = ImageEnhance.Sharpness(pil_big).enhance(1.4)
    pil_big = ImageEnhance.Contrast(pil_big).enhance(1.10)
    pil_big = ImageEnhance.Color(pil_big).enhance(1.18)

    canvas_bgr = cv2.cvtColor(np.array(pil_big), cv2.COLOR_RGB2BGR)

    # ── Camera path ──────────────────────────────────────────────────────────
    # Keys: cx/cy (0-1 in canvas), zoom (relative scale), tilt_v, tilt_h
    keyframes = [
        # Opening: high aerial, centred, slight forward lean
        {"t": 0.00, "cx": 0.50, "cy": 0.48, "zoom": 0.72, "tilt_v": 0.18, "tilt_h":  0.00},
        # Descend & glide toward left wing (bedrooms)
        {"t": 0.14, "cx": 0.30, "cy": 0.42, "zoom": 0.88, "tilt_v": 0.38, "tilt_h": -0.28},
        # Hover over bedroom cluster – closer look
        {"t": 0.28, "cx": 0.22, "cy": 0.50, "zoom": 1.08, "tilt_v": 0.50, "tilt_h": -0.18},
        # Sweep across living / family room (centre)
        {"t": 0.45, "cx": 0.50, "cy": 0.56, "zoom": 1.05, "tilt_v": 0.44, "tilt_h":  0.00},
        # Drift right toward verandah + garage
        {"t": 0.62, "cx": 0.74, "cy": 0.52, "zoom": 1.00, "tilt_v": 0.40, "tilt_h":  0.28},
        # Zoom on garage
        {"t": 0.73, "cx": 0.84, "cy": 0.50, "zoom": 1.12, "tilt_v": 0.35, "tilt_h":  0.20},
        # Ascend & pull back
        {"t": 0.86, "cx": 0.60, "cy": 0.44, "zoom": 0.83, "tilt_v": 0.26, "tilt_h":  0.12},
        # Final wide, nearly top-down – full overview
        {"t": 1.00, "cx": 0.50, "cy": 0.48, "zoom": 0.72, "tilt_v": 0.14, "tilt_h":  0.00},
    ]

    vignette = make_vignette(OUT_W, OUT_H, strength=0.62)

    print(f"── Rendering {TOTAL_FRAMES} frames at {OUT_W}×{OUT_H} …")
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(OUTPUT_MP4, fourcc, FPS, (OUT_W, OUT_H))

    rng = np.random.default_rng(42)   # deterministic grain seed

    for fi in range(TOTAL_FRAMES):
        t  = fi / max(TOTAL_FRAMES - 1, 1)
        kf = interpolate_keyframes(keyframes, t)

        cx, cy         = kf["cx"], kf["cy"]
        zoom           = kf["zoom"]
        tilt_v, tilt_h = kf["tilt_v"], kf["tilt_h"]

        # Crop window from canvas
        vw = int(OUT_W / zoom)
        vh = int(OUT_H / zoom)
        cx_px = int(cx * CANVAS_W)
        cy_px = int(cy * CANVAS_H)
        x1 = max(0, min(cx_px - vw // 2, CANVAS_W - vw))
        y1 = max(0, min(cy_px - vh // 2, CANVAS_H - vh))
        crop = canvas_bgr[y1:y1 + vh, x1:x1 + vw]

        # Resize to output resolution
        frame = cv2.resize(crop, (OUT_W, OUT_H), interpolation=cv2.INTER_LANCZOS4)

        # 3-D perspective tilt
        frame = perspective_tilt(frame, tilt_v, tilt_h)

        # Depth-of-field hint at the horizon
        frame = dof_blur(frame, tilt_v)

        # Convert to float32 for compositing
        f = frame.astype(np.float32)

        # Cinematic warm grade (golden-hour look)
        f[:, :, 2] *= 1.06   # R up
        f[:, :, 1] *= 1.02   # G slight up
        f[:, :, 0] *= 0.96   # B down
        np.clip(f, 0, 255, out=f)

        # Vignette
        f *= vignette

        # Subtle film grain (σ≈3)
        f += rng.normal(0, 3.0, f.shape).astype(np.float32)
        np.clip(f, 0, 255, out=f)

        writer.write(f.astype(np.uint8))

        if fi % FPS == 0:
            pct = 100 * fi / TOTAL_FRAMES
            print(f"   {fi:5d} / {TOTAL_FRAMES}  ({pct:5.1f}%)")

    writer.release()
    size_mb = os.path.getsize(OUTPUT_MP4) / 1_048_576
    print(f"\n── Done!  →  {OUTPUT_MP4}  ({size_mb:.1f} MB)")
    print(f"   {DURATION_S}s · {OUT_W}×{OUT_H} · {FPS} fps")


if __name__ == "__main__":
    main()
