// See LICENSE and THIRD_PARTY_NOTICES.md.
import { PathologyAnalysisError } from "./runtime.mjs";
async function fitBinaryLogistic(rows2, featureCount, regularization, maxIterations, execution, phase = "fitting-object-classifier") {
  let parameters = Array.from({ length: featureCount + 1 }, () => 0);
  let converged = false;
  let iterations = 0;
  const weightSum = rows2.reduce((sum2, row) => sum2 + row.weight, 0);
  for (let iteration = 0; iteration < maxIterations; iteration += 1) {
    execution.consume(rows2.length * parameters.length * parameters.length);
    const gradient = parameters.map(
      (_value2, index4) => index4 < featureCount ? regularization * parameters[index4] : 0
    );
    const hessian = parameters.map(
      (_value2, row) => parameters.map(
        (_other, column3) => row === column3 ? (row < featureCount ? regularization : 0) + 1e-10 : 0
      )
    );
    for (const row of rows2) {
      const design = [...row.values, 1];
      const probability3 = sigmoid(
        design.reduce(
          (sum2, value, index4) => sum2 + value * parameters[index4],
          0
        )
      );
      const residual = row.weight * (probability3 - row.target) / weightSum;
      const curvature = row.weight * probability3 * (1 - probability3) / weightSum;
      for (let column3 = 0; column3 < parameters.length; column3 += 1) {
        gradient[column3] += residual * design[column3];
        for (let other = 0; other <= column3; other += 1)
          hessian[column3][other] += curvature * design[column3] * design[other];
      }
    }
    for (let row = 0; row < parameters.length; row += 1)
      for (let column3 = 0; column3 < row; column3 += 1)
        hessian[column3][row] = hessian[row][column3];
    if (Math.max(...gradient.map(Math.abs)) <= 1e-7) {
      converged = true;
      break;
    }
    const step = solvePositiveDefinite(hessian, gradient);
    const previousLoss = logisticObjective(rows2, parameters, regularization);
    let accepted = false;
    for (let reduction = 0; reduction < 20; reduction += 1) {
      execution.consume(rows2.length * parameters.length);
      const rate = 2 ** -reduction;
      const candidate = parameters.map(
        (value, index4) => value - rate * step[index4]
      );
      if (candidate.every(Number.isFinite) && logisticObjective(rows2, candidate, regularization) < previousLoss) {
        parameters = candidate;
        accepted = true;
        iterations = iteration + 1;
        break;
      }
    }
    if (!accepted) break;
    await execution.checkpoint(phase, iterations, maxIterations);
  }
  return {
    parameters,
    iterations,
    converged,
    objective: logisticObjective(rows2, parameters, regularization)
  };
}
function solvePositiveDefinite(matrix, rightHandSide) {
  const size = rightHandSide.length;
  if (size === 0 || matrix.length !== size || !rightHandSide.every(Number.isFinite) || matrix.some((row) => row.length !== size || !row.every(Number.isFinite)))
    throw new PathologyAnalysisError(
      "INVALID_ARGUMENT",
      "Classifier Newton system must have finite, matching dimensions."
    );
  const lower = matrix.map(
    (_row, index4) => Array.from({ length: index4 + 1 }, () => 0)
  );
  for (let row = 0; row < size; row += 1) {
    for (let column3 = 0; column3 <= row; column3 += 1) {
      if (matrix[row][column3] !== matrix[column3][row])
        throw new PathologyAnalysisError(
          "INVALID_ARGUMENT",
          "Classifier Hessian must be symmetric."
        );
      let remainder = matrix[row][column3];
      for (let previous = 0; previous < column3; previous += 1)
        remainder -= lower[row][previous] * lower[column3][previous];
      if (!Number.isFinite(remainder) || row === column3 && remainder <= 0)
        throw new PathologyAnalysisError(
          "INVALID_ARGUMENT",
          "Classifier Hessian is not positive definite at working precision."
        );
      const value = row === column3 ? Math.sqrt(remainder) : remainder / lower[column3][column3];
      if (!Number.isFinite(value))
        throw new PathologyAnalysisError(
          "INVALID_ARGUMENT",
          "Classifier Hessian factorization exceeds finite numeric range."
        );
      lower[row][column3] = value;
    }
  }
  const solution = [...rightHandSide];
  for (let row = 0; row < size; row += 1) {
    for (let column3 = 0; column3 < row; column3 += 1)
      solution[row] -= lower[row][column3] * solution[column3];
    solution[row] /= lower[row][row];
    if (!Number.isFinite(solution[row]))
      throw new PathologyAnalysisError(
        "INVALID_ARGUMENT",
        "Classifier Newton step exceeds finite numeric range."
      );
  }
  for (let row = size - 1; row >= 0; row -= 1) {
    for (let column3 = row + 1; column3 < size; column3 += 1)
      solution[row] -= lower[column3][row] * solution[column3];
    solution[row] /= lower[row][row];
    if (!Number.isFinite(solution[row]))
      throw new PathologyAnalysisError(
        "INVALID_ARGUMENT",
        "Classifier Newton step exceeds finite numeric range."
      );
  }
  return solution;
}
function logisticObjective(rows2, parameters, regularization) {
  const coefficients = parameters.slice(0, -1);
  let loss = 0;
  let weight = 0;
  for (const row of rows2) {
    const logit = score(
      row.values,
      coefficients,
      parameters[parameters.length - 1]
    );
    loss += row.weight * (Math.max(logit, 0) - row.target * logit + Math.log1p(Math.exp(-Math.abs(logit))));
    weight += row.weight;
  }
  return loss / weight + regularization / 2 * coefficients.reduce((sum2, value) => sum2 + value * value, 0);
}
function standardize(values3, means, scales) {
  return values3.map((value, index4) => {
    const standardized = (value - means[index4]) / scales[index4];
    if (!Number.isFinite(standardized))
      throw new PathologyAnalysisError(
        "INVALID_ARGUMENT",
        "Classifier feature scaling exceeds finite numeric range."
      );
    return standardized;
  });
}
function score(values3, coefficients, intercept) {
  const result2 = values3.reduce(
    (sum2, value, index4) => sum2 + value * coefficients[index4],
    intercept
  );
  if (!Number.isFinite(result2))
    throw new PathologyAnalysisError(
      "INVALID_ARGUMENT",
      "Classifier score exceeds finite numeric range."
    );
  return result2;
}
function sigmoid(value) {
  return value >= 0 ? 1 / (1 + Math.exp(-value)) : Math.exp(value) / (1 + Math.exp(value));
}
export { fitBinaryLogistic, score, sigmoid, standardize };
