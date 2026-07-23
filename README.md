# MSG HRIT Terrestrial Archive Explorer

Local full-stack tool that catalogs the SATMET **MSG HRIT Terrestrial Archive** (`HRIT_Native/`), downloads a curated **3-files-per-date** sample (daytime / twilight / nighttime), processes each `.nat` file into SEVIRI channel + composite PNGs with satpy, and serves a self-explanatory liquid-glass web UI.

## Requirements

- Node.js 20+ (npm)
- Python 3.10+
- Network access to your MSG HRIT archive server (set `ARCHIVE_BASE_URL` in local `.env`)
- Disk: ~15 GB free for the default sample set (plus processing outputs)

## Setup

```bash
# From project root
npm install
cd frontend && npm install && cd ..

cd backend
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
# source .venv/bin/activate
pip install -r requirements.txt
cd ..

copy .env.example .env   # Windows; or: cp .env.example .env
```

All tunables live in `.env` / `backend/app/config.py` (sample target times, concurrency, disk floor, archive URL). Do not hardcode them in business logic.

## Run

```bash
npm run dev
```

This starts:

- Backend API — `http://127.0.0.1:8000` (docs at `/docs`)
- Frontend UI — `http://127.0.0.1:3000`

On Windows, the default backend script runs **without** uvicorn `--reload` so file-watch restarts do not tear down the frontend via `concurrently`. Use `npm run dev:backend:reload` if you want hot-reload on the API alone.

## Typical workflow

1. Open the dashboard → **Run discovery** (catalogs every timeslot; downloads nothing).
2. **Run sample selection** — assigns daytime / twilight / nighttime roles (prefer within tolerance; otherwise nearest available file on that date).
3. Confirm the dashboard shows **full archive size** vs **sample size**.
4. **Start download**, then **Start processing**.
5. Browse dates → timeslot → product gallery (with plain-language reference text).

## Out of scope

SatDump manual stitching, Word report deliverables, other server routes, Colab, auth, cloud deploy — see `BUILDPLAN.md`.

## Layout

See `BUILDPLAN.md` §7. Data lives under `/data` (gitignored): `raw/`, `processed/`, `thumbnails/`, `catalog.sqlite3`.
