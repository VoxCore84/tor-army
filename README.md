# Tor Army v3

Massively parallel async web scraper that routes through a fleet of Tor instances for IP diversity. Built for scraping Cloudflare-protected sites where cloud IPs (AWS Lambda, GCP, etc.) get instantly blocked.

**500K-1M pages/hour. Under 1% WAF block rate. Zero cost. One machine.**

## Why You Need This

Every other approach to scraping Cloudflare-protected sites at scale either doesn't work or costs a fortune:

| Approach | Speed | WAF Block Rate | Monthly Cost | Verdict |
|----------|-------|----------------|-------------|---------|
| **Tor Army** | **500K-1M/hr** | **<1%** | **$0** | Works |
| Rotating proxy service (Bright Data, Oxylabs) | ~100K/hr | ~5-15% | $300-1,000+ | Works but expensive |
| Residential proxy pool | ~50K/hr | ~5% | $50-500 | Works but expensive |
| AWS Lambda / GCP Functions | 2,500/hr | **90%+** | $25+ | **Doesn't work** |
| Datacenter proxies | ~10K/hr | **80%+** | $20-100 | **Doesn't work** |
| Selenium / Playwright | ~500/hr | ~10% | $0 | Too slow to scale |
| Scrapy + free proxies | ~5K/hr | ~50%+ | $0 | Unreliable |

**Why Tor works when everything else doesn't:**

Cloudflare maintains blocklists of known datacenter IP ranges — AWS, GCP, Azure, DigitalOcean, Hetzner, OVH, all of them. Your Lambda has a perfect Chrome TLS fingerprint? Doesn't matter. The IP is flagged before the request even reaches the server.

Tor exit nodes are different. They're run by volunteers on residential ISPs, university networks, and privacy-focused hosts worldwide. Cloudflare sees ~1,500 diverse IPs from across the globe — not a datacenter block. The same browser fingerprint impersonation that gets 90% WAF'd from AWS gets **under 1% WAF'd** through Tor.

