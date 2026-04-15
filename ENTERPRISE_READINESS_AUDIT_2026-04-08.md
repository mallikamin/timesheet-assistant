# Enterprise Readiness Audit - 2026-04-08

## Scope
- Repository: `timelogging` (POC web app in `poc/`)
- Audit dimensions: security, authorization, privacy, reliability, operational readiness, enterprise trust posture
- Constraint: read-only audit, no code changes

## Executive Decision
- Production/live external usage: **NO-GO** in current state
- Controlled demo usage: **GO with constraints** (trusted users, synthetic or low-sensitivity data, explicit POC disclaimer)

## Evidence Snapshot
- Backend framework: FastAPI with cookie session middleware
- UI: server-rendered HTML/JS
- Integrations: Google OAuth + Calendar + Drive + Gmail, Supabase, Google Sheets, Harvest, Anthropic
- Tests: smoke-only (`3 passed`), no meaningful security/authorization coverage

---

## Findings Register (Prioritized)

### Critical
1. Hardcoded Harvest credential exposed in repository
- Evidence: `poc/seed_harvest.py:10`
- Risk: immediate credential compromise and unauthorized API usage
- Impact: account takeover/data integrity compromise
- Required action:
  - Rotate token now
  - Remove token from code
  - Scrub git history if ever pushed remotely
  - Move to secure secret manager/env injection only

2. Broken authorization model: client-controlled user identity
- Evidence:
  - request model accepts `user`: `poc/app.py:153`
  - server persists/creates entries using `req.user`: `poc/app.py:542`, `poc/app.py:548`
  - frontend sends hidden DOM value: `poc/templates/index.html:494`, `poc/templates/index.html:614`
- Risk: authenticated user can impersonate another user
- Impact: data tampering, audit failure, trust collapse
- Required action:
  - Remove user identity from client payloads
  - Derive actor strictly from server session
  - Add ownership checks on every read/write action

3. Unprotected entry APIs (authz/authn gaps)
- Evidence:
  - read endpoint lacks auth check: `poc/app.py:590`
  - delete endpoint lacks auth check: `poc/app.py:597`
  - update endpoint lacks auth check: `poc/app.py:614`
  - approve endpoint checks auth but not ownership: `poc/app.py:623` and lookup at `poc/app.py:631`
- Risk: unauthorized access and manipulation
- Impact: cross-user data leakage and corruption
- Required action:
  - Require authenticated session on all `/api/entries*`
  - Enforce row-level ownership (`entry.user_name == session.user.name` or stable user_id)
  - Return 403 for cross-tenant access

### High
4. CSRF risk on state-changing routes
- Evidence: state-changing POST/PUT/DELETE requests made with cookie session auth and no CSRF token validation (`index.html` fetch calls at lines ~610, ~929, ~982)
- Risk: forged requests from malicious site
- Required action:
  - Implement CSRF tokens for all mutating endpoints
  - Set strict cookie options and same-site policy per deployment topology

5. Weak session secret fallback
- Evidence: default static secret in code `poc/app.py:38`
- Risk: predictable session signing when env misconfigured
- Required action:
  - Fail startup if `SESSION_SECRET` missing or weak
  - Use high-entropy secret from env manager only

6. Privacy/compliance mismatch (Gmail snippet usage)
- Evidence:
  - snippets ingested: `poc/gmail_sync.py:96`, `poc/gmail_sync.py:289`
  - policy text claims metadata-only/no body content: `poc/app.py:138`
- Risk: legal/compliance exposure due to mismatch between claim and behavior
- Required action:
  - Either remove snippet usage entirely, or update legal/policy disclosures and consent
  - Prefer metadata-only strict mode for enterprise contracts

### Medium
7. Approve-all flow trusts request-body user
- Evidence: `poc/app.py:562`, `poc/app.py:565`
- Risk: cross-user approval operations
- Required action: ignore body user and bind to session user only

8. Parser robustness issue may cause runtime failure
- Evidence: `parse_entries_from_response` relies on `.index()` for closing fence without guard (`poc/app.py:186-189`)
- Risk: malformed model output can break request path
- Required action:
  - Defensive parsing with bounds checks
  - safe fallback and telemetry on parse errors

