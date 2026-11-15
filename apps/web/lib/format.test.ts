import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { fmtNum, fmtQty, fmtTime, statusTone } from "./format.ts";

describe("fmtNum", () => {
  it("shows N/A for missing values instead of zero", () => {
    assert.equal(fmtNum(null), "N/A");
    assert.equal(fmtNum(undefined), "N/A");
    assert.equal(fmtNum(""), "N/A");
    assert.equal(fmtNum("abc"), "N/A");
  });
  it("formats decimals from API strings", () => {
    assert.equal(fmtNum("10000.5"), "10,000.50");
  });
});

describe("fmtTime", () => {
  it("renders UTC in Kuala Lumpur time (UTC+8)", () => {
    assert.ok(fmtTime("2026-03-10T01:30:00Z").includes("09:30:00"));
  });
  it("returns N/A for invalid input", () => {
    assert.equal(fmtTime("nope"), "N/A");
  });
});

describe("statusTone", () => {
  it("never shows a non-connected integration as ok", () => {
    assert.equal(statusTone("NOT CONNECTED"), "off");
    assert.equal(statusTone("CONNECTED"), "ok");
  });
});

describe("fmtQty", () => {
  it("strips storage padding only", () => {
    assert.equal(fmtQty("0.0100000000"), "0.01");
    assert.equal(fmtQty("1.0000"), "1");
    assert.equal(fmtQty("100"), "100");
    assert.equal(fmtQty(null), "N/A");
  });
});
