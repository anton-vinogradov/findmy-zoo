# findmy-zoo 📍

**English** | [Русский](README.ru.md)

A self-hosted map of where all your Apple things have been over the last day. Every
few minutes it polls Apple, accumulates the track in SQLite (a rolling 24-hour window)
and draws it on a map (Leaflet) — one colored line and a "last seen" marker per entity.

Installs as a single systemd service, all code is public, and **every secret (Apple ID,
tag keys, sessions) lives only in a local config on the server and never reaches the repo.**

## What it tracks (and what actually works)

| Layer | Source | 24-hour history | Status |
|---|---|---|---|
| 🟠 **Tags** — AirTags and DIY tags (OpenHaystack) | [FindMy.py](https://github.com/malmeloo/FindMy.py) + anisette | ✅ served by Apple (`fetch_location_history`) | working |
| 🔵 **Devices** — iPhone/Mac/Watch/AirPods from Find My | [pyicloud](https://github.com/picklepete/pyicloud) `api.devices` | ⚠️ current point only → we build the track by polling | working |
| 🟢 **People** — who shares their location via Find My | — | — | **unavailable, see below** |

### About the "People" layer

Apple no longer exposes a public "Find My Friends" API — it was folded into Find My long
ago and the old `fmf` endpoint is closed. In [pyicloud](https://github.com/picklepete/pyicloud)
the friends service is stuck in an unmerged PR. So **the people layer cannot be built with
supported open libraries in 2026**, and no fake module was added. A clean extension point is
left in place (`sources.icloud.people.enabled=false`): if a working method appears (or you
push your family's locations yourself from an iOS Shortcut), it drops in as a single source
in `collector/sources.py`.

## Ethics and boundaries 🔒

Only **your own** things, and only people who **themselves** shared their location with you in
Find My. This is a tool for your own devices/tags and consenting close ones — not for tracking
strangers. Apple also has anti-stalking protection for exactly this. No third-party keys or
accounts.

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/anton-vinogradov/findmy-zoo/main/install.sh | bash
# or as root:  … | sudo bash
```

install.sh: venv + dependencies, copies `config.json` from the example, brings up a
**macless anisette container** (`dadoum/anisette-v3-server` on `127.0.0.1:6969`, docker/podman),
registers the systemd service `findmy-zoo` on port **8815** and installs the setup command.

Then — **one step**, the setup wizard:

```bash
findmy-zoo-setup
```

It asks for your Apple ID + password + 2FA code (once — this is Apple's protection and can't
be bypassed; the password goes only into a cached session on disk, never into the repo/config).
It logs in your devices, optionally your tags, writes `appleId` into the config and restarts the
service. You can re-run it anytime (e.g. to enable tags later or refresh the session).

<sub>Under the hood it's `collector/setup.py`; if you prefer, the same steps can be done
piecemeal via `collector/login.py apple|tags`.</sub>

## Configuring tags

Put AirTag/DIY keys into `data/tags/*.json` (FindMy.py format — you can convert them from
OpenHaystack/macless-haystack, see the examples in the FindMy.py repo) and list them in
`collector/config.json`:

```json
"accessories": [
  { "name": "Keys",    "file": "data/tags/keys.json" },
  { "name": "Backpack", "b64key": "<base64-private-key>" }
]
```

Don't want the container? Set `sources.tags.anisetteUrl: null` and FindMy.py will generate
anisette in-process.

## How it works

```
collector/hub.py      — background source polling + HTTP (stdlib) + /api/points
collector/sources.py  — TagSource (FindMy.py) and IcloudSource (pyicloud)
collector/store.py    — SQLite, dedup by (entity_id, ts), retentionH window
collector/setup.py    — one-command setup wizard (findmy-zoo-setup)
collector/login.py    — piecemeal Apple login (apple|tags), for manual mode
index.html/app.js/... — Leaflet map, filter by type, auto-refresh every 30 s
install.sh            — systemd + macless anisette container
```

Map tiles come from OpenStreetMap by default (the server needs internet). Everything else is
local/offline.

## Data privacy

`data/history.db`, Apple sessions and tag keys are in `.gitignore` and are not served over
HTTP (`/data` and `/collector` are blocked). Only the code is public.
