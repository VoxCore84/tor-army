# Tor Army v3

Massively parallel async web scraper that routes through a fleet of Tor instances for IP diversity. Built for scraping Cloudflare-protected sites where cloud IPs get instantly blocked.

I originally built this to scrape [Wowhead](https://www.wowhead.com/) for [TrinityCore](https://www.trinitycore.org/) private server data. The 39 entity parsers and ID list generator are Wowhead-specific, but the scraping engine works for any target — see [Adapting to Other Targets](#adapting-to-other-targets).

## Why Tor?

Cloudflare blocklists all major cloud IP ranges (AWS, GCP, Azure, etc.). I [tried Lambda first](https://github.com/VoxCore84/lambda-swarm) — 3,000 concurrent Lambdas with perfect browser TLS fingerprints. 90% WAF rate. The same fingerprints through Tor? Under 1%.

Tor exit nodes run on residential ISPs, university networks, and volunteer hosts. Cloudflare doesn't blocklist them the way it does datacenters.

**Measured performance:** 500K+ pages/hr at 400 Tor instances on a single machine. Under 1% Cloudflare block rate.

## Features

- **HTTP/2 multiplexing** — shared session per Tor instance, workers send concurrent streams on one connection
- **Async engine** — `asyncio` + `curl_cffi`, no GIL bottleneck
- **Browser TLS fingerprints** — 7 profiles (Chrome, Edge, Safari, Firefox) via `curl_cffi`
- **Adaptive WAF throttling** — adjusts delay based on real-time block rate
- **Circuit rotation** — fresh exit IP every 150 requests per instance
- **HTML caching** — gzip-compressed raw HTML for re-parsing without re-scraping
- **39 Wowhead entity parsers** — spells, items, NPCs, quests, transmog, and more

## Quick Start

### 1. Install

```bash
pip install -e .
```

Requires Python 3.11+. On Windows, use `python` not `python3` (the Windows Store alias uses separate site-packages).

### 2. Install Tor

**Windows:** Download the [Tor Expert Bundle](https://www.torproject.org/download/tor/) (not the Browser). Extract so you have `tor/tor.exe`.

**Linux:** `sudo apt install tor` (Debian/Ubuntu) or `sudo dnf install tor` (Fedora).

**macOS:** `brew install tor`

Tell the scraper where Tor is:

```bash
# Option A: put the Expert Bundle next to the script
tor-army/
  tor_army.py
  tor/              # Tor Expert Bundle extracted here
    tor/tor.exe     # or tor/tor on Linux/Mac
    data/geoip
    data/geoip6

# Option B: flag or env var
python tor_army.py --tor-dir /path/to/tor ...
export TOR_DIR=/path/to/tor
```

### 3. Generate ID lists

The scraper reads ID lists from `id_lists/{target}.txt` (one ID per line). For Wowhead, generate these from [Wago DB2 CSV exports](https://wago.tools/db2):

```bash
python generate_id_lists.py --csv-dir /path/to/wago-csvs/
python generate_id_lists.py --csv-dir /path/to/wago-csvs/ --stats    # preview only
```

For non-Wowhead targets, just create the text files yourself — one ID per line.

### 4. Scrape

```bash
# Default: 400 Tor instances x 5 workers = 2,000 concurrent
python tor_army.py --start-tor --targets spell,item,npc,quest

# Smoke test
python tor_army.py --start-tor --workers 5 --smoke 10 --targets npc

# Aggressive
python tor_army.py --start-tor --workers 600 --multiplier 8 --targets all

# Check progress
python tor_army.py --list-targets

# Re-parse cached HTML offline
python tor_army.py --targets npc --reparse

# Kill leftover Tor processes
python tor_army.py --kill-tor
```

Output goes to `wowhead_data/{target}/raw/` (JSON) and `wowhead_data/{target}/html/` (gzip HTML). Already-scraped IDs are skipped automatically.

## How It Works

Each Tor instance gets one shared HTTP/2 connection. Multiple workers send concurrent requests as HTTP/2 streams on that connection. This gives you N workers per instance but only 1 file descriptor per instance.

Five throttling layers prevent WAF blocks:

1. **Per-instance rate limiter** — minimum interval between requests from the same exit IP
2. **Adaptive delay** — backs off based on WAF hits per minute
3. **Circuit rotation** — new exit IP every 150 requests
4. **Jittered exponential backoff** — on consecutive errors
5. **WAF-triggered rotation** — immediate circuit reset on 403

## Configuration

| Flag | Default | Description |
|------|---------|-------------|
| `--workers` | 400 | Tor instances (~25MB RAM each) |
| `--multiplier` | 5 | Workers per instance (HTTP/2 streams) |
| `--delay` | 0.15 | Base delay between requests (seconds) |
| `--per-circuit` | 150 | Requests before circuit rotation |
| `--cache-html` | true | Cache raw HTML as gzip |
| `--targets` | npc | Comma-separated entity types |
| `--tor-dir` | `./tor/` | Tor installation path (or `TOR_DIR` env var) |

## Scaling

| Config | Workers | RAM | Rate |
|--------|---------|-----|------|
| 400x5 | 2,000 | ~10 GB | ~500K+/hr |
| 600x5 | 3,000 | ~15 GB | ~600-800K/hr |
| 600x8 | 4,800 | ~15 GB | ~700K-1M/hr |

Returns diminish past ~600 instances. There are only ~1,000-1,500 Tor exit nodes globally — past that you're sharing exit IPs between instances and hitting the same Cloudflare rate limits.

## Adapting to Other Targets

The Wowhead parsers and ID generator are specific to my use case. The scraping engine is not. To scrape a different site:

1. **`TARGET_CONFIGS`** in `tor_army.py` — change URL patterns
2. **`parsers.py`** — replace with your own HTML parsers, or skip parsing and just cache raw HTML
3. **`id_lists/{target}.txt`** — create your own ID/URL lists (one per line)
4. **WAF detection** — the code looks for HTTP 403 and `cf-challenge` in the response, which is Cloudflare-specific. Adjust `async_worker()` for other WAFs

Everything else — Tor fleet management, HTTP/2 multiplexing, circuit rotation, rate limiting, the live dashboard — is target-agnostic.

## Requirements

- Python 3.11+
- Windows, Linux, or macOS
- [Tor](https://www.torproject.org/download/tor/)
- ~25 MB RAM per Tor instance

## License

MIT
