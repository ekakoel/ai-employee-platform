# Phase 2D: Auth Session Lifecycle

Snapshot 2026-10-12, branch `development`, baseline HEAD
`d0f586516a06061072088c197c3e2be6abb939b8`. Implementasi masih working tree,
belum commit, deploy, atau migrasi database workspace/produksi.

## 1. Desain yang diimplementasikan

- `User.auth_version` mengikat token pada versi kredensial. Perubahan/reset
  password menaikkan versi dan mencabut seluruh sesi user dalam transaksi sama.
- `AuthSession` memiliki ID UUID acak, user/company, versi kredensial, waktu
  pembuatan, absolute expiry, revocation timestamp/reason. Satu sesi adalah
  satu token family; bukan identifikasi perangkat fisik atau fingerprint browser.
- `RefreshTokenRecord` menyimpan identifier acak, SHA-256 digest JWT berentropi
  tinggi, session ID, issuance/expiry, consumed timestamp, dan replacement ID.
  Password tetap memakai helper password hashing yang sudah ada, bukan SHA-256.
- `PasswordResetRecord` menyimpan identifier/digest, user/company/version,
  expiry 30 menit dan consumed timestamp. Tidak ada token mentah dalam tabel ini.
- Access/refresh wajib membawa `sub`, `company_id`, `type`, `sid`, `jti`, `ver`,
  `iat`, `exp`. Reset memakai tipe/purpose `password_reset`, tanpa `sid`.
  Token legacy tanpa klaim sesi ditolak; tidak ada fallback stateless.
- Validator access memeriksa signature, expiry, tipe, sesi database, versi,
  user aktif, company aktif, dan binding user/company. Identitas dan permission
  tidak berasal dari header client atau role di JWT. Error database fail-closed.
- Access default/maksimum 15 menit; session/refresh absolut maksimum 14 hari.
  Refresh tidak memperpanjang absolute expiry. Idle expiry belum diterapkan.

## 2. Transaksi dan concurrency

Semua mutasi lifecycle mengambil lock user melalui SQL UPDATE sebelum membaca
ulang kredensial/sesi. PostgreSQL mengambil row lock dari UPDATE tersebut;
SQLite menserialisasikan writer pada database. Tidak ada lock Python in-memory.
Ini mengorbankan paralelisme antar sesi milik user yang sama demi konsistensi.

Consume refresh/reset memakai conditional UPDATE `consumed_at IS NULL` dan
memeriksa rowcount. Refresh baru, consume lama, replacement dan audit sukses
di-commit bersama. Error issuance/audit menyebabkan rollback tanpa menghabiskan
token lama. Login memverifikasi password lagi setelah lock agar reset paralel
tidak dapat menerbitkan sesi berdasarkan password lama.

Pemakaian ulang refresh yang sudah dikonsumsi mencabut seluruh session/family.
Revocation dan audit replay di-commit **sebelum** mengembalikan 401. Tidak ada
grace/retry window: dua refresh sah paralel dapat menghasilkan satu sukses,
lalu replay yang membatalkan token hasil sukses itu. Client harus mengoordinasi
refresh lintas tab dan tidak retry token lama setelah respons ambigu.

Logout/reset/password change memakai lock yang sama. Logout-all hanya mencabut
sesi user/company yang berasal dari token terverifikasi. Token revoked yang
diulang untuk logout adalah no-op; tidak boleh mencabut sesi baru setelahnya.

## 3. Kontrak API dan frontend

Semua path berikut relatif terhadap `/api/v1/auth`:

| Endpoint | Otoritas dan respons |
| --- | --- |
| `POST /login` | Email/password, optional `company_id`; bentuk respons token lama dipertahankan. Email aktif pada beberapa company memerlukan context eksplisit, jika password cocok tanpa context: 409 |
| `GET /me` | Bearer access terverifikasi terhadap record sesi; identitas/permission server |
| `POST /refresh` | Body `refresh_token`; rotasi sekali pakai, sesi sama; invalid/replay: 401 |
| `POST /logout` | Bearer access, tanpa body sebagai otoritas; current session, 204 |
| `POST /logout-all` | Bearer access; semua sesi milik user/company itu, 204 |
| `POST /change-password` | Bearer access, `current_password`, `new_password`; password 8-128 karakter; respons meminta login ulang |
| `POST /forgot-password` | Email, optional `company_id`; respons publik generik. Ambiguous email tanpa context tidak menerbitkan token |
| `POST /reset-password` | Body `token`, `new_password`; consume sekali pakai dan revoke all; invalid/consumed record: 400 |

