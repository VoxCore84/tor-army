# Example Scraper Output

Sample JSON files showing what Tor Army's scraped data looks like for
different entity types. These are real (lightly trimmed) outputs from
production scrapes against Wowhead.

## Files

| File | Entity | Source ID | Description |
|------|--------|-----------|-------------|
| `npc_sample.json` | NPC | 147991 | Zandalari Warrior -- name, tooltip, spawn coordinates, zone |
| `quest_sample.json` | Quest | 86942 | Culling the Spread -- objectives, requirements, quest text, rewards |
| `item_sample.json` | Item | 18540 | Sealed Reliquary of Purity -- full greedy parse with listviews, g_data, infobox, tooltip, related IDs |

## Structure Notes

- **NPC data** contains spawn coordinates as `[x, y]` pairs grouped by floor/phase index, plus the raw tooltip HTML that encodes level, type, and classification.
- **Quest data** contains objective text, kill/collect requirements as a list, quest-giver dialogue (`progress_text`, `completion_text`), XP, and money rewards (in copper).
- **Item data** is the richest -- the greedy parser captures every `WH.Listview` block on the page (`listviews`), the global metadata blob (`g_data`), sidebar info (`infobox`), icon URLs (`images`), tooltip HTML, and cross-references (`related_ids`). Top-level fields like `classs`, `quality`, `level` are promoted from `g_data` for convenience.

## Using These for Tests

These files can be loaded in tests to verify downstream consumers handle
the schema correctly without needing a live scrape:

```python
import json
from pathlib import Path

sample = json.loads((Path(__file__).parent / "item_sample.json").read_text())
assert sample["name"] == "Sealed Reliquary of Purity"
assert sample["quality"] == 1
```
