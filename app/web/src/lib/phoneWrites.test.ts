import { describe, expect, it } from "vitest";
import { phoneMayWrite } from "./phoneWrites";

describe("phoneMayWrite", () => {
  it("allows the listed writes", () => {
    expect(phoneMayWrite("POST", "/api/push/subscribe")).toBe(true);
    expect(phoneMayWrite("PUT", "/api/journal/2026-01-01")).toBe(true);
    expect(phoneMayWrite("POST", "/api/planner")).toBe(true);
    expect(phoneMayWrite("DELETE", "/api/planner/12")).toBe(true);
    expect(phoneMayWrite("PUT", "/api/reading/card-1")).toBe(true);
    expect(phoneMayWrite("POST", "/api/food/meals/3/log")).toBe(true);
    expect(phoneMayWrite("POST", "/api/food/log")).toBe(true);
    expect(phoneMayWrite("POST", "/api/food/entries/bulk")).toBe(true);
    expect(phoneMayWrite("POST", "/api/food/entries/7/restore")).toBe(true);
    expect(phoneMayWrite("PUT", "/api/settings/plan")).toBe(true);
    expect(phoneMayWrite("PUT", "/api/settings/calories")).toBe(true);
    expect(phoneMayWrite("POST", "/api/garmin/sync")).toBe(true);
    expect(phoneMayWrite("POST", "/api/activities/12/fetch")).toBe(true);
  });
  it("allows managing your own dish names, anchored", () => {
    expect(phoneMayWrite("POST", "/api/food/dishes/12/names")).toBe(true);
    expect(phoneMayWrite("PATCH", "/api/food/dishes/12/names/3")).toBe(true);
    expect(phoneMayWrite("DELETE", "/api/food/dishes/12/names/3")).toBe(true);
    expect(phoneMayWrite("DELETE", "/api/food/dishes/12")).toBe(false);
    expect(phoneMayWrite("PUT", "/api/food/dishes/12/names")).toBe(false);
    expect(phoneMayWrite("POST", "/api/food/dishes/12/names/3")).toBe(false);
    expect(phoneMayWrite("POST", "/api/food/dishes//names")).toBe(false);
  });

  it("keeps the new food writes anchored and method-specific", () => {
    expect(phoneMayWrite("POST", "/api/food/log/extra")).toBe(false);
    expect(phoneMayWrite("PUT", "/api/food/log")).toBe(false);
    expect(phoneMayWrite("POST", "/api/food/entries/7/restore/x")).toBe(false);
    expect(phoneMayWrite("POST", "/api/food/entries//restore")).toBe(false);
    expect(phoneMayWrite("POST", "/api/food/barcode/12345678/lookup")).toBe(false);
  });
  it("ignores the query string and method case", () => {
    expect(phoneMayWrite("post", "/api/weight/entries?x=1")).toBe(true);
  });
  it("rejects Garmin push/remove of planned sessions", () => {
    expect(phoneMayWrite("POST", "/api/planner/5/garmin")).toBe(false);
    expect(phoneMayWrite("DELETE", "/api/planner/5/garmin")).toBe(false);
  });
  it("rejects reading feed refresh and feed setting", () => {
    expect(phoneMayWrite("POST", "/api/reading/feed/refresh")).toBe(false);
    expect(phoneMayWrite("PUT", "/api/settings/reading-feed")).toBe(false);
  });
  it("rejects prefix lookalikes and wrong methods", () => {
    expect(phoneMayWrite("POST", "/api/push/subscribe/extra")).toBe(false);
    expect(phoneMayWrite("POST", "/api/planner-evil")).toBe(false);
    expect(phoneMayWrite("POST", "/api/settings/weatherx")).toBe(false);
    expect(phoneMayWrite("POST", "/api/settings/calories")).toBe(false);
    expect(phoneMayWrite("PUT", "/api/settings/calories/extra")).toBe(false);
    expect(phoneMayWrite("DELETE", "/api/push/subscribe")).toBe(false);
    expect(phoneMayWrite("GET", "/api/planner")).toBe(false);
    expect(phoneMayWrite("PUT", "/api/journal/")).toBe(false);
    expect(phoneMayWrite("POST", "/api/activities/1/fetch/x")).toBe(false);
    expect(phoneMayWrite("POST", "/api/activities/abc/fetch")).toBe(false);
    expect(phoneMayWrite("POST", "/api/days/2026-01-01/fetch")).toBe(false);
  });
  it("rejects sharing, credentials and goals", () => {
    expect(phoneMayWrite("POST", "/api/share/reset")).toBe(false);
    expect(phoneMayWrite("DELETE", "/api/share/sessions/abc")).toBe(false);
    expect(phoneMayWrite("POST", "/api/goals")).toBe(false);
    expect(phoneMayWrite("PUT", "/api/credentials")).toBe(false);
  });
});