Kesalahan kredensial/sesi 401, input schema 422, database auth tidak tersedia
503. Reset user tidak aktif/hilang dapat menghasilkan 401; pesan tetap generik.
`/token` tetap 410 dan `/register` tetap 403. `X-User-ID` tidak mengautentikasi.

Form login memiliki input company ID opsional. Nilainya hanya filter membership,
bukan permission/identity authority. Logout frontend menangkap access token,
segera membersihkan state/cache/localStorage, lalu POST logout menggunakan
Bearer yang ditangkap. UI menyebut server revocation hanya jika request sukses;
network/401/5xx tetap menghapus state lokal dan menyatakan konfirmasi belum ada.
Respons logout terlambat tidak boleh menimpa sesi login baru.

Penyimpanan token di `localStorage` tetap dipertahankan. Automatic refresh,
logout-all UI, serta change-password UI belum ditambahkan. Access expiry pendek
dapat meminta login ulang; jangan menganggap refresh berjalan otomatis.
Logout dengan access token expired tidak mencabut server session; UI hanya
logout lokal, family masih hidup sampai expiry/revocation lain.

Reset token hanya dikembalikan pada DEBUG di development/test. Production/staging
tidak mengembalikannya. Pengiriman email/reset link belum tersedia; fase ini
tidak mengirim email nyata atau menambah delivery provider. Respons generik
bukan jaminan timing resistance atau rate limiting.

## 4. Audit dan penyimpanan

Audit mencakup login, refresh, replay, logout, revoke-session/all, forgot/reset,
dan change-password. Actor/tenant/session berasal dari record terverifikasi.
Metadata hanya fixed reason dan request ID yang lolos format UUID. Kegagalan
login sebelum tenant terverifikasi memakai security logger dengan action tetap,
tanpa email/body/password/token. Helper `record_audit` **tidak memiliki redaction
otomatis**; service lifecycle memakai allowlist metadata sendiri.

Tidak ada cleanup otomatis. Record refresh yang consumed harus tetap tersedia
selama session/family masih hidup agar replay dapat dideteksi. Kebijakan purge
setelah absolute expiry, retensi audit, volume/index dan monitoring perlu review
operator terpisah; jangan menghapus revocation record saat sesi masih aktif.

## 5. Migrasi dan cutover

Revision baru: `0004_auth_sessions`, parent `0003_task_result_pins`.
Additive: kolom versi default 0, tiga tabel, FK, constraint dan indexes.
Data/password/admin grants lama tidak diubah. SQLite startup helper juga mengenal
kolom baru; startup normal dapat menjalankan create_all/schema sync, sehingga
**tidak dijalankan** terhadap workspace pada fase ini.

Migrasi baru mempunyai definisi schema eksplisit. Revision 0001/0002 lama masih
memakai live metadata; upgrade baru mengecek keberadaan tabel agar kompatibel
dengan fresh chain itu. Tidak ada stamp otomatis atau perubahan revision lama.
Downgrade 0004 sengaja ditolak: jangan drop revocation/reset records atau rollback
ke validator stateless. Recovery harus forward fix yang mempertahankan validasi
sesi, dengan service dihentikan bila enforcement tidak tersedia.

Langkah operator berikut belum dijalankan dan memerlukan persetujuan:

1. Review kode dan migration; backup, uji restore serta rencana maintenance.
2. Jalankan migrasi pada PostgreSQL disposable yang representatif: fresh chain
   serta salinan schema/data pra-0004. Periksa FK/index/default dan data lama.
3. Jalankan lima tes PostgreSQL concurrency pada database dedicated, bukan DB app.
4. Audit effective settings API/worker: `JWT_EXPIRE_MINUTES` 1-15 dan
   `JWT_REFRESH_EXPIRE_MINUTES` 1-20160; nilai lama 720 sekarang ditolak di semua
   environment. Konfigurasi aktual/secret tidak diubah pada fase ini.
5. Hentikan writer versi lama, migrate additive, kemudian jalankan hanya server
   baru. Jangan mencampur worker/API stateless lama dengan validator baru.
