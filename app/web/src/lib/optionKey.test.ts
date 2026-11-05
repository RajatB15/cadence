import { describe, expect, it } from "vitest";
import { optionKey } from "../components/Chart";

describe("optionKey", () => {
  it("is equal for identical content rebuilt each render", () => {
    const make = () => ({ series: [{ data: [1, 2, 3] }], tooltip: { formatter: (v: number) => `${v}` } });
    expect(optionKey(make())).toBe(optionKey(make()));
  });
  it("changes when data changes", () => {
    expect(optionKey({ series: [{ data: [1] }] })).not.toBe(optionKey({ series: [{ data: [2] }] }));
  });
});
