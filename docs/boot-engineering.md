# Boot engineering — durable state across disposable sandboxes (generic pattern)

Non-sensitive engineering pattern only. No case content, no personal data, no secrets.
Distilled from a long multi-window document operation; applicable to any agent workflow
whose local sandbox filesystem is wiped between turns (or mid-turn).

## 1. Problem and rule

- Window/sandbox filesystems are **disposable**: per-turn teardown is the *default*, and
  occasional mid-turn resets happen with no platform signal, log, or reason. Persisted-file
  caps (e.g. 8 MiB) can silently revert whole writes.
- **Rule: the local filesystem is transport, never the store.** The canonical rebuild source
  is a server-persisted store (library / object store). Nothing load-bearing lives locally.
- Consequence: a wipe is an efficiency tax, never a data-loss event — provided every boot
  verifies against the store before use.

## 2. One master store, never forked

- Single store = source of truth. Every writer re-reads the store before every write.
- After every write run the full loop: `verify` → `digest` → `read-back` of touched keys.
- Never fork the store; never edit sent/final artifacts in place. Supersede: write new
  version → verify → delete old. Corrections are new append-only entries referencing the old.

## 3. Boot manifest (integrity anchor)

- A JSON manifest lists every load-bearing file: `path`, `byte_size`, `sha256`, `location_id`
  (document id in the store), plus `tail_sessions` (how many recent session entries to fetch
  by default for incremental boot).
- Bump `manifest_version` whenever any listed file changes.
- **Verify-before-use:** check each file's sha256 against the manifest before relying on it.
  On mismatch: stop and report — never proceed on a stale store.

## 4. Signed-URL fetch protocol (per file, sequential)

1. `prepare` → returns an upload/fetch handle and a signed URL (expires ~30 min, single-use).
2. Exactly one request to the signed URL, exact method/headers, raw bytes body (not base64,
   not multipart). Any 2xx = success. On 403: re-run `prepare` for a fresh handle.
3. `complete` with the same filename and handle (for uploads).
4. Fetch back and byte-verify (`cmp`) before deleting any superseded copy.
- Transcribe handles/URLs exactly — never retype. Signed URLs never pass through chat.
- One file at a time, sequential (never parallel prepare+PUT).

## 5. Boot subcommand spec

`store-tools boot <manifest-path>` — one program, no partial boots:

1. Fetch manifest → verify manifest itself is the single expected copy in the store.
2. Per listed file (plus `tail_sessions` entries): fetch → save → sha256-verify against
   manifest → record result. Full archives only on demand (explicit flag).
3. Run store-level checks: `verify` → `digest` → `read-back` key keys.
4. Exit non-zero on ANY failure; print `VERIFY OK` summary incl. `last_updated`.

## 6. Incremental boot (transfer efficiency)

- Default boot fetches: manifest + recent-sessions tail (window explicit in the manifest).
  This cuts most transfer vs full-state round-trips when one key changed.
- Full archives are fetched on demand only, each verified against the manifest.

## 7. Write cycle (after any work session)

1. Log session (append-only). 2. `verify` → 3. `digest` → 4. `read-back`.
5. Delete-first refresh of the state file and hot file to the store
   (prepare → curl upload raw bytes → complete → fetch-back byte-verify → delete superseded).
6. Post the bumped manifest **last**. 7. Ghost check: re-list the store, confirm exactly one
   copy of each canonical artifact (no forks).

## 8. Hot-file growth

- The "hot" file grows monotonically under full rewrite. Staged improvement: per-key patch
  records (append-only) + a compact current-state pointer, keeping delete-first +
  verify-before-delete for the canonical state file. Stage after §6 lands.

## 9. Hygiene rules that travel with the pattern

- UTC timestamps everywhere; pinned dependencies; sha256 manifests for code as well
  (verify-before-run, stop-and-report on mismatch); secret regex scan on every change.
- Content gate (absolute): shared stores and public repos get generic patterns and
  non-sensitive reference only — never personal data, legal case material, financial
  account identifiers, third-party records, or secrets/keys.
- Provenance labels on relayed notes: [FACT] (source in hand) / [REPORTED] (relayed,
  unverified) / [INFERENCE] / [SPECULATION]. Keep discrepancies both ways; never smooth.
