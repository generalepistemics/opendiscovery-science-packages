# Result presentation handoff

Biohub ESM should finish with something the user can inspect immediately, while keeping checksummed scientific artifacts authoritative.

## Default completion

- ESMFold2: choose the viewer by the requested input using the rules below.
- For one unmodified protein sequence within the Biohub MCP input limits, call `ui_show_protein_structure` first.
- For multi-chain complexes, modified residues, ligands, DNA/RNA, structures outside those limits, or an explicit request to view the exact prediction file, use the separately installed OpenDiscovery Structure Viewer.
- Do not send an unsupported complex to the MCP app, concatenate chains, remove modifications, or show the receptor alone in its place.
- A missing MCP connection, denied approval, timeout, server error, or unavailable PNG preview is an operational failure, not an unsupported structure.
- Report that failure without switching viewers or repeating inference.
- `sequence_too_long_to_fold` establishes an unsupported length for that sequence on an Atlas miss; do not retry or truncate it.
- If the exact structure artifact already exists, it can use the OpenDiscovery Structure Viewer; otherwise report the limit without starting another fold.
- For that viewer, consume the emitted `presentation-request.json` and open its verified absolute PDB/mmCIF path once with the retained `openIntentId`.
- Verify the primary object and request predicted-confidence coloring only after the viewer is ready.
- Label serialized pLDDT as predicted confidence, not experimental temperature factors.
- The OpenDiscovery Structure Viewer is a separate host capability, not bundled with Biohub ESM.
- Discover its file-opening capability before declaring it unavailable; do not invent tool names, installation commands, or a successful open.
- If it is unavailable for an unsupported structure or exact prediction file, use the rendered-image fallback below and preserve the original presentation request.
- Do not ask whether to open a supported result.
- ESM Atlas: does not use this handoff. The Biohub MCP's `ui_show_protein_structure` result carries its own viewer and preview, as `$esm-atlas` describes.
- ESMC: display the deterministic `mutation-score.svg` artifact inline after a successful substitution score. Its labels must describe model likelihood in one masked context and must not imply biological fitness, stability, activity, binding, or function.
- ESMC structure results, including the PETase landscape and the ATP-synthase feature map, use only the Biohub MCP view, as `$esmc` describes. They never use this handoff.
- Every skill: when a protein's structure helps the answer, show it with the Biohub MCP as [Show a protein with the Biohub MCP](#show-a-protein-with-the-biohub-mcp) describes.

Visual presentation is best-effort and never replaces the raw result, normalized result, confidence metrics, or provenance.
- Render only the actual saved coordinates; never invent molecular geometry or silently repair it.
- Do not create a replacement viewer for a supported sequence request or a failed Biohub MCP view.

Identify the OpenDiscovery Structure Viewer by its file-opening capability; host tool prefixes can differ. A pending viewer and an unavailable viewer are distinct presentation outcomes; neither changes whether inference and artifact creation succeeded. If presentation is blocked, retain the intent, return the verified absolute artifact path, and report confidence values (pLDDT, pAE, pTM, iPTM) as text. The same independence applies to inline images.

## Rendered-image fallback

- As a last resort, the agent may generate and display a rendering image from the saved PDB/mmCIF when the structure is unsupported by the Biohub MCP app and the OpenDiscovery Structure Viewer is unavailable.
- This permission also covers requests for an exact prediction file, which the sequence-only MCP app cannot display.
- Render the exact verified coordinates using an available molecular rendering tool or library; no new interactive viewer or bundled rendering feature is required.
- Preserve every chain, modified residue, and ligand; do not substitute coordinates, silently repair geometry, or repeat inference.
- Keep chemistry warnings and confidence-mapping limitations visible in the answer.
- Use confidence coloring only when its mapping and scale are verified; otherwise use chain colors.
- Inspect the resulting image before claiming it is shown, and label it as a static rendering of the prediction.
- Keep the image separate from the authoritative prediction artifacts and return the verified coordinate path alongside it.
- If rendering or display is unavailable, report that limitation and return the saved artifacts.
- Supported sequence requests and MCP operational failures do not use this fallback.

## Semantic presentation contract

The producer status `pending-delivery` is not a viewer readiness state. It means
the retained intent has not yet been acknowledged by a renderer: deliver it once
using its exact `openIntentId`. Only after that initial open may a viewer report
`pending` while it mounts; do not skip delivery or treat `pending-delivery` as an
already-open session.