6. Informasikan logout massal: semua access/refresh/reset legacy ditolak;
   pengguna harus login ulang. Tidak ada grace period stateless.
7. Verifikasi login, refresh/logout/reset di staging dan browser, monitoring
   401/503/replay, sebelum meminta izin deployment/pilot.

Belum ada klaim production-ready atau PostgreSQL migration/concurrency berhasil.

## 6. Pengujian aktual

Python menggunakan `APP_ENV=test`, `DATABASE_URL=sqlite://`,
`JWT_EXPIRE_MINUTES=15`, `PYTHONDONTWRITEBYTECODE=1`, flag `-B`, dan
`-p no:cacheprovider`. Setiap file dijalankan dalam **proses berbeda**: hook P0
menolak semua SQLite file-backed, sedangkan lifecycle hanya mengizinkan temporary
root di luar repo. Keduanya menolak global application engine. Tidak ada startup
production, email/network nyata, full pytest, atau akses database workspace.

| Pemeriksaan terakhir | Hasil |
| --- | --- |
| `pytest tests/test_auth_p0_isolated.py -q -p no:cacheprovider --tb=short` | 66 passed; 1 existing Starlette/httpx warning |
| `pytest tests/test_auth_sessions_isolated.py -q -p no:cacheprovider --tb=short -x` | 46 passed; 2 warnings (Starlette/httpx, Alembic path_separator) |
| `pytest tests/test_auth_sessions_isolated.py -k parallel_refresh_password_change_cannot_restore_session` | 1 passed, 46 deselected; tes tambahan sesudah suite penuh |
| `pytest tests/test_auth_sessions_postgres.py -q -p no:cacheprovider --tb=short` | 5 skipped pada Phase 2D awal; file kini memuat 6 tes, blocked pada kelanjutan karena URL disposable tidak tersedia |
| `node --test tests/workspace_auth.test.cjs` | 30 passed setelah tes upload dokumen 401 |
| Enam file `workspace_{auth,chat,home,inbox,results,sidebar}.test.cjs` | 66 tes setelah koreksi; lihat Project Status untuk hasil akhir |
| `node --check` enam script workspace (termasuk `app.js`) | Lulus |
| AST parse dan import modul terkait | Lulus, tanpa startup/bytecode |
| `git diff --check` | Lulus; hanya peringatan normalisasi LF/CRLF |

SQLite lifecycle memakai file disposable dan koneksi/transaksi nyata. Coverage
termasuk claims, binding, expiry, rotation, commit replay, logout scope,
single-use reset, password change, race refresh/reset/login/logout, rollback,
inactive user/company, database failure, audit safety, invalid TTL, migration
old-user preservation, serta full Alembic fresh chain pada SQLite disposable.
Tes frontend memakai VM/mock fetch, bukan browser E2E.
Tidak ditemukan konfigurasi linter proyek (Ruff/Flake8/ESLint); tidak menginstal
toolchain baru. Pemeriksaan Python memakai AST parse, bukan full runtime lint.

Run awal lifecycle terhalang izin temporary pytest sebelum fixture database;
diulang dengan izin tooling. Tes auth frontend sempat mengungkap company field
lama tidak terhapus saat login gagal; koreksi sudah diverifikasi ulang.

PG test file opt-in hanya menerima driver `postgresql+psycopg` dan database
bernama `aiep_auth_test_*`. Setiap test membuat random isolated schema dan
**meninggalkannya untuk inspeksi**, tidak drop. Jangan memberikan URL produksi
walaupun namanya sesuai prefix. Review target sebelum menjalankannya.

## 7. Batas status

AUTH-007 dan AUTH-008 diimplementasikan dan perilaku wajib teruji pada SQLite
disposable. Review akhir, uji PostgreSQL representatif, dan browser E2E tetap
gate terpisah. Risiko tersisa: localStorage/XSS/CSP, rate limiting, email delivery,
coordinated client refresh, purge policy, expiry saat logout, serta fixture
backend lama yang belum aman untuk full suite. Tidak ada bypass P0 baru.

## 8. Seluruh file perubahan dan alasan