We know because [we built the Lambda version first](https://github.com/VoxCore84/lambda-swarm). 3,000 concurrent Lambdas across 3 AWS regions, perfect `curl_cffi` browser fingerprints, zstd compression, the works. Cloudflare didn't care. 90% blocked. Switched to Tor with the same fingerprints? Under 1%.

**The IP matters more than the fingerprint.**

## Features

- **HTTP/2 multiplexing** — shared session per Tor instance, workers send concurrent streams on one TCP connection (400 FDs instead of 2,000+)
- **Async engine** — `asyncio` + `curl_cffi` eliminates GIL bottleneck
- **Worker multiplexing** — N async workers per Tor instance (default 5x)
- **Browser TLS fingerprints** — 7 profiles (Chrome, Edge, Safari, Firefox) via `curl_cffi`
- **Adaptive WAF throttling** — auto-adjusts delay based on real-time block rate per minute
- **Per-instance rate limiting** — prevents WAF bursts from shared exit IPs
- **Circuit rotation** — fresh IP every 150 requests per instance
- **Windows `select()` bypass** — monkey-patches the 512 FD limit as safety net for extreme configs
- **Live dashboard** — real-time rate, WAF/min, per-target breakdown, ETA
- **HTML caching** — gzip-compressed raw HTML for re-parsing without re-scraping
- **39 Wowhead entity parsers** — spells, items, NPCs, quests, transmog, and 34 more

## Quick Start

### 1. Install dependencies

```bash
pip install -e .
```

Requires Python 3.11+. On Windows, use `python` (not `python3` — the Windows App alias has a separate `site-packages` that won't have your installed packages).

### 2. Install Tor Expert Bundle

Download the **Expert Bundle** (not the Browser) from [torproject.org](https://www.torproject.org/download/tor/). Extract it so you have a directory with `tor/tor.exe` inside.

By default, Tor Army looks for a `tor/` directory next to `tor_army.py`. You can override this:

```bash
# Option A: put Tor next to the script
tor-army/
  tor_army.py
  tor/            # <-- Tor Expert Bundle here
    tor/tor.exe
    data/geoip
    data/geoip6

# Option B: use a flag
python tor_army.py --tor-dir /path/to/tor-expert-bundle ...

# Option C: use an environment variable
export TOR_DIR=/path/to/tor-expert-bundle
```

### 3. Generate ID lists

The scraper needs ID lists to know which pages to fetch. These are generated from Wago DB2 CSV exports.

```bash
# Export CSVs from https://wago.tools/db2 (or extract from client data files)
# Place them in a directory — expected naming: {TableName}-enUS.csv

python generate_id_lists.py --csv-dir /path/to/wago-csvs/

# Generate for specific targets only
python generate_id_lists.py --csv-dir /path/to/wago-csvs/ --targets npc,quest

# Preview counts without writing files
python generate_id_lists.py --csv-dir /path/to/wago-csvs/ --stats
```

### 4. Scrape

```bash
# Launch with defaults (400 Tor instances x 5 workers = 2,000 concurrent)
python tor_army.py --start-tor --targets spell,item,npc,quest

# Smoke test (10 pages, 5 instances)
python tor_army.py --start-tor --workers 5 --smoke 10 --targets npc

# Aggressive config (4,800 concurrent workers)
python tor_army.py --start-tor --workers 600 --multiplier 8 --targets all

# List available targets with progress
python tor_army.py --list-targets

# Re-parse cached HTML without network
python tor_army.py --targets npc --reparse

# Kill leftover Tor instances
python tor_army.py --kill-tor
```

Output goes to `wowhead_data/{target}/raw/` (parsed JSON) and `wowhead_data/{target}/html/` (cached gzip HTML). The scraper automatically skips IDs that already have output files, so you can stop and resume freely.

## How It Works

### HTTP/2 Multiplexing

Most Tor scrapers create one TCP connection per request — wasteful and FD-hungry. Tor Army shares a single HTTP/2 connection per Tor instance. Multiple workers send concurrent requests as **HTTP/2 streams** on that one connection.

This means:
- **400 Tor instances = 400 file descriptors** (not 2,000)
- Windows `select()` 512 FD limit is no longer a bottleneck
- TLS handshake overhead amortized across all workers per instance
- You can crank the multiplier to 8-10 without hitting OS limits

```
                    ┌── Worker 1 ──┐
                    │── Worker 2 ──│── HTTP/2 streams ──▶ 1 TCP connection ──▶ Tor SOCKS5
                    │── Worker 3 ──│                      (1 file descriptor)
                    │── Worker 4 ──│
                    └── Worker 5 ──┘
```

### Five-Layer Throttle Stack

Each layer prevents a different failure mode:

| Layer | What | Why |
|-------|------|-----|
| **Per-instance rate limiter** | Min interval between requests from same exit IP | Prevents Cloudflare per-IP rate limits |
| **Adaptive delay** | Adjusts based on WAF hits/minute across all workers | Backs off when Cloudflare gets suspicious |
| **Circuit rotation** | New exit IP every 150 requests | Prevents long-term IP reputation damage |
| **Jittered backoff** | Exponential backoff on consecutive errors | Handles Tor circuit failures gracefully |
| **WAF-triggered rotation** | Immediate circuit + session reset on 403 | Abandons burned IPs instantly |

### Architecture

```
┌─────────────────────────────────────────────────┐
│  Tor Army Orchestrator (asyncio event loop)     │
│                                                 │
│  ┌─────────┐ ┌─────────┐       ┌─────────┐    │
│  │Worker 1 │ │Worker 2 │  ...  │Worker N │    │
│  │(async)  │ │(async)  │       │(async)  │    │
│  └────┬────┘ └────┬────┘       └────┬────┘    │
│       │           │                 │          │
│  ┌────┴────┐ ┌────┴────┐       ┌───┴─────┐   │
│  │  Tor    │ │  Tor    │  ...  │  Tor    │   │
│  │Instance1│ │Instance1│       │InstanceN│   │
│  │(HTTP/2) │ │(HTTP/2) │       │(HTTP/2) │   │
│  └────┬────┘ └────┬────┘       └────┬────┘   │
└───────┼───────────┼─────────────────┼─────────┘
        │           │                 │
   ┌────┴────┐ ┌────┴────┐      ┌────┴────┐
   │  Tor 1  │ │  Tor 1  │ ...  │  Tor N  │
   │SOCKS5h  │ │SOCKS5h  │      │SOCKS5h  │
   │:9050    │ │:9050    │      │:9050+2N │
   └────┬────┘ └────┬────┘      └────┬────┘
        │           │                 │
   [Exit Node A] [Exit Node A]  [Exit Node Z]
        │           │                 │
        └───────────┴────────┬────────┘
                             │
                    ┌────────┴────────┐
                    │   Cloudflare    │
                    │  (WAF / CDN)   │
                    └────────┬────────┘
                             │
                    ┌────────┴────────┐
                    │   Target Site   │
                    └─────────────────┘
```

Workers sharing a Tor instance send HTTP/2 streams on a single multiplexed connection, reducing FD count from N-per-instance to 1-per-instance. Rate limiting prevents WAF bursts per exit IP. Each instance rotates circuits every 150 requests for IP freshness.

## Configuration

| Flag | Default | Description |
|------|---------|-------------|
| `--workers` | 400 | Tor instances to run (~25MB RAM each) |
| `--multiplier` | 5 | Async workers per instance (HTTP/2 streams) |
| `--delay` | 0.15 | Base delay between requests (seconds) |
| `--per-circuit` | 150 | Requests before circuit rotation |
| `--max-waf` | 3 | WAF hits before forced rotation |
| `--cache-html` | true | Cache raw HTML as gzip |
| `--targets` | npc | Comma-separated entity types |

## Scaling Guide

| Config | Workers | FDs | RAM | Expected Rate |
|--------|---------|-----|-----|---------------|
| 400x5 | 2,000 | 400 | ~10 GB | ~500K+/hr |
| 400x8 | 3,200 | 400 | ~10 GB | ~600-700K/hr |
| 600x5 | 3,000 | 600 | ~15 GB | ~600-800K/hr |
| 600x8 | 4,800 | 600 | ~15 GB | ~700K-1M/hr |
| 800x5 | 4,000 | 800 | ~20 GB | ~650-850K/hr |

### Why returns diminish

The ceiling isn't your hardware — it's **Tor exit node diversity**. There are only ~1,000-1,500 Tor exit nodes globally. At ~600 instances, you've covered ~40% of them. Past that, new instances increasingly share exit IPs with existing ones, so you're hitting the same Cloudflare rate limits from the same IPs.

| Instances | Exit Node Coverage | Value |
|-----------|-------------------|-------|
| 400 | ~27% | Sweet spot — good diversity, low overhead |
| 600 | ~40% | Diminishing returns start |
| 800 | ~53% | Significant IP overlap |
| 1,500 | ~100% | Fully saturated — every exit node used |

### Completion time for 1.1M pages

| Rate | Time |
|------|------|
| 500K/hr | ~2.2 hours |
| 700K/hr | ~1.6 hours |
| 1M/hr | ~1.1 hours |

### Why HTTP/2 multiplexing matters

Without multiplexing, each worker opens its own TCP connection through Tor — one file descriptor per worker. Windows `select()` has a hard 512 FD limit, which means you need a monkey-patch just to run 400x3 (1,200 FDs).

With multiplexing, all workers on the same Tor instance share one TCP connection as HTTP/2 streams. 400 instances = 400 FDs, regardless of multiplier. You can push the multiplier to 10 (4,000 workers on 400 FDs) without touching the OS limit.

| Config | FDs (old) | FDs (HTTP/2) | Needs patch? |
|--------|-----------|--------------|-------------|
| 400x3 | 1,200 | 400 | No |
| 400x5 | 2,000 | 400 | No |
| 400x10 | 4,000 | 400 | No |
| 600x8 | 4,800 | 600 | Safety net only |
| 800x5 | 4,000 | 800 | Safety net only |

## Requirements

- Python 3.11+
- Windows (Linux support possible but untested)
- [Tor Expert Bundle](https://www.torproject.org/download/tor/)
- ~25 MB RAM per Tor instance

## Related

- [lambda-swarm](https://github.com/VoxCore84/lambda-swarm) — The AWS Lambda approach we built first (works for non-Cloudflare sites)

## License

MIT
