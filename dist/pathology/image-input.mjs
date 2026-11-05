// See LICENSE and THIRD_PARTY_NOTICES.md.
import { PathologyAnalysisError, requirePathologyIdentity } from "./runtime.mjs";
import { isUint8Array } from "node:util/types";
var MAX_PATHOLOGY_PIXEL_RASTER = 1048576;
function copyPathologySource(source2) {
  requirePathologyIdentity(source2.sourceId, "Image source ID");
  requirePathologyIdentity(source2.sourceRevision, "Image source revision");
  const { x, y, width, height } = source2.region;
  if (![x, y, width, height, x + width, y + height].every(Number.isFinite) || x < 0 || y < 0 || width <= 0 || height <= 0 || x + width <= x || y + height <= y)
    throw new PathologyAnalysisError(
      "INVALID_ARGUMENT",
      "Image footprints require finite nonnegative origins and representable positive dimensions."
    );
  const calibration2 = source2.calibration;
  if (calibration2 != null && (typeof calibration2.verified !== "boolean" || ![calibration2.micronsPerPixelX, calibration2.micronsPerPixelY].every(
    (value) => Number.isFinite(value) && value > 0
  )))
    throw new PathologyAnalysisError(
      "INVALID_ARGUMENT",
      "Image calibration requires finite positive XY pixel sizes and explicit verification status."
    );
  return {
    sourceId: source2.sourceId,
    sourceRevision: source2.sourceRevision,
    region: { x, y, width, height },
    ...calibration2 == null ? {} : {
      calibration: {
        verified: calibration2.verified,
        micronsPerPixelX: calibration2.micronsPerPixelX,
        micronsPerPixelY: calibration2.micronsPerPixelY
      }
    }
  };
}
function validatePathologyDimensions(width, height, execution, maximumPixels = MAX_PATHOLOGY_PIXEL_RASTER) {
  if (!Number.isSafeInteger(width) || !Number.isSafeInteger(height) || width < 1 || height < 1)
    throw new PathologyAnalysisError(
      "INVALID_ARGUMENT",
      "Image raster dimensions must be positive integers."
    );
  const pixels2 = width * height;
  if (!Number.isSafeInteger(pixels2) || pixels2 > Math.min(maximumPixels, execution.limits.maxPixels))
    throw new PathologyAnalysisError(
      "RESOURCE_EXHAUSTED",
      "Image raster exceeds the bounded pixel-operation size."
    );
  return pixels2;
}
function copyPathologyImage(source2, raster, execution, maximumPixels = MAX_PATHOLOGY_PIXEL_RASTER) {
  const pixels2 = validatePathologyDimensions(
    raster.width,
    raster.height,
    execution,
    maximumPixels
  );
  if (!isUint8Array(raster.rgb) || raster.rgb.byteLength !== pixels2 * 3)
    throw new PathologyAnalysisError(
      "INVALID_ARGUMENT",
      "Pixel operations require exactly width*height*3 interleaved RGB8 bytes."
    );
  return {
    source: copyPathologySource(source2),
    raster: {
      width: raster.width,
      height: raster.height,
      rgb: new Uint8Array(raster.rgb)
    }
  };
}
function samePathologyImage(left, right) {
  return left.sourceId === right.sourceId && left.sourceRevision === right.sourceRevision && left.region.x === right.region.x && left.region.y === right.region.y && left.region.width === right.region.width && left.region.height === right.region.height;
}
export { copyPathologyImage, copyPathologySource, samePathologyImage, validatePathologyDimensions };
