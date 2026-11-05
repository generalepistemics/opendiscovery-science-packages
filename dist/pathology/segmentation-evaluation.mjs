// See LICENSE and THIRD_PARTY_NOTICES.md.
import { PathologyAnalysisError, PathologyExecution, pathologyLabelBytes, pathologySha256, requirePathologyIdentity } from "./runtime.mjs";
import { copyPathologySource, samePathologyImage, validatePathologyDimensions } from "./image-input.mjs";
import { copyAnnotationReference } from "./annotation-raster.mjs";
import { PixelMetricAccumulator } from "./pixel-metrics.mjs";
import { isUint8Array as isUint8Array5, isUint32Array as isUint32Array2 } from "node:util/types";
async function evaluatePathologyPixels(input) {
  const execution = new PathologyExecution(input);
  const prediction = input.prediction;
  const reference = input.reference;
  const source2 = copyPathologySource(prediction.provenance.source);
  const image = copyPathologySource(reference.image);
  const annotation = copyAnnotationReference(reference.reference);
  const pixels2 = validatePathologyDimensions(
    prediction.mask.width,
    prediction.mask.height,
    execution
  );
  if (prediction.kind !== "pixel-classification" || reference.kind !== "semantic" || reference.width !== prediction.mask.width || reference.height !== prediction.mask.height || !samePathologyImage(source2, image) || !isUint8Array5(prediction.mask.labels) || !isUint8Array5(reference.labels) || prediction.mask.labels.length !== pixels2 || reference.labels.length !== pixels2)
    throw invalid8(
      "Pixel prediction and source annotations must cover the identical source revision, footprint, and raster dimensions."
    );
  const predicted = new Uint8Array(prediction.mask.labels);
  const truth = new Uint8Array(reference.labels);
  const predictionMaskSha256 = pathologySha256(predicted);
  const referenceMaskSha256 = pathologySha256(truth);
  if (predictionMaskSha256 !== prediction.provenance.maskSha256 || referenceMaskSha256 !== reference.provenance.maskSha256)
    throw invalid8(
      "Pixel evaluation masks differ from their recorded content digests."
    );
  const classes = prediction.classes.map((entry) => ({
    id: entry.id,
    label: entry.label
  }));
  const classIds = new Set(classes.map((entry) => entry.id));
  if (classes.length < 2 || classes.length > 8 || classIds.size !== classes.length || classes.some(
    (entry) => !Number.isSafeInteger(entry.id) || entry.id < 1 || entry.id > 255
  ))
    throw invalid8(
      "Pixel evaluation requires two to eight unique explicit class IDs."
    );
  for (const entry of classes)
    requirePathologyIdentity(entry.label, "Pixel class label");
  requirePathologyIdentity(prediction.modelId, "Pixel classifier model ID");
  const modelId = prediction.modelId;
  const warnings2 = [
    ...reference.provenance.warnings,
    "Reference-pixel evaluation is not automatically heldout evaluation; independence from model training must be established separately.",
    "Only explicitly labeled reference pixels are scored. Unannotated pixels remain ignored unless the reference declares exhaustive coverage and an explicit background class.",
    "The stored maximum class score is insufficient to calculate multiclass log loss; mask-only log loss is not reported."
  ];
  const accumulator = new PixelMetricAccumulator(classes);
  execution.consume(pixels2);
  for (let index4 = 0; index4 < pixels2; index4 += 1) {
    if (!classIds.has(predicted[index4]))
      throw invalid8("A predicted pixel refers to an undeclared class.");
    accumulator.observeMask(truth[index4], predicted[index4]);
    if (index4 % 65536 === 0)
      await execution.checkpoint("evaluating-source-pixels", index4, pixels2);
  }
  await execution.checkpoint("pixel-evaluation-complete", pixels2, pixels2);
  return {
    kind: "pixel-evaluation",
    researchOnly: true,
    source: source2,
    reference: annotation,
    modelId,
    predictionMaskSha256,
    referenceMaskSha256,
    metrics: accumulator.result("reference-pixels"),
    warnings: warnings2
  };
}
async function evaluatePathologySegmentation(input) {
  const execution = new PathologyExecution(input);
  const prediction = input.prediction;
  const reference = input.reference;
  const source2 = copyPathologySource(prediction.provenance.source);
  const image = copyPathologySource(reference.image);
  const annotation = copyAnnotationReference(reference.reference);
  const threshold = input.iouThreshold ?? 0.5;
  if (!Number.isFinite(threshold) || threshold < 0.5 || threshold > 1)
    throw invalid8(
      "Instance evaluation requires an IoU threshold between 0.5 and one."
    );
  const exhaustive = annotation.coverage === "exhaustive";
  if (!exhaustive && annotation.coverageBasis == null)
    throw invalid8(
      "Annotated-only instance evaluation requires an explicit reference-coverage and conversion basis."
    );
  const pixels2 = validatePathologyDimensions(
    prediction.mask.width,
    prediction.mask.height,
    execution
  );
  if (prediction.kind !== "instance-segmentation" && prediction.kind !== "cell-watershed-segmentation" || reference.kind !== "instances" || reference.width !== prediction.mask.width || reference.height !== prediction.mask.height || !samePathologyImage(source2, image) || !isUint32Array2(prediction.mask.labels) || !isUint32Array2(reference.labels) || prediction.mask.labels.length !== pixels2 || reference.labels.length !== pixels2)
    throw invalid8(
      "Instance prediction and source annotations must cover the identical source revision, footprint, and raster dimensions."
    );
  const predicted = new Uint32Array(prediction.mask.labels);
  const truth = new Uint32Array(reference.labels);
  const predictionMaskSha256 = pathologySha256(pathologyLabelBytes(predicted));
  const referenceMaskSha256 = pathologySha256(pathologyLabelBytes(truth));
  if (predictionMaskSha256 !== prediction.provenance.maskSha256 || referenceMaskSha256 !== reference.provenance.maskSha256)
    throw invalid8(
      "Instance evaluation masks differ from their recorded content digests."
    );
  const predictions = copyInstances(prediction.instances, execution);
  const references = copyInstances(reference.instances, execution);
  const predictionIndices = new Map(
    predictions.map((entry, index4) => [entry.label, index4])
  );
  const referenceIndices = new Map(
    references.map((entry, index4) => [entry.label, index4])
  );
  const predictionAreas = predictions.map(() => 0);
  const referenceAreas = references.map(() => 0);
  const intersections = /* @__PURE__ */ new Map();
  let foregroundIntersection = 0;
  let referenceForeground = 0;
  let predictedForeground = 0;
  execution.consume(pixels2 * 4);
  for (let index4 = 0; index4 < pixels2; index4 += 1) {
    const predictedIndex = predicted[index4] === 0 ? void 0 : predictionIndices.get(predicted[index4]);
    const referenceIndex = truth[index4] === 0 ? void 0 : referenceIndices.get(truth[index4]);
    if (predicted[index4] !== 0 && predictedIndex == null || truth[index4] !== 0 && referenceIndex == null)
      throw invalid8(
        "Every nonzero evaluation mask label needs its source-scoped instance ID."
      );
    if (predictedIndex != null) {
      predictionAreas[predictedIndex] += 1;
      predictedForeground += 1;
    }
    if (referenceIndex != null) {
      referenceAreas[referenceIndex] += 1;
      referenceForeground += 1;
    }
    if (predictedIndex != null && referenceIndex != null) {
      foregroundIntersection += 1;
      const key2 = referenceIndex * predictions.length + predictedIndex;
      intersections.set(key2, (intersections.get(key2) ?? 0) + 1);
    }
    if (index4 % 65536 === 0)
      await execution.checkpoint("counting-instance-overlap", index4, pixels2);
  }
  if (predictionAreas.some((area) => area === 0) || referenceAreas.some((area) => area === 0))
    throw invalid8(
      "Evaluation instance IDs must identify observed mask pixels, not unlocated or outside-ROI objects."
    );
  const edges = references.map(() => []);
  for (const [key2, intersection2] of intersections) {
    execution.consume(1);
    const referenceIndex = Math.floor(key2 / predictions.length);
    const predictionIndex = key2 % predictions.length;
    const iou = intersection2 / (referenceAreas[referenceIndex] + predictionAreas[predictionIndex] - intersection2);
    if (iou >= threshold) edges[referenceIndex].push({ predictionIndex, iou });
  }
  for (const candidates of edges)
    candidates.sort(
      (left, right) => right.iou - left.iou || left.predictionIndex - right.predictionIndex
    );
  const matchForPrediction = new Int32Array(predictions.length).fill(-1);
  const matchForReference = new Int32Array(references.length).fill(-1);
  for (let root = 0; root < references.length; root += 1) {
    const predecessor = new Int32Array(predictions.length).fill(-1);
    const visitedReferences = new Uint8Array(references.length);
    const queue2 = [root];
    visitedReferences[root] = 1;
    let found = -1;
    for (let cursor2 = 0; cursor2 < queue2.length && found < 0; cursor2 += 1) {
      const referenceIndex = queue2[cursor2];
      for (const candidate of edges[referenceIndex]) {
        execution.consume(1);
        const next3 = candidate.predictionIndex;
        if (predecessor[next3] !== -1) continue;
        predecessor[next3] = referenceIndex;
        if (matchForPrediction[next3] === -1) {
          found = next3;
          break;
        }
        const matchedReference = matchForPrediction[next3];
        if (visitedReferences[matchedReference] === 0) {
          visitedReferences[matchedReference] = 1;
          queue2.push(matchedReference);
        }
      }
    }
    while (found !== -1) {
      const referenceIndex = predecessor[found];
      const previous = matchForReference[referenceIndex];
      matchForPrediction[found] = referenceIndex;
      matchForReference[referenceIndex] = found;
      found = previous;
    }
    if (root % 128 === 0)
      await execution.checkpoint(
        "matching-reference-instances",
        root,
        references.length
      );
  }
  const matches2 = [];
  for (let index4 = 0; index4 < references.length; index4 += 1) {
    const matched = matchForReference[index4];
    if (matched < 0) continue;
    const edge = edges[index4].find(
      (entry) => entry.predictionIndex === matched
    );
    if (edge == null)
      throw invalid8("Invalid internal instance-matching state.");
    matches2.push({
      referenceId: references[index4].id,
      predictionId: predictions[matched].id,
      iou: edge.iou
    });
  }
  const truePositive = matches2.length;
  const falsePositive = predictions.length - truePositive;
  const falseNegative = references.length - truePositive;
  const matchedIoU = matches2.reduce((sum2, entry) => sum2 + entry.iou, 0);
  const qualityDenominator = truePositive + 0.5 * falsePositive + 0.5 * falseNegative;
  const warnings2 = [
    ...reference.provenance.warnings,
    "Accuracy is measured only against this explicitly supplied annotation source and declared coverage, not independent clinical truth or broad model validation.",
    "All observed ROI-edge fragments are scored; this is not a full-slide, challenge-hidden-test, or whole-cell benchmark.",
    "At IoU thresholds at least 0.5, distinct instance masks have unique above-threshold matches except equal-0.5 ties; those ties use deterministic maximum-cardinality matching.",
    ...!exhaustive ? [
      "Reference coverage is annotated-only. Unmatched predictions are not called false positives; precision, F1, PQ, foreground Dice and foreground IoU are withheld. Total predicted instances remain an image-derived count, not an error count."
    ] : []
  ];
  await execution.checkpoint(
    "instance-evaluation-complete",
    references.length,
    references.length
  );
  return {
    kind: "instance-evaluation",
    researchOnly: true,
    source: source2,
    reference: annotation,
    predictionMaskSha256,
    referenceMaskSha256,
    protocol: {
      iouThreshold: threshold,
      matching: "maximum-cardinality-at-iou-threshold",
      roiEdgeFragments: "included",
      coverage: exhaustive ? "declared-exhaustive" : "annotated-only"
    },
    metrics: {
      referenceInstances: references.length,
      predictedInstances: predictions.length,
      truePositive,
      falsePositive: exhaustive ? falsePositive : null,
      falseNegative,
      precision: !exhaustive || predictions.length === 0 ? null : truePositive / predictions.length,
      recall: references.length === 0 ? null : truePositive / references.length,
      f1: !exhaustive || qualityDenominator === 0 ? null : truePositive / qualityDenominator,
      meanMatchedIoU: truePositive === 0 ? null : matchedIoU / truePositive,
      panopticQuality: !exhaustive || qualityDenominator === 0 ? null : matchedIoU / qualityDenominator,
      foregroundDice: !exhaustive ? null : referenceForeground + predictedForeground === 0 ? 1 : 2 * foregroundIntersection / (referenceForeground + predictedForeground),
      foregroundIoU: !exhaustive ? null : referenceForeground + predictedForeground - foregroundIntersection === 0 ? 1 : foregroundIntersection / (referenceForeground + predictedForeground - foregroundIntersection),
      annotatedForegroundRecall: referenceForeground === 0 ? null : foregroundIntersection / referenceForeground
    },
    matches: matches2,
    warnings: warnings2
  };
}
function copyInstances(instances, execution) {
  if (instances.length > execution.limits.maxObjects)
    throw new PathologyAnalysisError(
      "RESOURCE_EXHAUSTED",
      "Instance evaluation exceeds the bounded object count."
    );
  const ids = /* @__PURE__ */ new Set();
  const labels = /* @__PURE__ */ new Set();
  return instances.map((entry) => {
    requirePathologyIdentity(entry.id, "Evaluation instance ID");
    if (ids.has(entry.id) || labels.has(entry.label) || !Number.isSafeInteger(entry.label) || entry.label < 1 || entry.label > 4294967295)
      throw invalid8(
        "Evaluation instance IDs and positive mask labels must be unique."
      );
    ids.add(entry.id);
    labels.add(entry.label);
    return { id: entry.id, label: entry.label };
  });
}
function invalid8(message) {
  return new PathologyAnalysisError("INVALID_ARGUMENT", message);
}
export { evaluatePathologyPixels, evaluatePathologySegmentation };
