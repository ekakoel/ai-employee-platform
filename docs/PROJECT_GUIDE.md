# Panduan Project AI Employee Platform

Tanggal pemetaan: 2026-10-12. Panduan ini menjelaskan source code saat ini,
bukan janji bahwa seluruh fitur sudah lulus pengujian atau siap produksi.

## 1. Mulai membaca dari sini

1. Baca dokumen ini untuk memahami produk, domain, dan lokasi kode.
2. Baca [Development Guide](DEVELOPMENT_GUIDE.md) sebelum menjalankan aplikasi atau tes.
3. Baca [Project Status](PROJECT_STATUS.md) untuk baseline, bukti tes, dan batasan.
4. Baca [Platform Access](PLATFORM_ACCESS.md) untuk kontrak akses P0.
5. Gunakan [Master Index](00_MASTER_INDEX.md) untuk blueprint dan roadmap jangka panjang.

Source code menjelaskan perilaku yang diimplementasikan. Tes menjelaskan perilaku
yang benar-benar diverifikasi. Blueprint menjelaskan arah desain; keberadaan
fitur dalam roadmap tidak berarti fitur itu sudah selesai.

## 2. Apa yang dibangun

AI Employee Platform adalah workspace multi-company untuk menjalankan pekerjaan
dengan AI employee, sambil mempertahankan otoritas manusia melalui permission,
policy, approval, dan audit.

Alur inti:

```text
Platform admin -> provision company + owner
Company owner -> tambah anggota dan hire agent dari catalog
User -> chat / buat task untuk agent milik company
Task -> context -> executor -> tools -> policy / approval
Hasil -> workspace / inbox / result library / audit
```

Ini bukan sekadar antarmuka chat ke LLM. Tool execution, akses agent, batas
company, dan persetujuan tindakan merupakan bagian penting model bisnis.
Chat tidak otomatis berarti tindakan operasional sudah dijalankan; baca jalur
conversation dan task bridge untuk membedakan respons percakapan dari task.

Contoh domain yang sudah memiliki layanan dan data pendukung adalah reservation:
inventory, availability, quotation, dan demo playbook. Keberadaan demo tidak
mengizinkan provisioning publik atau melewati approval.

## 3. Stack dan komponen

| Komponen | Implementasi saat ini |
| --- | --- |
| API | Python, FastAPI, Pydantic |
| Persistence | SQLAlchemy; SQLite untuk default lokal, PostgreSQL untuk Compose |
| Migration | Alembic; startup juga memiliki create-all dan penyesuaian schema SQLite |
| Frontend | HTML, CSS, JavaScript tanpa framework frontend/build pipeline |
| Autentikasi | Password login, access/refresh JWT; identitas dari Bearer token |
| LLM | Interface provider; factory saat ini mendukung Ollama |
| Knowledge | Upload, extraction, chunking, retrieval, embeddings; opsi vector retrieval |
| Storage | Implementasi lokal dan S3 |
| Automation | Rule/schedule service dan worker polling terpisah |
| Tes | pytest untuk Python; Node built-in test runner untuk frontend |

Dependency Python ada di [requirements.txt](../requirements.txt). Versi API
yang dideklarasikan di `app/main.py` adalah `0.2.0`; angka ini bukan ukuran
kelengkapan produk atau kesiapan deployment.

## 4. Peta repository

