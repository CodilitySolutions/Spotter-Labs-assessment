/** Name of the wind-arrow icon registered with the map. */
export const WIND_ARROW_ICON = 'wind-arrow';

/**
 * A small arrow pointing north (up), drawn once on a canvas: dark ink with a white outline so
 * it reads over both the basemap and the coloured heatmap bands. The map rotates it to the
 * direction the wind blows towards.
 */
export function windArrowImage(pixelRatio = 2): ImageData {
  const size = 24 * pixelRatio;
  const canvas = document.createElement('canvas');
  canvas.width = canvas.height = size;
  const ctx = canvas.getContext('2d')!;
  ctx.scale(pixelRatio, pixelRatio);

  const arrow = new Path2D();
  arrow.moveTo(12, 3); // tip
  arrow.lineTo(18, 11);
  arrow.lineTo(14, 11);
  arrow.lineTo(14, 21); // shaft
  arrow.lineTo(10, 21);
  arrow.lineTo(10, 11);
  arrow.lineTo(6, 11);
  arrow.closePath();

  ctx.lineJoin = 'round';
  ctx.strokeStyle = 'rgba(255, 255, 255, 0.95)';
  ctx.lineWidth = 3;
  ctx.stroke(arrow);
  ctx.fillStyle = '#3d3c39';
  ctx.fill(arrow);
  return ctx.getImageData(0, 0, size, size);
}
