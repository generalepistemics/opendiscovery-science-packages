---
name: runpod-mcp
description: >-
  Manage Runpod infrastructure — pods, serverless endpoints, jobs, templates,
  network volumes, container-registry auth, GPU/CPU catalog, and billing — via
  the Runpod MCP server's structured tool calls. Use when the Runpod MCP tools
  (create-pod, list-endpoints, …) are connected in this session, or to connect
  them (hosted OAuth or local npx). Prefer this over runpodctl for plain infra
  CRUD when MCP is available; use runpodctl for the terminal, file transfer, or
  SSH setup.
compatibility: Linux, macOS, Windows
metadata:
  author: runpod
  version: "1.1.2" # x-release-please-version
license: Apache-2.0
---

# Runpod MCP

The Runpod MCP server exposes Runpod's control plane as structured tool calls,
so an MCP-capable agent can manage infrastructure without shelling out. It is the
same Runpod REST API that `runpodctl` uses — pick MCP when its tools are
connected (typed params, structured errors, no shell quoting).

## Connect

Install Runpod once through Discover. Its hosted MCP endpoint is `https://mcp.runpod.io/`; sign in through the existing MCP servers controls when requested. The same installation provides the companion workflow skills. Check the connected tool list before relying on any operation; service versions and supported parameters can change.

OAuth connects the MCP service only. `runpodctl`, Flash and direct API workflows require their own supported `RUNPOD_API_KEY` setup. Do not copy OAuth tokens to a CLI or assume one connection authenticates everything. If the user explicitly selects API-key MCP authentication, configure the Authorization header through MCP settings without putting the value into chat, command arguments or source.

Use Settings → Extensions → MCP servers to reconnect and inspect status. Discover the actual server tools/schema before creating resources, and obtain approval for the requested cost and target. A connected server is not authorization to provision a pod or start a job.

## Tool surface

Structured tools, grouped by resource:

- **Pods** — list, get, create, update, start, stop, restart, delete, stream logs.
- **Serverless endpoints** — list, get, create, update, delete; list workers; list releases; stream worker logs.
  - `create-endpoint` takes `endpointType: QUEUE` (default) or `LOAD_BALANCER` — see golden path 14. The routing type is fixed at creation; `update-endpoint` cannot change it.
  - Read an endpoint's invoke URLs from `requestUrls` on the get/list reply instead of assembling them.
  - To pin a specific GPU **SKU** on an existing endpoint use `set-endpoint-gpus`; `create-endpoint`/`update-endpoint` expose only `gpuPoolIds` and can't express a SKU (`deploy-hub-repo` can pin one at deploy time via `gpuIds` exclusions).
- **Jobs (serverless runtime)** — run, runsync, status, stream, cancel, retry, health, purge queue.
- **Hub** — `list-hub-repos` (public catalog of prebuilt Serverless workers and Pod templates: vLLM, ComfyUI, …) and `deploy-hub-repo`, which deploys a repo's listed release as an endpoint — the same as clicking Deploy on the Hub.
- **Public endpoints** — `list-public-endpoints`: managed pay-per-use model APIs (text/image/video/audio) that need no deployment. Call the returned endpointId with `run-endpoint`/`runsync-endpoint`.
- **Templates** — list, get, create, update, delete.
- **Network volumes** — list, get, create, update, delete. `create-network-volume` takes `volumeType` (`STANDARD` | `HIGH_PERFORMANCE`) and a size of 10–4096 GB; omit `volumeType` to get the data center's default tier. The tier is **immutable after creation** — `update-network-volume` can't change it.
- **Container registry auth** — list, get, create, delete. A username + password for **any** registry; pass the resulting id as `containerRegistryAuthId` on create-pod/create-endpoint.
- **ECR delegations** (`list-`/`create-`/`delete-registry-delegation`) — **AWS ECR only**, v2 only, and stores no credentials: you register a repository ARN and Runpod gets scoped pull access instead. Prefer it over a stored username/password for ECR. The reply carries a `dockerRegistryUri` — that's the image URI to deploy with.
- **Catalog** — list/get GPU types, list/get CPU types, list/get data centers.
- **Billing** — scoped usage/cost breakdowns (`get-billing`).

> The tool list above is a map, not a contract. The server is the source of truth —
> `/mcp` (or your client's tool list) shows exactly what the connected version exposes,
> and each tool carries its own parameter descriptions. Check there before assuming a
> capability exists or doesn't.

> Delete tools (`delete-template`, `delete-pod`, …) can return `isError: true` with
> "Unexpected end of JSON input" **even on success** — the Runpod REST API returns
> 204 No Content. Don't treat it as failure; confirm with a follow-up `get-`/`list-`
> (a deleted resource then 404s).

## Use MCP vs runpodctl

- **Use runpod-mcp** when the tools are connected AND the task is infra CRUD or a
  serverless job call the server exposes. Cap large job/log output to a file.
- **Use runpodctl instead** for: **`send`/`receive`** file transfer, **SSH** key
  management, **`doctor`** setup, **model cache** — or any shell-only agent, or
  when the user wants a reproducible command.
- **Hand pod creation to runpodctl** for a **multi-GPU priority list** (MCP's v2
  create-pod takes one GPU type; extra `gpuTypeIds` are dropped with a `_warning`
  on success), or for a **template + CPU** pod together — `create-pod` rejects that
  combination, since a template deploy is GPU-and-v2-only. Each alone is fine in
  MCP: `templateId` (v2-only, `imageName` then optional, and each field you pass
  replaces the template's whole value rather than merging) or `computeType: "CPU"`.
- **Not this lane:** writing/deploying your own Python (→ flash); downloading
  models or building/pushing images (→ companion-clis).

For concepts (pods vs serverless, GPU selection, storage), read
`../runpod-usage/`.

## Source & docs

- Server source: https://github.com/runpod/runpod-mcp
- Package (npm): https://www.npmjs.com/package/@runpod/mcp-server
- Hosted endpoint: https://mcp.runpod.io/
- Docs: https://docs.runpod.io
