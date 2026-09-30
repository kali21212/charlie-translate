import { normalizeRegion, bitmapRegion } from "./screenshotGeometry";

test("reverse drag and out-of-viewport pointer are clamped", () => {
  expect(normalizeRegion({ x: 90, y: 70 }, { x: -20, y: 10 }, 100, 80)).toEqual(
    { x: 0, y: 10, width: 90, height: 60 }
  );
});
test("bitmap crop respects zoom/DPI and rounds outward", () => {
  expect(
    bitmapRegion(
      { x: 10.2, y: 20.3, width: 50, height: 30 },
      { width: 200, height: 100 },
      { width: 400, height: 200 }
    )
  ).toEqual({ x: 20, y: 40, width: 101, height: 61 });
});
test.each([
  { x: 0, y: 0, width: 1, height: 10 },
  { x: 90, y: 0, width: 20, height: 10 },
  { x: NaN, y: 0, width: 20, height: 10 },
])("rejects invalid selections before allocating a canvas", (region) => {
  expect(() =>
    bitmapRegion(
      region,
      { width: 100, height: 100 },
      { width: 200, height: 200 }
    )
  ).toThrow();
});
test("bounds OCR memory use", () => {
  expect(() =>
    bitmapRegion(
      { x: 0, y: 0, width: 5000, height: 5000 },
      { width: 5000, height: 5000 },
      { width: 5000, height: 5000 }
    )
  ).toThrow("截图过大");
});
