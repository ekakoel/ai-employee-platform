# Documentation Governance

## Purpose

The project is expected to evolve for years. Documentation must remain usable by a future developer who has never seen the original conversations.

## Source hierarchy

1. Current source code.
2. Automated tests.
3. Architecture documents.
4. Product blueprint.
5. Roadmap.
6. Historical handoffs.

Historical handoffs explain history but do not override current verified behavior.

## Required documentation updates

When a developer changes:

### Architecture

Update:

- architecture blueprint;
- relevant domain model;
- ADR if a significant decision is made.

### Product behavior

Update:

- product blueprint;
- acceptance criteria.

### Security

Update:

- security/test document;
- relevant policy/permission specification.

### Roadmap

Only update completion after implementation + tests.

## Suggested additional document: ADR

For major decisions use:

```text
docs/adr/ADR-XXXX-title.md
```

Structure:

```text
# ADR-XXXX — Title

Status:
Date:

Context:

Decision:

Alternatives considered:

Consequences:

Security impact:

Migration:

Tests:
```

## Handoff requirements

Every significant development session should leave:

- current state;
- completed work;
- tests;
- known warnings;
- exact next step;
- important constraints.

Do not create a handoff that claims work is incomplete when the latest verified repository state has already completed it.
