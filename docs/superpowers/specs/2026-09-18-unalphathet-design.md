# UnAlphaThet — rekordbox-free DJ library, inbox sorter and stick manager (TUI)

Status: **design spec (2026-09-18).** Base = Dixi's earlier design doc, with the deltas in §0 applied.
Sections marked ✅ are decided; items in §11 are decided at the start of the phase that needs them.

## Context

Dixi DJs occasionally (psy, techno, metal, dnb…); rekordbox makes library organization, set prep and USB
management painful, and on Linux it only runs in a VM/Wine — so "rekordbox as export engine" is not a
workable v1, it's the emergency hatch. She wants a keyboard-driven TUI that *owns* the library (crates as real
directories, vibes as crate-scoped tags, cross-crate playlists), ingests new music through an inbox pipeline
with a fast card-style sorter, and manages virtual/physical USB sticks — writing what Pioneer players read
(`export.pdb` + ANLZ) directly so rekordbox becomes optional.

Repo: `/workspace/UnAlphaThet` (git, MIT, one commit: `LICENSE`). Container: Fedora 44, Python 3.14 system,
`uv` 0.12 with 3.12/3.13 available, ffmpeg 8.1, ffprobe, fpcalc 1.6, sox, flac, mediainfo, mpv installed.
**Not yet:** audio path from container to host (needs pipewire socket mounted into podman — host-side, Dixi).

## 0. Deltas vs. the earlier doc (what this session changed)

| Was | Now | Why |
|---|---|---|
| ffmpeg/fpcalc/mpv "not installed yet" | installed | verified in container |
| Phase 1.5: rekordbox XML *import* for migration | **dropped** | Dixi: "only the files matter" — the old rekordbox dir is inbox #1 |
| Track identity = chromaprint fingerprint + duration | ✅ **UUID in tags = PK**; fingerprint + audio-MD5 for dedupe and identity recovery | chromaprint isn't a stable equality key (varies across fpcalc versions/re-encodes; matching is bit-error-rate) |
| "SQLite is the source of truth for everything not derivable from paths" | **reconciled** (§2): per-track facts live in tags *and* DB with a conflict rule; playlists also as m3u8, sticks as toml; SQLite stays the *read contract* for frontends | lost `.db` = a rescan, not a catastrophe; metadata travels with the file |
| Analysis lib choice in "open" list | **deferred to a Phase 2 spike**; schema stores results in a documented format regardless of producer | doesn't affect Phase 0–1 |
| ANLZ overhead "~1–2 MB/track" | budget code **measures** a sample instead of a constant | probably high; PQTZ+PWV3/4/5 for 7 min ≈ few hundred KB, .2EX adds |
| Phase 4 validation | explicit: **no hardware at home** → borrowed-deck protocol required before trusting a gig stick; `plain` flavor is the gig-day fallback and must exist from Phase 3 | Dixi doesn't own decks |
| Prior-art table | re-verified 2026-09-18, see §1 | |

## 1. Format landscape (verified 2026-09-18)

| Piece | State | Source |
|---|---|---|
| Reading `export.pdb` / ANLZ | solved | rekordcrate (Rust, read-only), pyrekordbox (Py), Deep Symmetry crate-digger (Kaitai, the reference) |
| Writing `export.pdb` from scratch | done by ≥3 independent projects, **hardware-validation thin** | DjManager (Electron, MIT, JS port of "rex"), rkbdb2xml (kuwa72; rekordbox still sometimes errors on output), manadj (parked Aug 2026, never reached a deck). `fragmede/rekordbox-pdb` (pure-Py, MIT) edits *existing* PDBs, FORMAT.md is the best prose spec |
| Writing ANLZ (.DAT/.EXT/.2EX) | solved | `rbox` (Rust, GPLv3) reads+writes all three; DjManager writes PQT2/PWV3/4/5/cues in JS; pyrekordbox has structs |
| BPM / grid / key / waveform | tractable | DjManager shells to the Mixxx analyzer binary; for fixed-tempo genres the grid is one BPM + first downbeat, which is what rekordbox writes by default |
| Device Library Plus (`exportLibrary.db`) | SQLCipher, non-standard params | only OPUS-QUAD / OMNIS-DUO / XDJ-AZ / CDJ-3000X; **verify in Phase 4** whether those fall back to classic PDB or folder browse |

