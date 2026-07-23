# BUILD PLAN — MSG HRIT Terrestrial Archive Explorer

**Project type:** Full-stack data pipeline + web application
**Owner:** Usaid (BSCS, SATMET internship, Assignment 04)
**Deadline context:** Assignment 04 is due Friday 17 July 2026, 9:00 PM, with review presentations on 15/16/17 July. Build efficiently; get a working vertical slice (discovery → one downloaded timeslot → processed images → visible in UI) before scaling to the full sample set.

This document is the single source of truth for Cursor Pro. Do not invent requirements not stated here. Where a decision point exists, this document states the decision — do not substitute your own default. If something is genuinely missing, stop and surface the gap instead of guessing.

**Revision note:** This version replaces the earlier "download everything" scope with a curated per-date sample (Section 5). This was a deliberate scope change made after running a size-check crawl against the real server (see Section 5 for the confirmed numbers behind the decision).

---

## 1. Context (read this before anything else)

This project is **not** the same thing as the SatDump manual deliverable or the two Word-document deliverables (interpretation report + two-page reference guides) from Assignment 04. Those are separate, already-in-progress, and out of scope for this codebase. What this codebase must do is:

1. Connect to the internal SATMET server, **catalog the entire** MSG HRIT Terrestrial Archive (every date, every timeslot it can find), but **only download a small, deliberately chosen sample of files per date** — see Section 5 for exactly what gets downloaded and why.
2. Process every downloaded file into per-channel images and standard multi-channel composites.
3. Store the results so they can be browsed quickly.
4. Serve everything through a web UI, launched with `npm run dev`, with a distinctive "liquid glass" visual style — explicitly **not** the default Bootstrap/Tailwind violet-purple theme — and written so that the UI itself explains what the tool is, what it shows, and why, without requiring outside explanation (see Section 14).

No Google Colab. Everything runs locally against the internal server.

---

## 2. Critical technical findings (do not re-derive these — they are settled)

These were confirmed by directly browsing the server's directory listings and by running a real crawl against the archive. Do not use the older segmented-HRIT assumptions from any prior script you may see referenced — that assumption was wrong for this route.

- **Server root:** configure via `ARCHIVE_BASE_URL` in local `.env` (never commit the real internal host)
- **The route to use is exactly:** `HRIT_Terrestrial Archive` as labeled in the server's route index, which resolves to the `HRIT_Native/` path on disk. Do **not** use `HRIT_Ground_Station`, any `LRIT_*` route, `GFS`, `WRF`, `Air Quality Index`, or `Flood Data` routes. Those are unrelated products on the same server and are out of scope.
- **Folder structure on the server (confirmed by browsing):**
  `HRIT_Native/<YYYY>/<YYYY-MM-DD>/<HH-MM>/msg15.nat`
  - The year level currently only contains `2026/`, but the pipeline must discover years dynamically from the listing rather than hardcoding `2026`, since more years may appear later.
  - **Each timeslot folder contains exactly one file: `msg15.nat`.** There are no separate per-channel segment files, and no separate prologue/epilogue files, for this archive route. One `.nat` file = one complete disk scan for that timeslot, all channels included.
  - **Confirmed real archive contents (from an actual size-check crawl run on 15 July 2026):** 1,022 files totaling 276.07 GB, spanning `2026-06-22` through `2026-07-15`. Per-date breakdown:
    - `2026-06-22`: 96 files (full day), 26.03 GB
    - `2026-06-23`: 36 files (partial day), 9.76 GB
    - `2026-06-29`: 5 files (partial day), 1.36 GB
    - `2026-06-30` through `2026-07-05`: **0 files each** — these date folders exist on the server but are genuinely empty, not a crawl error
    - `2026-07-06` through `2026-07-14`: 96 files each (full days), ~26 GB/day
    - `2026-07-15`: 21 files (partial — same-day, still accumulating at crawl time)
  - Every file that does exist reports a consistent ~271 MB size — there is no evidence of truncated or corrupted files in the confirmed data, so the pipeline does not need special corruption-recovery handling beyond the standard size-verification check in Section 10.