| Lokasi | Tanggung jawab dan kapan dibaca |
| --- | --- |
| [app/main.py](../app/main.py) | Entrypoint, router, halaman statis, health, dan lifespan startup |
| [app/core](../app/core) | Settings, database/session, JWT/password, auth dependency, logging/middleware |
| [app/api/routes.py](../app/api/routes.py) | Sebagian besar endpoint company dan permission/ownership helper |
| [app/api/auth_routes.py](../app/api/auth_routes.py) | Login, profil, refresh, password reset; legacy token/register yang ditutup |
| [app/api/admin_routes.py](../app/api/admin_routes.py) | Provisioning dan operasi platform-admin |
| [app/api/result_routes.py](../app/api/result_routes.py) | Pin hasil task per pengguna |
| [app/api/inbox_routes.py](../app/api/inbox_routes.py) | Attribution untuk record inbox |
| [app/models/entities.py](../app/models/entities.py) | ORM entities, relasi, enum status |
| [app/schemas/domain.py](../app/schemas/domain.py) | Request/response schema domain; schema auth/admin juga ada di router terkait |
| [app/services](../app/services) | Orkestrasi bisnis: task, approval, conversation, access, inventory, workflow, dan lainnya |
| [app/agents](../app/agents) | Context agent dan penyusunan context untuk runtime |
| [app/runtime](../app/runtime) | Executor deterministik/LLM, keputusan model, dan eksekusi tools |
| [app/security/policy_engine.py](../app/security/policy_engine.py) | Keputusan policy untuk tindakan tool |
| [app/tools](../app/tools) | Kontrak tool, registry, domain tools, connector |
| [app/llm](../app/llm) | Interface LLM dan provider Ollama |
| [app/knowledge](../app/knowledge) | Extraction, indexing, chunking, embeddings, retrieval |
| [app/storage](../app/storage) | Backend penyimpanan file |
| [app/workers/automation_worker.py](../app/workers/automation_worker.py) | CLI worker schedule; dapat menulis database dan menjalankan pekerjaan |
| [app/static/workspace](../app/static/workspace) | Workspace user dan developer console yang berbagi controller |
| [app/static/auth](../app/static/auth) | Halaman forgot/reset password |
| [tests](../tests) | Tes backend dan frontend; jangan anggap seluruh fixture aman untuk DB workspace |
| [scripts](../scripts) | Entrypoint Docker dan tooling operasional; baca sebelum menjalankan |
| [alembic](../alembic) | Migration versioned; jangan menjalankan tanpa target DB dan persetujuan jelas |
| [docs](.) | Panduan implementasi, blueprint, acceptance criteria, dan handoff historis |

`storage/` di root adalah lokasi data runtime default, bukan package
`app/storage/`. File `.db` di root adalah data, bukan dokumentasi atau fixture
yang boleh dihapus untuk mencoba aplikasi.

## 5. Domain: istilah yang perlu dibedakan

| Istilah | Makna |
| --- | --- |
| Company | Tenant yang memiliki user, agent instance, knowledge, task, dan data bisnis |
| User / Role / Permission | Identitas manusia dan izin; owner company bukan otomatis platform admin |
| Department / AgentTeam | Struktur organisasi dan pengelompokan AI employee |
| AgentCatalog | Template/catalog agent yang dapat di-hire |
| AgentInstance | Agent operasional milik company, bukan template global |
| AgentSubscription | Lifecycle hiring/subscription instance agent |
| AgentAccess | Grant penggunaan, pengelolaan, atau approval agent bagi user |
| Skill / AgentSkill | Kapabilitas dan assignment skill pada agent |
| KnowledgeItem / Document / Chunk | Pengetahuan, dokumen yang diproses, dan unit retrieval |
| AgentMemory / Experience | Memory serta pengalaman dengan lifecycle validasi tersendiri |
| Conversation / Message | Riwayat percakapan dan pesan |
| Task | Pekerjaan yang dapat dieksekusi, menunggu approval, selesai, gagal, atau dibatalkan |
| Approval | Keputusan manusia untuk tindakan tersimpan; bukan sekadar status UI |
| TaskResultPin | Pin hasil task per pengguna; bukan versi dokumen hasil |
| Policy / AuditLog | Aturan tindakan dan catatan aktivitas |
| Delegation / Workflow / Automation | Handoff, rangkaian pekerjaan, dan pemicu pekerjaan otomatis |
| Plan / UsageCounter / LLMUsage | Entitas kapasitas dan pencatatan penggunaan; bukan bukti billing komersial selesai |

Definisi field dan relasi aktual ada di `entities.py`, bukan tabel ringkasan ini.

## 6. Alur penting

### Login dan session

`POST /api/v1/auth/login` menerima email/password dan optional legacy
`company_id`. Respons berisi access token, optional refresh token, identitas,
role, permissions, dan status platform admin.

Controller frontend menyimpan session di localStorage dengan prefix `ws_`.
Pada boot, access token diverifikasi melalui `GET /api/v1/auth/me`. Respons
profil menjadi sumber identitas user/company. HTTP 401 membersihkan session;
network error atau 5xx mempertahankan kredensial tetapi menahan UI di login/offline.
Logout saat ini membersihkan session lokal, bukan mencabut JWT di server.

