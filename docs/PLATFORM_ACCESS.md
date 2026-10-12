A. Frontend — Company Client

Workspace perusahaan yang menggunakan AI Employee Platform.
- Registrasi perusahaan dan akun pemilik perusahaan
- Login dan logout pengguna perusahaan
- Session/token dan masa berlaku autentikasi
- Isolasi data antarperusahaan
- Role dan permission pengguna perusahaan

API authentication, authorization, dan tenant isolation

B. Backend — Developer / Platform Owner

Sistem internal untuk pemilik dan pengembang platform.
- Login akun developer/platform administrator
- Pemisahan identitas dan hak akses dari pengguna perusahaan
- Akses ke pengelolaan perusahaan dan konfigurasi platform
- Proteksi endpoint administratif
- Audit aktivitas dan pengelolaan akun istimewa

## Phase 2A: P0 Access Contract

Authentication requires a valid Bearer access token in every environment.
`X-User-ID` may still be sent by older frontend clients, but is ignored as a
credential. Company handlers receive an ID from the server authentication
dependency. Platform endpoints require an active authenticated user with a
persisted `is_platform_admin` grant. A company owner is not a platform admin.

### Supported Onboarding

1. An existing platform administrator signs in through `/api/v1/auth/login`.
2. The administrator calls `POST /api/v1/admin/companies` with company name,
   owner name, owner email, and an explicit owner password. The server assigns
   the owner role and creates company and owner in the same transaction.
3. The owner signs in through the normal password login endpoint.
4. A company user with `team.manage` adds employees through
   `POST /api/v1/companies/{company_id}/users`. This requires membership in the
   target company. Client requests cannot assign the owner role through this
   endpoint or the company role-update endpoint.

Company self-registration and email invitations are now available through the
verified flows in [Company Onboarding](COMPANY_ONBOARDING.md). Registration
does not accept a tenant or role selector and does not issue a token.
Passwordless `/auth/token` still returns 410. The old direct-user-creation
route returns 410; platform provisioning remains available to authenticated
platform administrators. `/companies` still requires platform authentication.

Existing persisted administrator grants are retained. `PLATFORM_ADMIN_EMAILS`
is deprecated and does not grant privileges on login, profile reads, or admin
requests. An existing administrator can still grant platform access using the
authenticated, audited admin grant endpoint. No new first-admin bootstrap or
development authentication bypass was added. If no legitimate administrator
exists, first-admin provisioning needs a separately reviewed operator process;
it cannot be performed through anonymous HTTP requests.

### Configuration

Production and staging require `AUTH_ENABLED=true`,
`ALLOW_LEGACY_USER_HEADER=false`, `PUBLIC_COMPANY_CREATE=false`, `DEBUG=false`,
and a non-development JWT signing secret of at least 32 characters. Unsafe
settings fail during Settings construction and are rechecked before application
startup touches the database. Environment aliases are normalized; unknown
environments are rejected. Legacy auth/public-create flags do not restore
header authentication or the old unsafe public-create path in development either.

Compose requires external `JWT_SECRET`, `POSTGRES_PASSWORD`, and `DATABASE_URL`.
The database URL must contain correctly encoded matching credentials and target
the Compose database service. Both API and worker use the production checks.
Never commit the actual values. Missing Compose variables fail interpolation.

Password-reset tokens now have their own type and cannot authenticate API
requests or refresh a login. Previously issued access-type reset tokens are
rejected as API credentials. Phase 2D implements durable sessions, refresh
rotation/replay revocation, single-use reset, and password-version invalidation.
Rate limiting and reset email delivery remain follow-up work. Access tokens now
expire within 15 minutes; sessions within 14 absolute days. Legacy stateless
tokens are rejected. See [Auth Session Lifecycle](AUTH_SESSION_LIFECYCLE.md)
for API contracts, migration/cutover, concurrency, and verification limits.

### Compatibility and Verification

Password login, refresh, and authenticated company/admin APIs retain their
response shapes. Bearer-only clients work without header injection middleware.
Connect IDs, anonymous Quick start, and legacy token requests no longer work.
Public company registration now follows verified owner onboarding; direct
employee creation is replaced by invitation. Platform provisioning still
requires an explicit owner password.
The Phase 2A report originally recorded a frontend JavaScript syntax blocker.
AUTH-011 has since corrected the three invalid assignments. AUTH-014 changes
in the baseline distinguish `/auth/me` 401 from network/server
failures and prevent optimistic session restoration after failed verification.
See [Project Status](PROJECT_STATUS.md) for the dated verification evidence and
review/commit status. These isolated frontend tests do not establish browser
E2E or real backend login success.

`tests/test_auth_p0_isolated.py` uses real routers on a separate FastAPI instance
without the production lifespan, SQLite in-memory databases, and a guard that
rejects connections to the global application engine.
An additional Python audit hook rejects every file-backed SQLite connection
before the driver opens it, and each fixture checks its empty database filename.
Run only that file with
`DATABASE_URL=sqlite://`, `APP_ENV=test`, `JWT_EXPIRE_MINUTES=15`, bytecode disabled, and pytest's cache
provider disabled. Do not run the existing file-based fixtures against workspace
databases. Broader regression fixture isolation remains follow-up work.
