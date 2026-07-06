# Multi-Account Collaboration Protocol

- GitHub source of truth: `https://github.com/tianat-2506/Attacker`.
- Every account/session starts by syncing from GitHub:
  ```powershell
  git clone https://github.com/tianat-2506/Attacker.git
  cd Attacker
  ```
  or, if the repo already exists:
  ```powershell
  git status
  git pull --ff-only origin main
  ```
- Read before work:
  - `PROJECT_STATE.md`
  - `README.md`
  - `docs/17-run-project-after-restart.md`
  - this file
- Do not rely on chat history as project memory. Persist useful state in repo files.
- Before editing:
  - run `git status --short --branch`.
  - identify owned work area and avoid files another account is actively editing.
  - prefer a branch for parallel work:
    ```powershell
    git checkout -b <short-task-branch>
    ```
- Avoid overlap:
  - Frontend-heavy work should avoid backend service files unless required.
  - Backend-heavy work should avoid `frontend/src/App.tsx` and `frontend/src/components/WorkspaceViews.tsx` unless required.
  - Do not rewrite `PROJECT_STATE.md` wholesale; append concise state only.
- Token/context budget rule:
  - When context is getting large, stop feature work early enough to preserve state.
  - Update `PROJECT_STATE.md` with:
    - latest completed slice.
    - files changed.
    - tests or commands run.
    - known gaps and next best work.
  - Commit and push before ending the session.
- End-of-session commands:
  ```powershell
  git status --short
  git add -A
  git commit -m "<clear short message>"
  git pull --ff-only origin main
  git push
  ```
- If `git pull --ff-only` fails:
  - do not force push.
  - fetch and inspect:
    ```powershell
    git fetch origin
    git log --oneline --graph --decorate --all -n 20
    git status
    ```
  - merge or rebase only after understanding conflicts.
- Never commit:
  - `.env`
  - real secrets or tokens.
  - `node_modules/`
  - local logs.
  - SQLite runtime DB or evidence object binaries unless explicitly requested.
- Commit style:
  - small commits.
  - message says what changed, not "misc".
  - push frequently when work is useful and verified.
- Product guardrails remain active:
  - do not claim pilot/production ready.
  - do not claim credit approval, default probability, verified supplier, invoice authenticity, fraud, legal breach, or automatic supplier replacement.
