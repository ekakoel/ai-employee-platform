# Company onboarding and identity

## Current model

`User.company_id` is the single active company membership in this release.
Changing it or introducing multi-company membership requires a separately
reviewed migration and session contract. Login accepts email and password;
the server resolves exactly one active user and binds the session to that
user's company. Duplicate active legacy email identities fail closed with 409
and require operator reconciliation. The optional legacy `company_id` login
field is ignored, not a tenant selector. `X-User-ID` is not authentication.

The only required company field at registration is a unique company name;
the registering owner supplies their name, email, and password. Company
`owner_user_id` is set to the newly created user in the same transaction.
The server assigns the existing `owner` role. Platform admin is never granted.
Email claims reserve normalized addresses and protect concurrent public
registration. Existing addresses are claimed during migration, including
ambiguous legacy duplicates. Registration returns a conflict for existing
addresses or company names. It does not issue a session.

## Verification and delivery

New public owners cannot sign in until email verification succeeds. Tokens are
random, single-use, expire after 24 hours, and are stored only as SHA-256
digests. `POST /api/v1/auth/request-verification` is the recovery route after
delivery failure; it returns a generic result for unknown addresses. Invitations
use the same verified email channel and expire after 48 hours. Acceptance
proves email control through the link, creates a `member`, and cannot select
company or role. Invitation links and verification links are delivered via
SMTP-over-TLS when `SMTP_HOST`, `SMTP_FROM`, and `PUBLIC_BASE_URL` are configured.
For deployed environments, the public base URL must be HTTPS. SMTP credentials
come from environment variables. Without delivery, production registration and
invitation issuance return 503; no email is claimed to have been sent. With
`DEBUG=true` in development/test only, response bodies expose tokens for local
testing. Tokens are never stored raw in the database or written to audit logs.

SMTP delivery occurs after the database transaction. If delivery fails, the
account remains pending; request verification again. Owners can reissue an
invitation. A mail outbox and endpoint rate limiting remain deployment work;
the public endpoints must be rate-limited at the gateway before exposure.

## Profile and permissions

New companies start with `onboarding_status=pending`. Owner can read and PUT
`/api/v1/companies/{company_id}/profile` before completion. A contact email
and industry are required to complete the profile. Company workspace routes
reject pending companies with 403, while `/auth/me` and profile routes remain
available. Legacy companies default to `complete` to preserve operations.
Onboarding state is separate from company activation and email verification.

Only the recorded owner may invite, revoke invitations, or appoint/revoke
`ai_admin` through `/api/v1/companies/{company_id}/administrators/{user_id}`.
An `ai_admin` has the existing AI workforce permissions, including agent
management, skills, policy, knowledge, and integrations. An administrator
cannot appoint owners or grant platform privileges. Role changes revoke active
sessions and require a fresh login. The legacy direct-user-creation endpoint
returns 410; employees join by invitation and choose their own password.
AI Employee records remain company-scoped and are governed by existing
permission, tool, and approval controls.

## Migration and cutover

`0005_company_onboarding` adds nullable profile/owner fields, email verification,
claims, and invitation records. Existing users remain verified; existing
companies remain complete, preventing a mass logout. The migration does not
guess legacy ownership. Inspect historical company users and audit records,
then assign `owner_user_id` through a reviewed operator procedure before
using owner-only invitation/profile management. Companies with no verified
owner need explicit reconciliation. Duplicate legacy email identities cannot
log in until resolved. Do not run this migration against workspace, staging, or
production data without backup and a reviewed rollout plan. PostgreSQL adds
the owner foreign key; SQLite's additive ALTER column cannot add that FK, so
application-level owner checks remain the boundary there.

Run isolated tests before deployment. Production needs SMTP, HTTPS origin,
database migration, gateway rate limits, backup, and operational owner/email
reconciliation. Browser E2E and PostgreSQL concurrency must be validated on
disposable environments; unit tests do not establish either result.

## First AI Employee: CEO

After the company profile is completed, onboarding offers the published catalog
template with slug `ceo` as the first AI Employee. The UI selects it by slug,
not by catalog ordering. Reservation and other specialist templates remain in
the catalog for later hiring.

The CEO template is an executive advisor and planning partner. Its initial
responsibilities include clarifying business goals, prioritizing work, preparing
action plans, identifying risks, and recommending specialist AI Employees.
Recommendations do not themselves hire another agent or execute delegated work.

The initial CEO template has no allowed tools and autonomy level `1`. Existing
company permissions, tool grants, approval rules, and human oversight remain in
force. Do not describe autonomous hiring or AI-to-AI delegation as available
unless those capabilities are implemented and verified separately.
