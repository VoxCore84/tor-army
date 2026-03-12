# Tor Army v3

Massively parallel async web scraper that routes through a fleet of Tor instances for IP diversity. Built for scraping Cloudflare-protected sites where cloud IPs (AWS Lambda, GCP, etc.) get instantly blocked.

## Why Tor beats Lambda

| Approach | Throughput | WAF Block Rate | Why |
|----------|-----------|----------------|-----|
| **Tor Army** | **380K+ pages/hr** | **<1%** | Tor exit nodes are residential/diverse IPs — Cloudflare trusts them |
| AWS Lambda | 2,500 pages/hr | **90%+** | Cloudflare maintains blocklists of all AWS IP ranges |

We built a [Lambda Swarm](https://github.com/VoxCore84/lambda-swarm) first — 3,000 concurrent Lambdas across 3 AWS regions with perfect browser TLS fingerprint impersonation. Cloudflare didn't care. 90% WAF rate. The same fingerprint impersonation through Tor exit nodes? Under 1% WAF.

**The IP matters more than the fingerprint.**

## Features

- **Async engine** — `asyncio` + `curl_cffi` eliminates GIL bottleneck
- **Worker multiplexing** — N async workers per Tor instance (default 3x)
- **Browser TLS fingerprints** — 7 profiles (Chrome, Edge, Safari, Firefox) via `curl_cffi`
- **Adaptive WAF throttling** — auto-adjusts delay based on block rate per minute
- **Per-instance rate limiting** — prevents WAF bursts from shared exit IPs
- **Circuit rotation** — fresh IP every 150 requests per instance
- **Windows `select()` bypass** — monkey-patches the 512 FD limit for 1,200+ workers
- **Live dashboard** — real-time rate, WAF/min, per-target breakdown, ETA
- **HTML caching** — gzip-compressed raw HTML for re-parsing without re-scraping
- **39 Wowhead entity parsers** — spells, items, NPCs, quests, transmog, and 34 more

## Quick Start

```bash
# Install
pip install -e .

# Download and install Tor Expert Bundle:
# https://www.torproject.org/download/tor/

# Generate ID lists (requires source CSVs)
python generate_id_lists.py --csv-dir /path/to/csvs

# Launch with defaults (400 Tor instances × 3 workers = 1,200 concurrent)
python tor_army.py --start-tor --targets spell,item,npc,quest

# Smoke test (10 pages, 5 instances)
python tor_army.py --start-tor --workers 5 --smoke 10 --targets npc

# List available targets
python tor_army.py --list-targets

# Re-parse cached HTML without network
python tor_army.py --targets npc --reparse

# Kill leftover Tor instances
python tor_army.py --kill-tor
```

## Architecture

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
│  │Circuit  │ │Circuit  │  ...  │Circuit  │   │
│  │Manager 1│ │Manager 1│       │Manager N│   │
│  │(shared) │ │(shared) │       │(shared) │   │
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

Workers sharing a Tor instance share its exit IP but are rate-limited by CircuitManager to prevent WAF bursts. Each instance rotates circuits every 150 requests for IP freshness.

## Configuration

| Flag | Default | Description |
|------|---------|-------------|
| `--workers` | 400 | Tor instances to run (~25MB RAM each) |
| `--multiplier` | 3 | Async workers per instance |
| `--delay` | 0.15 | Base delay between requests (seconds) |
| `--per-circuit` | 150 | Requests before circuit rotation |
| `--max-waf` | 3 | WAF hits before forced rotation |
| `--cache-html` | true | Cache raw HTML as gzip |
| `--targets` | npc | Comma-separated entity types |

## Scaling Guide

| Config | Workers | RAM | Expected Rate |
|--------|---------|-----|---------------|
| 240×2 | 480 | ~6 GB | ~270K/hr |
| 400×3 | 1,200 | ~10 GB | ~400-600K/hr |
| 600×3 | 1,800 | ~15 GB | ~500-700K/hr |
| 800×2 | 1,600 | ~20 GB | ~500-700K/hr |

Past ~600 instances, returns diminish — there are only ~1,000-1,500 Tor exit nodes globally, so you start getting duplicate exit IPs.

## Requirements

- Python 3.11+
- Windows (Linux support possible but untested)
- [Tor Expert Bundle](https://www.torproject.org/download/tor/)
- ~25 MB RAM per Tor instance

## Related

- [lambda-swarm](https://github.com/VoxCore84/lambda-swarm) — The AWS Lambda approach (works for non-Cloudflare sites)

## License

MIT
