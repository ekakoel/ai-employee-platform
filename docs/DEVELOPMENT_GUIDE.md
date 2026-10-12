# Panduan Development dan Pengujian Aman

Baca [Project Guide](PROJECT_GUIDE.md) untuk peta kode dan
[Project Status](PROJECT_STATUS.md) untuk bukti verifikasi terakhir.
Perintah di bawah adalah panduan, bukan catatan bahwa semuanya sudah dijalankan.

## 1. Aturan sebelum bekerja

```powershell
git status --short --branch
git rev-parse HEAD
git diff --stat
git diff
```

Pertahankan perubahan lokal. Jangan reset, checkout, stash, clean, atau menghapus
file database untuk memperoleh baseline bersih. Review diff secara lokal;
jangan mempublikasikan credential yang mungkin terdapat pada perubahan.

Jangan menjalankan aplikasi, worker, migration, atau full pytest sebelum
memastikan target database dan storage benar-benar boleh dimodifikasi.

## 2. Mengapa startup bukan inspeksi read-only

Lifespan di `app/main.py` melakukan:

1. Validasi keamanan settings.
2. Konfigurasi logging.
3. `Base.metadata.create_all` pada engine aplikasi.
4. Penyesuaian schema SQLite melalui `migrate_sqlite_schema()`.
5. Seed catalog melalui session database.

Worker memanggil `init_db()` lalu menjalankan schedule. Docker entrypoint
menjalankan `alembic upgrade head` sebelum command API maupun worker.
Karena itu, bahkan membuka API untuk melihat Swagger dapat menyebabkan
perubahan database saat startup.

Default database adalah `sqlite:///./ai_employee.db`; default storage `./storage`.
Keduanya relatif terhadap working directory. Override dependency `get_db` saja
tidak menjamin engine yang dipakai lifespan ikut terisolasi.

## 3. Persiapan dependency

Gunakan Python 3.12 sebagai baseline yang sama dengan Dockerfile. Node diperlukan
untuk pemeriksaan JavaScript dan tes frontend. Tidak diperlukan `npm install`
untuk tes `.cjs` saat ini karena memakai Node built-in test runner.

Jika environment Python belum tersedia, jalankan dari root repository:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Jangan menimpa virtual environment yang sudah digunakan tanpa memeriksanya.
Instalasi dependency membutuhkan jaringan; tidak diperlukan untuk membaca kode.

## 4. Menjalankan sandbox development

Hanya lakukan langkah ini ketika startup memang disetujui. Gunakan terminal
PowerShell khusus dan database/storage disposable di luar data workspace:

```powershell
$devRoot = Join-Path ([System.IO.Path]::GetTempPath()) ('aiep-dev-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $devRoot | Out-Null
$env:APP_ENV = 'development'
$env:DATABASE_URL = 'sqlite:///' + (Join-Path $devRoot 'development.db').Replace('\', '/')
$env:STORAGE_BACKEND = 'local'
$env:STORAGE_LOCAL_PATH = Join-Path $devRoot 'storage'
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

Periksa `$devRoot` sebelum startup. Jangan mengarahkannya ke data company asli.
Environment variables di terminal tersebut mengoverride nilai `.env`; setting
lain masih dapat berasal dari `.env`. Review `app/core/config.py` dan
`.env.example`, tanpa mencetak secret. Jangan memakai setting development untuk
deployment. Folder disposable ini tidak dibersihkan otomatis oleh panduan.

Alamat setelah proses berjalan:

| Alamat | Fungsi |
| --- | --- |
| `http://127.0.0.1:8001/workspace` | Workspace pengguna |
| `http://127.0.0.1:8001/developer` | Developer UI; bukan bypass platform-admin |
| `http://127.0.0.1:8001/docs` | Swagger |
| `http://127.0.0.1:8001/health` | Health aplikasi |
| `http://127.0.0.1:8001/health/ready` | Konektivitas database; bukan jaminan seluruh fitur siap |

Jika port terpakai, pilih port lain. Sandbox baru tidak otomatis memiliki akun
admin/owner yang dapat login. Onboarding membutuhkan platform admin sah; lihat
[kontrak akses](PLATFORM_ACCESS.md), jangan mencoba Quick start anonim.

## 5. Konfigurasi yang perlu dipahami

| Kelompok | Nama setting utama |
| --- | --- |
| Environment | `APP_ENV`, `DEBUG` |
| Database | `DATABASE_URL`, `DB_POOL_SIZE`, `DB_MAX_OVERFLOW` |
| JWT | `JWT_SECRET`, `JWT_ALGORITHM`, `JWT_EXPIRE_MINUTES`, `JWT_REFRESH_EXPIRE_MINUTES` |
| Auth legacy | `AUTH_ENABLED`, `ALLOW_LEGACY_USER_HEADER`, `PUBLIC_COMPANY_CREATE` |
| Storage | `STORAGE_BACKEND`, `STORAGE_LOCAL_PATH`, setting `S3_*` |
| LLM | `LLM_PROVIDER`, `OLLAMA_BASE_URL`, `OLLAMA_MODEL` |
| Retrieval | `KNOWLEDGE_VECTOR`, `EMBEDDING_PROVIDER`, `EMBEDDING_DIMS`, bobot hybrid |
| Automation | `WORKER_POLL_SECONDS` |
| Observability/budget | `LOG_LEVEL`, `LOG_JSON`, setting `LLM_COST_*` dan `LLM_DAILY_BUDGET_USD` |