- **File format implication:** `.nat` is the EUMETSAT **Native format**, not the segmented HRIT transmission format. The processing pipeline must use satpy's **native-format reader** (the reader designed for whole-disk `.nat` files), not a segmented-HRIT reader. Each `.nat` file is loaded as a single-file Scene — there is no segment-counting, no missing-segment logic, and no separate prologue/epilogue handling required.
- **Day/night behavior is expected, not a bug.** Four of the twelve SEVIRI channels (the visible/near-IR/solar ones, plus HRV) only contain valid data during daylight for the imaged region. Nighttime timeslots will legitimately be missing those channels and any composite that depends on them (e.g. natural_color). The pipeline must detect this and record it as "not available (night)" rather than treating it as a processing failure.
- **The twelve SEVIRI channels:** HRV, VIS006, VIS008, IR_016, IR_039, WV_062, WV_073, IR_087, IR_097, IR_108, IR_120, IR_134.
- **The five standard composites:** natural_color, airmass, dust, ash, convection.

---

## 3. In scope vs out of scope

**In scope for this codebase:**
- Discovering and cataloging **every** timeslot in the HRIT Terrestrial Archive (full catalog, not sampled).
- Downloading **a curated per-date sample** of `.nat` files (three per date — see Section 5), not the entire archive.
- Processing every downloaded file into 12 channel images + 5 composites (where physically possible per the day/night rule above).
- Storing processed outputs with metadata for fast retrieval.
- A web UI to browse, filter, view, and monitor all of the above — written to be self-explanatory (Section 14).
- Operational safety: resumability, disk-space awareness, progress visibility, error handling.

**Explicitly out of scope (do not build these, do not scaffold placeholders for them):**
- The manual SatDump stitching deliverable — that is done by hand in the SatDump desktop app, separately.
- Generating or editing the two Word documents (interpretation report, two-page reference guides).
- Any other server route (`HRIT_Ground_Station`, `LRIT_*`, `GFS`, `WRF`, `Air Quality Index`, `Flood Data`, `Internal Tasks 2026`, `Images`, aviation maps).
- Google Colab integration of any kind.
- User authentication / multi-user support — this is a single-user local tool for now.
- Cloud deployment — this runs on the local/internal machine only.
- Downloading the full archive by default — that path must exist only as a possible future toggle (Section 12 configuration), never as the out-of-the-box behavior.

---

## 4. Deliverables — definition of done

A complete build satisfies all of the following:

1. Running one command from the project root starts both the backend and the frontend, and the app is reachable in a browser.
2. A "Discovery" action crawls the entire `HRIT_Native/` tree on the server and produces a full catalog (every year/date/timeslot found), without requiring the date range to be known in advance.
3. The catalog is visible in the UI before any downloading starts, including a total known size/count for the full archive **and** a clearly separate count of how many files the current sample-selection rule would actually download — so the user always sees both "what exists" and "what we're pulling."
4. A download process works through the sample queue produced by the selection logic in Section 5, downloads each selected `msg15.nat`, verifies each download against the server-reported file size, and can be safely stopped and resumed at any time without re-downloading completed files or corrupting the catalog state.
5. A processing step runs on every successfully downloaded file, producing labeled PNG images for every available channel and every composite that can be built, and correctly marking channels/composites that are legitimately unavailable due to night-time as such (not as errors).
6. All processed outputs and their metadata (timeslot, channel/composite name, file path, generation time, availability status) are stored in a way the UI can query quickly (SQLite — Section 9).
7. The web UI lets the user browse by date, drill into a specific timeslot, view every channel/composite image for that timeslot at full resolution — **each accompanied by a plain-language explanation of what it shows and who uses it** (Section 14) — and see live status of discovery/download/processing jobs (including failures, with the ability to retry).
8. The UI is visually distinctive: a "liquid glass" aesthetic (translucent, blurred, layered panels), and explicitly does not use Bootstrap's or Tailwind's default indigo/violet/purple as the primary color.
9. A person with no prior context — e.g. reviewing this for the internship presentation — can open the app and understand, from the app's own on-screen text, what MSG HRIT is, what this tool does with it, why only a handful of files per date were chosen, and what each product image physically represents, without needing a separate explanation from the developer.
10. The system behaves safely: bounded concurrency, disk-space awareness, and clear visibility into what has been downloaded/processed versus what the full archive contains.
11. A one-click **Run full pipeline** action runs discovery → sample selection → download → processing in sequence (individual step buttons remain available and must keep working).
12. A **day / twilight / night compare** view shows the same product for a date’s three sample roles side by side.
13. The UI shows an **archive connectivity badge** (reachable / unreachable against the configured server).
14. The dashboard shows a **disk usage breakdown** (raw vs processed vs thumbnails, plus catalog size and free space) — not only a single total.

