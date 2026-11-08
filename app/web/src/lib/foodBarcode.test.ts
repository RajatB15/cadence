import { describe, expect, it } from "vitest";
import { validBarcode } from "./foodBarcode";

describe("barcode", () => {
  it("accepts 6 to 14 digits only", () => {
    expect(["123456", "8901234567890", "12345678901234"].every(validBarcode)).toBe(true);
    expect(["12345", "123456789012345", "12a456", "", " 123456"].some(validBarcode)).toBe(false);
  });
});