Conclusion: "make rekordbox obsolete" is realistic. The hard part is not analysis; it is a PDB that never
corrupts on a player at a gig → independent-reader validation on every sync + hardware protocol before trust.
Licensing: `rbox` is GPLv3, repo is MIT — fine to *call*, not to vendor. Prefer MIT pieces for ported code.

## 2. Decisions ✅

- **Hardware target: whatever the venue has.** Default stick *profile* "universal" = FAT32 + classic PDB +
  WAV compat. Per-stick profiles for known gear (FLAC/exFAT for NXS2+).
- **Deck reliance:** sync + quantize heavily → beatgrid on the stick is **mandatory** (ANLZ). Grid corrected
  on the fly while playing → right BPM + roughly right downbeat is enough. Hot cues barely used.
- **Migration:** none. Existing rekordbox collection = files only → first inbox run.
- **Collection size:** 2k–10k tracks. Fingerprinting is a one-off ~20 min in parallel, then incremental.
  Scans must be resumable and never block the UI.
- **Stack:** Python **3.13 via `uv`** (3.14 wheels lag for audio libs) · Textual (TUI) · Typer (CLI) ·
  SQLite WAL · TOML config · external: ffmpeg/ffprobe/fpcalc/mpv, optional keyfinder-cli. Rust rejected:
  every domain lib (mutagen, pyacoustid, pyrekordbox, rekordbox-pdb, yt-dlp, slskd client) is Python.
- **Shape:** core service layer (no UI imports) + thin CLI + thin TUI; GTK4/libadwaita frontend later as a
  second consumer. Seam rules in §4.
- **Preview playback is essential** in the sorter: mpv JSON IPC behind a `Player` interface.
- **Track identity:** a UUID minted on ingest and written into the file (`UAT_ID` Vorbis comment / ID3
  `TXXX:UAT_ID` / MP4 freeform) is the primary key. Chromaprint (`fpcalc`) and decoded-audio MD5 (free from
  FLAC STREAMINFO) are stored alongside for dupe detection; a file that arrives without a UUID is matched by
  fingerprint on scan and re-stamped. Path is never identity.
  - **Converted copies on sticks** get the same UUID stamped by mutagen after ffmpeg (WAV: `id3 ` chunk
    appended after `data`, as rekordbox does; M4A: freeform atom; MP3: `TXXX`). Hardware checklist item:
    oldest deck plays a WAV with our chunk.
  - **Every stick carries `.unalphathet-stick.json`** at its root: stick id, profile, and `on-stick path →
    track UUID, synced audio hash, synced meta hash, mode`. This manifest is the stick's truth; sync diffs run
    against it, a foreign machine or a post-DB-loss rescan reads it. Tags are redundancy, fingerprint is the
    parachute (`uat stick adopt` rebuilds a mapping fuzzily if both are gone).
- **Truth model (reconciled):**
  - Crate membership = the file's directory. Period.
  - Per-track facts (track id, vibes, energy, rating, bpm, key, loudness) are written **into the file's tags**
    (Vorbis comments / ID3 `TXXX`) *and* kept in SQLite. Conflict rule on scan: if the file's mtime is newer
    than the DB row's `tags_written_at` and tag values differ → **tag wins** (external edit, beets-style);
    otherwise DB wins and tags get re-written.
  - Playlists: SQLite is canonical (order, nesting); an `.m3u8` per playlist is exported on change for other
    software. Sticks: SQLite canonical; a `stick.toml` manifest is written on the stick itself for the sync diff.
  - Everything not in a file (analysis blobs, cues, sync state, jobs, history) lives only in SQLite.
  - **Consequence:** losing `library.db` costs a rescan (tags → DB) plus re-analysis, not years of sorting.
  - SQLite remains the **read contract** for all frontends; nobody parses tags except `scan`.
- **Sorter:** two card-style passes (§5). Pass 1 = crate triage while the inbox drains; pass 2 = vibes/
  playlists/energy per crate. Per-artist batches with hierarchical split and per-track override.
- **Pioneer:** native PDB+ANLZ export is **Phase 4, must-have**, nothing from Phase 5+ before it. rekordbox
  XML *export* exists from Phase 3 as the emergency bridge only. `plain` stick flavor is the gig-day fallback
  until the hardware protocol has passed.
- **Downloaders:** Phase 5, but the `wanted` track state + `Source` interface are in the schema from day 1.

## 3. Domain model