1. For `managed-post` or `managed-recover`, load and validate the exact emitted `presentation-request.json`. Use its absolute artifact path, checksum, requested view, and exact retained `openIntentId`; never replace that ID. Prefer mmCIF for all-atom output and PDB for sequence-only `/fold`, and do not inline coordinate bytes merely to open it.
2. Open once with the retained ID. Reuse it only for delivery retry. Generate one new stable `openIntentId` only for a legacy artifact set that lacks `presentation-request.json`.
3. Retain the returned viewer session only within the same task. Never infer or reuse a session identifier across tasks.
4. Respect reported readiness. While pending, retain the request and report `viewer pending`; do not reopen as polling, style, or use renderer-backed state as a startup probe. Continue only on a supported readiness signal. Once ready, use the viewer's listing capability to verify the primary object before requesting style.
5. If a mutation times out, treat its commit state as unknown. Inspect acknowledged state before retrying or issuing a different mutation; never retry blindly.

Report `structure available`, confidence completeness, and viewer status separately. Do not claim visible coloring from a file path, an issued request, or an unacknowledged mutation.

## Current `structure.*` adapter mapping

These names are the current host implementation, not a plugin requirement:

- Open: call `structure.open_from_chat` with the verified absolute path and exact `openIntentId` from `presentation-request.json`; retain returned `viewerSessionId` for this task.
- Verify: once ready, pass that value as `sessionId` to `structure.list_structures` and verify the primary object.
- Predicted confidence: once ready and verified, call `structure.control_viewer` with `action: set_color` and `color: bfactor`. Here `bfactor` means serialized pLDDT confidence, not experimental displacement.
- Timed-out mutation reconciliation only: call `structure.get_state` with the same `sessionId`; do not use it as the initial readiness probe.

## Compare generated structures

- Call `structure.add_structure` for each additional Atlas PDB using a stable object ID such as `atlas_hit_1`, representation `cartoon`, an explicit color, and the exact absolute local path.
- When Biohub already emitted `hit-N-aligned.pdb`, load that artifact directly. Do not align it again: report the recorded global-sequence plus unique chain/residue-bound ATOM C-alpha Kabsch RMSD and aligned-position count from `workflow-summary.json`.
- If the user instead asks to recompute from a raw Atlas PDB, call `structure.align_structures` with explicit primary/mobile object IDs and label the viewer's method and returned RMSD/count separately. Never replace or conflate it with the Biohub pipeline metric.
- For a reproducible live scene after readiness, read `structure.get_state`, use its current revision for `structure.apply_scene`, and target the named objects. When workspace publication is available, call `structure.render_image` with the viewer's source-relative destination contract: base `opened-source`, kind `workspace`, collision policy `exact`, a safe relative PNG path, matching `outputPath`, and `overwrite: false`. Preserve the PNG and viewer-owned `.render.json` provenance checksums.

## Show a protein with the Biohub MCP

Every Biohub ESM skill can show a protein's 3D structure with the public Biohub MCP tool `ui_show_protein_structure`.
It uses the connected MCP account and does not require an additional inference API key. It writes no local structure file; the host must support the returned MCP App.
Hosts that render MCP Apps show the interactive Mol* viewer, and every host gets a PNG preview when rendering succeeds.
Match the logical tool name in the connected catalog, because a host can add a server prefix.
Use the tool whose schema takes `sequence`; another Biohub server can expose a tool with the same name that takes only a saved `structure_id`.

### When each skill shows a structure

| Skill | Show the protein |
| --- | --- |
| `esm-atlas` | For every structure view, and for the top-ranked hit of a similarity search, as `$esm-atlas` describes |
| `esmc` | After an analysis of one protein that singles out residues, with those residues highlighted; it is the only structure presentation for the PETase landscape and the ATP-synthase feature map, as `$esmc` describes |
| `esmfold2` | First for a supported unmodified protein sequence; unsupported structures and exact prediction files use the OpenDiscovery Structure Viewer |
| `biohub-esm` | For a request to see a protein's ESM Atlas structure or Biohub MCP view, through `$esm-atlas`; a plain request to show a protein's 3D structure goes to `$esmfold2`, except a follow-up for a protein that `$esmc` analyzed in this conversation, which stays with `$esmc` |
| `biohub-esm-setup` | Never; it checks that the Biohub MCP is connected |

### Call it

Call it once for each protein with one exact protein sequence of 1 to 4,000 residues.

- It returns stored ESM Atlas coordinates at any supported length, and folds a miss of up to 700 residues.
  On `sequence_too_long_to_fold`, state the 700-residue fold limit with the returned `actual_length`, and ask for a domain of at most 700 residues.
  Never clip the sequence, and never retry it.
