# AI Employee Platform — Local MVP 0.1

Vertical slice awal untuk membuktikan model:

**Company → Agent Catalog → Hire Agent → Agent Instance → Knowledge → Task**

## Prinsip MVP

1. Company hanya dapat membuat Task menggunakan Agent Instance yang dimilikinya.
2. Agent Instance berasal dari Agent Catalog yang tersedia.
3. Skill dan allowed tools diwariskan dari Agent Catalog ke instance.
4. Knowledge dimiliki oleh Company dan dapat di-scope ke Agent Instance.
5. Knowledge dapat dibuat, dibaca, diubah, dan dihapus oleh API company-scoped.
6. Belum ada LLM, CRM, authentication, vector database, OCR, billing, atau background worker pada slice ini.

## Menjalankan di Windows PowerShell

```powershell
cd ai_employee_platform_v0_1
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn app.main:app --reload
```

Buka:
- API: http://127.0.0.1:8000
- Swagger: http://127.0.0.1:8000/docs
- Health: http://127.0.0.1:8000/health

## Test

```powershell
pytest -q
```

## Contoh alur API

1. `POST /api/v1/companies`
2. `GET /api/v1/agent-catalog`
3. `POST /api/v1/companies/{company_id}/agents/{catalog_agent_id}/hire`
4. `POST /api/v1/companies/{company_id}/knowledge`
5. `POST /api/v1/companies/{company_id}/tasks`

## Phase 0.3 yang sudah diimplementasikan

- Agent Subscription sebagai entitas terpisah dari Agent Catalog dan Agent Instance.
- Company dapat melihat subscription Agent yang dimilikinya.
- Subscription dapat dibatalkan oleh user berpermission `agent.hire`.
- Cancelled subscription otomatis menonaktifkan Agent Instance terkait.
- Agent inactive/cancelled tidak dapat menerima Task baru.
- Audit log untuk hiring dan cancellation.

## Next

- Authentication + user/company roles
- PostgreSQL + Alembic migrations
- File upload/object storage
- Document extraction
- Knowledge chunks + pgvector
- Policy/permission engine
- Task runtime
- LLM provider abstraction
- Approval workflow
- Audit log
- Frontend Company Control Center
