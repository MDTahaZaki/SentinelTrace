# SentinelTrace

**SIH 2026 · SIH26151: Dark Web Threat Actor De-anonymization (hackathon demo)**

SentinelTrace links threat-actor personas across dark-web marketplaces and forums. It uses
hard identifiers (PGP keys, BTC wallets), weaker infrastructure overlaps (SSL certs, server
banners) and **stylometry**, which can re-identify a "migrated persona" that shares no key
or wallet with anything else.

> **Synthetic data only.** The demo runs fully offline on a local JSON fixture
> (`data/seed_footprints.json`). Every handle, key, wallet and post in it is fictional.
> There is no code that connects to Tor, onion services or any live marketplace.

---

## Run it

Requires Python 3.11+ (tested on 3.14).

**First-time setup** (needs internet once, for `pip`):

```powershell
cd C:\SIH\demo
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

<sub>macOS/Linux: `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`</sub>

**Start the demo** (one command, works offline):

```powershell
.venv\Scripts\python -m uvicorn app.main:app --port 8000
```

Then open **http://127.0.0.1:8000** and click **▶ Run pipeline**.

Stop the server with `Ctrl+C`. Each restart begins with an empty pipeline.

### Pre-flight checklist (do this before leaving for the venue)

- [ ] `static\vendor\vis-network.min.js` exists (~690 KB). The graph library is stored locally
      in the project, so the demo does not need Wi-Fi.
- [ ] Turn Wi-Fi **off**, start the server, run the pipeline once: the graph must still render.
- [ ] `.venv\Scripts\python -m app.correlation` prints the similarity matrix with
      GhostMerchant ↔ silent_quill ≈ 0.82 and every noise pair < 0.10.

---

## How it works

The four stages match the architecture slide. Each one is a separate module and a separate
API call, so the UI can run them one at a time.

| Stage | Module | What it does |
|---|---|---|
| 1. Acquisition | `app/acquisition.py` | Loads the 15 synthetic footprints from 3 fake sources (ShadowBazaar, NullForum, CryptVault). |
| 2. Normalise / Store | `app/normalise.py` | PGP fingerprints → upper-case hex, no spaces; bech32 wallets → lower-case. Two matches only exist after this step. |
| 3. Correlation Engine | `app/correlation.py` | Builds a `networkx` identity graph and scores every pair of footprints. |
| 4. Attribution | `app/pipeline.py` | Groups handles into actors (by hard links) and flags lone personas with a strong stylometry link as *suggested aliases*. |

### Confidence scoring

| Signal | Confidence | Notes |
|---|---|---|
| Shared PGP fingerprint | 95 | hard link, merges handles into one actor |
| Shared BTC wallet | 90 | hard link, merges handles into one actor |
| Shared SSL cert CN | 40 | weak, supporting only |
| Shared server banner | 15 | very weak: stock banners like `nginx/1.24.0` are common |
| Stylometry ≥ 0.70 | similarity × 100 | suggested link, needs analyst review |

Multiple signals on the same pair combine with **noisy-OR**, `1 − Π(1 − cᵢ)`. Independent
evidence reinforces, but confidence never reaches 100: attribution is never certain.
Links below 30 are not shown.

**Stylometry**: TF-IDF over character 3–5-grams (`char_wb`), case preserved, cosine
similarity. On 2–3 sentence samples character n-grams catch spelling, punctuation and casing
habits (`recieve`, `guarenteed!!`, `sry ~`) that word-level models miss.

### API

| Method | Path | |
|---|---|---|
| GET | `/api/pipeline` | stage status |
| POST | `/api/pipeline/{acquire\|normalise\|correlate\|attribute}` | run the next stage |
| POST | `/api/pipeline/reset` | clear all results |
| GET | `/api/actors?q=&date_from=&date_to=&expand=` | actor profiles (search) |
| GET | `/api/graph` | nodes + edges |
| GET | `/api/export.csv`, `/api/export.json` | current result set (same filters) |

Interactive API docs: http://127.0.0.1:8000/docs

## Project layout

```
app/        FastAPI backend: acquisition, normalise, correlation, pipeline, export, main
data/       seed_footprints.json (synthetic)
static/     index.html, app.js, styles.css, vendor/vis-network.min.js
DEMO.md     3-minute click-through for the pitch
```