9. Sensitive operational logging
- Evidence: tool calls and exceptions printed (`poc/app.py:494`, broad exception prints)
- Risk: metadata leakage in logs
- Required action:
  - Structured logging with redaction
  - remove raw PII inputs from logs

10. Product trust inconsistency in docs/positioning
- Evidence: README badge/claims mismatch with actual implementation (`README.md:7` vs current code)
- Risk: enterprise buyer confidence loss
- Required action: align docs with current architecture and roadmap truthfully

### Low
11. Pilot user list not enforced server-side
- Evidence: list exists but no gate logic (`poc/app.py:56`)
- Required action: enforce allowlist for pilot mode or remove claim

12. Testing depth insufficient for launch readiness
- Evidence: only smoke tests in `poc/test_smoke.py`
- Required action: add authz, CSRF, ownership, integration, and regression tests

---

## Launch Gate Criteria (Must Pass)
- [ ] No hardcoded secrets in repo and credentials rotated
- [ ] All entry endpoints authenticated and ownership-enforced
- [ ] Client cannot set identity for any server-side action
- [ ] CSRF protection enabled on all mutating routes
- [ ] Session secret hard requirement with secure cookie settings
- [ ] Privacy behavior and legal text consistent (metadata-only if claimed)
- [ ] Security regression tests green in CI

---

## 30-60-90 Execution Roadmap

### 0-7 Days (Stabilize / Security Hardening)
- Secret incident response (rotate/scrub)
- Authorization repair across entries APIs
- Remove client-supplied user identity from all write paths
- Add CSRF defenses
- Enforce session secret policy
- Freeze demo scope and add explicit POC disclaimer

### 8-30 Days (Enterprise Foundations)
- Add structured logging + redaction policy
- Add audit trail for entry approvals/edits/deletes
- Strengthen input validation and error handling
- Add rate limiting and abuse protections
- Expand test suite (security + integration)
- Update docs for architecture truth and limitations

### 31-90 Days (Premium/Enterprise Feel)
- Role-based access model and admin controls
- SSO hardening plan (SAML/SCIM roadmap)
- Compliance package: privacy, retention, DPA templates
- Observability dashboards + alerting
- Change-management and release checklist

---

## Demo Guidance Until Fixes Land
- Use only trusted internal users
- Avoid high-sensitivity mail/doc data
- Disable or limit risky endpoints if possible
- Disclose that security hardening sprint is in progress before production launch

---

## Technical Debt Backlog (Implementation-Ready)

### P0 (Blocker)
- [ ] Remove hardcoded tokens; rotate compromised credentials
- [ ] Refactor API contracts to ignore client identity fields
- [ ] Add auth check + ownership check to GET/PUT/DELETE `/api/entries*`
- [ ] Add CSRF middleware/validation and frontend token plumbing
- [ ] Startup guard for missing/weak `SESSION_SECRET`

### P1 (High Priority)
- [ ] Align privacy implementation with metadata-only commitment
- [ ] Replace print logging with structured logger and redaction
- [ ] Harden parser for malformed model output
- [ ] Add unit/integration tests for authz and approval workflows

### P2 (Scale/Trust)
- [ ] Add per-user immutable audit log
- [ ] Add role model (user/reviewer/admin)
- [ ] Add operational runbooks and incident response playbook
- [ ] Add SLOs and monitoring thresholds

---

## Acceptance Tests (Minimum)
- Unauthorized user cannot read/update/delete any other user's entries
- Forged cross-site POST/PUT/DELETE is rejected
- Session secret missing => app fails fast at startup
- Gmail path does not ingest/store body-like content if metadata-only mode active
- Approval endpoints only mutate entries owned by current session user
- All P0 tests pass in CI before release tag

---

## Notes for Next Implementation Sprint
- Keep scope tight: land P0 first, then re-audit
- Do not expand features before authorization and CSRF are fixed
- Treat this as enterprise trust debt, not just bug fixing
