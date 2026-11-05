// See LICENSE and THIRD_PARTY_NOTICES.md.
function evaluateObjectClassifier(rows2) {
  let truePositive = 0;
  let trueNegative = 0;
  let falsePositive = 0;
  let falseNegative = 0;
  let logLoss = 0;
  let brierScore = 0;
  for (const { probability: probability3, target } of rows2) {
    const predicted = probability3 >= 0.5;
    if (target === 1 && predicted) truePositive += 1;
    else if (target === 0 && !predicted) trueNegative += 1;
    else if (predicted) falsePositive += 1;
    else falseNegative += 1;
    const bounded = Math.min(1 - 1e-15, Math.max(1e-15, probability3));
    logLoss -= target * Math.log(bounded) + (1 - target) * Math.log1p(-bounded);
    brierScore += (probability3 - target) ** 2;
  }
  const positiveCount = truePositive + falseNegative;
  const negativeCount = trueNegative + falsePositive;
  const precision = truePositive + falsePositive === 0 ? null : truePositive / (truePositive + falsePositive);
  const recall = positiveCount === 0 ? null : truePositive / positiveCount;
  const sorted = [...rows2].sort(
    (left, right) => left.probability - right.probability
  );
  let positiveRankSum = 0;
  for (let start = 0; start < sorted.length; ) {
    let end = start + 1;
    while (end < sorted.length && sorted[end].probability === sorted[start].probability)
      end += 1;
    const meanRank = (start + 1 + end) / 2;
    for (let index4 = start; index4 < end; index4 += 1)
      if (sorted[index4].target === 1) positiveRankSum += meanRank;
    start = end;
  }
  return {
    evaluation: rows2.length === 0 ? "not-evaluated" : "heldout-objects",
    decisionThreshold: 0.5,
    sampleCount: rows2.length,
    positiveCount,
    negativeCount,
    truePositive,
    trueNegative,
    falsePositive,
    falseNegative,
    accuracy: rows2.length === 0 ? null : (truePositive + trueNegative) / rows2.length,
    balancedAccuracy: positiveCount === 0 || negativeCount === 0 ? null : (truePositive / positiveCount + trueNegative / negativeCount) / 2,
    precision,
    recall,
    f1: 2 * truePositive + falsePositive + falseNegative === 0 ? null : 2 * truePositive / (2 * truePositive + falsePositive + falseNegative),
    logLoss: rows2.length === 0 ? null : logLoss / rows2.length,
    rocAuc: positiveCount === 0 || negativeCount === 0 ? null : (positiveRankSum - positiveCount * (positiveCount + 1) / 2) / (positiveCount * negativeCount),
    brierScore: rows2.length === 0 ? null : brierScore / rows2.length
  };
}
export { evaluateObjectClassifier };
