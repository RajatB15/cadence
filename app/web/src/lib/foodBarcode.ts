/** The server only resolves 6 to 14 digit codes (EAN-13, EAN-8, UPC-A, UPC-E and short internal codes). */
export const validBarcode = (c: string): boolean => /^[0-9]{6,14}$/.test(c);
