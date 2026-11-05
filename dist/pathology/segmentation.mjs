// See LICENSE and THIRD_PARTY_NOTICES.md.
import { external_exports3, init_zod } from "./../vendor/runtime.mjs";
import { PathologyAnalysisError, PathologyExecution, pathologyJsonSha256, pathologySha256 } from "./runtime.mjs";
import { copyPathologyImage } from "./image-input.mjs";
import { runPathologyRoiAnalysis } from "./roi-analysis.mjs";
init_zod();
import { spawn } from "node:child_process";
import { access as access2, mkdir as mkdir3, readFile as readFile2, stat as stat4 } from "node:fs/promises";
import { tmpdir as tmpdir2 } from "node:os";
import path12 from "node:path";
import { fileURLToPath as fileURLToPath5 } from "node:url";
var digestSchema2 = external_exports3.string().regex(/^sha256:[0-9a-f]{64}$/u);
var modelRegistrySchema = external_exports3.object({
  schemaVersion: external_exports3.literal(1),
  id: external_exports3.literal("stardist-2d-versatile-he"),
  release: external_exports3.literal("0.1"),
  license: external_exports3.literal("BSD-3-Clause"),
  source: external_exports3.literal(
    "https://github.com/stardist/stardist-models/releases/download/v0.1/python_2D_versatile_he.zip"
  ),
  archiveSha256: digestSchema2,
  weightsSha256: digestSchema2,
  configSha256: digestSchema2,
  thresholdsSha256: digestSchema2,
  probabilityThreshold: external_exports3.number().finite().gt(0).lt(1),
  nmsThreshold: external_exports3.number().finite().gt(0).lt(1),
  runtime: external_exports3.record(external_exports3.string().min(1).max(64), external_exports3.string().min(1).max(64)),
  input: external_exports3.literal("RGB8-H&E"),
  output: external_exports3.literal("predicted-nucleus-instances-not-whole-cells"),
  trainingData: external_exports3.array(external_exports3.string().min(1).max(128)).max(8)
}).strict();
var workerResultSchema = external_exports3.object({
  schemaVersion: external_exports3.literal(1),
  width: external_exports3.number().int().min(1).max(512),
  height: external_exports3.number().int().min(1).max(512),
  labelsLittleEndianBase64: external_exports3.string().max(1398104),
  maskSha256: digestSchema2,
  rasterSha256: digestSchema2,
  instances: external_exports3.array(
    external_exports3.object({
      label: external_exports3.number().int().min(1).max(4096),
      probability: external_exports3.number().finite().min(0).max(1)
    }).strict()
  ).max(4096),
  runtime: external_exports3.record(external_exports3.string().min(1).max(64), external_exports3.string().min(1).max(128))
}).strict();
var activeWorker = false;
function resolvePathologySegmentationRuntime(pluginDirectory) {
  const ownDirectory = path12.dirname(fileURLToPath5(import.meta.url));
  const sourceRun = path12.basename(ownDirectory) === "pathology" && path12.basename(path12.dirname(ownDirectory)) === "src";
  const root = pluginDirectory ?? path12.resolve(ownDirectory, sourceRun ? "../.." : "..");
  return {
    pythonExecutable: path12.join(
      root,
      ".pathology-venv",
      process.platform === "win32" ? "Scripts/python.exe" : "bin/python"
    ),
    assetsDirectory: path12.join(root, ".pathology-assets"),
    workerPath: path12.join(
      root,
      sourceRun ? "src/pathology/stardist_worker.py" : "dist/pathology/stardist_worker.py"
    ),
    timeoutMs: 12e4
  };
}
async function runPathologySegmentation(input) {
  const execution = new PathologyExecution(input);
  const { source: source2, raster } = copyPathologyImage(
    input.source,
    input.raster,
    execution,
    262144
  );
  const request2 = { ...input.request };
  const runtime = {
    ...input.runtime ?? resolvePathologySegmentationRuntime()
  };
  const onWorkerSpawn = input.onWorkerSpawn;
  const signal = input.signal;
  const onProgress = input.onProgress;
  const limits = { ...execution.limits };
  if (request2.model !== "stardist-2d-versatile-he")
    throw invalid4(
      "Only the explicitly provisioned StarDist H&E nucleus model is supported."
    );
  if (raster.width > 512 || raster.height > 512)
    throw exhausted2(
      "CPU nucleus inference is limited to 512 by 512 raster pixels per job."
    );
  const timeoutMs = runtime.timeoutMs ?? 12e4;
  if (!Number.isSafeInteger(timeoutMs) || timeoutMs < 1 || timeoutMs > 18e4)
    throw invalid4(
      "The trusted worker deadline must be between 1 and 180,000 milliseconds."
    );
  const registry3 = await readRegistry(runtime);
  execution.check();
  const parameters = {
    probabilityThreshold: request2.probabilityThreshold ?? registry3.probabilityThreshold,
    nmsThreshold: request2.nmsThreshold ?? registry3.nmsThreshold
  };
  const percentileLow = request2.normalizationPercentileLow ?? 1;
  const percentileHigh = request2.normalizationPercentileHigh ?? 99.8;
  if (!Object.values(parameters).every(
    (value) => Number.isFinite(value) && value > 0 && value < 1
  ) || !Number.isFinite(percentileLow) || !Number.isFinite(percentileHigh) || percentileLow < 0 || percentileLow >= percentileHigh || percentileHigh > 100)
    throw invalid4(
      "Model thresholds must be between zero and one; normalization requires ordered percentiles within zero and 100."
    );
  execution.consume(raster.rgb.byteLength);
  const rasterSha256 = pathologySha256(raster.rgb);
  await execution.checkpoint("starting-cpu-nucleus-worker", 0, 1);
  const decodedResult = workerResultSchema.safeParse(
    await invokePathologyPythonWorker(
      runtime,
      {
        schemaVersion: 1,
        width: raster.width,
        height: raster.height,
        rgbBase64: Buffer.from(raster.rgb).toString("base64"),
        ...parameters,
        percentileLow,
        percentileHigh
      },
      timeoutMs,
      signal,
      onWorkerSpawn
    )
  );
  if (!decodedResult.success)
    throw unavailable2(
      "The CPU worker returned an invalid nucleus-mask protocol."
    );
  const result2 = decodedResult.data;
  execution.check();
  const labels = decodeWorkerMask(
    result2,
    raster,
    rasterSha256,
    registry3,
    execution
  );
  const identityPrefix = pathologyJsonSha256({
    source: source2,
    rasterSha256,
    model: registry3.archiveSha256,
    parameters,
    percentileLow,
    percentileHigh
  });
  const instances = result2.instances.map((instance3) => ({
    ...instance3,
    id: `${source2.sourceId}:${identityPrefix}:nucleus-prediction:${instance3.label}`,
    kind: "nucleus-prediction",
    identityStatus: "model-prediction-not-verified",
    confidenceMeaning: "stardist-object-score-not-calibrated"
  }));
  await execution.checkpoint("measuring-predicted-nuclei", 0, instances.length);
  const measured = await runPathologyRoiAnalysis({
    source: source2,
    raster,
    operation: {
      kind: "measure-objects",
      objects: {
        format: "label-mask",
        labels,
        definitions: instances.map((instance3) => ({
          id: instance3.id,
          label: instance3.label,
          declaredEntityKind: "nucleus-prediction"
        }))
      }
    },
    signal,
    onProgress,
    limits
  });
  execution.check();
  return {
    kind: "instance-segmentation",
    researchOnly: true,
    mask: { width: raster.width, height: raster.height, labels },
    instances,
    featureTable: measured.featureTable,
    provenance: {
      source: source2,
      rasterSha256,
      maskSha256: result2.maskSha256,
      model: {
        id: registry3.id,
        release: registry3.release,
        license: registry3.license,
        source: registry3.source,
        archiveSha256: registry3.archiveSha256,
        weightsSha256: registry3.weightsSha256,
        configSha256: registry3.configSha256,
        thresholdsSha256: registry3.thresholdsSha256
      },
      runtime: result2.runtime,
      preprocessing: {
        input: "interleaved-RGB8-code-values",
        normalization: "per-channel-spatial-percentile",
        percentileLow,
        percentileHigh,
        clipping: false
      },
      parameters,
      warnings: [
        "Research-only predicted nuclei, not verified cells, whole-cell boundaries, phenotypes or diagnoses.",
        "The pretrained H&E model was trained on MoNuSeg 2018 training data and TNBC; generalization to this source has not been established by inference alone.",
        "Object scores are model confidence values, not calibrated probabilities of biological identity.",
        "Inference uses the supplied RGB8 raster at its acquisition scale; no hidden rescaling to an assumed nuclear diameter or physical resolution occurs.",
        "Clipped ROI-edge nuclei are retained and flagged in the measured feature table; no full-slide stitching is performed.",
        "Feature areas and perimeters are measured from raster pixel cells, not subpixel StarDist contours."
      ]
    }
  };
}
async function readRegistry(runtime) {
  try {
    await access2(runtime.pythonExecutable);
    await access2(runtime.workerPath);
    const file2 = path12.join(
      path12.dirname(runtime.workerPath),
      "model-registry.json"
    );
    if ((await stat4(file2)).size > 16384) throw new Error("Registry size");
    const bytes2 = await readFile2(file2);
    if (bytes2.byteLength > 16384) throw new Error("Registry size changed");
    return modelRegistrySchema.parse(JSON.parse(bytes2.toString("utf8")));
  } catch {
    throw unavailable2(
      "The optional plugin-local CPU runtime is not provisioned. Run the explicit pathology setup and pinned-model provisioning actions; jobs never install or download assets."
    );
  }
}
async function invokePathologyPythonWorker(runtime, payload2, timeoutMs, signal, onWorkerSpawn) {
  if (activeWorker)
    throw exhausted2(
      "Only one plugin CPU segmentation worker may run at a time."
    );
  activeWorker = true;
  try {
    return await invokeWorker(
      runtime,
      payload2,
      timeoutMs,
      signal,
      onWorkerSpawn
    );
  } finally {
    activeWorker = false;
  }
}
async function invokeWorker(runtime, payload2, timeoutMs, signal, onWorkerSpawn) {
  const cache = path12.join(runtime.assetsDirectory, "runtime-cache");
  await mkdir3(cache, { recursive: true });
  if (signal?.aborted) throw cancelled();
  return new Promise((resolve2, reject) => {
    const child = spawn(
      runtime.pythonExecutable,
      [
        "-I",
        runtime.workerPath,
        "--assets-directory",
        runtime.assetsDirectory,
        "--timeout-seconds",
        String(Math.max(1, Math.ceil(timeoutMs / 1e3)))
      ],
      {
        windowsHide: true,
        stdio: ["pipe", "pipe", "pipe"],
        env: {
          PATH: process.platform === "win32" ? path12.dirname(runtime.pythonExecutable) : `${path12.dirname(runtime.pythonExecutable)}:/usr/bin:/bin`,
          ...process.env.SystemRoot == null ? {} : { SystemRoot: process.env.SystemRoot },
          TMPDIR: tmpdir2(),
          OAIPKG_BOOTSTRAP_SKIP: "1",
          OAIPKG_DISABLE_META: "1",
          PYTHONDONTWRITEBYTECODE: "1",
          CUDA_VISIBLE_DEVICES: "-1",
          TF_CPP_MIN_LOG_LEVEL: "2",
          TF_NUM_INTEROP_THREADS: "1",
          TF_NUM_INTRAOP_THREADS: "1",
          OMP_NUM_THREADS: "1",
          OPENBLAS_NUM_THREADS: "1",
          VECLIB_MAXIMUM_THREADS: "1",
          NUMBA_NUM_THREADS: "1",
          MPLCONFIGDIR: path12.join(cache, "matplotlib"),
          KERAS_HOME: path12.join(cache, "keras"),
          NUMBA_CACHE_DIR: path12.join(cache, "numba")
        }
      }
    );
    const chunks = [];
    let outputBytes = 0;
    let diagnosticBytes = 0;
    let failure;
    let closed = false;
    const fail = (error50) => {
      failure ??= error50;
      if (!closed) child.kill("SIGKILL");
    };
    const abort = () => fail(cancelled());
    const timeout = setTimeout(
      () => fail(
        exhausted2(
          "The bounded CPU inference deadline expired; its worker was terminated."
        )
      ),
      timeoutMs
    );
    signal?.addEventListener("abort", abort, { once: true });
    child.on(
      "error",
      () => fail(
        unavailable2(
          "The explicitly provisioned CPU inference worker could not be started."
        )
      )
    );
    child.stdin.on(
      "error",
      () => fail(unavailable2("The bounded local inference input pipe failed."))
    );
    child.stdout.on("data", (chunk) => {
      outputBytes += chunk.byteLength;
      if (outputBytes > 8 * 1024 * 1024)
        fail(
          exhausted2("The CPU worker exceeded its bounded derived-result size.")
        );
      else chunks.push(chunk);
    });
    child.stderr.on("data", (chunk) => {
      diagnosticBytes += chunk.byteLength;
      if (diagnosticBytes > 256 * 1024)
        fail(
          exhausted2("The CPU worker exceeded its bounded diagnostic output.")
        );
    });
    child.on("close", (code2) => {
      closed = true;
      clearTimeout(timeout);
      signal?.removeEventListener("abort", abort);
      if (failure != null) {
        reject(failure);
        return;
      }
      if (code2 !== 0) {
        reject(
          unavailable2(
            "The provisioned CPU worker failed model/runtime validation or inference. Check the explicit setup qualification; no partial mask was published."
          )
        );
        return;
      }
      try {
        resolve2(JSON.parse(Buffer.concat(chunks).toString("utf8")));
      } catch {
        reject(
          unavailable2(
            "The CPU worker did not return the closed bounded derived-mask protocol."
          )
        );
      }
    });
    void (async () => {
      if (child.pid == null) return;
      if (signal?.aborted) {
        abort();
        return;
      }
      await onWorkerSpawn?.(child.pid);
      if (closed || failure != null) return;
      if (signal?.aborted) {
        abort();
        return;
      }
      child.stdin.end(JSON.stringify(payload2));
    })().catch(
      (error50) => fail(
        error50 instanceof Error ? error50 : unavailable2("The trusted worker-admission hook failed.")
      )
    );
  });
}
function decodeWorkerMask(result2, raster, rasterSha256, registry3, execution) {
  const pixels2 = raster.width * raster.height;
  if (result2.width !== raster.width || result2.height !== raster.height || result2.rasterSha256 !== rasterSha256 || result2.instances.length > execution.limits.maxObjects || result2.runtime.device !== "CPU" || result2.runtime.cpuThreads !== "1" || Object.entries(registry3.runtime).some(
    ([name, version2]) => result2.runtime[name] !== version2
  ))
    throw unavailable2(
      "The worker result differs from the requested image, model runtime, or object bound."
    );
  const bytes2 = Buffer.from(result2.labelsLittleEndianBase64, "base64");
  if (bytes2.byteLength !== pixels2 * 4 || bytes2.toString("base64") !== result2.labelsLittleEndianBase64 || pathologySha256(bytes2) !== result2.maskSha256)
    throw unavailable2(
      "The worker label-mask encoding or content digest is invalid."
    );
  const definitions = new Set(result2.instances.map((entry) => entry.label));
  if (definitions.size !== result2.instances.length)
    throw unavailable2("Worker object labels must be unique.");
  const seen = /* @__PURE__ */ new Set();
  const labels = new Uint32Array(pixels2);
  const view = new DataView(bytes2.buffer, bytes2.byteOffset, bytes2.byteLength);
  execution.consume(pixels2);
  for (let index4 = 0; index4 < pixels2; index4 += 1) {
    labels[index4] = view.getUint32(index4 * 4, true);
    if (labels[index4] !== 0) {
      if (!definitions.has(labels[index4]))
        throw unavailable2(
          "A predicted mask label lacks an explicit model object score."
        );
      seen.add(labels[index4]);
    }
  }
  if (seen.size !== definitions.size)
    throw unavailable2(
      "A worker object score has no pixels in the derived mask."
    );
  return labels;
}
function invalid4(message) {
  return new PathologyAnalysisError("INVALID_ARGUMENT", message);
}
function exhausted2(message) {
  return new PathologyAnalysisError("RESOURCE_EXHAUSTED", message);
}
function unavailable2(message) {
  return new PathologyAnalysisError("RUNTIME_UNAVAILABLE", message);
}
function cancelled() {
  return new PathologyAnalysisError(
    "CANCELLED",
    "CPU nucleus inference was cancelled and its worker was drained."
  );
}
export { invokePathologyPythonWorker, resolvePathologySegmentationRuntime, runPathologySegmentation };