`Settings` membaca `.env`; jangan commit `.env` berisi credential. Production
dan staging menolak auth lemah, legacy header auth, public company creation,
debug, signing secret development/terlalu pendek, dan algoritma signing yang
tidak didukung. Nama environment dinormalisasi dan nilai tidak dikenal ditolak.

`PLATFORM_ADMIN_EMAILS` tidak memberikan grant admin. Flag legacy tidak
menghidupkan kembali `/auth/token`, registrasi publik, atau header authentication.
Factory provider saat ini hanya mendukung `ollama`; interface LLM bukan bukti
semua provider tersedia. Ollama adalah service terpisah, tidak disediakan oleh
Compose yang sekarang.

## 6. Tes frontend tanpa database

Jalankan pemeriksaan sintaks dan tes auth terlebih dahulu:

```powershell
node --check app/static/workspace/app.js
node --test tests/workspace_auth.test.cjs
git diff --check
```

Untuk regresi seluruh modul frontend yang saat ini tersedia:

```powershell
node --test tests/workspace_auth.test.cjs tests/workspace_chat.test.cjs tests/workspace_home.test.cjs tests/workspace_inbox.test.cjs tests/workspace_results.test.cjs tests/workspace_sidebar.test.cjs
```

Tes ini memakai file lokal dan mock, bukan backend atau browser nyata. Dua tes
lama masih gagal pada baseline terakhir; lihat Project Status. Jika sandbox
menolak child process dengan `spawn EPERM`, minta izin eksekusi sesuai tooling,
bukan menonaktifkan isolasi database atau keamanan aplikasi.

## 7. Tes backend P0 yang terisolasi

`tests/test_auth_p0_isolated.py` memasang router pada FastAPI terpisah tanpa
lifespan produksi. Fixture memakai SQLite in-memory, menolak global engine
aplikasi, dan memasang audit hook yang menolak SQLite file-backed.
Jalankan hanya file ini dalam proses terpisah, setelah memeriksa source fixture:

```powershell
$env:APP_ENV = 'test'
$env:DATABASE_URL = 'sqlite://'
$env:PYTHONDONTWRITEBYTECODE = '1'
.\.venv\Scripts\python.exe -B -m pytest tests/test_auth_p0_isolated.py -q -p no:cacheprovider
```

Gunakan terminal khusus untuk menghindari perubahan environment yang terbawa
ke proses aplikasi lain. Jangan menggabungkan tes P0 ini dengan fixture lama.
Hasil suite ini tidak diklaim sudah diverifikasi ulang pada sesi dokumentasi.

### Mengapa bukan langsung full pytest?

`pytest.ini` mengumpulkan seluruh `tests/`; marker `integration` tidak otomatis
mengecualikan tes eksternal. Beberapa file membuat atau menghapus tabel pada
database file-backed, bahkan pada waktu import/collection. Contohnya
`test_mvp.py`, `test_approval_lifecycle.py`, dan `test_auth_job15.py`.

`tests/conftest.py` mengubah PRAGMA untuk koneksi SQLite bernama `test_*`, tetapi
tidak mengganti database aplikasi dan bukan jaminan isolasi suite. Bahkan
`pytest --collect-only` dapat menjalankan import dengan side effect.

Sebelum memperluas tes: periksa URL engine, lifespan TestClient, dependency
override, `create_all`/`drop_all`, storage, fixture import, dan service eksternal.

## 8. Docker, migration, dan operasi

Compose menyediakan PostgreSQL, API, dan worker. Volume `pgdata`/`storage_data`
adalah data persisted. `JWT_SECRET`, `POSTGRES_PASSWORD`, dan `DATABASE_URL`
harus disediakan secara eksternal; jangan menaruh nilai aktual dalam dokumentasi.
URL database harus cocok dengan credential dan service database Compose.

Jangan menjalankan Compose atau migration hanya untuk membaca project. Jangan
menghapus volume untuk memperbaiki error login. Baca
[Backup/Restore](BACKUP_RESTORE.md) dan script terkait sebelum operasi data.
Review target, backup, hak operator, dan dampak worker terlebih dahulu.

## 9. Checklist perubahan dan handoff

1. Catat branch, HEAD, dan perubahan lokal.
2. Baca router, service, schema, UI, dan fixture yang benar-benar terkait.
3. Pisahkan autentikasi, permission, tenant membership, akses agent, dan approval.
4. Gunakan perubahan kecil; jangan menghapus handler demi membuat tes lulus.
5. Jalankan tes relevan dengan database/network yang terbukti terisolasi.
6. Review diff dan `git diff --check`; jangan ikut men-stage data runtime.
7. Update panduan/status jika kontrak berubah; bedakan bukti tes dari asumsi.
8. Catat tes gagal/tidak dijalankan dan langkah berikutnya. Commit/deploy hanya
   setelah persetujuan, bukan sebagai bagian otomatis dari dokumentasi.