Frontend masih dapat mengirim `X-User-ID`, tetapi backend mengabaikannya sebagai
kredensial. Jangan menjadikan header itu sumber otoritas baru.

### Onboarding company

Platform administrator yang sah membuat company dan owner melalui
`POST /api/v1/admin/companies`. Owner kemudian login dan user dengan
`team.manage` menambah anggota company. Tidak ada invitation model saat ini.
Registrasi publik dan anonymous first-user bootstrap ditutup.

Instance development yang benar-benar baru tidak otomatis memiliki akun login
atau platform admin. Tidak ada bootstrap admin publik yang aman untuk dijadikan
contoh; operator provisioning harus direview terpisah.

### Task dan approval

1. Router memeriksa identitas, membership, permission, dan akses agent sesuai endpoint.
2. `TaskRuntimeService` melakukan claim atomik `pending -> planning`.
3. Runtime memuat context company/agent/task dan menjalankan executor.
4. `ToolExecutor` memvalidasi agent/tool dan mengevaluasi policy.
5. Policy dapat mengizinkan, menolak, atau membuat approval sebelum side effect.
6. Task dapat berakhir `completed`, `failed`, atau `waiting_approval`.
7. Resume setelah approval memeriksa status dan menjalankan tindakan tersimpan;
   jangan mengganti proses ini dengan menjalankan ulang tool tanpa approval.

Status task yang tersedia: `pending`, `planning`, `running`,
`waiting_approval`, `completed`, `failed`, `cancelled`. Ini daftar enum, bukan
jaminan semua transisi antarstatus diperbolehkan.

Mode konsultasi memblokir tool side effect. Jalur deterministik dan jalur LLM
berbeda; mulai dari `services/task_runtime.py` dan `runtime/executor.py`.

### Knowledge dan inventory

Dokumen masuk melalui router, disimpan melalui storage, kemudian diproses oleh
layanan knowledge untuk extraction/chunking/indexing/retrieval. Dependencies
OCR dan format tertentu dapat membutuhkan instalasi sistem tambahan.

Inventory company disimpan di database. Endpoint `inventory/hydrate` memuat
inventory durable ke connector proses; controller memanggilnya setelah login
atau restore. Connector runtime dan data durable bukan hal yang sama.

## 7. Peta frontend

| File | Fokus |
| --- | --- |
| `index.html` / `styles.css` | Struktur halaman dan tampilan |
| `app.js` | Session, API wrapper, login/logout/boot, navigasi, banyak handler fitur |
| `home.js` | Ringkasan pekerjaan dan AI team |
| `chat.js` | Conversation, history, draft, pengiriman pesan |
| `inbox.js` | Queue pekerjaan/perhatian dan deduplikasi record |
| `results.js` | Library hasil tersimpan, preview, filter, pin |
| `sidebar.js` | Context yang mengikuti halaman utama |

`/workspace` dan `/developer` memakai HTML/script yang sama; developer page
mengubah `data-workspace`. UI developer bukan grant admin dan tidak menggantikan
permission check backend. Modul dashboard memiliki `reset()` dan guard request;
controller auth juga menjaga respons terlambat agar tidak memulihkan session lama.

## 8. Mencari lokasi perubahan

- Login/session: `app.js`, `auth_routes.py`, `core/auth.py`, `core/security.py`.
- Role dan tenant: helper `require_company_user`/`require_permission` di `routes.py`,
  `services/access.py`, `services/platform_admin.py`.
- Task gagal atau tertahan: `task_runtime.py`, executor, policy engine, approval service.
- Chat berbeda dari task: `services/conversation.py`, route messages, `chat.js`.
- Knowledge tidak terbaca: router upload, `knowledge/service.py`, extractor dan retrieval.
- Hasil/pin: `results.js`, `result_routes.py`, `TaskResultPin`.
- Automation: `services/automation.py` dan worker; jangan menjalankan tick sebagai inspeksi read-only.

API lengkap harus diperiksa melalui router dan schema. File `openapi-*.json`
adalah snapshot yang dapat tertinggal; Swagger dari proses sandbox aktif lebih
representatif, tetapi menjalankan proses tersebut memiliki efek startup.
