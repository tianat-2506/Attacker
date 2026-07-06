# Session Handoff And Workload Map

## Prompt For A New Account

```text
You are continuing VietSupply Radar from GitHub:
https://github.com/tianat-2506/Attacker

Start by running:
git status --short --branch
git pull --ff-only origin main

Read these files before editing:
- PROJECT_STATE.md
- docs/19-multi-account-collaboration-protocol.md
- README.md
- docs/17-run-project-after-restart.md
- docs/18-deep-research-technical-assessment.md
- deep-research-report.md

Goal:
Continue turning the current supply-chain/SME finance-ready demo into a trust-first backend/data/security platform.

Hard guardrails:
- Do not claim pilot-ready or production-ready.
- Do not claim credit approval, default probability, bank approval, verified supplier, invoice authenticity, fraud, legal breach, or automatic supplier replacement.
- Preserve tenant/role/period/evidence/audit guardrails.
- Before ending, update PROJECT_STATE.md, commit, pull --ff-only, and push.

Before coding:
- Pick one narrow slice.
- State the owned files.
- Avoid files another account may own.
- If parallel work is active, create a task branch.
```

## Recommended Parallel Tracks

- Track A - Frontend stakeholder workflows.
  - Goal: make each account feel like a distinct stakeholder workspace.
  - Own:
    - `frontend/src/components/`
    - `frontend/src/utils/`
    - frontend tests.
  - Avoid unless required:
    - backend services.
    - large rewrites of `frontend/src/App.tsx`.
  - Good next slices:
    - role-specific empty states and action explanations.
    - Intake/Vault UX for uploader/reviewer/lender personas.
    - per-account dashboard copy and disabled action states.

- Track B - Backend trust foundation.
  - Goal: strengthen policy, audit, evidence, invoice and period provenance.
  - Own:
    - `backend/app/services/`
    - `backend/app/domain/`
    - `backend/tests/`
    - `backend/migrations/`
  - Avoid unless required:
    - frontend layout files.
  - Good next slices:
    - policy decision/audit coverage tests.
    - evidence access grant/revoke and download audit hardening.
    - invoice claim registry state transition tests.
    - PostgreSQL RLS smoke improvements.

- Track C - Docs/ops/handoff.
  - Goal: keep new accounts productive and prevent context loss.
  - Own:
    - `docs/`
    - `README.md`
    - `PROJECT_STATE.md` append-only updates.
    - `scripts/` only for ops checks.
  - Good next slices:
    - concise operator runbook.
    - branch/merge conflict recovery guide.
    - pilot readiness checklist.

## High-Conflict Files

- `frontend/src/App.tsx`
- `frontend/src/components/WorkspaceViews.tsx`
- `backend/app/services/radar_service.py`
- `backend/app/services/governance_service.py`
- `backend/app/services/postgres_pilot_service.py`
- `PROJECT_STATE.md`

Rules for high-conflict files:

- Pull latest before editing.
- Keep changes small.
- Mention the file in the commit message.
- Do not format or rewrite unrelated sections.
- If two accounts need the same file, split by function/component and merge frequently.

## End-Of-Session State Template

Append a short slice to `PROJECT_STATE.md`:

```text
- <slice name> completed.
- Files changed: <short list>.
- Verification: <commands/tests run>.
- Remaining gaps: <short list>.
- Next best work: <one or two concrete steps>.
```

Then run:

```powershell
git status --short
git add -A
git commit -m "<clear short message>"
git pull --ff-only origin main
git push
```

If pull fails, do not force push. Fetch, inspect, and resolve deliberately.