---

## 5. Download scope & per-date sample selection logic

This is the scope decision that replaces the earlier "download everything" instruction, made after running a real size-check crawl (Section 2) that confirmed the full archive is 1,022 files / 276 GB.

**Decision:** for every date that has at least one discovered timeslot, download **exactly three files**, chosen to cover the only three data behaviors that actually matter for this pipeline — a full daytime timeslot, a full nighttime timeslot, and a twilight/terminator timeslot — instead of all ~96 timeslots for that date.

**Why three is enough:** the twelve channels only vary along one meaningful axis for processing purposes — daylight vs. darkness at the imaged location — plus the harder edge case where the solar channels are only partially populated because the terminator is crossing the disk. Downloading every timeslot for a given date repeats these same three scenarios dozens of times without exercising any new behavior; three well-chosen timeslots already cover the full success path (channel/composite generated), the full night-unavailable path, and the ambiguous partial/terminator path.

**Selection rule (implement exactly this, do not approximate differently):**
- Three configurable target times of day: a default **daytime** target (e.g. `09:00`), a default **nighttime** target (e.g. `20:00`), and a default **twilight** target (e.g. `14:00`) — expressed in the same time convention the server's own folder names already use (`HH-MM`), so no timezone conversion is required.
- For each date discovered, and for each of the three target times, select the discovered timeslot on that date whose time is closest to the target, provided it falls within a configurable tolerance window (default 30 minutes). If no timeslot on that date falls within tolerance of a given target, skip that role for that date entirely — do not substitute a different time and do not download an extra file to compensate.
- A date can therefore contribute 0, 1, 2, or 3 downloaded files depending on how much of that date's data actually exists on the server. This is expected and correct on the confirmed partial days (`2026-06-23`, `2026-06-29`, `2026-07-15`) and on the confirmed empty date range (`2026-06-30` through `2026-07-05`, which contributes nothing).
- Discovery itself is unaffected and must still catalog **every** timeslot on the server (Section 10, Step 1) — sample selection only determines which already-discovered timeslots get enqueued for download. This keeps "what exists on the server" fully visible in the UI even though only a subset is ever fetched.
- Record which role a downloaded timeslot fills (`daytime` / `nighttime` / `twilight`) so the UI can label it clearly rather than presenting it as an arbitrary pick (Section 9).

**Expected resulting scope**, based on the confirmed size-check data: roughly 19 dates currently have at least one file on the server, so the realistic download total under this rule is on the order of 50-57 files (~14-15 GB) — a small, fast, iterable dataset rather than the full 276 GB archive. If the archive grows with new dates in the future, this scales linearly and predictably (up to 3 files per new date), not exponentially.

**This is a default policy, not a hard ceiling.** The three target times, the tolerance window, and the "3 per date" count must all be configuration values (Section 12), not hardcoded, so the sampling strategy can be adjusted later without a code change — but the out-of-the-box behavior on first run must be exactly this rule.

---

## 6. High-level architecture

Two services in one repository, started together with a single `npm run dev` from the project root:

- **Backend: Python service.** Owns the server crawling, downloading, satpy-based processing, the SQLite database, and a REST API. Python is required here because satpy (the library that decodes `.nat` files) is Python-only — there is no equivalent Node library, so this is not a stylistic choice, it is a hard technical constraint.
- **Frontend: Next.js (TypeScript) application.** Owns all UI/UX. Talks to the backend exclusively through its REST API (never touches the `.nat` files, the filesystem, or the database directly).
- **Orchestration:** a root-level `package.json` whose `dev` script starts both processes concurrently (one process manager, e.g. `concurrently`, running the frontend's `next dev` and the backend's server process side by side), so the single command `npm run dev` brings up the whole stack. The backend itself remains a normal Python process (its own virtual environment, its own dependency file) — Node is only orchestrating the two processes, not running Python code.
- **Background work:** discovery, downloading, and processing are long-running and must not block API requests. The backend needs an internal job/worker mechanism (a simple background task queue is sufficient — this does not need to be a heavyweight distributed system) so that starting a job returns immediately and progress is reported asynchronously to the UI.

---

## 7. Repository / folder structure

