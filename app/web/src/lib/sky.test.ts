import { describe, expect, it } from "vitest";
import { autoTheme, beatSeconds, minutesOf, moodFor, skyStage } from "./sky";

describe("the sky through the day", () => {
  it("changes stage at the stated times, and wraps at midnight", () => {
    const at = (h: number, m = 0) => skyStage(h * 60 + m);
    expect([at(0), at(4, 59), at(5), at(6, 59), at(7), at(10, 59), at(11), at(15, 59), at(16), at(18, 29), at(18, 30), at(20, 29), at(20, 30), at(23, 59)])
      .toEqual(["night", "night", "dawn", "dawn", "morning", "morning", "day", "day", "golden", "golden", "dusk", "dusk", "night", "night"]);
    expect(skyStage(1440 + 8 * 60)).toBe("morning");
    expect(skyStage(-60)).toBe("night");
  });
  it("is light in daylight and dark otherwise", () => {
    expect(autoTheme(6 * 60 + 29)).toBe("dark");
    expect(autoTheme(6 * 60 + 30)).toBe("light");
    expect(autoTheme(18 * 60 + 29)).toBe("light");
    expect(autoTheme(18 * 60 + 30)).toBe("dark");
    expect(autoTheme(0)).toBe("dark");
  });
  it("reads minutes after midnight from a date", () => {
    expect(minutesOf(new Date(2026, 10, 15, 7, 45))).toBe(465);
  });
});

describe("moods", () => {
  it("maps the day phases that have one, and nothing else", () => {
    expect(moodFor("post_workout")).toBe("afterglow");
    expect(moodFor("race_week")).toBe("electric");
    expect(moodFor("race_day")).toBe("electric");
    expect(moodFor("sick")).toBe("calm");
    expect(moodFor("time_off")).toBe("calm");
    expect(moodFor("rest_day")).toBe("sage");
    for (const p of ["morning", "midday", "afternoon", "evening", "late", "dawn", undefined, null, "bogus"]) expect(moodFor(p as string)).toBe("none");
  });
});

describe("the decorative pulse", () => {
  it("beats at the resting rate and is absent when the rate is unknown or implausible", () => {
    expect(beatSeconds(60)).toBe(1);
    expect(beatSeconds(48)).toBe(1.25);
    expect(beatSeconds(null)).toBeNull();
    expect(beatSeconds(undefined)).toBeNull();
    expect(beatSeconds(0)).toBeNull();
    expect(beatSeconds(200)).toBeNull();
    expect(beatSeconds(NaN)).toBeNull();
  });
});
