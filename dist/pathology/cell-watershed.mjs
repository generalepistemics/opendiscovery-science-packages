// See LICENSE and THIRD_PARTY_NOTICES.md.
import { external_exports3, init_zod, microscopySelectionSchema } from "./../vendor/runtime.mjs";
import { PathologyAnalysisError, PathologyExecution, pathologyJsonSha256, pathologySha256, requirePathologyIdentity } from "./runtime.mjs";
import { copyPathologyImage } from "./image-input.mjs";
import { runPathologyRoiAnalysis } from "./roi-analysis.mjs";
import { invokePathologyPythonWorker, resolvePathologySegmentationRuntime } from "./segmentation.mjs";
init_zod();
import { access as access3, readFile as readFile3, stat as stat5 } from "node:fs/promises";
import path13 from "node:path";
var thresholdSchema = external_exports3.union([
  external_exports3.literal("otsu"),
  external_exports3.number().finite().min(0).max(1)
]);
var pathologyCellWatershedParametersSchema = external_exports3.object({
  nucleiSigmaPixels: external_exports3.number().finite().min(0).max(4).default(1),
  cytoplasmSigmaPixels: external_exports3.number().finite().min(0).max(4).default(1),
  nucleiThreshold: thresholdSchema.default("otsu"),
  cytoplasmThreshold: thresholdSchema.default("otsu"),
  minimumNucleusAreaPixels: external_exports3.number().int().min(1).max(65536).default(16),
  minimumCellAreaPixels: external_exports3.number().int().min(1).max(65536).default(64),
  minimumSeedDistancePixels: external_exports3.number().int().min(1).max(32).default(5),
  foregroundClosingRadiusPixels: external_exports3.number().int().min(0).max(4).default(1)
}).strict();
var digestSchema3 = external_exports3.string().regex(/^sha256:[a-f0-9]{64}$/u);
var resultSchema = external_exports3.object({
  schemaVersion: external_exports3.literal(1),
  width: external_exports3.number().int().min(1).max(512),
  height: external_exports3.number().int().min(1).max(512),
  labelsLittleEndianBase64: external_exports3.string().max(1398104),
  maskSha256: digestSchema3,
  nucleiChannelSha256: digestSchema3,
  cytoplasmChannelSha256: digestSchema3,
  instances: external_exports3.array(
    external_exports3.object({
      label: external_exports3.number().int().min(1).max(4096),
      nucleusSeedLabel: external_exports3.number().int().min(1).max(4096)
    }).strict()
  ).max(4096),
  seedCount: external_exports3.number().int().min(0).max(4096),
  thresholdsUsed: external_exports3.object({
    nuclei: external_exports3.number().finite().min(0).max(1),
    cytoplasm: external_exports3.number().finite().min(0).max(1)
  }).strict(),
  runtime: external_exports3.record(external_exports3.string().min(1).max(64), external_exports3.string().min(1).max(128))
}).strict();
async function runPathologyCellWatershed(input) {
  const execution = new PathologyExecution(input);
  const nuclei = copyChannel(input.nuclei, execution);
  const cytoplasm = copyChannel(input.cytoplasm, execution);
  const parameters = pathologyCellWatershedParametersSchema.parse(
    input.parameters ?? {}
  );
  requirePathologyIdentity(
    input.registration.basis,
    "Cell-channel registration basis"
  );
  if (input.registration.kind !== "same-pixel-grid" || input.channelRoles.nuclei !== "nuclear-DNA" || input.channelRoles.cytoplasm !== "cytoplasm-or-cell-body")
    throw invalid5(
      "Cell watershed requires explicit DNA and cytoplasm roles with a declared shared pixel grid."
    );
  const registration = {
    kind: "same-pixel-grid",
    basis: input.registration.basis
  };
  const pixels2 = nuclei.raster.width * nuclei.raster.height;
  if (pixels2 * 2 > execution.limits.maxPixels)
    throw exhausted3(
      "The two cell channels exceed the aggregate raster-pixel bound."
    );
  if (nuclei.raster.width !== cytoplasm.raster.width || nuclei.raster.height !== cytoplasm.raster.height || ["x", "y", "width", "height"].some(
    (key2) => nuclei.source.region[key2] !== cytoplasm.source.region[key2]
  ) || nuclei.plane.selection != null && cytoplasm.plane.selection != null && (nuclei.plane.selection.z !== cytoplasm.plane.selection.z || nuclei.plane.selection.t !== cytoplasm.plane.selection.t))
    throw invalid5(
      "Cell channels must cover identical raster dimensions, pixel footprints and known Z/T indices; this operation does not register, resample or project images."
    );
  if (nuclei.selectedSha256 === cytoplasm.selectedSha256)
    throw invalid5(
      "The DNA and cytoplasm selections contain identical bytes; distinct channel evidence is required."
    );
  const defaultRuntime = resolvePathologySegmentationRuntime();
  const runtime = {
    ...input.runtime ?? {
      ...defaultRuntime,
      workerPath: path13.join(
        path13.dirname(defaultRuntime.workerPath),
        "cell_watershed_worker.py"
      ),
      timeoutMs: 6e4
    }
  };
  const timeoutMs = runtime.timeoutMs ?? 6e4;
  if (!Number.isSafeInteger(timeoutMs) || timeoutMs < 1 || timeoutMs > 18e4)
    throw invalid5(
      "Cell worker deadline must be between one and 180,000 milliseconds."
    );
  const signal = input.signal;
  const onProgress = input.onProgress;
  const onWorkerSpawn = input.onWorkerSpawn;
  const limits = { ...execution.limits };
  const registry3 = await readCellRegistry(runtime);
  await execution.checkpoint("starting-registered-cell-watershed", 0, 1);
  const decoded = resultSchema.safeParse(
    await invokePathologyPythonWorker(
      runtime,
      {
        schemaVersion: 1,
        width: nuclei.raster.width,
        height: nuclei.raster.height,
        nucleiBase64: Buffer.from(nuclei.selected).toString("base64"),
        cytoplasmBase64: Buffer.from(cytoplasm.selected).toString("base64"),
        parameters
      },
      timeoutMs,
      signal,
      onWorkerSpawn
    )
  );
  execution.check();
  if (!decoded.success)
    throw unavailable3(
      "The cell worker did not return the closed derived-instance protocol."
    );
  const result2 = decoded.data;
  if (result2.width !== nuclei.raster.width || result2.height !== nuclei.raster.height || result2.nucleiChannelSha256 !== nuclei.selectedSha256 || result2.cytoplasmChannelSha256 !== cytoplasm.selectedSha256 || result2.runtime.device !== "CPU" || result2.runtime.cpuThreads !== "1" || Object.entries(registry3.runtime).some(
    ([name, version2]) => result2.runtime[name] !== version2
  ) || result2.seedCount > execution.limits.maxObjects || result2.instances.length > execution.limits.maxObjects)
    throw unavailable3(
      "The cell worker output does not match the admitted channels, runtime, or object bound."
    );
  const bytes2 = Buffer.from(result2.labelsLittleEndianBase64, "base64");
  if (bytes2.byteLength !== pixels2 * 4 || bytes2.toString("base64") !== result2.labelsLittleEndianBase64 || pathologySha256(bytes2) !== result2.maskSha256)
    throw unavailable3(
      "Cell instance mask encoding or content integrity is invalid."
    );
  const view = new DataView(bytes2.buffer, bytes2.byteOffset, bytes2.byteLength);
  const labels = new Uint32Array(pixels2);
  const definitions = new Map(
    result2.instances.map((entry) => [entry.label, entry.nucleusSeedLabel])
  );
  if (definitions.size !== result2.instances.length || result2.instances.some(
    (entry) => entry.label !== entry.nucleusSeedLabel || entry.nucleusSeedLabel > result2.seedCount
  ))
    throw unavailable3(
      "Each estimated cell region must retain its distinct image-derived nucleus seed."
    );
  const seen = /* @__PURE__ */ new Set();
  execution.consume(pixels2);
  for (let index4 = 0; index4 < pixels2; index4 += 1) {
    labels[index4] = view.getUint32(index4 * 4, true);
    if (labels[index4] !== 0) {
      if (!definitions.has(labels[index4]))
        throw unavailable3(
          "A cell mask label lacks its image-derived seed record."
        );
      seen.add(labels[index4]);
    }
  }
  if (seen.size !== definitions.size)
    throw unavailable3("A cell instance record has no observed mask pixels.");
  const inputProvenance = {
    nuclei: {
      source: nuclei.source,
      rasterSha256: nuclei.rasterSha256,
      selectedChannelSha256: nuclei.selectedSha256,
      channelIndex: nuclei.channelIndex,
      plane: nuclei.plane,
      role: "nuclear-DNA"
    },
    cytoplasm: {
      source: cytoplasm.source,
      rasterSha256: cytoplasm.rasterSha256,
      selectedChannelSha256: cytoplasm.selectedSha256,
      channelIndex: cytoplasm.channelIndex,
      plane: cytoplasm.plane,
      role: "cytoplasm-or-cell-body"
    },
    registration,
    parameters
  };
  const id2 = pathologyJsonSha256({
    ...inputProvenance,
    methodVersion: "1",
    runtime: registry3.runtime
  });
  const instances = result2.instances.map((entry) => ({
    ...entry,
    id: `${cytoplasm.source.sourceId}:${id2}:estimated-cell-region:${entry.label}`,
    kind: "estimated-cell-region",
    identityStatus: "algorithm-estimate-not-verified",
    confidenceMeaning: "no-calibrated-probability-for-classical-watershed"
  }));
  const measured = await runPathologyRoiAnalysis({
    source: cytoplasm.source,
    raster: cytoplasm.raster,
    operation: {
      kind: "measure-objects",
      objects: {
        format: "label-mask",
        labels,
        definitions: instances.map((entry) => ({
          id: entry.id,
          label: entry.label,
          declaredEntityKind: "estimated-cell-region"
        }))
      }
    },
    signal,
    onProgress,
    limits
  });
  execution.check();
  return {
    kind: "cell-watershed-segmentation",
    researchOnly: true,
    mask: { width: nuclei.raster.width, height: nuclei.raster.height, labels },
    instances,
    featureTable: measured.featureTable,
    provenance: {
      source: cytoplasm.source,
      rasterSha256: cytoplasm.rasterSha256,
      maskSha256: result2.maskSha256,
      method: "DNA-seeded-cytoplasm-gradient-watershed",
      methodVersion: "1",
      runtime: result2.runtime,
      ...inputProvenance,
      thresholdsUsed: result2.thresholdsUsed,
      seedCount: result2.seedCount,
      preprocessing: "selected-RGB8-code-values-divided-by-255-no-raw-intensity-or-stain-calibration",
      warnings: [
        "Research-only estimated fluorescence cell regions. Not verified biological cells, H&E cell segmentation, diagnoses, or equivalence to Cellpose.",
        "DNA and cytoplasm channel roles and same-pixel-grid registration are explicit acquisition/user declarations, not independently established by image color or matching dimensions.",
        "Nucleus seeds are derived from the supplied DNA image using thresholding and distance peaks; no manual reference masks or labels enter inference.",
        "Cell boundaries follow the supplied cytoplasm gradient within image-derived foreground; touching nuclei, multinucleate cells, weak actin signal and channel misregistration can split or merge cells.",
        "Thresholds operate on selected RGB8 display code values divided by 255, including the recorded display contrast/gamma; these are not raw fluorescence intensity measurements.",
        "Cell areas/perimeters use raster pixel cells in the cytoplasm source frame; ROI-edge regions are retained and flagged. No full-slide stitching or Z/T projection is performed."
      ]
    }
  };
}
function copyChannel(input, execution) {
  const { source: source2, raster } = copyPathologyImage(
    input.source,
    input.raster,
    execution,
    262144
  );
  if (raster.width > 512 || raster.height > 512)
    throw exhausted3(
      "Cell watershed channels are limited to 512 by 512 raster pixels."
    );
  if (![0, 1, 2].includes(input.channelIndex))
    throw invalid5(
      "Select the explicit DNA or cytoplasm component of the supplied RGB8 raster."
    );
  if (!Number.isSafeInteger(input.plane.level) || input.plane.level < 0)
    throw invalid5("Cell source levels must be nonnegative integers.");
  const parsedSelection = input.plane.selection === null ? null : microscopySelectionSchema.safeParse(input.plane.selection);
  if (parsedSelection != null && !parsedSelection.success)
    throw invalid5("Cell source acquisition selection is invalid.");
  const selection = parsedSelection?.data ?? null;
  if (selection?.projection != null)
    throw invalid5(
      "Cell watershed requires single Z/T source planes, not projections."
    );
  const plane2 = { level: input.plane.level, selection };
  const selected = new Uint8Array(raster.width * raster.height);
  execution.consume(selected.length);
  for (let index4 = 0; index4 < selected.length; index4 += 1)
    selected[index4] = raster.rgb[index4 * 3 + input.channelIndex];
  return {
    source: source2,
    raster,
    plane: plane2,
    channelIndex: input.channelIndex,
    selected,
    selectedSha256: pathologySha256(selected),
    rasterSha256: pathologySha256(raster.rgb)
  };
}
async function readCellRegistry(runtime) {
  try {
    await access3(runtime.pythonExecutable);
    await access3(runtime.workerPath);
    const file2 = path13.join(
      path13.dirname(runtime.workerPath),
      "cell-watershed-registry.json"
    );
    if ((await stat5(file2)).size > 16384) throw new Error("Registry too large");
    const bytes2 = await readFile3(file2);
    if (bytes2.byteLength > 16384) throw new Error("Registry changed size");
    return external_exports3.object({
      schemaVersion: external_exports3.literal(1),
      id: external_exports3.literal("DNA-seeded-cytoplasm-gradient-watershed"),
      methodVersion: external_exports3.literal("1"),
      license: external_exports3.string(),
      runtime: external_exports3.record(external_exports3.string().min(1).max(64), external_exports3.string().min(1).max(64)),
      reference: external_exports3.string(),
      noPretrainedWeights: external_exports3.literal(true),
      output: external_exports3.literal(
        "estimated-fluorescence-cell-regions-not-verified-cells"
      )
    }).strict().parse(JSON.parse(bytes2.toString("utf8")));
  } catch {
    throw unavailable3(
      "The optional registered-channel CPU watershed runtime is not explicitly provisioned; no packages or models are installed by this job."
    );
  }
}
function invalid5(message) {
  return new PathologyAnalysisError("INVALID_ARGUMENT", message);
}
function exhausted3(message) {
  return new PathologyAnalysisError("RESOURCE_EXHAUSTED", message);
}
function unavailable3(message) {
  return new PathologyAnalysisError("RUNTIME_UNAVAILABLE", message);
}
export { runPathologyCellWatershed };