### Verdicts on the original design
1. **`collection > crates > vibes`** — right shape. One dir = one crate, so "vibes only within your crate" falls
   out of the filesystem for free. Playlists are the cross-crate escape hatch. Add **energy 1–5** and rating
   now (set prep lives on "same vibe, energy+1, key ±1"). Crates carry an optional **BPM range** — cheapest
   fix for octave errors (70 vs 140) and it's genre knowledge Dixi already has.
2. **Playlists** — Pioneer *hardware* reads exactly one format: the PDB. M3U does nothing on a CDJ; rekordbox
   *software* imports M3U8/XML. So: SQLite + M3U8 export + PDB on the stick.
3. **Inbox** — identity per §2 (UUID + fingerprint), never path. Dupe tiers cheapest-first. Analyze at
   ingest once, cache by track. Lossless (WAV/AIFF/ALAC/APE/WV) → FLAC; never transcode lossy. Loudness
   (EBU R128) tagged, not applied. Filenames `Artist - Title.ext`, FAT-safe. Move = copy → verify → delete
   with an undo journal.
4. **Sticks** — an entity with capacity, mode, fs type, export flavor, physical binding. Membership is a table
   so it *is* a tag, with statuses that distinguish audio-stale from meta-stale. Budget in **output bytes per
   mode** + FAT overhead + measured ANLZ. Playlists on sticks are references expanded at sync.
5. **Pioneer + analysis** — first-class, Phase 4.

### Filesystem
```
~/music/dj/                       ← collection root (configurable)
  .unalphathet/library.db         ← SQLite
  .unalphathet/cache/{converted,analysis}/
  inbox/                          ← drop zone; sub-folders named like crate[/vibe] pre-fill triage
  inbox/_trash/                   ← sorter "trash" target; never rm
  psy/    Artist - Title.flac     ← crate dirs
  techno/
  metal/
  playlists/*.m3u8                ← exported, regenerated on change
```
`uat scan` reconciles FS ↔ DB (moved/deleted/new) by track id / fingerprint so manual moves don't break anything.

### SQLite schema (draft — refined while writing `core/db.py` in Phase 0/1)
- `track(id, fingerprint, audio_hash, rel_path, crate_id, title, artist, album, duration_ms, bpm, key, energy,
  rating, loudness_lufs, size_bytes, codec, sample_rate, bit_depth, state[wanted|inbox|crated|sorted|missing],
  deferred, source_url, added_at, analyzed_at, tags_written_at)`
- `crate(id, name, dir_name, hotkey, bpm_min, bpm_max)` · `vibe(id, crate_id, name, hotkey)` · `track_vibe`
- `playlist(id, name, parent_id)` · `playlist_track(playlist_id, track_id, position)`
- `stick(id, name, profile, capacity_bytes, mode, fs_type, export_flavor, device_uuid, last_synced_at)`
- `stick_track(stick_id, track_id, via_playlist_id, status[pending|synced|audio_stale|meta_stale|remove],
  synced_audio_hash, synced_meta_hash, output_bytes)` · `stick_playlist(stick_id, playlist_id)`
- `analysis(track_id, beatgrid, waveform_preview, waveform_detail, version)` · `cue(track_id, kind, idx,
  position_ms, end_ms, color, name)`
- `history(track_id, stick_id, played_at)` · `sort_log(id, track_id, action, from_path, to_path, prev_state, at)`
- `job(id, kind, payload, status, log)`

## 4. Architecture

**Package layout** (`/workspace/UnAlphaThet/unalphathet/`)
```
core/      models.py db.py ids.py fs.py tags.py scan.py
ingest/    inbox.py dedupe.py convert.py batches.py analyze/{bpm,key,waveform,loudness}.py
library/   crates.py vibes.py playlists.py query.py
sticks/    model.py budget.py plan.py sync.py devices.py manifest.py
export/    m3u.py rekordbox_xml.py pioneer/{pdb,anlz,settings,validate}.py
sources/   base.py ytdlp.py slskd.py telegram.py          (phase 5)
tui/       app.py player.py screens/{triage,tagging,dupes,browse,sticks,jobs}.py
jobs.py    background worker (ProcessPool); analysis/convert/download never block the TUI
cli.py
```

**Core / frontend seam** — the rules that make GTK4 a second consumer, not a rewrite:
1. `core` + `library` + `ingest` + `sticks` + `export` = service layer: plain functions + dataclasses, no
   Textual imports, no terminal assumptions. Every TUI action exists here and is exposed by the CLI.