| File | Alasan |
| --- | --- |
| `app/models/entities.py`, `app/models/__init__.py` | Model session/refresh/reset dan versi user, constraints/index/export |
| `alembic/versions/0004_auth_sessions.py` | Migrasi additive; downgrade keamanan ditolak |
| `app/core/database.py` | Adaptasi helper schema SQLite untuk auth_version; tidak dijalankan pada workspace |
| `app/core/security.py` | JWT claims/type/expiry wajib dan envelope terikat sesi |
| `app/core/auth.py`, `app/api/routes.py` | Identitas Bearer, penanganan DB gagal, webhook dan katalog tools terautentikasi |
| `app/services/integrations.py`, `app/services/automation.py` | Company aktif dan event bertanda tangan, metadata terpercaya, secret baru acak server |
| `app/services/auth_sessions.py` | Service transaksi, lock, rotation/replay, revocation, reset/change, audit aman |
| `app/api/auth_routes.py` | Integrasi service dan endpoint logout/all/change-password |
| `app/core/config.py`, `.env.example` | Batas TTL access/session dan default baru |
| `app/static/workspace/app.js`, `app/static/workspace/index.html` | Logout server-safe, company context, respons 401 dan header Bearer-only |
| `app/static/workspace/home.js`, `app/static/workspace/sidebar.js` | Greeting personal dan konteks seluruh view navigasi |
| `tests/test_auth_p0_isolated.py` | Fixture Bearer sesi server-side, perlindungan P0 dipertahankan |
| `tests/test_auth_sessions_isolated.py` | Lifecycle/concurrency/rollback/migration disposable |
| `tests/test_auth_sessions_postgres.py` | Lima tes concurrency PostgreSQL opt-in dedicated |
| `tests/workspace_auth.test.cjs` | Regresi logout server/network dan company context |
| `README.md`, `docs/00_MASTER_INDEX.md` | Entry point dokumentasi dan hasil tes aktual |
| `docs/PROJECT_GUIDE.md`, `docs/DEVELOPMENT_GUIDE.md` | Kontrak session dan command tes terisolasi |
| `docs/PROJECT_STATUS.md`, `docs/PLATFORM_ACCESS.md` | Status/batas bukti dan kompatibilitas cutover |
| `docs/AUTH_SESSION_LIFECYCLE.md` | Laporan implementasi, risiko, operasi, dan review Phase 2D |

Tidak ada file database, konfigurasi deployment aktual, dependency, atau
approval policy yang diubah. Tidak ada commit/push/deploy.

## 9. Kelanjutan keamanan dan integrasi

Webhook sekarang mensyaratkan company aktif selain integration aktif dan HMAC
valid. Jenis event harus berada dalam body bertanda tangan. Query `event_name`
ditolak dengan 400 karena query tidak termasuk tanda tangan. Metadata identitas
integration dan event milik server tidak bisa diganti oleh field payload.
Kegagalan HMAC mencatat audit denied yang di-commit sebelum 401 dikirim.

Secret untuk integrasi baru selalu dihasilkan server; parameter custom
`webhook_secret` ditolak dengan 400. Ini mengubah kontrak untuk client yang
menentukan secret sendiri. Integrasi lama tetap bisa diverifikasi memakai
secret yang tersimpan; secret lemah lama perlu rotasi terpisah. Runtime secret
masih disimpan dalam config database untuk verifikasi HMAC, meskipun API list
tidak mengembalikannya. Penyimpanan terenkripsi dan rotasi credential masih
pekerjaan P1.

Katalog `/api/v1/tools` sekarang memerlukan Bearer session dan memakai database
dependency. Workspace mengirim hanya Bearer. 401 dari resource auth menghapus
session yang cocok; 503 dan respons terlambat tidak menghapus session baru.
Upload dokumen yang memakai fetch langsung juga mengirim hanya Bearer dan
menangani 401 dengan guard versi sesi.
`/auth/me` memberi 503 ketika query profil gagal dan tidak commit read-only.
Automatic refresh lintas tab tetap belum tersedia karena replay policy akan
mencabut family saat token refresh lama dipakai ulang.

Tes lanjutan mencakup signed event, disabled tenant, audit rejected HMAC,
secret custom, katalog tools, cross-tenant URL, metadata automation, race
refresh/change-password, 401/503
frontend dan late response. Enam file frontend sudah lulus setelah greeting
dan sidebar dibetulkan; ini tetap tes VM/mock, bukan browser E2E.
