// See LICENSE and THIRD_PARTY_NOTICES.md.
import { PathologyAnalysisError } from "./runtime.mjs";
var PixelMetricAccumulator = class {
  constructor(classes) {
    this.classes = classes;
    this.indices = new Map(classes.map((entry, index4) => [entry.id, index4]));
    this.confusion = classes.map(() => classes.map(() => 0));
  }
  classes;
  indices;
  confusion;
  ignored = 0;
  evaluated = 0;
  scoreCount = 0;
  logLoss = 0;
  observeMask(reference, prediction) {
    if (reference === 0) {
      this.ignored += 1;
      return;
    }
    const row = this.indices.get(reference);
    const column3 = this.indices.get(prediction);
    if (row == null || column3 == null)
      throw new PathologyAnalysisError(
        "INVALID_ARGUMENT",
        "Evaluated pixels must refer to declared reference and prediction classes."
      );
    this.confusion[row][column3] += 1;
    this.evaluated += 1;
  }
  observeScores(reference, scores) {
    if (reference === 0) {
      this.ignored += 1;
      return;
    }
    const index4 = this.indices.get(reference);
    if (index4 == null || scores.length !== this.classes.length || scores.some((value) => !Number.isFinite(value) || value < 0 || value > 1))
      throw new PathologyAnalysisError(
        "INVALID_ARGUMENT",
        "Pixel evaluation requires finite normalized class scores and a declared reference class."
      );
    let winner = 0;
    for (let candidate = 1; candidate < scores.length; candidate += 1)
      if (scores[candidate] > scores[winner]) winner = candidate;
    this.observeMask(reference, this.classes[winner].id);
    this.logLoss -= Math.log(Math.max(1e-15, scores[index4]));
    this.scoreCount += 1;
  }
  result(evaluation) {
    const classes = this.classes.map((entry, index4) => {
      const truePositive = this.confusion[index4][index4];
      const truePixels = this.confusion[index4].reduce(
        (sum2, value) => sum2 + value,
        0
      );
      const predictedPixels = this.confusion.reduce(
        (sum2, row) => sum2 + row[index4],
        0
      );
      const falsePositive = predictedPixels - truePositive;
      const falseNegative = truePixels - truePositive;
      return {
        classId: entry.id,
        classLabel: entry.label,
        truePixels,
        predictedPixels,
        truePositive,
        falsePositive,
        falseNegative,
        precision: predictedPixels === 0 ? null : truePositive / predictedPixels,
        recall: truePixels === 0 ? null : truePositive / truePixels,
        dice: truePixels + predictedPixels === 0 ? null : 2 * truePositive / (truePixels + predictedPixels),
        iou: truePositive + falsePositive + falseNegative === 0 ? null : truePositive / (truePositive + falsePositive + falseNegative)
      };
    });
    return {
      evaluation: this.evaluated === 0 ? "not-evaluated" : evaluation,
      confusion: this.confusion.map((row) => [...row]),
      classes,
      evaluatedPixels: this.evaluated,
      ignoredPixels: this.ignored,
      accuracy: this.evaluated === 0 ? null : classes.reduce((sum2, entry) => sum2 + entry.truePositive, 0) / this.evaluated,
      balancedAccuracy: meanDefined(classes.map((entry) => entry.recall)),
      macroDice: meanDefined(classes.map((entry) => entry.dice)),
      meanIoU: meanDefined(classes.map((entry) => entry.iou)),
      logLoss: this.scoreCount === 0 || this.scoreCount !== this.evaluated ? null : this.logLoss / this.scoreCount
    };
  }
};
function meanDefined(values3) {
  const present = values3.filter((value) => value != null);
  return present.length === 0 ? null : present.reduce((sum2, value) => sum2 + value, 0) / present.length;
}
export { PixelMetricAccumulator };