2. SQLite is the contract: all state incl. analysis results in the documented schema, never pickles.
3. Long-running work goes through the `job` table; frontends enqueue + observe. Worker = `uat worker`.
4. Writers are subcommands with file in/out (`uat export pioneer --stick A --dest …`); swapping in a Rust
   writer = replacing one subcommand.
5. Every CLI command has `--json`.
6. Preview behind a `Player` interface (mpv IPC now; GStreamer for GTK later).

## 5. Sorter — two card-style passes ✅

**Goal:** every decision is one keypress on a card. Pass 1 decides *where* (crate) while the inbox drains;
pass 2 decides *what* (vibes, playlists, energy) per crate once the inbox is empty. Shared: batching, preview,
undo.

**Batching:** level-1 item = artist (normalized `albumartist`/`artist`), grouped by album + `singles`.
Compilations are one item. `x` splits one level (artist → albums → tracks), `X` straight to tracks; split items
queue right after the current one. `tab` toggles batch focus ↔ track focus for per-track overrides without
splitting. Queue: biggest batches first.

**Pre-fill** (first hit wins, reason shown on card): inbox sub-folder `crate[/vibe]` → same artist already in
library (majority crate, vibes on ≥50%, median energy) → genre-tag map from config → crate BPM range if
exactly one matches. `enter` accepts.

**Pass 1 — triage**
```
┌ Inbox triage ── 37 files · 14 items left ──────────────────────────────────────┐
│   ASTRIX                                               9 tracks · 3 albums      │
│   Deep Jungle Walk (2016)        5 tracks   138–141 BPM   8A 9A    FLAC         │
│   He.art (2016)                  3 tracks   140–142 BPM   8A       FLAC         │
│   singles                        1 track    140 BPM       9A       MP3 320      │
│   ▶ Deep Jungle Walk     01:48 / 07:12   ━━━━━━━●━━━━━━━━━━━━━━━━━━━━━━  25 %   │
│   CRATE  →  [1] psy     2 techno     3 metal     4 dnb      suggested: 7 tracks │
├─────────────────────────────────────────────────────────────────────────────────┤
│ 1–9 crate · enter accept · x/X split · tab track focus · s skip · S later · u   │
└─────────────────────────────────────────────────────────────────────────────────┘
```
Keys: `1–9` crate + advance (`0` picker if >9) · `enter` accept suggestion · `x`/`X` split · `tab` focus ·
`s` skip / `S` later (deferred, `L` reveals) · `D` trash → `inbox/_trash/` · `E` edit metadata · `u` undo ·
`space` play/pause, `←/→` ±10 s, `shift+←/→` ±60 s, `g` hop 25→50→75 %, `↑/↓` preview track · `/` filter ·
`?` help · `q` quit (commits are per card).
Commit → move to `<crate>/Artist - Title.ext` (rename same-fs, else copy→verify→delete job), state `crated`,
journal, next card. **Tags not written yet.**

**Pass 2 — tagging** (per crate; entered from browse `psy · 23 untagged` or offered when inbox hits zero)
```
┌ psy › tagging ── 23 untagged · 6 items left ──────────────────────────────────┐
│   ASTRIX – Deep Jungle Walk                      5 tracks · 138–141 BPM · 8A   │
│   ▶ Deep Jungle Walk     01:48 / 07:12   ━━━━━━●━━━━━━━━━━━━━━━━━━━━━  25 %   │
│   VIBES     [f] full-on   [n] night   ( d) dark   ( o) morning   ( t) twilight │
│   PLAYLIST  +jungle-set                                            p: add     │
│   ENERGY    ●●●●○   (1–5)                     suggested from: 3 Astrix tracks  │
├────────────────────────────────────────────────────────────────────────────────┤
│ letters vibes · 1–5 energy · p playlist · enter commit · x/X split · tab · u   │
└────────────────────────────────────────────────────────────────────────────────┘
```
Keys: unreserved `a–z` toggle vibe (hotkeys from config, else first free letter; reserved `s u p x m q`) ·
`1–5` energy · `p` playlist picker (fuzzy, create-on-type) · `:` type-to-tag line (`fu ni +late-night e4`) ·
`enter` commit (zero vibes valid) · rest as pass 1.
Commit → DB vibes/playlists/energy, state `sorted` → tags written → journal → next. Any track/selection in
browse can be sent back through this screen.

**Preview:** autoplay on card focus from 25 % (`preview.autoplay`, `preview.start_at`), batch card previews
first track, `↑/↓` moves preview within batch.

