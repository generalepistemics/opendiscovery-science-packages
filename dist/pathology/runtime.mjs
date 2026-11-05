// See LICENSE and THIRD_PARTY_NOTICES.md.
import { createHash as createHash9 } from "node:crypto";
var DEFAULT_PATHOLOGY_LIMITS = {
  maxPixels: 4194304,
  maxObjects: 4096,
  maxBoundaryCoordinates: 32768,
  maxReferenceCoordinates: 262144,
  maxWorkUnits: 64e6,
  maxTrainingRows: 8192,
  maxFeatures: 16
};
var PathologyAnalysisError = class extends Error {
  constructor(code2, message) {
    super(message);
    this.code = code2;
    this.name = "PathologyAnalysisError";
  }
  code;
};
var PathologyExecution = class {
  limits;
  work = 0;
  signal;
  onProgress;
  constructor(options = {}) {
    this.signal = options.signal;
    this.onProgress = options.onProgress;
    this.limits = { ...DEFAULT_PATHOLOGY_LIMITS, ...options.limits };
    for (const key2 of Object.keys(DEFAULT_PATHOLOGY_LIMITS)) {
      const value = this.limits[key2];
      if (!Number.isSafeInteger(value) || value < 1 || value > DEFAULT_PATHOLOGY_LIMITS[key2]) {
        throw new PathologyAnalysisError(
          "INVALID_ARGUMENT",
          "Pathology limits must be positive integers no larger than the engine ceilings."
        );
      }
    }
    this.check();
  }
  consume(units) {
    this.work += units;
    if (!Number.isFinite(this.work) || this.work > this.limits.maxWorkUnits) {
      throw new PathologyAnalysisError(
        "RESOURCE_EXHAUSTED",
        "The pathology operation exceeds the bounded work budget."
      );
    }
    this.check();
  }
  check() {
    if (this.signal?.aborted)
      throw new PathologyAnalysisError(
        "CANCELLED",
        "The pathology operation was cancelled."
      );
  }
  async checkpoint(phase, completed, total) {
    this.check();
    this.onProgress?.({ phase, completed, total });
    await new Promise((resolve2) => setTimeout(resolve2, 0));
    this.check();
  }
};
function pathologySha256(bytes2) {
  return `sha256:${createHash9("sha256").update(bytes2).digest("hex")}`;
}
function pathologyLabelBytes(labels) {
  const bytes2 = new Uint8Array(labels.length * 4);
  const view = new DataView(bytes2.buffer);
  for (let index4 = 0; index4 < labels.length; index4 += 1)
    view.setUint32(index4 * 4, labels[index4], true);
  return bytes2;
}
function pathologyJsonSha256(value) {
  return pathologySha256(new TextEncoder().encode(JSON.stringify(value)));
}
function pathologyFeatureTableSha256(table5) {
  const provenance2 = table5.provenance;
  return pathologyJsonSha256({
    features: table5.features,
    rows: table5.rows,
    provenance: {
      schemaVersion: provenance2.schemaVersion,
      method: provenance2.method,
      methodVersion: provenance2.methodVersion,
      source: provenance2.source,
      raster: provenance2.raster,
      objectInputSha256: provenance2.objectInputSha256,
      parameters: provenance2.parameters,
      geometryMeasurement: provenance2.geometryMeasurement,
      researchOnly: provenance2.researchOnly,
      warnings: provenance2.warnings
    }
  });
}
function requirePathologyIdentity(value, description3) {
  if (typeof value !== "string" || value.trim().length === 0 || value.length > 4096 || /[\u0000-\u001f\u007f]/u.test(value)) {
    throw new PathologyAnalysisError(
      "INVALID_ARGUMENT",
      `${description3} must be a bounded nonempty stable identity.`
    );
  }
}
export { PathologyAnalysisError, PathologyExecution, pathologyFeatureTableSha256, pathologyJsonSha256, pathologyLabelBytes, pathologySha256, requirePathologyIdentity };
