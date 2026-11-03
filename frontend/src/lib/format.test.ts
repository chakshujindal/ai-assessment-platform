import { describe, expect, it } from "vitest";
import { errorMessage } from "../api";
import { formatClock, formatScore, parseSkills, statusLabel } from "./format";

describe("formatClock", () => {
  it("formats minutes and hours", () => {
    expect(formatClock(75)).toBe("1:15");
    expect(formatClock(3725)).toBe("1:02:05");
    expect(formatClock(-4)).toBe("0:00");
  });
});

describe("formatScore", () => {
  it("rounds to one decimal and handles missing scores", () => {
    expect(formatScore(7.25, 10)).toBe("7.3 / 10");
    expect(formatScore(null, 10)).toBe("-");
  });
});

describe("parseSkills", () => {
  it("splits, trims and drops empties", () => {
    expect(parseSkills(" Python, SQL ,, ")).toEqual(["Python", "SQL"]);
  });
});

describe("statusLabel", () => {
  it("maps known statuses and passes unknown ones through", () => {
    expect(statusLabel("in_progress")).toBe("In progress");
    expect(statusLabel("custom")).toBe("custom");
  });
});

describe("errorMessage", () => {
  it("reads FastAPI string and validation details", () => {
    expect(errorMessage(409, { detail: "Already submitted." })).toBe("Already submitted.");
    const validation = { detail: [{ msg: "Value error, give a topic" }, { msg: "too long" }] };
    expect(errorMessage(422, validation)).toBe("give a topic; too long");
    expect(errorMessage(429, null)).toMatch(/Too many requests/);
    expect(errorMessage(500, "oops")).toBe("Request failed (500).");
  });
});