**Why fast:** one decision per card, no modes in the hot path (only `p`/`E` open anything), pre-fill makes most
cards `enter`, batches turn 9 decisions into 1, `u` instead of "are you sure?".

## 6. Browser (list view) ✅ shape; keys settled in Phase 3
Crate → vibe / playlist / artist / album tree left, tracks (BPM/key/length/format) right, player bottom.
Search/sort by BPM/key/energy. Per-stick badge column (`A✓ B~ C·`), filters `on A` / `not on any`. Mark
`m`/`M`, assign to sticks/playlists, send to re-tagging, preview. Keys settled in the sticks session.

## 7. Sticks & sync (shape ✅; exact semantics settled at Phase 3 start)
- Stick = capacity, **mode** (regular / compat / compressed), **fs type** (FAT32 / exFAT), **export flavor**
  (`pioneer` = PIONEER/ folder with PDB+ANLZ · `plain` = folder tree, no DB, plays anywhere), physical binding
  (partition UUID + `.unalphathet-stick.json` ID file that survives reformats).
- Compat: FLAC → WAV 16-bit ≤48 kHz (pre-NXS2 players). Compressed: AAC (libfdk often missing in distro
  ffmpeg) **or** MP3 320 (LAME, plays on everything) — offer both, default configurable.
- Budget = output bytes per mode (WAV exact from duration×rate×depth×ch; lossy = bitrate×duration; FLAC
  actual) + ~5 % FAT overhead + **measured** ANLZ for `pioneer` flavor.
- Sync = plan desired set → diff against on-stick manifest → convert via local cache keyed by (track, mode) →
  copy → verify → write `PIONEER/` (Phase 4) → **re-parse with an independent reader** (rekordcrate /
  pyrekordbox) → update statuses.
- Physical detection: `lsblk -J`; mount via `udisksctl`.

## 8. Pioneer export + analysis (Phase 4)
- ANLZ writer: `PQTZ`/`PQT2` beatgrid, `PWAV`/`PWV2` in .DAT, `PWV3/4/5` in .EXT, `PCOB/PCO2` cues, `PVBR`,
  `PPTH`. From-scratch PDB writer ported to Python from DjManager / `rekordbox-pdb` FORMAT.md. `MYSETTING*.DAT`
  with CRC-16. Validation = rekordcrate `dump-pdb` + pyrekordbox parse identically.
- Analysis: global tempo + first-downbeat (fit constant grid to detected beats; octave disambiguated by crate
  BPM range). Candidates: `beat_this` (torch), essentia, aubio, or shell to Mixxx analyzer like DjManager.
  Key: keyfinder-cli / essentia. Waveforms: decode → downsample → 3-band envelope. **Spike in Phase 2**
  (wheels on 3.13).
- **Hardware protocol before any gig stick:** tiny stick, 5 tracks, borrowed deck (oldest available first —
  if a CDJ-2000nexus accepts it, newer will), check browse / waveform / grid / playlist. `plain` flavor until then.
- Open: Device Library Plus fallback behaviour on OPUS/OMNIS/AZ/3000X.

## 9. Phases
0. **Bootstrap** — `uv init` (3.13), pyproject, deps, config loader, schema + migrations, `uat scan`,
   `uat doctor`. Commit.
1. **Library core + browse TUI** — crates/vibes/playlists CRUD, ids + fingerprinting, tag read/write-back,
   browse screen, mpv preview behind `Player`.
2. **Inbox pipeline** — scan → dedupe tiers → "which to keep" screen → FLAC conversion → analysis spike +
   jobs → batching → triage cards → move + undo → tagging cards.
3. **Sticks & sync** — profiles, virtual sticks + per-mode budgets, badges in browse, physical binding, sync in
   `plain` flavor (folders + M3U8), conversion cache, manifest + verification, rekordbox XML export (bridge).
4. **Native Pioneer export** — ANLZ + PDB writers, settings files, independent-reader validation, hardware
   protocol.
5. **Sources** — `wanted` tracks; yt-dlp, slskd, Telegram; lazy download at sync.
6. **Set-prep extras** — history import, harmonic neighbours, braille waveform + grid nudging.
7. **GTK4 frontend.**

## 10. Verification
- Unit: synthetic click tracks (ffmpeg) with known BPM/downbeat for analysis; fixture files for tags/dedupe/
  batching; in-memory SQLite for model tests.
