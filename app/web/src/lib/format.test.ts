import { describe, expect, it } from "vitest";
import {
  deltaTone,
  formatDelta,
  formatDuration,
  formatMetric,
  formatPace,
  parseDay,
  reminderCopy,
  timeAgo,
} from "./format";
import type { CredentialStatus } from "./types";

const base: CredentialStatus = {
  configured: true,
  expires_on: "2027-10-22",
  days_remaining: 365,
  level: "ok",
  active_threshold: null,
  thresholds: [30, 7, 1],
  reminder_dates: ["2027-09-22", "2027-10-15", "2027-10-21"],
  reminder_key: null,
  dismissed: false,
  today: "2026-10-22",
};

describe("reminderCopy", () => {
  it("shows nothing while the key is healthy or missing", () => {
    expect(reminderCopy(base)).toBeNull();
    expect(reminderCopy({ ...base, level: "missing", configured: false })).toBeNull();
  });

  it("escalates tone across thresholds", () => {
    expect(reminderCopy({ ...base, level: "notice", days_remaining: 30 })?.tone).toBe("info");
    expect(reminderCopy({ ...base, level: "warning", days_remaining: 7 })?.tone).toBe("warn");
    expect(reminderCopy({ ...base, level: "critical", days_remaining: 1 })?.title).toMatch(/tomorrow/);
  });

  it("respects dismissal except once expired", () => {
    expect(reminderCopy({ ...base, level: "warning", days_remaining: 5, dismissed: true })).toBeNull();
    expect(reminderCopy({ ...base, level: "expired", days_remaining: 0, dismissed: true })?.tone).toBe("danger");
  });

  it("flags unreadable expiry", () => {
    expect(reminderCopy({ ...base, level: "invalid_expiry", expires_on: null })?.title).toMatch(/unreadable/);
  });
});

describe("formatters", () => {
  it("parses calendar days locally", () => {
    const d = parseDay("2027-10-22");
    expect([d.getFullYear(), d.getMonth(), d.getDate()]).toEqual([2027, 9, 22]);
  });

  it("formats durations, pace and metrics", () => {
    expect(formatDuration(45 * 60)).toBe("45m");
    expect(formatDuration(3725)).toBe("1h 02m");
    expect(formatPace(1800, 6000)).toBe("5:00");
    expect(formatPace(1800, null)).toBeNull();
    expect(formatPace(359.8, 1000)).toBe("6:00");
    expect(formatMetric(7.5, "sleep_hours")).toBe("7:30");
    expect(formatMetric(7.999, "sleep_hours")).toBe("8:00");
  });

  it("colours deltas by direction of benefit", () => {
    expect(deltaTone(5, true)).toBe("good");
    expect(deltaTone(5, false)).toBe("bad");
    expect(deltaTone(1, true)).toBe("neutral");
    expect(deltaTone(5, null)).toBe("neutral");
    expect(formatDelta(-4.24)).toBe("−4.2%");
    expect(formatDelta(null)).toBe("No baseline");
  });
});

describe("timeAgo", () => {
  const now = new Date("2026-10-25T09:00:00Z");
  it("reads naturally at each scale", () => {
    expect(timeAgo(new Date("2026-10-25T08:59:40Z"), now)).toBe("just now");
    expect(timeAgo(new Date("2026-10-25T08:15:00Z"), now)).toBe("45 min ago");
    expect(timeAgo(new Date("2026-10-25T03:31:00Z"), now)).toBe("5 h ago");
    expect(timeAgo(new Date("2026-10-24T08:00:00Z"), now)).toBe("1 day ago");
    expect(timeAgo(new Date("2026-10-21T09:00:00Z"), now)).toBe("4 days ago");
  });
});
