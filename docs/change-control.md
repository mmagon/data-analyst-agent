# Change control and prompt versioning (repo workflow)

Generic mechanics only; non-sensitive.

## 1. Change pipeline (every repo change)

1. Owner decides the change.
2. Agent (Prudentia) gives **explicit approval before commit**.
3. Byte-verify blobs (`git hash-object` vs GitHub blobs API) + secret regex scan
   (ghp_/sk-/AKIA/AIza/xox/private-key/api-key patterns) on every change — clean required.
4. Commit. Redeploy **only at a pinned commit SHA, with agent approval**, never "latest".
5. Smoke test via workflow API after each redeploy; keep any interim manual relay until
   fixes are verified in production.
6. Tests must pass (`pytest`) at the pinned SHA before redeploy.

## 2. Prompt versioning like code

- Prompt/instruction text lives in the repo (e.g. `main.py` INSTRUCTIONS blocks), not only
  in platform UI fields; export UI-side config into the repo after changes. Git history is
  the version history.
- Tag releases (`git tag -a vX.Y.Z`); redeploy only at tags/pinned SHAs. `CHANGELOG.md`:
  one line per change (what/why/who approved).
- sha256 manifest covers every load-bearing file **including prompt-bearing files**; bump
  manifest version on any change; verify-before-run, stop-and-report on mismatch.
- Golden tests in CI: representative inputs with expected behavioral checks; run before
  any redeploy (smoke test made repeatable).
- Secret scan automated in CI, not just manual.

## 3. Release-pinned code fetch (scheduled turns)

- Scheduled turns fetch runnable code from a **release tag** (e.g. `monitor-release`),
  re-pointed at the verified commit on each release — never from `main`.
- Fetch the manifest with the code; verify sha256 of each fetched file against the manifest
  **before executing**; on mismatch, stop and report — never run unverified code.
- Each run logs its script sha256 (run log), so the code that actually ran is auditable.

## 4. Filing conventions (N-store)

- Generate once → one sha256 → write to each target store via its own authorized writer →
  fetch-back byte-verify each → supersede-delete only after verify → manifest records
  per-store MATCH/MISMATCH.
- Deterministic names: append-only per-run artifacts (`…-<UTC ts>`), delete-first per-day
  artifacts (`…-YYYY-MM-DD`).
- Only the shared operational library is workspace-shared; matter libraries stay private;
  nothing crosses from private shelves into shared stores or public repos.

## 5. Scheduled-turn grammar

- Turns begin with the literal `[SCHEDULED]` prefix; publish the accepted grammar in the
  README; first line of each scheduled turn may carry a machine-readable JSON header
  `{kind, ts_utc, run_id}`; unknown wrappers are logged and ignored, never silently skipped.

## 6. Backups

- Encrypted backup (AES-256, PBKDF2, salt) of the shared operational library only, uploaded
  to the designated Drive folder. Passphrase supplied per-request, used only inside the
  single encryption command (via stdin), never stored in files/logs/chat/library, deleted
  from the sandbox afterwards. Drive writes require per-action human approval.
- Restore = download → decrypt with passphrase → extract → verify against manifest.
  Run a restore test at least once per quarter and after any format change.
