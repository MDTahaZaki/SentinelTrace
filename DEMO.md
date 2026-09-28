# SentinelTrace: 3-minute demo script

Every step is **one click → one sentence**. The quoted lines are suggested narration;
say them in your own words.

## Before judges arrive

1. Wi-Fi off (proves it's offline). Start the server:
   `.venv\Scripts\python -m uvicorn app.main:app --port 8000`
2. Open http://127.0.0.1:8000 in a **full-screen, foreground** Chrome window.
   Browsers slow down animations in background tabs.
3. If a previous run is on screen, click **↺ Reset**. The page should show an empty graph.
4. Use **Step ›** to control the pace while you talk. **▶ Run pipeline** plays all
   four stages automatically in about 8 seconds, which is good for a quick replay.

---

## 0:00 – 0:20 · Set-up

> "Threat actors on the dark web burn their handles and reappear under new ones. SentinelTrace
> links those personas back together. Everything you'll see runs offline on synthetic data:
> no live dark-web access."

Point at the yellow **SYNTHETIC DATA · OFFLINE DEMO** badge.

## 0:20 – 0:40 · Stage 1: Acquisition. Click **Step ›**

15 nodes appear, coloured by source.

> "Our collectors have gathered 15 vendor footprints from three marketplaces and forums:
> handles, PGP keys, wallets, certificates, and how each vendor writes."

## 0:40 – 1:00 · Stage 2: Normalise. Click **Step ›**

Two pairs of nodes flash. The log shows two lines in yellow.

> "The same wallet appears in upper case on one market and lower case on another; the same
> PGP key with and without spaces. Without this cleaning step, those matches are invisible."

## 1:00 – 1:40 · Stage 3: Correlation. Click **Step ›**

Links draw in, strongest first: two red hard links, then the **dashed yellow 82**, then a grey 49.

> "Red is hard evidence. **v3nom_x** on ShadowBazaar and **GhostMerchant** on CryptVault
> share a wallet: 98 confidence."
>
> "Now the important one. This dashed line links GhostMerchant to **silent_quill** on NullForum.
> They share *no* key, *no* wallet, *nothing*. The link comes purely from writing style."

**Click the dashed 82 edge.** The evidence panel shows both writing samples with the shared
tics highlighted.

> "Character-level stylometry picks up habits people don't think about: 'recieve', 'guarenteed!!',
> 'sry ~'. That scores 0.82. Every unrelated pair in the dataset scores below 0.10."

## 1:40 – 2:10 · Stage 4: Attribution. Click **Step ›**

Nodes recolour by actor. silent_quill gets a dashed orange ring and reads *alias? ACTOR-001*.

> "Fifteen handles collapse into thirteen actors. ACTOR-001 now spans three marketplaces.
> silent_quill is flagged as a *suggested* alias: a lead for an analyst, not a conviction."

## 2:10 – 2:40 · Search + table

Scroll to the table. Type `bc1qv3n` (the start of the shared wallet) in the search box.

> "An investigator with one wallet address gets the full footprint: both confirmed personas
> plus the suggested alias, with confidence and the reason for every link."

Optional: click the **silent_quill** row to jump to it in the graph.

## 2:40 – 3:00 · Export + close

Click **⤓ CSV** (or **⤓ JSON**).

> "Everything exports as evidence-ready CSV or JSON for case files. SentinelTrace: hard
> identifiers, infrastructure overlap, and AI stylometry, so burned handles don't mean
> a burned trail."

---

## Likely judge questions

**"Why is the wallet link 98 and not 100?"**
Signals combine with noisy-OR, `1 − Π(1 − cᵢ)`: wallet (90) and style (76) add up to 98.
Attribution is never certain, so confidence never reaches 100; we don't claim proof.

**"Couldn't stylometry just match people who sell the same thing?"**
It uses character n-grams with case preserved, so it responds to *habits*, not topic.
DarkPharma and rx_kingpin sell the same product and score 0.04 on style.

**"Why isn't CardKing ↔ dumps_depot a confirmed actor?"**
A shared SSL certificate and server banner only give 49. Infrastructure can be shared hosting,
so it stays a weak link. Only keys and wallets merge actors.

**"Is this real dark-web data?"**
No. It's a synthetic fixture built to show the method. A production deployment would run
sandboxed collectors under legal authorisation. The correlation engine is the same.

**"Why vanilla JS and not React?"**
Zero-build prototype that runs with one command. The production UI would be React.

## If something goes wrong

- **Graph looks tangled:** drag a node, or click **↺ Reset** then **▶ Run pipeline**.
- **Page shows an error in the log:** restart the server (`Ctrl+C`, run the command again) and refresh.
- **Refreshing the page mid-demo** is safe: it restores whatever stages have already run.
