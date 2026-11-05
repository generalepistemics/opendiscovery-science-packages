// See LICENSE and THIRD_PARTY_NOTICES.md.
import { PathologyAnalysisError, PathologyExecution, pathologyLabelBytes, pathologySha256, requirePathologyIdentity } from "./runtime.mjs";
import { copyPathologySource, validatePathologyDimensions } from "./image-input.mjs";
import { isUint8Array as isUint8Array2 } from "node:util/types";
async function rasterizePathologyAnnotations(input) {
  const execution = new PathologyExecution(input);
  const { kind, width, height } = input;
  const pixels2 = validatePathologyDimensions(width, height, execution);
  if (!isUint8Array2(input.bytes) || input.bytes.byteLength > 16 * 1024 * 1024)
    throw exhausted(
      "Annotation sources are limited to 16 MiB of actual GeoJSON bytes."
    );
  const bytes2 = new Uint8Array(input.bytes);
  const image = copyPathologySource(input.image);
  const reference = copyAnnotationReference(input.reference);
  if (pathologySha256(bytes2) !== reference.contentSha256)
    throw invalid2(
      "Annotation bytes do not match the caller-recorded source content digest."
    );
  if (kind === "instances" && reference.unannotatedClass != null)
    throw invalid2(
      "Instance annotations use label zero for outside-annotation space, not a semantic background class."
    );
  const overlapPolicy = input.overlapPolicy ?? "error";
  if (overlapPolicy !== "error" && overlapPolicy !== "last-feature-wins")
    throw invalid2("Unknown annotation-overlap policy.");
  const classMapping2 = copyClassMapping(input.classMapping ?? []);
  if (kind === "semantic" && classMapping2.length === 0)
    throw invalid2(
      "Semantic reference rasterization requires an explicit source-label to class-ID mapping."
    );
  const mapping = new Map(
    classMapping2.map((item) => [item.sourceLabel, item.classId])
  );
  execution.consume(bytes2.byteLength);
  let data2;
  try {
    data2 = JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(bytes2));
  } catch {
    throw invalid2("Annotation sources must be valid UTF-8 GeoJSON.");
  }
  const collection = Array.isArray(data2) ? data2 : isRecord3(data2) && data2.type === "FeatureCollection" && Array.isArray(data2.features) ? data2.features : isRecord3(data2) && data2.type === "Feature" ? [data2] : null;
  if (collection == null)
    throw invalid2(
      "Annotation sources must contain GeoJSON Features, a FeatureCollection, or a QuPath feature array."
    );
  if (collection.length > execution.limits.maxObjects)
    throw exhausted(
      "Annotation source feature count exceeds the bounded reference-object limit."
    );
  let coordinateCount2 = 0;
  const seen = /* @__PURE__ */ new Set();
  const parsed = [];
  for (const [index4, feature2] of collection.entries()) {
    if (!isRecord3(feature2) || feature2.type !== "Feature" || !isRecord3(feature2.geometry))
      throw invalid2(
        "Quantitative annotation references require located polygon Features."
      );
    const rawId = feature2.id;
    if (rawId != null && typeof rawId !== "string" && (typeof rawId !== "number" || !Number.isFinite(rawId)))
      throw invalid2("Reference feature IDs must be finite numbers or strings.");
    const id2 = rawId == null ? `${reference.sourceId}:ordinal:${index4}` : `${reference.sourceId}:${typeof rawId}:${String(rawId)}`;
    requirePathologyIdentity(id2, "Reference feature ID");
    if (seen.has(id2))
      throw invalid2("Reference annotation feature IDs must be unique.");
    seen.add(id2);
    const geometry = feature2.geometry;
    const polygons = geometry.type === "Polygon" ? [geometry.coordinates] : geometry.type === "MultiPolygon" && Array.isArray(geometry.coordinates) ? geometry.coordinates : null;
    if (polygons == null || polygons.length === 0 || polygons.length > 1024)
      throw invalid2(
        "Reference masks require Polygon or MultiPolygon geometries."
      );
    const copied = polygons.map((polygon2) => {
      if (!Array.isArray(polygon2) || polygon2.length < 1 || polygon2.length > 1024)
        throw invalid2(
          "Reference polygons require bounded exterior/hole rings."
        );
      return polygon2.map((ring2) => {
        if (!Array.isArray(ring2) || ring2.length < 4)
          throw invalid2(
            "Reference polygon rings must be closed and have at least four coordinates."
          );
        coordinateCount2 += ring2.length;
        if (coordinateCount2 > execution.limits.maxReferenceCoordinates)
          throw exhausted(
            "Reference annotations exceed the total coordinate budget."
          );
        const points = ring2.map((point4) => {
          if (!Array.isArray(point4) || point4.length !== 2 || typeof point4[0] !== "number" || typeof point4[1] !== "number" || !Number.isFinite(point4[0]) || !Number.isFinite(point4[1]))
            throw invalid2("Reference polygons require finite XY pairs.");
          const x = point4[0] + (reference.coordinateSpace === "roi-pixels" ? image.region.x : 0);
          const y = point4[1] + (reference.coordinateSpace === "roi-pixels" ? image.region.y : 0);
          if (!Number.isFinite(x) || !Number.isFinite(y))
            throw invalid2(
              "Reference coordinates exceed finite source-pixel range."
            );
          return [x, y];
        });
        if (points[0][0] !== points[points.length - 1][0] || points[0][1] !== points[points.length - 1][1])
          throw invalid2("Reference polygon rings must be explicitly closed.");
        return points;
      });
    });
    parsed.push({
      id: id2,
      sourceLabel: readSourceLabel(feature2.properties),
      polygons: copied
    });
  }
  const labels = kind === "semantic" ? new Uint8Array(pixels2) : new Uint32Array(pixels2);
  if (kind === "semantic" && reference.unannotatedClass != null)
    labels.fill(reference.unannotatedClass);
  const assigned = new Uint8Array(pixels2);
  const instances = [];
  for (const [index4, feature2] of parsed.entries()) {
    const label2 = kind === "semantic" ? feature2.sourceLabel == null ? void 0 : mapping.get(feature2.sourceLabel) : index4 + 1;
    if (label2 == null)
      throw invalid2(
        "Every semantic reference feature must match the explicit source-label mapping; ignored labels can map to zero."
      );
    for (const polygon2 of feature2.polygons)
      await paintPolygon(
        polygon2,
        label2,
        labels,
        assigned,
        image,
        width,
        height,
        overlapPolicy,
        execution
      );
    instances.push({ id: feature2.id, label: label2, sourceLabel: feature2.sourceLabel });
    if ((index4 + 1) % 32 === 0)
      await execution.checkpoint(
        "rasterizing-reference-annotations",
        index4 + 1,
        parsed.length
      );
  }
  const warnings2 = [
    "Reference labels come from the supplied annotation source, not independently verified biological truth.",
    "Polygons are rasterized with the documented even-odd half-open pixel-center rule; this is not a claim of byte-identical QuPath or challenge rasterization.",
    "Reference polygons are clipped to the requested image footprint; ROI-edge fragments are retained.",
    reference.coverage === "exhaustive" ? "Exhaustive coverage is an explicit caller/dataset declaration, not inferred from the presence of polygons." : "Unannotated pixels are ignored, not interpreted as verified background."
  ];
  if (overlapPolicy === "last-feature-wins")
    warnings2.push(
      "Overlapping source annotations resolve by last feature in the source file, as explicitly requested."
    );
  await execution.checkpoint(
    "reference-annotations-complete",
    parsed.length,
    parsed.length
  );
  const provenance2 = {
    method: "geojson-pixel-center-even-odd-half-open",
    overlapPolicy,
    annotationCount: parsed.length,
    maskSha256: pathologySha256(
      labels instanceof Uint32Array ? pathologyLabelBytes(labels) : labels
    ),
    warnings: warnings2
  };
  if (kind === "semantic" && labels instanceof Uint8Array)
    return {
      kind: "semantic",
      width,
      height,
      labels,
      image,
      reference,
      provenance: { ...provenance2, classMapping: classMapping2 }
    };
  if (!(labels instanceof Uint32Array))
    throw invalid2("Invalid instance-mask storage.");
  const observed = new Set(labels);
  return {
    kind: "instances",
    width,
    height,
    labels,
    image,
    reference,
    instances: instances.filter((instance3) => observed.has(instance3.label)),
    provenance: provenance2
  };
}
function copyAnnotationReference(reference) {
  requirePathologyIdentity(reference.sourceId, "Annotation source ID");
  requirePathologyIdentity(
    reference.sourceRevision,
    "Annotation source revision"
  );
  if (!/^sha256:[a-f0-9]{64}$/u.test(reference.contentSha256) || reference.coordinateSpace !== "source-pixels" && reference.coordinateSpace !== "roi-pixels" || reference.coverage !== "annotated-only" && reference.coverage !== "exhaustive")
    throw invalid2(
      "Annotation references require a content digest, declared alignment, and explicit coverage policy."
    );
  if (reference.unannotatedClass != null && (reference.coverage !== "exhaustive" || !Number.isInteger(reference.unannotatedClass) || reference.unannotatedClass < 1 || reference.unannotatedClass > 255))
    throw invalid2(
      "Unannotated space can become a semantic background class only with explicit exhaustive coverage and a positive class ID."
    );
  if (reference.coverageBasis != null)
    requirePathologyIdentity(
      reference.coverageBasis,
      "Annotation coverage basis"
    );
  return {
    sourceId: reference.sourceId,
    sourceRevision: reference.sourceRevision,
    contentSha256: reference.contentSha256,
    coordinateSpace: reference.coordinateSpace,
    coverage: reference.coverage,
    ...reference.unannotatedClass == null ? {} : { unannotatedClass: reference.unannotatedClass },
    ...reference.coverageBasis == null ? {} : { coverageBasis: reference.coverageBasis }
  };
}
function copyClassMapping(input) {
  if (input.length > 256)
    throw exhausted(
      "Reference class mappings are limited to 256 source labels."
    );
  const seen = /* @__PURE__ */ new Set();
  return input.map((entry) => {
    requirePathologyIdentity(entry.sourceLabel, "Source class label");
    if (seen.has(entry.sourceLabel) || !Number.isInteger(entry.classId) || entry.classId < 0 || entry.classId > 255)
      throw invalid2(
        "Reference mappings require unique source labels and uint8 class IDs (zero means ignore)."
      );
    seen.add(entry.sourceLabel);
    return { sourceLabel: entry.sourceLabel, classId: entry.classId };
  });
}
async function paintPolygon(polygon2, label2, labels, assigned, image, width, height, overlapPolicy, execution) {
  let minimumY = Infinity;
  let maximumY = -Infinity;
  let vertices = 0;
  for (const ring2 of polygon2)
    for (const point4 of ring2) {
      minimumY = Math.min(minimumY, point4[1]);
      maximumY = Math.max(maximumY, point4[1]);
      vertices += 1;
    }
  const stepX = image.region.width / width;
  const stepY = image.region.height / height;
  if (![stepX, stepY].every((value) => Number.isFinite(value) && value > 0))
    throw invalid2(
      "Reference raster sampling exceeds finite source-pixel resolution."
    );
  const start = Math.max(
    0,
    Math.ceil((minimumY - image.region.y) / stepY - 0.5)
  );
  const end = Math.min(
    height,
    Math.ceil((maximumY - image.region.y) / stepY - 0.5)
  );
  if (start >= end) return;
  execution.consume((end - start) * vertices);
  for (let y = start; y < end; y += 1) {
    const ordinate = image.region.y + (y + 0.5) * stepY;
    const crossings = [];
    for (const ring2 of polygon2)
      for (let index4 = 1; index4 < ring2.length; index4 += 1) {
        const left = ring2[index4 - 1];
        const right = ring2[index4];
        if (left[1] <= ordinate && ordinate < right[1] || right[1] <= ordinate && ordinate < left[1]) {
          const crossing = left[0] + (ordinate - left[1]) * (right[0] - left[0]) / (right[1] - left[1]);
          if (!Number.isFinite(crossing))
            throw invalid2(
              "Reference edge interpolation exceeds finite source-pixel range."
            );
          crossings.push(crossing);
        }
      }
    crossings.sort((left, right) => left - right);
    if (crossings.length % 2 !== 0)
      throw invalid2(
        "Reference polygon has an inconsistent scanline intersection count."
      );
    for (let pair = 0; pair < crossings.length; pair += 2) {
      const left = Math.max(
        0,
        Math.ceil((crossings[pair] - image.region.x) / stepX - 0.5)
      );
      const right = Math.min(
        width,
        Math.ceil((crossings[pair + 1] - image.region.x) / stepX - 0.5)
      );
      if (left >= right) continue;
      execution.consume(right - left);
      for (let x = left; x < right; x += 1) {
        const pixel = y * width + x;
        if (assigned[pixel] !== 0 && labels[pixel] !== label2 && overlapPolicy === "error")
          throw invalid2(
            "Reference polygons overlap with different labels; supply a documented overlap policy rather than silently overwriting them."
          );
        labels[pixel] = label2;
        assigned[pixel] = 1;
      }
    }
    if ((y - start + 1) % 64 === 0)
      await execution.checkpoint(
        "rasterizing-reference-rows",
        y - start + 1,
        end - start
      );
  }
}
function readSourceLabel(properties) {
  if (!isRecord3(properties)) return null;
  const classification = properties.classification;
  const value = typeof classification === "string" ? classification : isRecord3(classification) && typeof classification.name === "string" ? classification.name : null;
  if (value != null)
    requirePathologyIdentity(value, "Source classification label");
  return value;
}
function isRecord3(value) {
  return value != null && typeof value === "object" && !Array.isArray(value);
}
function invalid2(message) {
  return new PathologyAnalysisError("INVALID_ARGUMENT", message);
}
function exhausted(message) {
  return new PathologyAnalysisError("RESOURCE_EXHAUSTED", message);
}
export { copyAnnotationReference, rasterizePathologyAnnotations };
