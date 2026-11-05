// See LICENSE and THIRD_PARTY_NOTICES.md.
import { PathologyAnalysisError, PathologyExecution, pathologyJsonSha256, pathologySha256, requirePathologyIdentity } from "./runtime.mjs";
import { copyPathologyImage, copyPathologySource, samePathologyImage, validatePathologyDimensions } from "./image-input.mjs";
import { copyAnnotationReference } from "./annotation-raster.mjs";
import { fitBinaryLogistic, score, standardize } from "./binary-logistic.mjs";
import { createPixelFeatureSampler } from "./pixel-features.mjs";
import { PixelMetricAccumulator } from "./pixel-metrics.mjs";
import { PATHOLOGY_PIXEL_FEATURE_UNITS } from "./pixel-types.mjs";
import { isUint8Array as isUint8Array4 } from "node:util/types";
async function trainPathologyPixelClassifier(input) {
  const execution = new PathologyExecution(input);
  const classes = copyPixelClasses(input.classes);
  const names2 = copyPixelFeatures(input.features, execution);
  const localRadius = input.localRadius ?? 2;
  const regularization = input.regularization ?? 0.1;
  const classBalance = input.classBalance ?? "balanced";
  const maxIterations = input.maxIterations ?? 25;
  const maxTrainingPixels = input.maxTrainingPixels ?? Math.min(4096, execution.limits.maxTrainingRows);
  const seed2 = input.seed ?? 1831565813;
  if (!Number.isInteger(localRadius) || localRadius < 0 || localRadius > 16 || !Number.isFinite(regularization) || regularization < 1e-6 || regularization > 1e3 || classBalance !== "balanced" && classBalance !== "none" || !Number.isSafeInteger(maxIterations) || maxIterations < 1 || maxIterations > 100 || !Number.isSafeInteger(maxTrainingPixels) || maxTrainingPixels < classes.length * 2 || maxTrainingPixels > execution.limits.maxTrainingRows || !Number.isInteger(seed2) || seed2 < 0 || seed2 > 4294967295)
    throw invalid7(
      "Pixel-classifier hyperparameters exceed the documented bounds."
    );
  const samples = copyTrainingSamples(input.samples, execution);
  const sampleProvenance = samples.map(describeSample);
  rejectKnownSplitLeakage(sampleProvenance);
  if (!samples.some((sample) => sample.partition === "train"))
    throw invalid7(
      "At least one explicitly designated training image is required."
    );
  const indices3 = new Map(classes.map((entry, index4) => [entry.id, index4]));
  const populationCounts = classes.map(() => 0);
  const reservoirs = classes.map(() => []);
  const perClassLimit = Math.floor(maxTrainingPixels / classes.length);
  const random = seededRandom2(seed2);
  for (const sample of samples) {
    if (sample.partition !== "train") continue;
    const sampler = await createPixelFeatureSampler(
      sample.raster,
      names2,
      localRadius,
      execution
    );
    execution.consume(sample.annotations.labels.length * (names2.length + 1));
    for (let pixel = 0; pixel < sample.annotations.labels.length; pixel += 1) {
      const label2 = sample.annotations.labels[pixel];
      if (label2 !== 0) {
        const classIndex = indices3.get(label2);
        if (classIndex == null)
          throw invalid7(
            "An annotated training pixel uses an undeclared class ID."
          );
        populationCounts[classIndex] += 1;
        const reservoir = reservoirs[classIndex];
        const replacement = reservoir.length < perClassLimit ? reservoir.length : Math.floor(random() * populationCounts[classIndex]);
        if (replacement < perClassLimit)
          reservoir[replacement] = {
            sampleId: sample.id,
            pixel,
            classIndex,
            values: sampler.vector(pixel)
          };
      }
      if ((pixel + 1) % 65536 === 0)
        await execution.checkpoint(
          "sampling-labeled-pixels",
          pixel + 1,
          sample.annotations.labels.length
        );
    }
  }
  const selectedCounts = reservoirs.map((rows2) => rows2.length);
  if (selectedCounts.some((count6) => count6 < 2))
    throw invalid7(
      "Every class requires at least two explicitly annotated training pixels; heldout labels never contribute to fitting."
    );
  const selected = reservoirs.flat();
  const means = names2.map(() => 0);
  const moments = names2.map(() => 0);
  for (const [index4, row] of selected.entries())
    for (let column3 = 0; column3 < names2.length; column3 += 1) {
      const delta = row.values[column3] - means[column3];
      means[column3] += delta / (index4 + 1);
      moments[column3] += delta * (row.values[column3] - means[column3]);
    }
  const deviations = moments.map(
    (moment) => Math.sqrt(Math.max(0, moment / selected.length))
  );
  if (deviations.every((value) => value === 0))
    throw invalid7("No selected pixel feature varies in the training images.");
  const scales = deviations.map((value) => value === 0 ? 1 : value);
  const standardized = selected.map((row) => ({
    ...row,
    values: standardize(row.values, means, scales),
    weight: classBalance === "balanced" ? selected.length / (classes.length * selectedCounts[row.classIndex]) : populationCounts[row.classIndex] / selectedCounts[row.classIndex]
  }));
  const heads = [];
  for (const [classIndex, entry] of classes.entries()) {
    const fitted = await fitBinaryLogistic(
      standardized.map((row) => ({
        values: row.values,
        weight: row.weight,
        target: row.classIndex === classIndex ? 1 : 0
      })),
      names2.length,
      regularization,
      maxIterations,
      execution,
      `fitting-pixel-class-${entry.id}`
    );
    heads.push({
      classId: entry.id,
      coefficients: fitted.parameters.slice(0, names2.length),
      intercept: fitted.parameters[names2.length],
      iterations: fitted.iterations,
      converged: fitted.converged,
      objective: fitted.objective
    });
  }
  const accumulator = new PixelMetricAccumulator(classes);
  for (const sample of samples) {
    if (sample.partition !== "heldout") continue;
    const sampler = await createPixelFeatureSampler(
      sample.raster,
      names2,
      localRadius,
      execution
    );
    for (let pixel = 0; pixel < sample.annotations.labels.length; pixel += 1) {
      const reference = sample.annotations.labels[pixel];
      if (reference === 0) accumulator.observeMask(0, 0);
      else {
        execution.consume(names2.length * (heads.length + 1));
        accumulator.observeScores(
          reference,
          pixelClassScores(
            standardize(sampler.vector(pixel), means, scales),
            heads
          )
        );
      }
      if ((pixel + 1) % 65536 === 0)
        await execution.checkpoint(
          "evaluating-heldout-pixels",
          pixel + 1,
          sample.annotations.labels.length
        );
    }
  }
  const metrics2 = accumulator.result("heldout-source-pixels");
  const warnings2 = [
    "Research-only learned pixel classes and areas; neither pixel classes nor connected regions establish cell/nucleus identity or a diagnosis.",
    "Optical-density features are negative-log RGB8 code-value proxies, not scanner-calibrated absorbance or stain concentrations.",
    "Scores are normalized one-vs-rest sigmoids, not calibrated class probabilities; class balancing changes the effective training prevalence.",
    "Known image IDs, revisions, identical raster bytes, and declared specimens are kept out of both partitions; unknown donor aliases and generalization are not independently verified.",
    "Local features use clipped raster-pixel neighborhoods; staining, scanner, pixel scale and spatial autocorrelation can affect performance."
  ];
  if (metrics2.evaluation === "not-evaluated")
    warnings2.push(
      "No labeled heldout pixels were supplied; no heldout accuracy estimate is available."
    );
  if (heads.some((head) => !head.converged))
    warnings2.push(
      "At least one one-vs-rest fit did not reach the gradient tolerance within its requested iteration budget."
    );
  if (deviations.some((value) => value === 0))
    warnings2.push(
      "Constant training features use scale one and cannot contribute fitted discrimination."
    );
  const body = {
    schemaVersion: 1,
    kind: "one-vs-rest-l2-logistic-pixel-classifier",
    researchOnly: true,
    classes,
    features: names2.map((name) => ({
      name,
      unit: PATHOLOGY_PIXEL_FEATURE_UNITS[name]
    })),
    localRadius,
    scaling: { method: "selected-training-pixel-z-score", means, scales },
    heads,
    metrics: metrics2,
    provenance: {
      methodVersion: "1",
      optimizer: "damped-newton-irls",
      regularization,
      classBalance,
      sampling: {
        method: "seeded-stratified-reservoir",
        seed: seed2,
        maxTrainingPixels,
        populationCounts,
        selectedCounts
      },
      samples: sampleProvenance,
      trainingDataSha256: pathologyJsonSha256(selected),
      probabilityMeaning: "normalized-one-vs-rest-sigmoid-scores-not-calibrated",
      warnings: warnings2
    }
  };
  await execution.checkpoint(
    "pixel-classifier-complete",
    selected.length,
    selected.length
  );
  return { ...body, modelId: pathologyJsonSha256(body) };
}
async function applyPathologyPixelClassifier(input) {
  const execution = new PathologyExecution(input);
  const { source: source2, raster } = copyPathologyImage(
    input.source,
    input.raster,
    execution
  );
  const model = structuredClone(input.model);
  validatePathologyPixelClassifierModel(model, input);
  const names2 = model.features.map((feature2) => feature2.name);
  const sampler = await createPixelFeatureSampler(
    raster,
    names2,
    model.localRadius,
    execution
  );
  const labels = new Uint8Array(raster.width * raster.height);
  const maximumClassScore = new Float32Array(labels.length);
  const counts = model.classes.map(() => 0);
  for (let pixel = 0; pixel < labels.length; pixel += 1) {
    execution.consume(names2.length * (model.heads.length + 1));
    const scores = pixelClassScores(
      standardize(
        sampler.vector(pixel),
        model.scaling.means,
        model.scaling.scales
      ),
      model.heads
    );
    let winner = 0;
    for (let candidate = 1; candidate < scores.length; candidate += 1)
      if (scores[candidate] > scores[winner]) winner = candidate;
    labels[pixel] = model.classes[winner].id;
    maximumClassScore[pixel] = scores[winner];
    counts[winner] += 1;
    if ((pixel + 1) % 65536 === 0)
      await execution.checkpoint(
        "applying-pixel-classifier",
        pixel + 1,
        labels.length
      );
  }
  const pixelArea = source2.region.width / raster.width * (source2.region.height / raster.height);
  const calibration2 = source2.calibration;
  const measurements = model.classes.map((entry, index4) => ({
    classId: entry.id,
    pixelCount: counts[index4],
    areaPx2: counts[index4] * pixelArea,
    areaUm2: calibration2?.verified === true ? counts[index4] * pixelArea * calibration2.micronsPerPixelX * calibration2.micronsPerPixelY : null
  }));
  if (measurements.some(
    (row) => !Number.isFinite(row.areaPx2) || row.areaUm2 != null && !Number.isFinite(row.areaUm2)
  ))
    throw invalid7("Classified pixel areas exceed finite numeric range.");
  await execution.checkpoint(
    "pixel-prediction-complete",
    labels.length,
    labels.length
  );
  return {
    kind: "pixel-classification",
    researchOnly: true,
    modelId: model.modelId,
    mask: {
      width: raster.width,
      height: raster.height,
      labels,
      maximumClassScore
    },
    classes: model.classes,
    measurements,
    provenance: {
      source: source2,
      rasterSha256: pathologySha256(raster.rgb),
      maskSha256: pathologySha256(labels),
      probabilityMeaning: "normalized-one-vs-rest-sigmoid-scores-not-calibrated",
      warnings: [...model.provenance.warnings]
    }
  };
}
function validatePathologyPixelClassifierModel(model, options = {}) {
  const execution = new PathologyExecution(options);
  const { modelId, ...body } = model;
  if (modelId !== pathologyJsonSha256(body) || model.schemaVersion !== 1 || model.kind !== "one-vs-rest-l2-logistic-pixel-classifier" || model.researchOnly !== true)
    throw invalid7("Pixel model content identity or method is invalid.");
  const classes = copyPixelClasses(model.classes);
  const names2 = copyPixelFeatures(
    model.features.map((feature2) => feature2.name),
    execution
  );
  if (!Number.isInteger(model.localRadius) || model.localRadius < 0 || model.localRadius > 16 || model.features.some(
    (feature2) => feature2.unit !== PATHOLOGY_PIXEL_FEATURE_UNITS[feature2.name]
  ) || model.scaling.method !== "selected-training-pixel-z-score" || model.scaling.means.length !== names2.length || model.scaling.scales.length !== names2.length || ![...model.scaling.means, ...model.scaling.scales].every(Number.isFinite) || model.scaling.scales.some((value) => value <= 0) || model.heads.length !== classes.length)
    throw invalid7(
      "Pixel model features, units, scaling or head dimensions are invalid."
    );
  if (model.heads.some(
    (head, index4) => head.classId !== classes[index4].id || head.coefficients.length !== names2.length || ![...head.coefficients, head.intercept, head.objective].every(
      Number.isFinite
    )
  ))
    throw invalid7("Pixel model coefficients or class assignments are invalid.");
}
function copyPixelClasses(input) {
  if (input.length < 2 || input.length > 8)
    throw invalid7(
      "Pixel classifiers require two to eight explicitly named classes."
    );
  const ids = /* @__PURE__ */ new Set();
  const names2 = /* @__PURE__ */ new Set();
  return input.map((entry) => {
    requirePathologyIdentity(entry.label, "Pixel class label");
    if (!Number.isInteger(entry.id) || entry.id < 1 || entry.id > 255 || ids.has(entry.id) || names2.has(entry.label))
      throw invalid7(
        "Pixel class IDs and labels must be unique; zero is reserved for ignored reference pixels."
      );
    ids.add(entry.id);
    names2.add(entry.label);
    return { id: entry.id, label: entry.label };
  });
}
function copyPixelFeatures(input, execution) {
  if (input.length < 1 || input.length > Math.min(8, execution.limits.maxFeatures) || new Set(input).size !== input.length || input.some((name) => !Object.hasOwn(PATHOLOGY_PIXEL_FEATURE_UNITS, name)))
    throw invalid7(
      "Pixel features must be an explicit bounded unique selection of documented fields."
    );
  return [...input];
}
function copyTrainingSamples(input, execution) {
  if (input.length < 1 || input.length > 8)
    throw exhausted5(
      "Pixel training is limited to eight source-authorized image/reference samples."
    );
  let totalPixels = 0;
  for (const sample of input)
    totalPixels += validatePathologyDimensions(
      sample.raster.width,
      sample.raster.height,
      execution
    );
  if (totalPixels > execution.limits.maxPixels)
    throw exhausted5(
      "The aggregate training and heldout raster size exceeds the pixel budget."
    );
  const ids = /* @__PURE__ */ new Set();
  const footprints = /* @__PURE__ */ new Set();
  return input.map((sample) => {
    requirePathologyIdentity(sample.id, "Training sample ID");
    if (sample.specimenId != null)
      requirePathologyIdentity(sample.specimenId, "Declared specimen ID");
    if (ids.has(sample.id) || sample.partition !== "train" && sample.partition !== "heldout")
      throw invalid7(
        "Training samples require unique IDs and explicit train/heldout partitions."
      );
    ids.add(sample.id);
    const { source: source2, raster } = copyPathologyImage(
      sample.source,
      sample.raster,
      execution
    );
    const footprint = pathologyJsonSha256({
      sourceId: source2.sourceId,
      sourceRevision: source2.sourceRevision,
      region: source2.region
    });
    if (footprints.has(footprint))
      throw invalid7(
        "A source image footprint cannot be duplicated as multiple training samples."
      );
    footprints.add(footprint);
    const annotation = sample.annotations;
    if (annotation.kind !== "semantic" || annotation.width !== raster.width || annotation.height !== raster.height || !isUint8Array4(annotation.labels) || annotation.labels.length !== raster.width * raster.height || !samePathologyImage(source2, annotation.image))
      throw invalid7(
        "Semantic annotation masks must be aligned with the exact image source revision and raster footprint."
      );
    const labels = new Uint8Array(annotation.labels);
    if (pathologySha256(labels) !== annotation.provenance.maskSha256)
      throw invalid7(
        "A semantic reference mask changed after its provenance was recorded."
      );
    return {
      id: sample.id,
      source: source2,
      raster,
      partition: sample.partition,
      ...sample.specimenId == null ? {} : { specimenId: sample.specimenId },
      annotations: {
        ...annotation,
        labels,
        image: copyPathologySource(annotation.image),
        reference: copyAnnotationReference(annotation.reference),
        provenance: {
          ...annotation.provenance,
          classMapping: annotation.provenance.classMapping.map((entry) => ({
            ...entry
          })),
          warnings: [...annotation.provenance.warnings]
        }
      }
    };
  });
}
function describeSample(sample) {
  return {
    id: sample.id,
    partition: sample.partition,
    ...sample.specimenId == null ? {} : { specimenId: sample.specimenId },
    image: sample.source,
    raster: {
      width: sample.raster.width,
      height: sample.raster.height,
      sha256: pathologySha256(sample.raster.rgb)
    },
    reference: sample.annotations.reference,
    referenceMaskSha256: sample.annotations.provenance.maskSha256
  };
}
function rejectKnownSplitLeakage(samples) {
  const partitions = /* @__PURE__ */ new Map();
  for (const sample of samples) {
    const identities = [
      `id:${sample.image.sourceId}`,
      `revision:${sample.image.sourceRevision}`,
      `raster:${sample.raster.sha256}`,
      ...sample.specimenId == null ? [] : [`specimen:${sample.specimenId}`]
    ];
    for (const identity15 of identities) {
      const previous = partitions.get(identity15);
      if (previous != null && previous !== sample.partition)
        throw invalid7(
          "Training and heldout partitions share an image identity, revision, identical raster bytes or declared specimen."
        );
      partitions.set(identity15, sample.partition);
    }
  }
}
function pixelClassScores(values3, heads) {
  const logScores = heads.map((head) => {
    const logit = score(values3, head.coefficients, head.intercept);
    return -Math.max(-logit, 0) - Math.log1p(Math.exp(-Math.abs(logit)));
  });
  const maximum = Math.max(...logScores);
  const scaled = logScores.map((value) => Math.exp(value - maximum));
  const total = scaled.reduce((sum2, value) => sum2 + value, 0);
  return scaled.map((value) => value / total);
}
function seededRandom2(seed2) {
  let state = seed2 >>> 0;
  return () => {
    state = Math.imul(state, 1664525) + 1013904223 >>> 0;
    return state / 4294967296;
  };
}
function invalid7(message) {
  return new PathologyAnalysisError("INVALID_ARGUMENT", message);
}
function exhausted5(message) {
  return new PathologyAnalysisError("RESOURCE_EXHAUSTED", message);
}
export { applyPathologyPixelClassifier, trainPathologyPixelClassifier, validatePathologyPixelClassifierModel };