```
project-root/
├── package.json                  # root — only holds the "dev" orchestration script
├── README.md                      # setup + run instructions
├── .gitignore                     # must exclude /data and any venv/.env
│
├── backend/
│   ├── pyproject.toml (or requirements.txt)
│   ├── app/
│   │   ├── main.py                # API entrypoint
│   │   ├── config.py              # all tunables — see Section 12
│   │   ├── db/
│   │   │   ├── models.py          # SQLite schema (see Section 9)
│   │   │   └── session.py
│   │   ├── discovery/
│   │   │   └── crawler.py         # walks HRIT_Native/<year>/<date>/<time>/
│   │   ├── sampling/
│   │   │   └── selector.py        # applies the per-date 3-file rule (Section 5)
│   │   ├── downloader/
│   │   │   └── worker.py          # queue-driven, resumable file fetcher
│   │   ├── processing/
│   │   │   ├── reader.py          # satpy native-format loading
│   │   │   ├── channels.py        # per-channel PNG rendering
│   │   │   └── composites.py      # 5 standard composites
│   │   ├── reference/
│   │   │   └── product_reference.py  # static per-product descriptive content (Section 9)
│   │   ├── jobs/
│   │   │   └── manager.py         # background job orchestration + status
│   │   └── api/
│   │       └── routes/            # discovery, sampling, downloads, processing, browse, jobs
│   └── tests/
│
├── frontend/
│   ├── package.json
│   ├── app/                       # Next.js app router pages (see Section 14)
│   ├── components/
│   │   └── ui/                    # glass-panel primitives (see Section 15)
│   ├── lib/
│   │   └── api-client.ts          # typed wrapper around backend REST API
│   └── styles/
│
└── data/                          # NOT committed to git — see .gitignore
    ├── raw/<YYYY>/<YYYY-MM-DD>/<HH-MM>/msg15.nat
    ├── processed/<YYYY>/<YYYY-MM-DD>/<HH-MM>/<product_name>.png
    ├── thumbnails/<YYYY>/<YYYY-MM-DD>/<HH-MM>/<product_name>_thumb.png
    └── catalog.sqlite3
```

Notes:
- The raw/processed/thumbnail folder layout must mirror the server's own date/time structure exactly, so any given timeslot's files are trivially locatable without a database lookup, even though the database remains the primary access path for the UI.
- Do not restructure this layout — the UI's browse-by-date views are built assuming this exact hierarchy.

---

## 8. Do not initialize git or create a remote repository

Version control for this project is handled separately by the user. Do not run `git init`, do not create commits, and do not connect a remote origin as part of the build process.

---

## 9. Data model (SQLite)

Four tables. Use SQLite because the dataset (a few thousand timeslots at most in the catalog, only dozens actually downloaded) is well within SQLite's comfortable range, and it avoids the operational overhead of running a separate database server for what is a single-user local tool.

