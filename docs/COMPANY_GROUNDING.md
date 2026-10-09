# Company-Grounded Execution

## Trust Boundary

Authenticated API requests resolve the company and employee on the server.
Employee access is required for conversation reads/writes and direct task
execution. Internal tasks use the same tenant-bound context loader and runtime.
Inactive employees/subscriptions, task/employee mismatches, and out-of-scope
instructions are rejected before execution. Client scope flags cannot disable
the check. Scope matching is conservative and lexical, not a semantic proof;
the explicit tool allow-list and policy remain the execution authority.

Workflow, automation, and delegation consultation use that same service. Human
actors must have access to the selected employee. Delegation scope is checked
against the original instruction, not a capability label prepended to it.
Failed/cancelled child tasks cannot become successful orchestration results.

The boundary remains:

`AgentContext -> ToolRegistry -> ToolExecutor -> PolicyEngine -> ApprovalService -> Tool Execution`

The effective tool list uses explicit employee configuration/snapshots. Formal
skills further restrict that list; a skill cannot grant an otherwise unavailable
tool. Catalog tools are not an implicit grant. Formal skill instructions,
workflows, and required-knowledge metadata are included in the reasoning context.

## Grounding

Context includes active shared company knowledge and knowledge assigned to this
employee, relevant chunks, active memories, and validated experiences. Chunk
retrieval also checks parent ownership, employee access, and item active status.
Documents, memories, experiences, and tool results are untrusted data, not
instructions overriding policy. Memories and experiences are supplementary,
not authoritative pricing or inventory.

Business answers use an extractive response protocol:

```json
{"citations":[{"source_id":"knowledge:RECORD_ID","quote":"Exact company source excerpt"}]}
```

The server validates each ID against retrieved authorized sources and checks
that each excerpt occurs verbatim. Unsupported model prose is not displayed or
saved as verified output. This deliberately limits free-form synthesis. Citation
validation proves provenance, not the truth or completeness of company records;
companies remain responsible for maintaining authoritative records.

Small social exchanges use bounded templates. Missing sources or invalid
citations produce a clarification, not a fabricated answer. Chat remains
advisory: it can create a linked pending task, but cannot silently execute tools.
Work-result links refer only to completed, nonempty, persisted task results.
No new automatic production LLM execution path is enabled.

## Business Tools

Availability comes from the configured company connector's `availability`
records, filtered and rechecked by company and dates. There is no hard-coded
inventory or price fallback. The default mock is empty until explicitly loaded.
Bookings require a matching availability ID, verified rate/currency, and guest
and dates supplied in the task instruction. Reservation reads are tenant-bound.

Quotation pricing uses active accessible `KnowledgeItem` records with category
`pricing` and structured content, for example:

```json
{
  "prices": [
    {
      "sku": "bali-3-day",
      "description": "3-day Bali tour",
      "amount": "300.00",
      "currency": "USD",
      "unit": "guest"
    }
  ]
}
```

A quotation item references `price_id: "KNOWLEDGE_ITEM_ID:bali-3-day"` and an
integer quantity. The customer must appear in the task instruction. The tool
calculates totals with Decimal and rejects supplied amounts/currencies that
disagree with the source. Guest-unit quantities must match the requested guest
count. Derived totals are validated before policy evaluation, preventing a
model from hiding the actual amount from amount-based approval rules.

An administrator must explicitly authorize `draft_quotation` in the employee's
tool list, assigned skill, and policy. Existing employees are not silently
granted new capabilities or given invented business records.

## Policy, Approval, and Persistence

Unmatched policies deny by default; unknown tools never execute. Unknown
condition keys cannot match an allow rule. Tool risk/action metadata comes from
the registered tool, not model arguments. Side effects require a task.
An applicable company rule whose conditions do not match cannot fall back to an
employee snapshot allow. Department metadata is resolved from company records.

Pending and rejected approvals cannot execute. Approved execution accepts only
the stored payload, revalidates current access/policy/data, and atomically claims
the approval. Replays are blocked. An interrupted approval remains `executing`
and requires operator reconciliation rather than automatic retry. External
connectors still need their own idempotency and inventory-reservation guarantees.

LLM tasks atomically claim pending status, persist validated excerpts or actual
tool outputs, and only then commit completion. Provider, context, execution,
serialization, and persistence errors cannot produce a successful completed
record. Tool audits retain actual results and source references; approval and
task transitions retain actor/time through the existing audit model.

The Output Center reads `Task.result`, previews the persisted quotation text,
offers a text download, and keeps source/execution metadata expandable. It never
constructs a document from transient model prose or status alone. Approved
quotation execution stores the same structured output format.

## Tests

`tests/test_company_grounding.py` covers source/skill context, source validation,
missing information, active/scope/access checks, real quotation persistence,
LLM failure/reexecution, approval states/replay, and tenant-bound business reads.
Workspace tests cover persisted previews and chat attribution/result links.

Disposable `test_*.db` SQLite fixtures disable synchronous disk flushes for test
speed only. Production databases retain their normal durability settings.
External Ollama integration tests remain opt-in with `RUN_OLLAMA_TESTS=1`.