- It takes one protein chain.
  DNA, RNA, ligands, modified residues, and multi-chain complexes go to the handoff above.
- The view fails when the tool is not in the catalog, when it returns an error code, or when `preview_status` is not `available`.
  Report operational failures without switching viewers.
  A returned `sequence_too_long_to_fold` may route an existing verified artifact to the OpenDiscovery Structure Viewer, as the default completion rules describe.
- Pass `view_options` only for what the answer needs: `color_by: confidence` for pLDDT, `representation` for `cartoon` or `surface`, and up to 32 `highlights`.
- A highlight addresses chain `A` and a residue number from 1 to N of the exact sequence passed.
  Convert other numbering, such as PDB author numbering or a zero-based tensor index, to that position first.
  Set `expected_residue` on every highlight to the three-letter code of the residue at that position, such as `TRP`.
- If the call returns `invalid_input` because a highlighted residue identity does not match the structure, the numbering is wrong.
  Correct the mapping one time, and never remove `expected_residue` to make the call pass.
- If the analysis singles out more than 32 residues, highlight the 32 that it ranks highest, and state how many it left out.
  Give each group of residues its own `color` when the answer compares groups.
- The view draws chain `A` in blue, so do not use blue highlight colors.
  Use `#D55E00`, `#009E73`, and `#CC79A7`, in that order, unless a skill names other colors.

### Read the result

- The result carries the PNG preview and a `descriptor` with the coordinate filename, its SHA-256, and its `source`.
- Look at the preview before you make a structural judgment, and describe what it shows in words.
  If `preview_status` is not `available`, say that visual inspection is unresolved.
- Never say that a structure is shown above, write viewer code, draw your own image of the structure, or hand the result to a different viewer.
- Name the coordinates from `descriptor.source`: a stored Atlas prediction, or an on-demand fold when `folded_on_miss` is `true`.
  When `source.model` is `null`, do not name a folding model.
- The coordinates are a model hypothesis.
  They are not the ESMFold2 prediction that this plugin wrote, and they are not an experimental structure such as PDB 2XND.
  Report ESMFold2 confidence values only from the ESMFold2 artifacts.
- The view is response-local and has no saved ID or URL.
  A separate call can compute again, so do not call it again to refresh or poll.
  A user's request to see the structure again is not a refresh: call it once more with the same sequence and `view_options`.
  Camera and selection gestures inside the viewer do not call the server.

### Cost, limits, and failures

- The call is a public Biohub MCP read, not a managed request.
  It uses no `ESM_API_KEY` credits and needs no spend confirmation, but it obeys a planning-only or no-network request.
- When a workflow discloses its calls before it runs, include this call in that list.
  Pinned starter and tutorial call lists, request counts, and exact qualification lines cover only their pinned calls, so add this call only where the pinned contract names it.
  The GB1 fold, the GB1 similarity search, the PETase landscape, and the ATP-synthase feature map name it.
  For the other pinned workflows, name the view only in the answer's source line.
- Name `ui_show_protein_structure` in the answer's source line.
- If the tool is not in the catalog, say that the Biohub MCP is not connected, and point to `$biohub-esm-setup`.
- On `rate_limited`, wait as the error advises before one retry.
  On `indeterminate`, never retry automatically.
  For every other code, name the tool and the code.
- A failed or unavailable view never changes the success of the analysis or of its artifacts.

## Point back to the source

Close a successful result with one link to the model or dataset behind it, so the user
can read what produced the answer. Use the exact page for what ran:

- ESMC results: <https://biohub.ai/models/esmc>
- ESMFold2 results: <https://biohub.ai/models/esmfold2>
- Atlas results: <https://biohub.ai/esm/protein/atlas>
- General ESM models and data: <https://biohub.ai/esm/protein>

One link, after the science, not before it. Do not stack all four, and do not turn this
into a marketing line.

## Evidence labels

- ESMFold2 coordinates are static model hypotheses.
- Atlas PDB formatting does not make a structure experimental. Treat Atlas coordinates as model hypotheses unless an authoritative source explicitly proves an experimentally determined structure and records that provenance.
- The combined demonstration contains no experimental structure. Keep query pLDDT/pTM, Atlas pLDDT/pTM, similarity, alignment method/RMSD/count, model IDs, accessions, source metadata, timestamps, and checksums in Biohub JSON. Viewer annotations are only a bounded visual summary, not the authoritative record.

The Structure Viewer does not ingest arbitrary Biohub JSON sidecars. The model must preserve `workflow-summary.json` and `provenance.json` alongside the coordinate artifacts and use their metrics when answering.