**`timeslots`** — every timeslot found by discovery, whether or not it was ever downloaded
- id
- year, date, time (as discovered from the server's own folder names — do not reformat them)
- server_relative_path (the exact path segment used to build the download URL)
- server_reported_size_bytes (captured during discovery, used to verify downloads)
- sample_role: `daytime`, `nighttime`, `twilight`, or `null` — set by the selection logic in Section 5; only non-null rows are ever enqueued for download
- download_status: `discovered` → `queued` → `downloading` → `downloaded` → `failed` (rows with `sample_role = null` simply stay at `discovered` forever, by design)
- local_raw_path (once downloaded)
- discovered_at, downloaded_at
- last_error (nullable — populated on failure, cleared on successful retry)

**`products`** — per-timeslot generated output, only populated for downloaded timeslots
- id
- timeslot_id (references `timeslots`)
- product_name (one of the 12 channel names or 5 composite names)
- product_kind: `channel` or `composite`
- availability_status: `generated`, `unavailable_night`, `unavailable_error`
- local_image_path, local_thumbnail_path (nullable if unavailable)
- generated_at
- error_message (nullable, only for `unavailable_error`)

**`product_reference`** — static, seeded once at build time, not per-timeslot. This is what makes the UI self-explanatory (Section 14): one row per product name (17 rows total — 12 channels + 5 composites), holding the descriptive content shown alongside every image of that product.
- product_name, product_kind
- wavelength_or_spectral_band (plain text, e.g. "0.6 µm visible")
- approximate_resolution
- plain_language_description (2-4 sentences: what this product physically shows)
- agriculture_application, aviation_application, natural_resource_application, disaster_response_application (one to two sentences each — how this specific product is used in that sector)
- This content must be written with real, accurate meteorological/remote-sensing knowledge of the standard SEVIRI channels and standard composite definitions (this is well-documented, publicly available domain knowledge — e.g. what IR_108 shows, what the dust/ash/airmass composites highlight). Do not leave these fields as placeholder or lorem-ipsum text; if uncertain about a specific fact, write a reasonable, clearly-general description rather than inventing a false specific.

**`jobs`**
- id
- job_type: `discovery`, `sampling`, `download`, `processing`, `pipeline`
  - `pipeline` is the one-click orchestrator (Section 14): it runs the four phases in order by reusing the same step runners. It must not replace or break the individual step job types — those remain startable on their own when no pipeline is active.
- scope (e.g. "full catalog", "sample selection", "discover → sample → download → process", or a specific timeslot id if applicable)
- status: `queued`, `running`, `completed`, `failed`, `paused`
- progress_current, progress_total
- started_at, finished_at
- log_summary (short human-readable status line for the UI, not a full log dump)

A timeslot's overall processing status can be derived from whether all its expected products (accounting for night-time unavailability) exist — it does not need its own separate status column beyond what `download_status` and the linked `products` rows already express.

---

## 10. Backend pipeline logic (step by step)

**Step 1 — Discovery.**
Crawl the server starting at `HRIT_Native/`. For each year folder found, for each date folder found inside it, for each time folder found inside that, record the timeslot (and the size of `msg15.nat`, read directly from the directory listing rather than downloaded) into the `timeslots` table with status `discovered`, unless it already exists (discovery must be safely re-runnable — re-running it should pick up newly appeared timeslots on the server without duplicating or disturbing existing rows). This step must not download any `.nat` file — it only reads the lightweight HTML directory listings, and it must catalog the entire tree regardless of the sampling rule in Step 2.

**Step 2 — Sample selection.**
After discovery, run the selection logic from Section 5 against the current catalog: for each distinct date present in `timeslots`, find the closest-matching timeslot to each of the three configured target times (within tolerance) and set that row's `sample_role` accordingly, then its `download_status` to `queued`. Re-running this step after a fresh discovery should only affect newly-discovered dates/timeslots — it must not change the `sample_role` of timeslots already downloaded or in progress.

**Step 3 — Download.**
A background worker pulls `queued` timeslots (i.e. `sample_role is not null`) and downloads each `msg15.nat` to its mirrored path under `data/raw/`. After each download, compare the local file size against `server_reported_size_bytes`; if they don't match, mark the timeslot `failed` with an explanatory error and do not proceed to processing for it. Successful downloads are marked `downloaded`. The worker must respect a configurable maximum concurrency and a configurable minimum delay between requests, since this is hitting an internal server that other tools may also depend on. The worker must be interruptible and resumable: on restart, it should pick up exactly where it left off using the database state, never re-downloading a file already verified as `downloaded`.

**Step 4 — Processing.**
A second background worker picks up `downloaded` timeslots. For each:
- Load the `.nat` file with satpy's native-format reader.
- List which of the 12 channels are actually present/loadable for this timeslot.
- For each of the 12 channels: if loadable, render a labeled PNG (consistent styling — title showing satellite, channel name, and timeslot; appropriate colormap per channel type) plus a smaller thumbnail, and record a `products` row as `generated`. If not loadable because it's a solar-dependent channel during nighttime, record it as `unavailable_night` (no error, no retry needed). If not loadable for any other reason, record it as `unavailable_error` with the underlying message.
- For each of the 5 composites: attempt to build it; same three-way outcome (`generated` / `unavailable_night` / `unavailable_error`) depending on whether the composite's required input channels were present.
- Once all 17 products (12 channels + 5 composites) have a recorded outcome for a timeslot, that timeslot is considered fully processed — this doesn't need a separate flag beyond the `products` rows themselves being complete.

**Step 5 — Serving.**
The API reads from the `timeslots`/`products`/`product_reference` tables and serves image files directly from `data/processed/` and `data/thumbnails/`. The frontend never re-triggers satpy or touches the filesystem — it only calls the API.

---

## 11. Backend API surface (describe endpoints in prose — exact routing/framework conventions are Cursor's implementation detail, but every capability below must exist)

- Trigger a discovery run; get current discovery status/results (total timeslots known across the whole archive, date range covered, total known bytes).
- Get the current sample-selection result: how many timeslots per date were selected and for which role, and how many total files/bytes that amounts to — this must be visible before download starts.
- Trigger the download worker to start/pause/resume; get current download progress (counts by status, bytes downloaded vs. total selected, current throughput).
- Trigger the processing worker to start/pause/resume; get current processing progress (counts by status).
- Trigger / pause a **full pipeline** job that runs discovery → sampling → download → processing sequentially. While a pipeline is active, starting an overlapping individual step must fail with a clear error (not corrupt state). Pausing a phase or the pipeline must be safe and resumable via the existing workers.
- Archive **connectivity** check: lightweight HEAD/GET against the configured archive listing URL (no `.nat` download); returns reachable flag, latency, and error text for the UI badge.
- **Compare** endpoint: given a date and product name, return the daytime / twilight / nighttime sample panels (timeslot + product thumbnail/status or a clear missing reason) plus the list of available product names.
- List timeslots with filtering (by date range, by sample role, by download/processing status) and pagination.
- Get full detail for one timeslot: all 17 products, their availability status, their image/thumbnail URLs, and the matching `product_reference` descriptive content for each.
- Get the full `product_reference` table on its own (for a standalone "about the products" view, independent of any specific timeslot).
- Serve individual processed images and thumbnails as static files.
- List/get job history and status (for the jobs/monitoring view), including the ability to retry a specific failed timeslot's download or processing without restarting everything.
- A summary/dashboard endpoint returning aggregate stats: total timeslots discovered (full archive), total selected for download, total downloaded, total processed, date range covered, **disk usage breakdown** (raw / processed / thumbnails / catalog bytes + free GB), and soft archive reachability fields.

---

## 12. Configuration (must be externally configurable, not hardcoded)

All of the following must live in one clearly documented config location (e.g. environment variables plus a single config file with sane, clearly commented defaults) and must never be hardcoded inside business logic:

- Server base URL (`ARCHIVE_BASE_URL` in local `.env`) and the archive route path (`HRIT_Native/`).
- Local data root directory path.
- The three sample target times (daytime/nighttime/twilight) and the tolerance window, per Section 5.
- The number of files sampled per date (default 3) — must be a single named constant, not scattered magic numbers, so it can be changed later without hunting through the codebase.
- An explicit, off-by-default toggle to fall back to "download everything for a date" instead of the 3-file sample, for the rare case the user wants a full day's worth of data for a specific date later. This must default to **off**.
- Maximum concurrent downloads.
- Minimum delay between successive requests to the server.
- Minimum free disk space to maintain before pausing downloads automatically.
- Backend port and frontend port.

---

## 13. Operational safety rules

- The system must never attempt unlimited-concurrency downloading — concurrency is always bounded by the configured maximum.
- The system must check remaining disk space before each download and pause automatically (not crash, not fail silently) if the configured minimum free space would be violated, surfacing this clearly as a distinct job status in the UI. (Given the confirmed sample scope is only ~15 GB, this is a defensive measure rather than an anticipated real constraint — but it must still exist, since the "download everything" fallback toggle in Section 12 could otherwise fill a disk if ever enabled.)
- Every long-running action (discovery, sampling, download, processing) must be resumable from database state after any interruption (process restart, crash, manual stop) — none of them should need to start over.
- A failed individual timeslot (download or processing) must not halt the overall job — the worker logs the failure against that specific timeslot and continues with the rest of the queue. Failed items must be visible and retriable from the UI.
- Discovery and sample-selection results must both be visible in the UI dashboard before or as soon as downloading begins, so the difference between "what exists on the server" and "what we're actually pulling" is always clear, not hidden inside logs.

---

## 14. Frontend — pages, UX flows, and self-explanatory content requirements

The UI must work as a **standalone explanation of the project**, not just a viewer for images a developer already understands. Anyone opening it cold — including during the internship presentation — should be able to understand the purpose, the data, and the sampling method entirely from what's on screen.

- **Dashboard (home page).**
  - A short, plain-language intro block explaining: what MSG-2/SEVIRI is and what this tool does with it, the four sectors this data supports (agriculture, aviation, natural resource monitoring, disaster response), and — explicitly — why the tool only downloads three timeslots per date instead of the full archive (a one-paragraph version of the Section 5 rationale: daytime/nighttime/twilight cover every processing behavior; the full archive is cataloged but not fully fetched).
  - At-a-glance stats: total timeslots discovered (full archive) vs. total selected for the sample vs. total downloaded/processed, date range covered, storage used, current job activity with progress.
  - **Disk usage breakdown** panel: raw `.nat` bytes, processed PNG bytes, thumbnail bytes, catalog DB size, and free space on the data volume — so “storage used” is interpretable, not a black box.
  - Primary actions here: **Run full pipeline** (and pause pipeline), plus the existing individual actions: run discovery, run/review sample selection, start/pause downloading, start/pause processing. The one-click action must not remove or disable the individual steps permanently — only reject overlapping starts while a pipeline (or that step) is already running.

- **Browse.**
  - A date-first navigation: pick a date (calendar or scrollable date list), see that date's discovered timeslot count **and** how many of the 3 sample roles were actually available for it (e.g. "3/3 sampled", "1/3 sampled — partial day", "0/3 — no data this date"), so a sparse day is self-explanatory rather than looking broken.
  - Click a date to see its selected timeslot(s) with status badges (queued/downloading/downloaded/failed/processed) and their assigned role (daytime/nighttime/twilight).
  - From a selected date, a clear link into the **Compare** view for that date.

- **Compare (day / twilight / night).**
  - Pick a date and a product name; show three panels (daytime, twilight, nighttime) with thumbnail or a worded empty-state (missing role, not yet processed, unavailable_night, error).
  - Links through to the full timeslot viewer / full-resolution image. This view exists to demonstrate why the three-role sample is sufficient — it must not invent new sampling logic.

- **Timeslot detail / product viewer.**
  - A gallery grid of all 17 products (channels + composites) for that timeslot. Every tile shows its name, a thumbnail, and its availability status.
  - Clicking a product opens a full-resolution view **paired with its `product_reference` content**: the plain-language description, wavelength/resolution, and the four sector-application notes, displayed directly alongside the image — this is what makes an individual image self-explanatory rather than just a picture.
  - Products that are `unavailable_night` must render as a clear, worded empty-state (not a blank or broken-looking tile) — e.g. explaining that this channel depends on sunlight and this timeslot falls at night for the imaged region, so no data exists for it here, and that this is expected.
  - Previous/next navigation between a timeslot's three sampled roles (daytime → twilight → nighttime) so the day/night contrast is easy to explore directly, plus a link to the side-by-side Compare view for the same date.

- **Global chrome.**
  - Persistent **archive connectivity badge** in the nav (or equivalent always-visible chrome): green/online when the configured archive listing responds, red/offline otherwise, with latency or error on hover. Clicking may re-check. This must never block page load if the archive is down — badge failure is soft.

- **Product reference / "About the data" view.**
  - A standalone page listing all 17 products with their full reference content (independent of any specific timeslot) — effectively a browsable glossary of every channel and composite, its meaning, and its sector applications. This doubles as the in-app equivalent of a quick-reference guide.
  - Includes a short glossary of terms someone unfamiliar with the domain would need (MSG-2, SEVIRI, IODC disk, terminator/twilight, composite) so the rest of the UI's language is understandable without external context.

- **Jobs & status.**
  - A live view of running/queued/completed/failed jobs (discovery, sampling, download, processing), each with its progress and a way to retry failures at the individual-timeslot level.

- No authentication, no multi-user concerns, no settings-editing UI required for v1 (configuration is edited directly in the backend config, per Section 12) — a read-only display of the active configuration (including the current sample target times) on the dashboard or jobs page is a reasonable nice-to-have, not a requirement.

---

## 15. Frontend — visual design language ("liquid glass")

- Overall aesthetic: layered, translucent, frosted-glass panels over a dark background — soft background blur (backdrop blur), subtle inner/outer glow, gently rounded corners, thin light-catching borders, smooth depth via layered shadows rather than flat cards. Motion should be minimal and smooth (subtle transitions on hover/press), not flashy.
- Base theme: **dark by default.** This suits satellite/IR imagery, which is itself often dark, and avoids a stark white canvas competing with the imagery.
- **Do not use Tailwind's or Bootstrap's default indigo/violet/purple as the primary/accent color.** Choose a distinct accent palette appropriate to a weather/satellite tool — for example a cyan/teal or amber/copper accent against a deep slate/graphite background — and apply it consistently across buttons, active states, and highlighted data. The exact hex values are Cursor's implementation choice as long as the primary accent is clearly not violet/purple/indigo.
- Typography: a clean modern sans-serif (system font stack or a widely available one such as Inter), generous whitespace, clear hierarchy between page titles, section labels, explanatory copy, and data — explanatory text (Section 14) needs its own clearly distinct, comfortably readable style so it reads as guidance rather than as a caption or afterthought.
- Componentize the glass panel as a reusable primitive (e.g. a `GlassPanel`/`GlassCard` component), and componentize the explanatory-content block (used on the dashboard intro, the product viewer, and the reference page) as its own reusable primitive too, so self-explanatory copy is presented consistently everywhere it appears rather than styled ad hoc per page.
- Status indicators (discovered/queued/downloading/downloaded/failed/processed, generated/unavailable_night/unavailable_error) need clear, distinct, colorblind-considerate visual treatment (color plus icon/label, not color alone).
- Content tone: explanatory copy throughout the app should be written in plain, direct language for someone with general technical literacy but no prior familiarity with satellite meteorology — avoid unexplained jargon; when a domain term is used (e.g. "terminator," "composite," "IODC disk"), it should either be briefly defined in place or linked to the glossary on the reference page.

---

## 16. Build order (milestones for Cursor to follow)

1. Scaffold the repo structure from Section 7, with the root `npm run dev` successfully starting an empty backend and an empty frontend side by side.
2. Backend: implement the `timeslots`/`products`/`product_reference`/`jobs` schema, seed the 17 `product_reference` rows with real descriptive content, and a health-check API endpoint; confirm the frontend can call it.
3. Backend: implement discovery (Step 1) against the real server and confirm the full catalog fills in correctly for a small manual test before running it against the whole tree.
4. Backend: implement sample selection (Step 2) per Section 5 and verify against the confirmed known dates (e.g. `2026-06-23` should yield fewer than 3 selected roles, `2026-06-30` through `2026-07-05` should yield none, a full day like `2026-07-08` should yield exactly 3).
5. Backend: implement the download worker (Step 3) for a single timeslot end-to-end (queue → download → size verification → status update), then extend to the full sample queue with concurrency/throttling/disk-space guards from Section 13.
6. Backend: implement processing (Step 4) for a single downloaded timeslot end-to-end (all 12 channels + 5 composites, correct day/night handling), then extend to the full sample queue.
7. Backend: complete the remaining API endpoints from Section 11.
8. Frontend: build the glass-panel and explanatory-content design primitives first (Section 15), then the Dashboard (including Run full pipeline, disk breakdown, connectivity badge), then Browse, then Compare, then the Timeslot/product viewer, then the Product reference page, then Jobs & status.
9. End-to-end pass: run discovery against the real archive, confirm the dashboard shows both the full catalog size and the (much smaller) sample size correctly, then run download + processing on the real sample set (or via Run full pipeline) and verify every product tile — including night-unavailable ones — displays correctly with its reference content. Confirm Compare shows day/twilight/night for at least one full sample date, and that individual step buttons still work when no pipeline is running.

---

## 17. Assumptions log

This section exists so no assumption is silently made without being visible. Current resolved assumptions:

- **Reader/format:** satpy's native-format reader is used for `.nat` files (confirmed from directory listing evidence and the assignment's own wording — Section 2). Not an open question.
- **Archive scope:** superseded — originally "download everything," now explicitly a curated 3-files-per-date sample (Section 5), decided by the user after seeing the real 276 GB / 1,022-file size-check result.
- **Storage:** local disk for files, SQLite for metadata/status, confirmed by the user directly.
- **Backend/frontend split:** Python backend (required by satpy) + Next.js frontend, run together via a root `npm run dev` orchestration script — left to best-approach judgment, resolved as the recommended architecture for this exact combination of constraints.
- **Self-explanatory UI:** the user explicitly asked for the UI/UX to describe the tool's whole purpose itself — resolved as the `product_reference` table plus the dashboard/reference-page content requirements in Section 14, rather than relying on the (out-of-scope) Word documents for explanation.
- **Demo UX extras (additive):** one-click pipeline, day/twilight/night compare, archive connectivity badge, and disk usage breakdown were added as presentation helpers. They reuse existing workers/APIs and must not change sampling rules, download defaults, or remove the individual pipeline step controls.

If Cursor encounters a genuine gap not covered above or in Sections 1–16, it should stop and ask rather than filling the gap with an unstated assumption.