- Round-trip: written PDB/ANLZ → rekordcrate + pyrekordbox parse → field-by-field compare.
- Sticks: sync to a loop-mounted FAT32 image; then the hardware protocol.
- Sorter: Textual `Pilot` tests for split/override/undo; timed manual session on ~50 inbox files, target
  < 3 s per card in pass 1.

## 11. Open items — decided at the start of the phase that needs them (Dixi: "code asap")
1. ✅ **Track identity** — UUID-in-tags PK, fingerprint recovery, per-stick manifest (see §2).
2. **Dedupe policy** (Phase 2 start) — Claire's proposal on the table: auto for identical audio (tiers 1–2),
   one-keypress screen for re-encodes (tier 3, better file preselected; newcomer wins = **upgrade** in place,
   UUID/vibes/playlists/stick memberships kept, affected sticks → `audio_stale`), flag-only for fuzzy (tier 4).
   Losers → `inbox/_trash/dupes/<date>/`, journaled, never `rm`.
3. ✅ **Tag write-back fields** (Phase 1): `UAT_ID`, `TITLE/ARTIST/ALBUM/ALBUMARTIST/GENRE`, `GROUPING` =
   `crate/vibe;crate/vibe`, `BPM`, `INITIALKEY`, `UAT_ENERGY`. Vorbis for FLAC/Ogg, ID3 for MP3/WAV/AIFF,
   MP4 atoms (+ freeform `----:com.apple.iTunes:*`) for M4A. Config `tags.write_back = true`.
   Deferred: `GENRE` = crate name, `REPLAYGAIN`/`R128` loudness, `RATING` (Phase 2, when ingest sets them).
   Open (Phase 2): read RIFF `INFO` chunks from WAVs that carry no ID3 (Bandcamp WAVs do).
4. ✅ **Filenames** (Dixi, 2026-09-18): `Artist - Title.ext`; FAT-forbidden characters become `_`,
   everything is transliterated to ASCII (oldest decks show garbage for UTF-8), whitespace collapses,
   trailing dots/spaces are dropped, over-long names lose title characters first. `core/fs.safe_filename`.
5. ✅ **Vibe invariant enforcement** (Dixi, 2026-09-18): strict. `set_track_vibes` raises
   `VibeCrateMismatch` and changes nothing if any offered vibe is foreign or unknown; callers that expect
   foreign entries (GROUPING from outside the app) filter first via `apply_grouping`, which counts them.
   Scan drops all vibes when a file changes crate (`recrated`) and strips the stale GROUPING on write-back.
6. ✅ **Scan conflict rule** (Dixi, 2026-09-18): file wins only if its mtime is strictly newer than
   `tags_written_at`; never-written-by-us, equal, or older → DB wins and is written back. With
   `write_back = false` nothing is written, so external edits are ignored every scan (read-only-trial mode).
   BPM is compared at the precision the file can hold (integer for MP4 `tmpo`) so lossy formats converge.
   A file that already carries a valid `UAT_ID` unknown to the DB keeps it (lost `library.db` = rescan).
7. **Stick profiles & sync semantics** (Phase 3 start) — names/defaults, AAC vs MP3, WAV rules, stale
   states, sync steps, browse keys for stick assignment.
8. ✅ **Schema v1 + service API** — `core/db.py` (Phase 0/1). Not yet in v1: stick*, analysis, cue, history,
   job tables (added by migration in their phases).
9. **Phase 2 notes from Phase 1 review:** two *copies* of one file sharing a `UAT_ID` ping-pong as "moved"
   on every scan until dedupe resolves them; first scan is sequential `fpcalc` (~0.5 s/file, Ctrl-C safe and
   resumable because each file is its own transaction) — parallelise via the job table.
   Real-file run (58 tracks, 2026-09-18): vibe **hotkeys** are DB-only and are lost with the DB — move them to
   the config file (`vibes.psy = { "full-on" = "f" }`) as the old plan had it; `playlists/*.m3u8` survive a
   DB loss but are not re-imported — scan should offer to import them when the playlist table is empty;
   a rescan after DB loss re-fingerprints every file even though all carry a `UAT_ID` (27 s / 58 files).
10. ✅ **Naming defaults** (override anytime): package `unalphathet`, CLI `uat`, config
   `~/.config/unalphathet/config.toml` (XDG), collection root from config (default `~/music/dj`), DB inside the
   collection at `.unalphathet/library.db` so the collection dir is self-contained and portable.

