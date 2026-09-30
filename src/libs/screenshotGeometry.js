// CSS pixels and captured bitmap pixels differ with zoom and display scaling.
export function normalizeRegion(start, end, width, height) {
  const clamp = (value, max) => Math.min(max, Math.max(0, value));
  const x = clamp(Math.min(start.x, end.x), width);
  const y = clamp(Math.min(start.y, end.y), height);
  return {
    x,
    y,
    width: clamp(Math.max(start.x, end.x), width) - x,
    height: clamp(Math.max(start.y, end.y), height) - y,
  };
}

export function bitmapRegion(region, viewport, bitmap) {
  for (const value of [
    region.x,
    region.y,
    region.width,
    region.height,
    viewport.width,
    viewport.height,
    bitmap.width,
    bitmap.height,
  ]) {
    if (!Number.isFinite(value))
      throw new Error("Invalid screenshot dimensions");
  }
  if (
    region.x < 0 ||
    region.y < 0 ||
    region.width < 4 ||
    region.height < 4 ||
    viewport.width <= 0 ||
    viewport.height <= 0 ||
    bitmap.width <= 0 ||
    bitmap.height <= 0 ||
    region.x + region.width > viewport.width ||
    region.y + region.height > viewport.height
  ) {
    throw new Error("截图区域无效，请重新框选");
  }
  const sx = bitmap.width / viewport.width;
  const sy = bitmap.height / viewport.height;
  const x = Math.floor(region.x * sx);
  const y = Math.floor(region.y * sy);
  const width = Math.ceil((region.x + region.width) * sx) - x;
  const height = Math.ceil((region.y + region.height) * sy) - y;
  if (width * height > 16000000) throw new Error("截图过大，请缩小框选区域");
  return { x, y, width, height };
}
