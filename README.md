# AI Employee Platform

[![CI](https://github.com/ekakoel/ai-employee-platform/actions/workflows/ci.yml/badge.svg)](https://github.com/ekakoel/ai-employee-platform/actions/workflows/ci.yml)


Workspace multi-company untuk kolaborasi manusia dan AI employee: agent catalog,
hiring, chat, knowledge, task execution, tools, policy, approval, dan audit.

```text
Company -> Hire Agent -> Agent Instance -> Knowledge / Chat -> Task
Task -> Runtime -> Tool / Policy / Approval -> Hasil dan Audit
```

Backend memakai Python/FastAPI/SQLAlchemy. Frontend memakai HTML/CSS/JavaScript.
SQLite tersedia untuk lokal dan PostgreSQL untuk deployment Compose. Runtime
memiliki provider Ollama dan worker automation terpisah.
Keberadaan fitur tidak berarti seluruh alur sudah terverifikasi atau siap produksi.

## Dokumentasi: Mulai di Sini

| Panduan | Isi |
| --- | --- |
| [Project Guide](docs/PROJECT_GUIDE.md) | Pemahaman produk, domain, arsitektur, peta kode, dan alur utama |
| [Development Guide](docs/DEVELOPMENT_GUIDE.md) | Setup, sandbox terpisah, konfigurasi, pengujian aman, dan aturan kerja |
| [Project Status](docs/PROJECT_STATUS.md) | Baseline keamanan, hasil tes terakhir, batasan, dan checklist pilot company |
| [Platform Access](docs/PLATFORM_ACCESS.md) | Login, onboarding, hak admin, dan kontrak akses P0 |
| [Master Index](docs/00_MASTER_INDEX.md) | Blueprint, roadmap, acceptance criteria, dan governance dokumentasi |

Panduan implementasi di atas dipetakan pada 2026-10-12. Source code dan tes
aktual mengungguli blueprint atau handoff historis jika terjadi perbedaan.

## Akses dan Onboarding

- Login menggunakan email/password melalui `/api/v1/auth/login`.
- Identitas API berasal dari Bearer token; `X-User-ID` bukan kredensial.
- Platform admin sah membuat company dan owner melalui `/api/v1/admin/companies`.
- Owner company bukan otomatis platform admin.
- Registrasi publik, token tanpa password, dan anonymous first-user bootstrap ditutup.
- Quick start anonim dan Connect IDs lama bukan jalur onboarding yang didukung.
- Database baru tidak otomatis memiliki platform admin yang sah. Bootstrap
  operator membutuhkan proses yang direview terpisah, bukan bypass development.

Halaman tersedia pada `/workspace`, `/developer`, `/forgot-password`, dan
`/reset-password`. Developer UI tidak menggantikan permission check backend.

## Menjalankan dengan Aman

Entrypoint yang benar adalah `app.main:app`, bukan `src.main`.
Baca [langkah sandbox development](docs/DEVELOPMENT_GUIDE.md#4-menjalankan-sandbox-development)
sebelum menjalankan Uvicorn.

**Startup dapat membuat tabel, menyesuaikan schema SQLite, dan menulis seed.**
Default database menunjuk `./ai_employee.db`. Jangan menjalankan aplikasi,
worker, Docker Compose, migration, atau full pytest terhadap data workspace
hanya untuk mencoba project.

## Verifikasi Frontend Tanpa Database

```powershell
node --check app/static/workspace/app.js
node --test tests/workspace_auth.test.cjs
git diff --check
```

Tes auth memakai mock dan tidak membuktikan browser E2E atau integrasi backend.
Validasi lanjutan: 30 tes auth frontend lulus dan seluruh 66 tes frontend lulus.
Detail dan batas bukti ada di [Project Status](docs/PROJECT_STATUS.md). Hasil
ini dieksekusi pada kelanjutan Phase 2D;
lihat [Auth Session Lifecycle](docs/AUTH_SESSION_LIFECYCLE.md) untuk batas bukti.

Untuk backend, baca isolasi fixture dan perintah suite P0 khusus dalam
[Development Guide](docs/DEVELOPMENT_GUIDE.md#7-tes-backend-p0-yang-terisolasi).
Jangan menganggap `pytest -q` atau collection seluruh tes aman untuk database.
