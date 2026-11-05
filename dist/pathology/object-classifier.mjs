// See LICENSE and THIRD_PARTY_NOTICES.md.
import { PathologyAnalysisError, PathologyExecution, pathologyFeatureTableSha256, pathologyJsonSha256, requirePathologyIdentity } from "./runtime.mjs";
import { PATHOLOGY_FEATURE_UNITS } from "./types.mjs";
import { fitBinaryLogistic, score, sigmoid, standardize } from "./binary-logistic.mjs";
import { evaluateObjectClassifier } from "./classifier-metrics.mjs";
async function trainObjectClassifier(input) {
  const execution = new PathologyExecution(input);
  const table5 = copyFeatureTable(input.table, execution);
  const positiveClass = input.positiveClass;
  const negativeClass = input.negativeClass;
  requirePathologyIdentity(positiveClass, "Positive class");
  requirePathologyIdentity(negativeClass, "Negative class");
  if (positiveClass === negativeClass)
    throw invalid6(
      "Binary object classifiers require two distinct explicit class labels."
    );
  const regularization = input.regularization ?? 0.1;
  const maxIterations = input.maxIterations ?? 50;
  const classBalance = input.classBalance ?? "balanced";
  if (!Number.isFinite(regularization) || regularization < 1e-6 || regularization > 1e3 || !Number.isSafeInteger(maxIterations) || maxIterations < 1 || maxIterations > 100 || classBalance !== "balanced" && classBalance !== "none")
    throw invalid6(
      "Classifier regularization, class balance, or iteration bounds are invalid."
    );
  if (input.labels.length > execution.limits.maxTrainingRows)
    throw exhausted4("Object labels exceed the bounded training row count.");
  const names2 = [...input.features];
  validateFeatureSelection(names2, execution);
  const features = names2.map((name) => ({
    name,
    unit: PATHOLOGY_FEATURE_UNITS[name]
  }));
  const byId = new Map(table5.rows.map((row) => [row.objectId, row]));
  const labels = input.labels.map((label2) => ({
    objectId: label2.objectId,
    label: label2.label,
    partition: label2.partition
  }));
  const seen = /* @__PURE__ */ new Set();
  const selected = labels.map((label2) => {
    if (seen.has(label2.objectId))
      throw invalid6(
        "Training and heldout labels must use distinct object IDs without duplication."
      );
    seen.add(label2.objectId);
    const row = byId.get(label2.objectId);
    if (row == null)
      throw invalid6(
        "A provided label does not refer to an object in the selected feature result."
      );
    if (label2.label !== positiveClass && label2.label !== negativeClass)
      throw invalid6(
        "Every provided label must match one of the two explicit classifier classes."
      );
    if (label2.partition !== "train" && label2.partition !== "heldout")
      throw invalid6(
        "Every label requires an explicit train or heldout partition."
      );
    return {
      row,
      values: featureVector(row, names2),
      target: label2.label === positiveClass ? 1 : 0,
      partition: label2.partition
    };
  });
  const training = selected.filter((row) => row.partition === "train");
  const heldout = selected.filter((row) => row.partition === "heldout");
  execution.consume(selected.length * names2.length * 3);
  const positive = training.filter((row) => row.target === 1).length;
  const negative = training.length - positive;
  if (positive < 2 || negative < 2)
    throw invalid6(
      "Training requires at least two explicitly labeled objects in each class; heldout labels do not count as training data."
    );
  const means = names2.map(() => 0);
  const moments = names2.map(() => 0);
  for (const [index4, row] of training.entries()) {
    for (let column3 = 0; column3 < names2.length; column3 += 1) {
      const delta = row.values[column3] - means[column3];
      means[column3] += delta / (index4 + 1);
      moments[column3] += delta * (row.values[column3] - means[column3]);
    }
  }
  const standardDeviations = moments.map(
    (moment) => Math.sqrt(Math.max(0, moment / training.length))
  );
  if (![...means, ...standardDeviations].every(Number.isFinite))
    throw invalid6("Training feature scaling exceeds finite numeric range.");
  if (standardDeviations.every((value) => value === 0))
    throw invalid6(
      "No selected feature varies in the training partition; an informative object classifier cannot be fitted."
    );
  const scales = standardDeviations.map((value) => value === 0 ? 1 : value);
  const classWeights = {
    positive: classBalance === "balanced" ? training.length / (2 * positive) : 1,
    negative: classBalance === "balanced" ? training.length / (2 * negative) : 1
  };
  const rows2 = training.map((row) => ({
    objectId: row.row.objectId,
    values: standardize(row.values, means, scales),
    target: row.target,
    weight: row.target === 1 ? classWeights.positive : classWeights.negative
  }));
  const optimized = await fitBinaryLogistic(
    rows2,
    names2.length,
    regularization,
    maxIterations,
    execution
  );
  const coefficients = optimized.parameters.slice(0, names2.length);
  const intercept = optimized.parameters[names2.length];
  const metrics2 = evaluateObjectClassifier(
    heldout.map((row) => ({
      probability: sigmoid(
        score(standardize(row.values, means, scales), coefficients, intercept)
      ),
      target: row.target
    }))
  );
  const warnings2 = [
    "Research-only binary object-class predictions from explicit user labels; predictions do not establish cell identity or diagnosis.",
    "Probabilities are uncalibrated model scores; no annotated real-data accuracy, QuPath parity, or clinical validation is established by this fit.",
    "Heldout objects share one source ROI feature table; these metrics do not demonstrate independent slide, donor, scanner, or stain generalization.",
    "RGB8 and raster-grid features are acquisition dependent; applying to a different stain, sampling scale, or scanner requires independent validation."
  ];
  if (classBalance === "balanced")
    warnings2.push(
      "Class balancing changes the effective training prevalence; these scores are not population prevalence estimates."
    );
  if (metrics2.evaluation === "not-evaluated")
    warnings2.push(
      "No heldout labels were supplied; no heldout performance estimate is available."
    );
  else if (metrics2.positiveCount === 0 || metrics2.negativeCount === 0)
    warnings2.push(
      "The heldout partition lacks one class; balanced accuracy and ROC AUC are undefined."
    );
  if (standardDeviations.some((value) => value === 0))
    warnings2.push(
      "Constant training features use scale 1 and provide no fitted discrimination."
    );
  if (!optimized.converged)
    warnings2.push(
      "Optimization did not reach its gradient tolerance within the requested iteration budget."
    );
  const body = {
    schemaVersion: 1,
    kind: "binary-l2-logistic-object-classifier",
    researchOnly: true,
    positiveClass,
    negativeClass,
    features,
    coefficients,
    intercept,
    scaling: { method: "training-population-z-score", means, scales },
    metrics: metrics2,
    provenance: {
      methodVersion: "1",
      optimizer: "damped-newton-irls",
      regularization,
      interceptRegularized: false,
      classBalance,
      classCounts: { positive, negative },
      classWeights,
      iterations: optimized.iterations,
      converged: optimized.converged,
      objective: optimized.objective,
      featureTableSha256: table5.provenance.featureTableSha256,
      trainingDataSha256: pathologyJsonSha256(
        training.map((row) => ({
          objectId: row.row.objectId,
          values: row.values,
          target: row.target
        }))
      ),
      labelsSha256: pathologyJsonSha256(labels),
      geometryMeasurement: table5.provenance.geometryMeasurement,
      source: table5.provenance.source,
      warnings: warnings2
    }
  };
  await execution.checkpoint(
    "classifier-complete",
    optimized.iterations,
    maxIterations
  );
  return { ...body, modelId: pathologyJsonSha256(body) };
}
async function applyObjectClassifier(input) {
  const execution = new PathologyExecution(input);
  const table5 = copyFeatureTable(input.table, execution);
  const { modelId, ...originalBody } = input.model;
  const body = {
    ...originalBody,
    features: originalBody.features.map((feature2) => ({ ...feature2 })),
    coefficients: [...originalBody.coefficients],
    scaling: {
      ...originalBody.scaling,
      means: [...originalBody.scaling.means],
      scales: [...originalBody.scaling.scales]
    },
    provenance: {
      ...originalBody.provenance,
      warnings: [...originalBody.provenance.warnings]
    }
  };
  validateObjectClassifierModel({ ...body, modelId }, input);
  const names2 = body.features.map((feature2) => feature2.name);
  if (body.provenance.geometryMeasurement !== table5.provenance.geometryMeasurement)
    throw invalid6(
      "Classifier application must use the same vector-boundary or raster-grid measurement convention as training."
    );
  const threshold = input.threshold ?? 0.5;
  if (!Number.isFinite(threshold) || threshold <= 0 || threshold >= 1)
    throw invalid6(
      "Classifier decision thresholds must lie strictly between zero and one."
    );
  const predictions = [];
  for (const [index4, row] of table5.rows.entries()) {
    execution.consume(names2.length);
    const positiveProbability = sigmoid(
      score(
        standardize(
          featureVector(row, names2),
          body.scaling.means,
          body.scaling.scales
        ),
        body.coefficients,
        body.intercept
      )
    );
    predictions.push({
      objectId: row.objectId,
      sourceId: row.sourceId,
      sourceRevision: row.sourceRevision,
      objectKind: row.kind,
      positiveProbability,
      predictedClass: positiveProbability >= threshold ? body.positiveClass : body.negativeClass,
      confidenceKind: "uncalibrated-model-probability"
    });
    if ((index4 + 1) % 256 === 0)
      await execution.checkpoint(
        "applying-object-classifier",
        index4 + 1,
        table5.rows.length
      );
  }
  await execution.checkpoint(
    "classifier-application-complete",
    table5.rows.length,
    table5.rows.length
  );
  return {
    researchOnly: true,
    modelId,
    featureTableSha256: table5.provenance.featureTableSha256,
    threshold,
    predictions,
    warnings: [
      ...body.provenance.warnings,
      "Application preserves source object kind; predicted class strings are not verified biological entity identities."
    ]
  };
}
function validateObjectClassifierModel(model, options = {}) {
  const execution = new PathologyExecution(options);
  const { modelId, ...body } = model;
  if (modelId !== pathologyJsonSha256(body) || body.schemaVersion !== 1 || body.kind !== "binary-l2-logistic-object-classifier" || body.researchOnly !== true)
    throw invalid6(
      "The classifier model is invalid or its content identity changed."
    );
  requirePathologyIdentity(body.positiveClass, "Positive class");
  requirePathologyIdentity(body.negativeClass, "Negative class");
  const names2 = body.features.map((feature2) => feature2.name);
  validateFeatureSelection(names2, execution);
  if (body.positiveClass === body.negativeClass || body.scaling.method !== "training-population-z-score" || body.features.some(
    (feature2) => feature2.unit !== PATHOLOGY_FEATURE_UNITS[feature2.name]
  ) || body.coefficients.length !== names2.length || body.scaling.means.length !== names2.length || body.scaling.scales.length !== names2.length || ![
    ...body.coefficients,
    body.intercept,
    ...body.scaling.means,
    ...body.scaling.scales
  ].every(Number.isFinite) || body.scaling.scales.some((scale) => scale <= 0))
    throw invalid6(
      "Classifier coefficients, feature units, or training scaling are invalid."
    );
}
function copyFeatureTable(table5, execution) {
  if (table5.rows.length > execution.limits.maxTrainingRows || table5.features.length > Object.keys(PATHOLOGY_FEATURE_UNITS).length)
    throw exhausted4(
      "The pathology feature table exceeds bounded classifier dimensions."
    );
  const names2 = table5.features.map((feature2) => feature2.name);
  if (names2.length === 0 || new Set(names2).size !== names2.length || names2.some((name) => !Object.hasOwn(PATHOLOGY_FEATURE_UNITS, name)))
    throw invalid6(
      "The pathology feature table contains invalid or duplicate measured fields."
    );
  if (table5.features.some(
    (feature2) => feature2.unit !== PATHOLOGY_FEATURE_UNITS[feature2.name]
  ))
    throw invalid6("The pathology feature table contains mismatched units.");
  execution.consume(table5.rows.length * names2.length);
  const seen = /* @__PURE__ */ new Set();
  for (const row of table5.rows) {
    requirePathologyIdentity(row.objectId, "Feature object ID");
    if (seen.has(row.objectId) || row.sourceId !== table5.provenance.source.sourceId || row.sourceRevision !== table5.provenance.source.sourceRevision)
      throw invalid6(
        "Feature rows must have unique IDs and match their recorded source revision."
      );
    if (Object.values(row.values).some(
      (value) => value !== null && !Number.isFinite(value)
    ))
      throw invalid6(
        "Object features must be finite measurements or explicit missing values."
      );
    seen.add(row.objectId);
  }
  if (pathologyFeatureTableSha256(table5) !== table5.provenance.featureTableSha256)
    throw invalid6(
      "The feature result changed since its provenance was recorded."
    );
  return {
    features: table5.features.map((feature2) => ({ ...feature2 })),
    rows: table5.rows.map((row) => ({
      ...row,
      bounds: { ...row.bounds },
      values: { ...row.values }
    })),
    provenance: {
      ...table5.provenance,
      source: {
        ...table5.provenance.source,
        region: { ...table5.provenance.source.region },
        ...table5.provenance.source.calibration == null ? {} : { calibration: { ...table5.provenance.source.calibration } }
      },
      raster: { ...table5.provenance.raster },
      parameters: { ...table5.provenance.parameters },
      warnings: [...table5.provenance.warnings]
    }
  };
}
function validateFeatureSelection(names2, execution) {
  if (names2.length < 1 || names2.length > execution.limits.maxFeatures || new Set(names2).size !== names2.length || names2.some((name) => !Object.hasOwn(PATHOLOGY_FEATURE_UNITS, name)))
    throw invalid6(
      "Classifier features must be an explicit bounded unique selection of measured fields with documented units."
    );
}
function featureVector(row, names2) {
  return names2.map((name) => {
    const value = row.values[name];
    if (value == null || !Number.isFinite(value))
      throw invalid6(
        "Selected classifier features contain missing values; choose measured features rather than implicitly imputing them."
      );
    return value;
  });
}
function invalid6(message) {
  return new PathologyAnalysisError("INVALID_ARGUMENT", message);
}
function exhausted4(message) {
  return new PathologyAnalysisError("RESOURCE_EXHAUSTED", message);
}
export { applyObjectClassifier, trainObjectClassifier, validateObjectClassifierModel };
