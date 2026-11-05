// See LICENSE and THIRD_PARTY_NOTICES.md.
import { MAX_ANNOTATION_COORDINATES, annotationBounds, annotationContainsPoint, annotationCoordinates, annotationGeometrySchema, init_annotation_geometry } from "./../vendor/runtime.mjs";
import { measureAnnotationGeometry } from "./../slide/region-measurements.mjs";
import { PathologyAnalysisError, PathologyExecution, pathologyFeatureTableSha256, pathologyJsonSha256, pathologySha256, requirePathologyIdentity } from "./runtime.mjs";
import { PATHOLOGY_FEATURE_UNITS } from "./types.mjs";
init_annotation_geometry();
import { isUint8Array as isUint8Array3, isUint32Array } from "node:util/types";
async function runPathologyRoiAnalysis(input) {
  const execution = new PathologyExecution(input);
  validateRasterSource(input.source, input.raster, execution);
  const source2 = {
    sourceId: input.source.sourceId,
    sourceRevision: input.source.sourceRevision,
    region: {
      x: input.source.region.x,
      y: input.source.region.y,
      width: input.source.region.width,
      height: input.source.region.height
    },
    ...input.source.calibration == null ? {} : { calibration: { ...input.source.calibration } }
  };
  const raster = { ...input.raster, rgb: new Uint8Array(input.raster.rgb) };
  const rasterSha256 = pathologySha256(raster.rgb);
  const warnings2 = [
    "Research-only analysis of the supplied RGB8 ROI; no diagnosis, cell identity, scanner-intensity calibration, or QuPath-equivalence claim.",
    "RGB8 color statistics are observed code values, not optical density or stain-normalized concentrations."
  ];
  if (source2.calibration?.verified !== true)
    warnings2.push(
      "Physical calibration is unverified or absent; micrometer measurements are null, not inferred."
    );
  let labels;
  let definitions;
  let boundaries;
  let thresholdUsed = null;
  let confidence = null;
  let method;
  let objectInputSha256;
  let parameters;
  if (input.operation.kind === "foreground-components") {
    const operation = normalizeForegroundOperation(input.operation);
    const luma = new Uint8Array(raster.width * raster.height);
    const histogram = new Uint32Array(256);
    for (let index4 = 0; index4 < luma.length; index4 += 1) {
      luma[index4] = rgbLuma(
        raster.rgb[index4 * 3],
        raster.rgb[index4 * 3 + 1],
        raster.rgb[index4 * 3 + 2]
      );
      histogram[luma[index4]] += 1;
      if ((index4 + 1) % 65536 === 0) {
        execution.consume(65536);
        await execution.checkpoint(
          "foreground-histogram",
          index4 + 1,
          luma.length
        );
      }
    }
    execution.consume(luma.length % 65536);
    const otsu = otsuThreshold(histogram);
    thresholdUsed = operation.threshold === "otsu" ? otsu.threshold : operation.threshold;
    if (operation.threshold === "otsu")
      confidence = {
        kind: "histogram-separation-not-tissue-probability",
        score: otsu.separation
      };
    if (thresholdUsed == null)
      warnings2.push(
        "The ROI has no separable intensity classes; automatic thresholding returns no foreground."
      );
    const foreground2 = new Uint8Array(luma.length);
    for (let index4 = 0; index4 < luma.length; index4 += 1) {
      const red = raster.rgb[index4 * 3];
      const green = raster.rgb[index4 * 3 + 1];
      const blue = raster.rgb[index4 * 3 + 2];
      const maximum = Math.max(red, green, blue);
      const saturation = maximum === 0 ? 0 : (maximum - Math.min(red, green, blue)) / maximum;
      foreground2[index4] = thresholdUsed != null && luma[index4] <= thresholdUsed && saturation >= operation.minimumSaturation ? 1 : 0;
      if ((index4 + 1) % 65536 === 0) {
        execution.consume(65536);
        await execution.checkpoint(
          "thresholding-foreground",
          index4 + 1,
          luma.length
        );
      }
    }
    execution.consume(luma.length % 65536);
    objectInputSha256 = pathologySha256(foreground2);
    parameters = {
      thresholdMode: operation.threshold === "otsu" ? "otsu" : "manual",
      thresholdUsed,
      minimumSaturation: operation.minimumSaturation,
      minAreaPixels: operation.minAreaPixels,
      connectivity: operation.connectivity,
      foregroundRule: "rounded-luma<=threshold AND saturation>=minimum",
      lumaFormula: "round(0.299R+0.587G+0.114B)"
    };
    const analysisIdentity = pathologyJsonSha256({
      source: source2,
      rasterSha256,
      objectInputSha256,
      parameters
    });
    ({ labels, definitions } = await labelComponents(
      foreground2,
      raster.width,
      raster.height,
      operation.minAreaPixels,
      operation.connectivity,
      analysisIdentity,
      execution
    ));
    method = "rgb8-threshold-connected-components";
    warnings2.push(
      "Dark/saturated connected components are foreground candidates, not validated tissue classes, nuclei, or cells; stains, pen marks, folds, and debris can satisfy the rule."
    );
  } else {
    if (input.operation.objects.format === "label-mask") {
      if (!isUint32Array(input.operation.objects.labels) || input.operation.objects.labels.length !== raster.width * raster.height) {
        throw invalid3(
          "Supplied label masks must be aligned uint32 rasters with the exact ROI dimensions."
        );
      }
      labels = input.operation.objects.labels.slice();
      definitions = copyDefinitions(
        input.operation.objects.definitions,
        execution
      );
      objectInputSha256 = pathologyJsonSha256({
        labelsSha256: pathologySha256(
          new Uint8Array(labels.buffer, labels.byteOffset, labels.byteLength)
        ),
        definitions,
        labelByteOrder: new Uint8Array(new Uint32Array([1]).buffer)[0] === 1 ? "little-endian" : "big-endian"
      });
      method = "supplied-label-mask-features";
      parameters = {
        backgroundLabel: 0,
        suppliedObjectCount: definitions.length,
        perimeterMethod: "exposed-raster-pixel-edges"
      };
    } else {
      boundaries = await copyBoundaries(
        input.operation.objects.boundaries,
        source2,
        execution
      );
      definitions = boundaries.map((boundary2, index4) => ({
        id: boundary2.id,
        label: index4 + 1,
        ...boundary2.declaredEntityKind == null ? {} : { declaredEntityKind: boundary2.declaredEntityKind }
      }));
      labels = await rasterizeBoundaries(boundaries, source2, raster, execution);
      objectInputSha256 = pathologyJsonSha256(boundaries);
      method = "supplied-boundary-features";
      parameters = {
        suppliedObjectCount: boundaries.length,
        pixelInclusion: "source-pixel-center-covered-by-boundary",
        overlappingPixelPolicy: "reject",
        boundaryPolicy: "must-be-contained-in-roi",
        perimeterMethod: "vector-boundary-including-holes"
      };
    }
    warnings2.push(
      "Supplied object IDs and declared entity kinds are source annotations, not independently verified biological identities."
    );
  }
  const rows2 = await extractObjectFeatures(
    labels,
    definitions,
    boundaries,
    source2,
    raster,
    method === "rgb8-threshold-connected-components" ? "foreground-component" : "supplied-object",
    execution
  );
  if (rows2.some(
    (row) => Object.values(row.values).some(
      (value) => value !== null && !Number.isFinite(value)
    )
  ))
    throw invalid3("Pathology measurements exceed finite numeric range.");
  if (rows2.length < definitions.length)
    warnings2.push(
      `${definitions.length - rows2.length} supplied label definitions have no observed pixels in this ROI and were omitted.`
    );
  if (rows2.some((row) => row.touchesRoiBoundary))
    warnings2.push(
      "Some objects touch the ROI edge; shape and color measurements may be truncated."
    );
  if (rows2.some((row) => row.values.pixel_count === 0))
    warnings2.push(
      "Some supplied vector boundaries contain no sampled raster pixel centers; geometric measurements are retained but RGB8 statistics are missing."
    );
  const features = Object.keys(PATHOLOGY_FEATURE_UNITS).map((name) => ({ name, unit: PATHOLOGY_FEATURE_UNITS[name] }));
  const provenance2 = {
    schemaVersion: 1,
    method,
    methodVersion: "1",
    source: source2,
    raster: {
      width: raster.width,
      height: raster.height,
      encoding: "RGB8",
      sha256: rasterSha256,
      sourcePixelsPerRasterPixelX: source2.region.width / raster.width,
      sourcePixelsPerRasterPixelY: source2.region.height / raster.height
    },
    objectInputSha256,
    parameters,
    geometryMeasurement: boundaries == null ? "raster-pixel-cells" : "vector-boundary",
    researchOnly: true,
    warnings: warnings2
  };
  const featureTableSha256 = pathologyFeatureTableSha256({
    features,
    rows: rows2,
    provenance: provenance2
  });
  const foreground = Uint8Array.from(labels, (label2) => label2 === 0 ? 0 : 1);
  await execution.checkpoint(
    "complete",
    raster.width * raster.height,
    raster.width * raster.height
  );
  return {
    researchOnly: true,
    mask: { width: raster.width, height: raster.height, foreground, labels },
    featureTable: {
      features,
      rows: rows2,
      provenance: { ...provenance2, featureTableSha256 }
    },
    thresholdUsed,
    confidence,
    warnings: warnings2
  };
}
function otsuThreshold(histogram) {
  if (histogram.length !== 256)
    throw invalid3("Otsu thresholding requires exactly 256 intensity bins.");
  let count6 = 0;
  let total = 0;
  let sumSquares = 0;
  for (let value = 0; value < 256; value += 1) {
    if (!Number.isSafeInteger(histogram[value]) || histogram[value] < 0)
      throw invalid3("Histogram bins must be nonnegative integer counts.");
    count6 += histogram[value];
    total += value * histogram[value];
    sumSquares += value * value * histogram[value];
  }
  if (!Number.isSafeInteger(count6))
    throw invalid3("Histogram total exceeds the safe count range.");
  if (count6 === 0) return { threshold: null, separation: 0 };
  const variance = sumSquares / count6 - (total / count6) ** 2;
  if (!(variance > 0)) return { threshold: null, separation: 0 };
  let lowerCount = 0;
  let lowerTotal = 0;
  let best = -1;
  let threshold = null;
  for (let value = 0; value < 255; value += 1) {
    lowerCount += histogram[value];
    lowerTotal += value * histogram[value];
    if (lowerCount === 0 || lowerCount === count6) continue;
    const difference = lowerTotal / lowerCount - (total - lowerTotal) / (count6 - lowerCount);
    const between = lowerCount / count6 * ((count6 - lowerCount) / count6) * difference * difference;
    if (between > best) {
      best = between;
      threshold = value;
    }
  }
  return { threshold, separation: Math.max(0, Math.min(1, best / variance)) };
}
function validateRasterSource(source2, raster, execution) {
  requirePathologyIdentity(source2.sourceId, "Source ID");
  requirePathologyIdentity(source2.sourceRevision, "Source revision");
  const { x, y, width, height } = source2.region;
  if (![x, y, width, height, x + width, y + height].every(Number.isFinite) || x < 0 || y < 0 || width <= 0 || height <= 0)
    throw invalid3(
      "Pathology source regions require finite nonnegative origins and positive dimensions."
    );
  if (!Number.isSafeInteger(raster.width) || !Number.isSafeInteger(raster.height) || raster.width < 1 || raster.height < 1)
    throw invalid3("Pathology raster dimensions must be positive integers.");
  const pixels2 = raster.width * raster.height;
  if (!Number.isSafeInteger(pixels2) || pixels2 > execution.limits.maxPixels)
    throw new PathologyAnalysisError(
      "RESOURCE_EXHAUSTED",
      "The pathology ROI exceeds the raster pixel limit."
    );
  if (!isUint8Array3(raster.rgb) || raster.rgb.length !== pixels2 * 3)
    throw invalid3(
      "Pathology input must contain exactly width*height*3 interleaved RGB8 bytes."
    );
  if (source2.calibration != null && (![
    source2.calibration.micronsPerPixelX,
    source2.calibration.micronsPerPixelY
  ].every((value) => Number.isFinite(value) && value > 0) || typeof source2.calibration.verified !== "boolean"))
    throw invalid3(
      "Provided pixel calibration must have finite positive X/Y sizes and explicit verification status."
    );
}
function normalizeForegroundOperation(operation) {
  const threshold = operation.threshold;
  const minimumSaturation = operation.minimumSaturation ?? 0;
  const minAreaPixels = operation.minAreaPixels ?? 1;
  const connectivity = operation.connectivity ?? 4;
  if (threshold !== "otsu" && (!Number.isInteger(threshold) || threshold < 0 || threshold > 255))
    throw invalid3("Manual RGB8 thresholds must be integers between 0 and 255.");
  if (!Number.isFinite(minimumSaturation) || minimumSaturation < 0 || minimumSaturation > 1 || !Number.isSafeInteger(minAreaPixels) || minAreaPixels < 1 || connectivity !== 4 && connectivity !== 8)
    throw invalid3(
      "Foreground saturation, minimum area, and connectivity parameters are invalid."
    );
  return { threshold, minimumSaturation, minAreaPixels, connectivity };
}
async function labelComponents(foreground, width, height, minimumArea, connectivity, identity15, execution) {
  const labels = new Uint32Array(foreground.length);
  const queue2 = new Uint32Array(foreground.length);
  const definitions = [];
  let componentOrdinal = 0;
  for (let origin = 0; origin < foreground.length; origin += 1) {
    if (foreground[origin] === 0 || labels[origin] !== 0) continue;
    componentOrdinal += 1;
    let head = 0;
    let tail = 1;
    queue2[0] = origin;
    labels[origin] = componentOrdinal;
    while (head < tail) {
      const index4 = queue2[head++];
      const x = index4 % width;
      const y = Math.floor(index4 / width);
      for (let dy = -1; dy <= 1; dy += 1) {
        for (let dx = -1; dx <= 1; dx += 1) {
          if (dx === 0 && dy === 0 || connectivity === 4 && dx !== 0 && dy !== 0)
            continue;
          const nextX = x + dx;
          const nextY = y + dy;
          if (nextX < 0 || nextX >= width || nextY < 0 || nextY >= height)
            continue;
          const next3 = nextY * width + nextX;
          if (foreground[next3] !== 0 && labels[next3] === 0) {
            labels[next3] = componentOrdinal;
            queue2[tail++] = next3;
          }
        }
      }
      execution.consume(connectivity);
      if (head % 65536 === 0)
        await execution.checkpoint(
          "connected-components",
          origin,
          foreground.length
        );
    }
    if (tail < minimumArea) {
      for (let index4 = 0; index4 < tail; index4 += 1) {
        labels[queue2[index4]] = 0;
        foreground[queue2[index4]] = 0;
      }
    } else {
      if (definitions.length >= execution.limits.maxObjects)
        throw new PathologyAnalysisError(
          "RESOURCE_EXHAUSTED",
          "Foreground object count exceeds the bounded ROI limit."
        );
      const acceptedLabel = definitions.length + 1;
      for (let index4 = 0; index4 < tail; index4 += 1)
        labels[queue2[index4]] = acceptedLabel;
      definitions.push({
        label: acceptedLabel,
        id: `${identity15}:component:${componentOrdinal}`
      });
    }
    if (componentOrdinal % 128 === 0)
      await execution.checkpoint(
        "connected-components",
        origin,
        foreground.length
      );
  }
  execution.consume(foreground.length);
  return { labels, definitions };
}
function copyDefinitions(definitions, execution) {
  if (definitions.length > execution.limits.maxObjects)
    throw new PathologyAnalysisError(
      "RESOURCE_EXHAUSTED",
      "Supplied object definitions exceed the ROI object limit."
    );
  const ids = /* @__PURE__ */ new Set();
  const labels = /* @__PURE__ */ new Set();
  return definitions.map((definition) => {
    requirePathologyIdentity(definition.id, "Object ID");
    if (!Number.isSafeInteger(definition.label) || definition.label <= 0 || definition.label > 4294967295 || labels.has(definition.label) || ids.has(definition.id))
      throw invalid3(
        "Supplied objects require unique positive uint32 labels and stable object IDs."
      );
    if (definition.declaredEntityKind != null)
      requirePathologyIdentity(
        definition.declaredEntityKind,
        "Declared source entity kind"
      );
    ids.add(definition.id);
    labels.add(definition.label);
    return {
      id: definition.id,
      label: definition.label,
      ...definition.declaredEntityKind == null ? {} : { declaredEntityKind: definition.declaredEntityKind }
    };
  });
}
async function copyBoundaries(boundaries, source2, execution) {
  if (boundaries.length > execution.limits.maxObjects)
    throw new PathologyAnalysisError(
      "RESOURCE_EXHAUSTED",
      "Supplied boundaries exceed the ROI object limit."
    );
  copyDefinitions(
    boundaries.map((boundary2, index4) => ({
      id: boundary2.id,
      label: index4 + 1,
      declaredEntityKind: boundary2.declaredEntityKind
    })),
    execution
  );
  let coordinates = 0;
  const copied = [];
  for (const boundary2 of boundaries) {
    const count6 = countBoundaryCoordinates(boundary2, execution);
    coordinates += count6;
    if (coordinates > execution.limits.maxBoundaryCoordinates)
      throw new PathologyAnalysisError(
        "RESOURCE_EXHAUSTED",
        "Supplied boundaries exceed the coordinate budget."
      );
    execution.consume(3 * count6 * count6);
    const geometry = annotationGeometrySchema.parse(boundary2.geometry);
    if (geometry.type !== "Polygon" && geometry.type !== "MultiPolygon")
      throw invalid3(
        "Supplied object boundaries must be polygons or multipolygons."
      );
    const bounds2 = annotationBounds(geometry);
    if (bounds2.x < source2.region.x || bounds2.y < source2.region.y || bounds2.x + bounds2.width > source2.region.x + source2.region.width || bounds2.y + bounds2.height > source2.region.y + source2.region.height)
      throw invalid3(
        "Supplied boundaries must be fully contained within the authorized ROI; enlarge the ROI rather than silently clipping objects."
      );
    copied.push({
      id: boundary2.id,
      geometry,
      ...boundary2.declaredEntityKind == null ? {} : { declaredEntityKind: boundary2.declaredEntityKind }
    });
  }
  await execution.checkpoint(
    "validating-boundaries",
    copied.length,
    copied.length
  );
  return copied;
}
function countBoundaryCoordinates(boundary2, execution) {
  const polygons = boundary2.geometry.type === "Polygon" ? [boundary2.geometry.coordinates] : boundary2.geometry.type === "MultiPolygon" ? boundary2.geometry.coordinates : [];
  if (!Array.isArray(polygons) || polygons.length < 1 || polygons.length > 1024)
    throw invalid3("Supplied boundaries require bounded polygon geometry.");
  let count6 = 0;
  for (const polygon2 of polygons) {
    if (!Array.isArray(polygon2) || polygon2.length < 1 || polygon2.length > 1024)
      throw invalid3("Supplied boundary polygon rings are invalid.");
    for (const ring2 of polygon2) {
      if (!Array.isArray(ring2))
        throw invalid3("Supplied boundary coordinates must be arrays.");
      count6 += ring2.length;
      if (count6 > MAX_ANNOTATION_COORDINATES || count6 > execution.limits.maxBoundaryCoordinates)
        throw new PathologyAnalysisError(
          "RESOURCE_EXHAUSTED",
          "Supplied boundaries exceed the coordinate budget."
        );
    }
  }
  return count6;
}
async function rasterizeBoundaries(boundaries, source2, raster, execution) {
  const labels = new Uint32Array(raster.width * raster.height);
  const stepX = source2.region.width / raster.width;
  const stepY = source2.region.height / raster.height;
  for (const [index4, boundary2] of boundaries.entries()) {
    const bounds2 = annotationBounds(boundary2.geometry);
    const startX = Math.max(
      0,
      Math.floor((bounds2.x - source2.region.x) / stepX)
    );
    const endX = Math.min(
      raster.width,
      Math.ceil((bounds2.x + bounds2.width - source2.region.x) / stepX)
    );
    const startY = Math.max(
      0,
      Math.floor((bounds2.y - source2.region.y) / stepY)
    );
    const endY = Math.min(
      raster.height,
      Math.ceil((bounds2.y + bounds2.height - source2.region.y) / stepY)
    );
    const vertices = annotationCoordinates(boundary2.geometry).length;
    execution.consume((endX - startX) * (endY - startY) * vertices);
    for (let y = startY; y < endY; y += 1) {
      for (let x = startX; x < endX; x += 1) {
        if (!annotationContainsPoint(boundary2.geometry, [
          source2.region.x + (x + 0.5) * stepX,
          source2.region.y + (y + 0.5) * stepY
        ]))
          continue;
        const pixel = y * raster.width + x;
        if (labels[pixel] !== 0)
          throw invalid3(
            "Supplied boundaries overlap at observed pixels; analyze overlapping object layers separately."
          );
        labels[pixel] = index4 + 1;
      }
      if ((y - startY + 1) % 32 === 0)
        await execution.checkpoint(
          "rasterizing-boundaries",
          index4,
          boundaries.length
        );
    }
    await execution.checkpoint(
      "rasterizing-boundaries",
      index4 + 1,
      boundaries.length
    );
  }
  return labels;
}
async function extractObjectFeatures(labels, definitions, boundaries, source2, raster, kind, execution) {
  const accumulators = new Map(
    definitions.map((definition) => [
      definition.label,
      {
        definition,
        count: 0,
        sumX: 0,
        sumY: 0,
        red: 0,
        green: 0,
        blue: 0,
        lumaMean: 0,
        lumaM2: 0,
        horizontalEdges: 0,
        verticalEdges: 0,
        minX: Infinity,
        minY: Infinity,
        maxX: -Infinity,
        maxY: -Infinity,
        touchesBoundary: false
      }
    ])
  );
  for (let y = 0; y < raster.height; y += 1) {
    for (let x = 0; x < raster.width; x += 1) {
      const pixel = y * raster.width + x;
      const label2 = labels[pixel];
      if (label2 === 0) continue;
      const accumulator = accumulators.get(label2);
      if (accumulator == null)
        throw invalid3(
          "The supplied mask contains a label without an explicit object definition."
        );
      accumulator.count += 1;
      accumulator.sumX += x + 0.5;
      accumulator.sumY += y + 0.5;
      const red = raster.rgb[pixel * 3];
      const green = raster.rgb[pixel * 3 + 1];
      const blue = raster.rgb[pixel * 3 + 2];
      accumulator.red += red;
      accumulator.green += green;
      accumulator.blue += blue;
      const luma = rgbLuma(red, green, blue);
      const delta = luma - accumulator.lumaMean;
      accumulator.lumaMean += delta / accumulator.count;
      accumulator.lumaM2 += delta * (luma - accumulator.lumaMean);
      accumulator.minX = Math.min(accumulator.minX, x);
      accumulator.maxX = Math.max(accumulator.maxX, x);
      accumulator.minY = Math.min(accumulator.minY, y);
      accumulator.maxY = Math.max(accumulator.maxY, y);
      if (x === 0 || labels[pixel - 1] !== label2)
        accumulator.verticalEdges += 1;
      if (x === raster.width - 1 || labels[pixel + 1] !== label2)
        accumulator.verticalEdges += 1;
      if (y === 0 || labels[pixel - raster.width] !== label2)
        accumulator.horizontalEdges += 1;
      if (y === raster.height - 1 || labels[pixel + raster.width] !== label2)
        accumulator.horizontalEdges += 1;
      if (x === 0 || y === 0 || x === raster.width - 1 || y === raster.height - 1)
        accumulator.touchesBoundary = true;
    }
    execution.consume(raster.width * 4);
    if ((y + 1) % 32 === 0)
      await execution.checkpoint("measuring-objects", y + 1, raster.height);
  }
  const stepX = source2.region.width / raster.width;
  const stepY = source2.region.height / raster.height;
  const calibrated = source2.calibration?.verified === true;
  const mppX = source2.calibration?.micronsPerPixelX ?? 1;
  const mppY = source2.calibration?.micronsPerPixelY ?? 1;
  const boundaryById = new Map(
    boundaries?.map((boundary2) => [boundary2.id, boundary2]) ?? []
  );
  const rows2 = [];
  for (const accumulator of accumulators.values()) {
    const boundary2 = boundaryById.get(accumulator.definition.id);
    if (accumulator.count === 0 && boundary2 == null) continue;
    const geometric = boundary2 == null ? null : measureAnnotationGeometry(boundary2.geometry);
    const physical = boundary2 == null || !calibrated ? null : measureAnnotationGeometry(boundary2.geometry, source2.calibration);
    const bounds2 = boundary2 == null ? {
      x: source2.region.x + accumulator.minX * stepX,
      y: source2.region.y + accumulator.minY * stepY,
      width: (accumulator.maxX - accumulator.minX + 1) * stepX,
      height: (accumulator.maxY - accumulator.minY + 1) * stepY
    } : annotationBounds(boundary2.geometry);
    const area = geometric?.area ?? accumulator.count * stepX * stepY;
    const perimeter = geometric?.perimeter ?? accumulator.horizontalEdges * stepX + accumulator.verticalEdges * stepY;
    rows2.push({
      objectId: accumulator.definition.id,
      sourceId: source2.sourceId,
      sourceRevision: source2.sourceRevision,
      kind,
      ...accumulator.definition.declaredEntityKind == null ? {} : { declaredEntityKind: accumulator.definition.declaredEntityKind },
      maskLabel: accumulator.definition.label,
      bounds: bounds2,
      touchesRoiBoundary: boundary2 == null ? accumulator.touchesBoundary : bounds2.x <= source2.region.x || bounds2.y <= source2.region.y || bounds2.x + bounds2.width >= source2.region.x + source2.region.width || bounds2.y + bounds2.height >= source2.region.y + source2.region.height,
      values: {
        pixel_count: accumulator.count,
        area_px2: area,
        perimeter_px: perimeter,
        area_um2: calibrated ? physical?.area ?? area * mppX * mppY : null,
        perimeter_um: calibrated ? physical?.perimeter ?? accumulator.horizontalEdges * stepX * mppX + accumulator.verticalEdges * stepY * mppY : null,
        centroid_x_px: geometric?.centroid.x ?? source2.region.x + accumulator.sumX / accumulator.count * stepX,
        centroid_y_px: geometric?.centroid.y ?? source2.region.y + accumulator.sumY / accumulator.count * stepY,
        mean_red: accumulator.count === 0 ? null : accumulator.red / accumulator.count,
        mean_green: accumulator.count === 0 ? null : accumulator.green / accumulator.count,
        mean_blue: accumulator.count === 0 ? null : accumulator.blue / accumulator.count,
        mean_luma: accumulator.count === 0 ? null : accumulator.lumaMean,
        std_luma: accumulator.count === 0 ? null : Math.sqrt(Math.max(0, accumulator.lumaM2 / accumulator.count)),
        extent: area / (bounds2.width * bounds2.height)
      }
    });
  }
  return rows2;
}
function rgbLuma(red, green, blue) {
  return Math.round(0.299 * red + 0.587 * green + 0.114 * blue);
}
function invalid3(message) {
  return new PathologyAnalysisError("INVALID_ARGUMENT", message);
}
export { runPathologyRoiAnalysis };
