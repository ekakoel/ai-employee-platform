# Knowledge Source Access Control

## Security contract

Knowledge retrieval is deny-by-default. A knowledge item or document is retrievable only when all of the following are true:

1. The task or request has a persisted, active requester in the same company.
2. An active source policy exists for the exact company, source type and source ID.
3. The policy is approved, has an owner, review timestamp, approval reference and unexpired validity.
4. The source classification is A, B or C. D and U are never retrieved.
5. The requested purpose is explicitly listed in the policy.
6. B/C policies grant the persisted user, role or department.
7. The current source content hash matches the hash approved by the owner.
8. The source is active; documents must also be READY.
9. The source is in the same company and within the agent's allowed scope.

Missing requester identity, policy, owner/review evidence, approval reference, purpose grant or matching source hash means DENY. No source is admitted automatically during migration.

## Classification

| Class | Meaning | Retrieval |
|---|---|---|
| A | Approved public corpus | Purpose-bound; owner approval and source hash required |
| B | Internal company knowledge | Explicit user/role/department grant and purpose |
| C | Restricted business/personal data | Explicit grant and purpose; use narrow grants |
| D | Secrets/credentials | Never indexed or retrieved |
| U | Unknown/unreviewed | Deny until reviewed and reclassified |

## Owner admission API

PUT /api/v1/companies/{company_id}/knowledge/sources/{source_type}/{source_id}/policy

Only the company owner can approve or change a source policy. Supported source types: item, document.

Example request:

~~~json
{
  "classification": "B",
  "allowed_user_ids": ["<same-company-user-id>"],
  "allowed_role_ids": [],
  "allowed_department_ids": [],
  "allowed_purposes": ["task_execution", "interactive_knowledge_search"],
  "approval_ref": "KB-REVIEW-2026-001",
  "source_version": "1.0",
  "is_active": true
}
~~~

The server calculates the SHA-256 content hash; clients cannot supply or override it. Documents must be READY before admission. User and department grants are checked against the same company; role IDs must exist. B/C sources require at least one explicit identity grant.

Revocation:

DELETE /api/v1/companies/{company_id}/knowledge/sources/{source_type}/{source_id}/policy

Revocation is immediate because retrieval checks policy state and content hash on every request. Re-approval after source content changes is mandatory.

## Runtime propagation

- Task creation stores the authenticated requester in tasks.requested_by_user_id.
- Agent context and tool context receive only that persisted identity.
- search_knowledge_chunks, search_knowledge_items, SearchKnowledge, SearchContract, ReadDocument and pricing lookup enforce the source policy.
- Search SQL is constrained to authorized source IDs before chunk contents are loaded.
- Retrieval audit events record requester, purpose, source count and outcome, never query text or passage contents.
- Duplicate normalized passages are suppressed within the same source. Distinct source provenance is retained.
- AgentMemory and Experience are withheld from model context until equivalent source ACL and classification controls are implemented.

## Migration and rollout

Run Alembic migration 0006_knowledge_source_policies on a disposable database first, then validate against PostgreSQL before production rollout. Existing tasks keep a NULL requester and therefore cannot retrieve knowledge until recreated or safely backfilled from a trusted audit trail. Existing sources receive no policy rows and remain denied.

Do not bulk-admit the Knowledge Hub. Classify and approve source-by-source with owner, purpose and audience review. Keep the general-agent allowlist empty until the negative security tests and PostgreSQL migration checks pass.
