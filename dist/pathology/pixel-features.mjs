// See LICENSE and THIRD_PARTY_NOTICES.md.
import { PathologyAnalysisError } from "./runtime.mjs";
async function createPixelFeatureSampler(raster, features, radius, execution) {
  const usesLocal = features.some((feature2) => feature2.startsWith("local_"));
  const stride = raster.width + 1;
  const sums = usesLocal ? new Float64Array(stride * (raster.height + 1)) : null;
  const squares = usesLocal ? new Float64Array(stride * (raster.height + 1)) : null;
  if (sums != null && squares != null) {
    execution.consume(raster.width * raster.height * 4);
    for (let y = 0; y < raster.height; y += 1) {
      let rowSum = 0;
      let rowSquares = 0;
      for (let x = 0; x < raster.width; x += 1) {
        const pixel = y * raster.width + x;
        const value = Math.round(
          0.299 * raster.rgb[pixel * 3] + 0.587 * raster.rgb[pixel * 3 + 1] + 0.114 * raster.rgb[pixel * 3 + 2]
        );
        rowSum += value;
        rowSquares += value * value;
        const target = (y + 1) * stride + x + 1;
        sums[target] = sums[target - stride] + rowSum;
        squares[target] = squares[target - stride] + rowSquares;
        if ((pixel + 1) % 65536 === 0)
          await execution.checkpoint(
            "pixel-feature-integrals",
            pixel + 1,
            raster.width * raster.height
          );
      }
    }
  }
  const rectangularSum = (array2, left, top, right, bottom) => array2[bottom * stride + right] - array2[top * stride + right] - array2[bottom * stride + left] + array2[top * stride + left];
  return {
    vector(pixel) {
      if (!Number.isSafeInteger(pixel) || pixel < 0 || pixel >= raster.width * raster.height)
        throw new PathologyAnalysisError(
          "INVALID_ARGUMENT",
          "Pixel feature positions must lie inside the supplied raster."
        );
      let mean = 0;
      let standardDeviation = 0;
      if (sums != null && squares != null) {
        const x = pixel % raster.width;
        const y = Math.floor(pixel / raster.width);
        const left = Math.max(0, x - radius);
        const top = Math.max(0, y - radius);
        const right = Math.min(raster.width, x + radius + 1);
        const bottom = Math.min(raster.height, y + radius + 1);
        const count6 = (right - left) * (bottom - top);
        mean = rectangularSum(sums, left, top, right, bottom) / count6;
        standardDeviation = Math.sqrt(
          Math.max(
            0,
            rectangularSum(squares, left, top, right, bottom) / count6 - mean * mean
          )
        );
      }
      return features.map((feature2) => {
        switch (feature2) {
          case "red":
            return raster.rgb[pixel * 3];
          case "green":
            return raster.rgb[pixel * 3 + 1];
          case "blue":
            return raster.rgb[pixel * 3 + 2];
          case "optical_density_red":
            return -Math.log((raster.rgb[pixel * 3] + 1) / 256);
          case "optical_density_green":
            return -Math.log((raster.rgb[pixel * 3 + 1] + 1) / 256);
          case "optical_density_blue":
            return -Math.log((raster.rgb[pixel * 3 + 2] + 1) / 256);
          case "local_mean_luma":
            return mean;
          case "local_std_luma":
            return standardDeviation;
        }
      });
    }
  };
}
export { createPixelFeatureSampler };
