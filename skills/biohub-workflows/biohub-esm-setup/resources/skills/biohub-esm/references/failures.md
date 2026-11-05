# Reliability and failure handling

## Normalized failure classes

| Failure | Response |
| --- | --- |
| missing credentials | stop only the credentialed route; continue public/mocked work |
| `401` | report authentication failure without echoing the response or header |
| `500`, empty body, managed call | usually a rejected key; the API returns this instead of `401`. Suggest re-checking the key before reporting an outage |
| `402` / credit denial | direct to https://biohub.ai/developer-console; do not invent quotas |
| `403` / safety restriction | do not work around; direct legitimate research to documented review |
| `408` / timeout | preserve job state and partial files; retry only a proven-idempotent public read, setup, or control-plane action, or a response proven not to have accepted the request |
| `429` | honor `Retry-After`, lower concurrency, and resume later |
| `5xx` | retain durable IDs, status, retry metadata, and a bounded redacted provider message when available; retry only when the operation is proven idempotent or non-acceptance is proven |
| malformed JSON / missing fields | classify as schema drift; keep raw response |
| partial batch output | checksum completed artifacts, identify missing items, resume only those |
| expired async job | retain the terminal state and resubmit only after checking idempotency |

A timeout or provider failure during paid managed ESMC or ESMFold2 inference can have consumed work or credits even when no complete response arrived. If acceptance is uncertain, record the call as indeterminate, preserve its exact request and partial evidence, and reconcile provider state without replaying it. Bounded retry applies only to a documented or otherwise proven-idempotent public read, setup, or control-plane action, or to a definitive response that proves the request was not accepted.

## Durable execution

- Atlas batch jobs: persist `job_id`, status counts, and timestamps. Keep signed download URLs in memory only and reacquire them by polling after a resume. If submission acceptance is indeterminate and no `job_id` was durably captured, do not resubmit automatically; preserve the request digest and reconcile manually. Definitive non-accepting HTTP responses use a separate retry-safe `submission-rejected` state; remediate the error, then retry only the identical request from a new invocation and never before the persisted `Retry-After` deadline. The state file is authoritative if a crash leaves its separate provenance sidecar stale; the next batch command repairs the sidecar.
- Modal jobs: use the pinned SDK and deployed Function version recorded in state, and persist each validated `FunctionCall` ID immediately after spawn. An empty/invalid returned ID or interrupted spawn is submission-indeterminate, not retry-safe. Gather can produce completed and failed results together. Cancellation is best effort; preserve late results if the provider already completed them. Artifact records in a returned envelope are provider declarations until their bytes are separately retrieved and checksum-verified.
- Downloads: write `.partial`, use HTTPS `Range` resume when supported, and atomically rename only after completion. Always compute SHA-256.

Never use an agent's manual reasoning loop as a background-job poller. Launch a bounded CLI poller or use durable provider job state, then check on an explicit cadence.
