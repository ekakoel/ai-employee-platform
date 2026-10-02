# Architecture MVP 0.1

## Domain

Agent Catalog = produk/template AI Employee yang disediakan platform.

Agent Instance = AI Employee yang telah di-hire oleh satu Company.

Company Knowledge = informasi milik Company, opsional di-scope ke Agent Instance.

Task = pekerjaan yang diberikan kepada Agent Instance.

## Boundary

Company A -> Agent Instance A -> hanya Task milik Company A.
Company B -> Agent Instance B -> hanya Task milik Company B.

Tidak boleh mengandalkan prompt untuk tenant isolation; enforcement dilakukan di service/API layer. Pada tahap PostgreSQL production, tenant isolation juga dapat diperkuat dengan Row-Level Security.

## Roadmap

MVP 0.1: domain slice lokal.
MVP 0.2: authentication, RBAC, PostgreSQL, migrations, audit.
MVP 0.3: file/document knowledge pipeline.
MVP 0.4: LLM runtime + tool permission.
MVP 0.5: approval + CRM integration.
MVP 0.6: frontend control center.
