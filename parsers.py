"""Wowhead Page Parsers -- Plugin Registry

Greedy extraction: every parser captures ALL available data from each page.
Instead of cherry-picking specific WH.Listview IDs, we find and extract
every data block on the page. This means we never have to re-scrape.

Each parser returns: {
    "listviews": { "<id>": [full data arrays] },     # ALL WH.Listview blocks
    "g_data": { full $.extend(g_xxx[ID], ...) },      # Global entity metadata
    "infobox": { key: value pairs },                   # Sidebar infobox
    "coords": [{ x, y, uiMapId }],                    # Spawn coordinates
    "images": { "icons": [...], "screenshots": [...], "models": [...] },
    "tooltip": "...",                                   # Raw tooltip HTML
    "related_ids": { "spells": [...], "npcs": [...], "items": [...], ... },
    ... plus entity-specific fields
}

Shared extractors:
  _extract_all_listviews  -- finds EVERY WH.Listview on the page
  _extract_all_g_data     -- finds ALL $.extend(g_xxx) blocks
  _extract_infobox        -- sidebar key-value pairs
  _extract_mapper_data    -- g_mapperData spawn coordinates
  _extract_all_images     -- icons, screenshots, model viewer renders
  _extract_tooltip        -- raw tooltip HTML content
"""

import json
import re


# == Shared Extractors =========================================================

def _parse_js_value(html: str, start: int, open_char: str, close_char: str,
                    max_len: int = 500000) -> str | None:
    """Parse a balanced JS object/array starting at `start`."""
    depth = 0
    str_char = None  # tracks which quote char opened the current string
    esc = False
    for i in range(start, min(start + max_len, len(html))):
        ch = html[i]
        if esc:
            esc = False
            continue
        if ch == "\\":
            esc = True
            continue
        if str_char is None and ch in ('"', "'"):
            str_char = ch
            continue
        if str_char is not None and ch == str_char:
            str_char = None
            continue
        if str_char is not None:
            continue
        if ch == open_char:
            depth += 1
        elif ch == close_char:
            depth -= 1
            if depth == 0:
                return html[start:i + 1]
    return None


def _js_to_json(raw: str) -> str:
    """Convert JS object literals to valid JSON (unquoted keys, trailing commas)."""
    raw = re.sub(r'(?<=[{,\[\n])\s*(\w+)\s*:', r'"\1":', raw)
    raw = re.sub(r",\s*([}\]])", r"\1", raw)
    return raw


def _safe_parse(raw: str):
    """Parse JS-flavored JSON, returning None on failure.

    Tries raw JSON first (many Wowhead blocks are valid JSON already),
    then falls back to _js_to_json for unquoted-key JS object literals.
    """
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        pass
    try:
        return json.loads(_js_to_json(raw))
    except (json.JSONDecodeError, ValueError):
        return None


def _extract_all_listviews(html: str) -> dict[str, list]:
    """Find ALL WH.Listview({id:'xxx', ...data:[...]}) blocks on the page.

    Returns dict mapping listview ID -> data array. This is greedy --
    it captures every listview regardless of what data it contains.
    """
    results = {}

    # Match all WH.Listview( and new Listview( occurrences
    for m in re.finditer(r'(?:WH\.Listview|new Listview)\(\s*\{', html):
        block_start = m.end() - 1  # position of the opening {
        raw_obj = _parse_js_value(html, block_start, '{', '}')
        if not raw_obj:
            continue

        # Extract the listview ID
        id_match = re.search(r'''id\s*:\s*['"]([^'"]+)['"]''', raw_obj[:500])
        if not id_match:
            continue
        lv_id = id_match.group(1)

        # Extract the data array
        data_match = re.search(r'data\s*:\s*\[', raw_obj)
        if not data_match:
            # Some listviews use data: _data or similar references -- skip
            continue

        arr_start = raw_obj.index('[', data_match.start())
        raw_arr = _parse_js_value(raw_obj, arr_start, '[', ']')
        if not raw_arr:
            continue

        parsed = _safe_parse(raw_arr)
        if parsed is not None:
            results[lv_id] = parsed

    return results


def _extract_all_g_data(html: str) -> dict[str, dict]:
    """Find ALL $.extend(g_xxx[ID], {...}) blocks and return them.

    Returns dict: { "g_npcs": {...}, "g_quests": {...}, etc. }
    """
    results = {}
    for m in re.finditer(r'\$\.extend\((g_\w+)\[\d+\],\s*\{', html):
        var_name = m.group(1)
        obj_start = html.index('{', m.start() + len(m.group(0)) - 1)
        raw_obj = _parse_js_value(html, obj_start, '{', '}')
        if raw_obj:
            parsed = _safe_parse(raw_obj)
            if parsed:
                results[var_name] = parsed
    return results


def _extract_mapper_data(html: str) -> list | None:
    """Extract g_mapperData (spawn coordinates)."""
    idx = html.find("g_mapperData")
    if idx < 0:
        return None
    bracket = html.find("[", idx)
    if bracket < 0 or bracket > idx + 100:
        return None
    raw = _parse_js_value(html, bracket, '[', ']', 200000)
    if raw:
        return _safe_parse(raw)
    return None


def _extract_infobox(html: str) -> dict:
    """Extract key-value pairs from the Wowhead infobox sidebar.

    Handles both raw HTML infoboxes and WH.markup.printHtml("[ul][li]...") format.
    """
    result = {}

    # Method 1: WH.markup.printHtml (most common on modern Wowhead)
    for m in re.finditer(r'WH\.markup\.printHtml\("(.*?)"', html):
        markup = m.group(1).replace("\\/", "/")
        # Parse [li]Key: Value[/li] pairs
        for li in re.finditer(r'\[li\](.*?)\[/li\]', markup):
            content = li.group(1)
            # Strip markup tags: [url=...], [color=...], [acronym=...], etc.
            clean = re.sub(r'\[/?(?:url|color|icon|icondb|acronym|b|i|small)[^\]]*\]', '', content)
            clean = clean.strip()
            if ":" in clean:
                key, _, val = clean.partition(":")
                key = key.strip().lower().replace(" ", "_").replace(".", "")
                val = val.strip()
                if key and val:
                    result[key] = val
            elif clean:
                # Boolean flags like "Can repair", "Tameable"
                key = clean.lower().replace(" ", "_").replace(".", "")
                result[key] = True

        # Extract linked IDs from markup [url=/spell=123/...]
        for link in re.finditer(r'\[url=/(spell|npc|item|quest|achievement|zone|faction)=(\d+)', markup):
            link_type = link.group(1)
            link_id = int(link.group(2))
            key = f"infobox_{link_type}_ids"
            if key not in result:
                result[key] = []
            if link_id not in result[key]:
                result[key].append(link_id)

    # Method 2: Raw HTML infobox (fallback for older pages)
    if not result:
        idx = html.find('class="infobox-wrapper"')
        if idx < 0:
            idx = html.find('id="infobox-contents"')
        if idx >= 0:
            block = html[idx:idx + 15000]
            for m2 in re.finditer(r'<li[^>]*>.*?<b[^>]*>([^<]+)</b>\s*:?\s*(.*?)</li>', block, re.DOTALL):
                key = m2.group(1).strip().lower().replace(" ", "_").replace(".", "")
                val = re.sub(r'<[^>]+>', '', m2.group(2)).strip()
                if val:
                    result[key] = val

            for m2 in re.finditer(r'<a\s+href="/(spell|npc|item|quest|achievement|zone)=(\d+)"', block):
                link_type = m2.group(1)
                link_id = int(m2.group(2))
                key = f"infobox_{link_type}_ids"
                if key not in result:
                    result[key] = []
                if link_id not in result[key]:
                    result[key].append(link_id)

    return result


def _parse_coords(html: str) -> list:
    """Extract spawn coordinates from g_mapperData."""
    mapper = _extract_mapper_data(html)
    if not mapper:
        return []
    coords = []
    for entry in mapper:
        if isinstance(entry, dict) and "coords" in entry:
            for coord in entry["coords"]:
                if isinstance(coord, list) and len(coord) >= 2:
                    coords.append({
                        "x": coord[0], "y": coord[1],
                        "uiMapId": entry.get("uiMapId"),
                    })
    return coords


def _extract_all_images(html: str) -> dict:
    """Extract ALL image URLs from the page: icons, screenshots, model renders."""
    images = {"icons": [], "screenshots": [], "models": [], "other": []}

    # Icons (zamimg.com/images/wow/icons/)
    for m in re.finditer(r'(https?://wow\.zamimg\.com/images/wow/icons/\w+/[^"\'>\s]+)', html):
        url = m.group(1)
        if url not in images["icons"]:
            images["icons"].append(url)

    # Screenshots (zamimg.com/uploads/screenshots/)
    for m in re.finditer(r'(https?://wow\.zamimg\.com/uploads/screenshots/\w+/\d+[^"\'>\s]*)', html):
        url = m.group(1)
        if url not in images["screenshots"]:
            images["screenshots"].append(url)

    # Model viewer (data-mv-* attributes contain display IDs)
    for m in re.finditer(r'data-mv-(?:display-id|id)="(\d+)"', html):
        mid = int(m.group(1))
        if mid not in images["models"]:
            images["models"].append(mid)

    # DisplayInfo IDs from g_modelviewer configs
    for m in re.finditer(r'"displayId"\s*:\s*(\d+)', html):
        mid = int(m.group(1))
        if mid not in images["models"]:
            images["models"].append(mid)

    # General wow.zamimg.com images
    for m in re.finditer(r'(https?://wow\.zamimg\.com/[^"\'>\s]+\.(?:png|jpg|gif|webp))', html):
        url = m.group(1)
        if url not in images["other"] and url not in images["icons"] and url not in images["screenshots"]:
            images["other"].append(url)

    # Remove empty categories
    return {k: v for k, v in images.items() if v}


def _extract_tooltip(html: str) -> str | None:
    """Extract raw tooltip HTML content."""
    # Wowhead embeds tooltips in various formats
    m = re.search(r'<div\s+class="(?:wowhead-tooltip|tooltip)"[^>]*>(.*?)</div>\s*</div>', html, re.DOTALL)
    if m:
        return m.group(1).strip()

    # Alternative: tooltip_ variable
    m = re.search(r'tooltip_\w+\s*=\s*["\'](.+?)["\'];', html)
    if m:
        return m.group(1)

    return None


def _extract_related_ids(html: str) -> dict[str, list[int]]:
    """Extract ALL entity cross-references from the page.

    Scans the entire HTML for every npc=, spell=, item=, quest=, etc. link.
    Returns a deduplicated map of entity_type -> [ids].
    """
    related = {}
    for m in re.finditer(r'(?:href=["\']/|/)(\w+)=(\d+)', html):
        entity_type = m.group(1)
        entity_id = int(m.group(2))
        # Only collect known entity types
        if entity_type in ("spell", "npc", "item", "quest", "achievement",
                           "object", "zone", "mount", "currency", "faction",
                           "title", "event", "questline", "item-set",
                           "transmog-set", "class", "race", "pet", "mission",
                           "building", "follower", "profession"):
            key = entity_type.replace("-", "_") + "s"
            if key not in related:
                related[key] = []
            if entity_id not in related[key]:
                related[key].append(entity_id)
    return related


# Wowhead entity type IDs used in WH.Gatherer.addData(TYPE, ...)
_GATHERER_TYPE_NAMES = {
    1: "npcs", 2: "objects", 3: "items", 4: "item_sets", 5: "quests",
    6: "spells", 7: "zones", 8: "factions", 9: "pets", 10: "achievements",
    11: "titles", 12: "events", 17: "currencies", 100: "mounts",
}


def _extract_gatherer_data(html: str) -> dict[str, dict]:
    """Extract ALL WH.Gatherer.addData() calls.

    This is the RICHEST data source on any Wowhead page. Every referenced
    entity (NPC, item, spell, quest, zone, etc.) gets its name, icon,
    tooltip, screenshot, stats, and metadata registered here.

    Returns: { "npcs": {id: {data}, ...}, "items": {id: {data}}, ... }
    """
    results = {}
    for m in re.finditer(r'WH\.Gatherer\.addData\(\s*(\d+)\s*,\s*\d+\s*,\s*\{', html):
        type_id = int(m.group(1))
        type_name = _GATHERER_TYPE_NAMES.get(type_id, f"type_{type_id}")

        obj_start = html.index('{', m.start() + len("WH.Gatherer.addData("))
        # Find the closing of the outer wrapper: addData(type, fmt, { ... })
        # But the { at obj_start contains id-keyed sub-objects
        raw_obj = _parse_js_value(html, obj_start, '{', '}')
        if not raw_obj:
            continue

        parsed = _safe_parse(raw_obj)
        if not parsed or not isinstance(parsed, dict):
            continue

        if type_name not in results:
            results[type_name] = {}
        # Merge — keys are string IDs like "36597"
        for eid, edata in parsed.items():
            try:
                int_id = int(eid)
            except (ValueError, TypeError):
                continue
            if isinstance(edata, dict):
                results[type_name][int_id] = edata

    return results


def _extract_json_ld(html: str) -> list[dict]:
    """Extract JSON-LD structured data (Schema.org) from the page."""
    results = []
    for m in re.finditer(
        r'<script[^>]*type\s*=\s*["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html, re.DOTALL,
    ):
        try:
            data = json.loads(m.group(1))
            results.append(data)
        except (json.JSONDecodeError, ValueError):
            pass
    return results


def _extract_page_info(html: str) -> dict | None:
    """Extract g_pageInfo — page type, entity ID, entity name."""
    m = re.search(r'g_pageInfo\s*=\s*\{([^}]+)\}', html)
    if not m:
        return None
    raw = '{' + m.group(1) + '}'
    return _safe_parse(raw)


def _extract_videos(html: str) -> list[str]:
    """Extract all YouTube video IDs from the page."""
    ids = []
    for m in re.finditer(r'youtu(?:\.be/|be\.com/(?:embed/|watch\?v=))([a-zA-Z0-9_-]{11})', html):
        vid = m.group(1)
        if vid not in ids:
            ids.append(vid)
    return ids


def _extract_markup_sections(html: str) -> list[dict]:
    """Extract rich content from WH.markup.printHtml calls beyond infobox.

    Captures ability descriptions, phase breakdowns, encounter guides, etc.
    Returns list of sections with headers and content.
    """
    sections = []
    for m in re.finditer(r'WH\.markup\.printHtml\(\s*"(.*?)"\s*\)', html, re.DOTALL):
        markup = m.group(1).replace("\\/", "/").replace("\\r\\n", "\n").replace("\\n", "\n")

        # Skip the infobox markup (already parsed separately)
        if markup.startswith("[ul][li]") and "[/ul]" in markup[:500]:
            continue

        # Extract headings and content
        section = {"raw_markup": markup}

        # Find section headers [h2]...[/h2], [h3]...[/h3]
        headers = re.findall(r'\[h[23](?:=[^\]]*)?](.*?)\[/h[23]\]', markup)
        if headers:
            clean_headers = []
            for h in headers:
                clean = re.sub(r'\[/?[a-z]+[^\]]*\]', '', h).strip()
                if clean:
                    clean_headers.append(clean)
            if clean_headers:
                section["headers"] = clean_headers

        # Extract tab names if present [tabs][tab name=X]
        tabs = re.findall(r'\[tab\s+name=([^\]]+)\]', markup)
        if tabs:
            section["tabs"] = tabs

        if len(markup) > 20:  # Skip trivially empty ones
            sections.append(section)

    return sections


def _extract_comments(html: str) -> list[dict]:
    """Extract top user comments (Wowhead stores them in lv_comments vars)."""
    comments = []
    for m in re.finditer(r'var\s+lv_comments\d*\s*=\s*\[', html):
        arr_start = html.index('[', m.start())
        raw_arr = _parse_js_value(html, arr_start, '[', ']', 500000)
        if not raw_arr:
            continue
        parsed = _safe_parse(raw_arr)
        if parsed and isinstance(parsed, list):
            for c in parsed:
                if isinstance(c, dict):
                    comment = {}
                    for key in ("body", "rating", "date", "user", "roles"):
                        if key in c:
                            comment[key] = c[key]
                    if comment:
                        comments.append(comment)
    return comments


def _extract_spell_formula_refs(html: str) -> list[int]:
    """Extract spell IDs from <!--spXXXXX--> formula placeholders.

    These are embedded by Wowhead wherever a spell's coefficients or damage
    values are displayed. They represent actual spell formula dependencies.
    """
    ids = []
    for m in re.finditer(r'<!--sp(\d+)', html):
        sid = int(m.group(1))
        if sid not in ids:
            ids.append(sid)
    return ids


def _extract_sound_ids(html: str) -> list[int]:
    """Extract SoundKit IDs from the page."""
    ids = []
    # From sounds listview data (captured in listviews), but also from
    # standalone references in HTML
    for m in re.finditer(r'"soundId"\s*:\s*(\d+)', html):
        sid = int(m.group(1))
        if sid not in ids:
            ids.append(sid)
    # From data attributes
    for m in re.finditer(r'data-sound(?:kit)?-id="(\d+)"', html, re.IGNORECASE):
        sid = int(m.group(1))
        if sid not in ids:
            ids.append(sid)
    return ids


# Wowhead source type IDs (used in listview item "source" arrays)
_SOURCE_TYPE_NAMES = {
    1: "crafted", 2: "dropped", 3: "pvp", 4: "quest_reward", 5: "vendor",
    6: "trainer", 7: "discovery", 8: "redemption", 9: "talent",
    10: "starter_gear", 11: "event", 12: "achievement", 13: "pickup",
    14: "salvage", 15: "cache", 16: "contained_in", 17: "profession",
}

# sourcemore keys: t=entity_type, ti=entity_id, n=name, z=zone_id,
# bd=boss_difficulty, dd=dungeon_difficulty


def _singularize(name: str) -> str:
    """Convert plural entity type names to singular (currencies->currency, etc.)."""
    if name in ("class", "unknown", "entity"):
        return name
    if name.endswith("ies"):
        return name[:-3] + "y"  # currencies -> currency
    if name.endswith("s"):
        return name[:-1]  # npcs -> npc, items -> item
    return name


def _build_relationship_web(result: dict) -> list[dict]:
    """Build an explicit typed relationship edge list from ALL extracted data.

    Mines every data source to produce edges like:
        {from_type, from_id, to_type, to_id, relation, detail}

    This is the cross-referencing web — "which spell links to which spell,
    which NPC uses what, who wears what, who drops what."
    """
    entity_id = result.get("id", 0)
    page_info = result.get("page_info", {})
    entity_type = _GATHERER_TYPE_NAMES.get(page_info.get("type", 0), "unknown")
    entity_type = _singularize(entity_type)

    edges = []

    def add(to_type, to_id, relation, detail=None):
        edge = {"from_type": entity_type, "from_id": entity_id,
                "to_type": _singularize(to_type), "to_id": to_id,
                "relation": relation}
        if detail:
            edge["detail"] = detail
        edges.append(edge)

    # --- 1. Mine listview data for typed relationships ---
    listviews = result.get("listviews", {})

    # Map listview IDs to relationship types
    _LV_RELATIONS = {
        "drops": ("item", "drops"),
        "drop-currency": ("currency", "drops_currency"),
        "sells": ("item", "sells"),
        "abilities": ("spell", "uses_ability"),
        "teaches": ("spell", "teaches"),
        "teaches-recipe": ("spell", "teaches_recipe"),
        "starts": ("quest", "starts_quest"),
        "ends": ("quest", "ends_quest"),
        "objective-of": ("quest", "objective_of"),
        "skinning": ("item", "skinning_drop"),
        "pickpocketing": ("item", "pickpocket_drop"),
        "mining": ("item", "mining_drop"),
        "herbalism": ("item", "herbalism_drop"),
        "salvage": ("item", "salvage_drop"),
        "criteria-of": ("achievement", "criteria_of"),
        "contains": ("item", "contains"),
        "same-model-as": (None, "same_model_as"),
        "summoned-by": ("spell", "summoned_by"),
        "outfit": ("item", "wears"),
        "sounds": ("sound", "plays_sound"),
        # Item-centric
        "sold-by": ("npc", "sold_by"),
        "dropped-by": ("npc", "dropped_by"),
        "reward-from-q": ("quest", "reward_from"),
        "reward-from-a": ("achievement", "reward_from"),
        "contained-in-object": ("object", "contained_in"),
        "contained-in-item": ("item", "contained_in"),
        "created-by": ("spell", "created_by"),
        "reagent-for": ("spell", "reagent_for"),
        "currency-for": ("item", "currency_for"),
        "disenchanted-from": ("item", "disenchanted_from"),
        "disenchants-into": ("item", "disenchants_into"),
        "objective-of-q": ("quest", "objective_of"),
        "used-by-npc": ("npc", "used_by"),
        # Spell-centric
        "taught-by-npc": ("npc", "taught_by"),
        "cast-by-npc": ("npc", "cast_by"),
        "cast-by-object": ("object", "cast_by"),
        "taught-by-item": ("item", "taught_by"),
        "triggers": ("spell", "triggers"),
        "triggered-by": ("spell", "triggered_by"),
        "related": ("spell", "related_to"),
        "modified-by": ("spell", "modified_by"),
        "modifies": ("spell", "modifies"),
        "aura-of": ("spell", "aura_of"),
        "effect-of": ("spell", "effect_of"),
        "enchant-for": ("item", "enchant_for"),
        "item-enchant": ("item", "enchants"),
        # Quest-centric
        "provided-item": ("item", "provides"),
        "required-by": ("quest", "required_by"),
        "leads-to": ("quest", "leads_to"),
        # Achievement-centric
        "criteria": (None, "has_criteria"),
        "reward-item": ("item", "rewards"),
        "reward-spell": ("spell", "rewards"),
        "reward-title": ("title", "rewards"),
        "series": ("achievement", "in_series"),
        "required-for": ("achievement", "required_for"),
        "see-also": (None, "see_also"),
        # Zone-centric
        "npcs": ("npc", "contains_npc"),
        "quests": ("quest", "contains_quest"),
        "objects": ("object", "contains_object"),
        "rares": ("npc", "contains_rare"),
        "flight-paths": (None, "has_flight_path"),
        "subzones": ("zone", "has_subzone"),
        "achievements": ("achievement", "zone_achievement"),
        "items": ("item", "contains_item"),
        # Dungeon-centric
        "bosses": ("npc", "has_boss"),
        "loot": ("item", "dungeon_loot"),
        # Event-centric
        "spells": ("spell", "event_spell"),
        # Guide/misc
        "guides": (None, "has_guide"),
        "models": (None, "has_model"),
    }

    for lv_id, lv_data in listviews.items():
        if not isinstance(lv_data, list):
            continue
        rel_info = _LV_RELATIONS.get(lv_id)
        if not rel_info:
            # Unknown listview — still extract IDs
            to_type_guess = lv_id.rstrip("s") if lv_id not in ("class",) else lv_id
            rel_info = (None, f"lv_{lv_id}")

        default_to_type, relation = rel_info

        for entry in lv_data:
            if not isinstance(entry, dict):
                continue
            entry_id = entry.get("id")
            if entry_id is None:
                continue

            # Determine target entity type
            to_type = default_to_type or "entity"

            detail = {}
            # Extract drop rate if present
            if "count" in entry and "outof" in entry:
                detail["drop_rate"] = entry["count"] / max(entry["outof"], 1)
            if "modes" in entry:
                detail["modes"] = entry["modes"]
            # Extract specs (class/spec restrictions)
            if "specs" in entry:
                detail["specs"] = entry["specs"]
            # Extract sourcemore (provenance chain)
            if "sourcemore" in entry:
                for sm in entry["sourcemore"]:
                    if isinstance(sm, dict) and "ti" in sm:
                        sm_type = _singularize(
                            _GATHERER_TYPE_NAMES.get(sm.get("t", 0), "entity")
                        )
                        detail.setdefault("source_chain", []).append({
                            "type": sm_type, "id": sm["ti"],
                            "name": sm.get("n", ""),
                            "zone": sm.get("z"),
                        })
            # Extract appearance/transmog data
            if "appearances" in entry:
                detail["appearances"] = entry["appearances"]

            add(to_type, entry_id, relation, detail if detail else None)

    # --- 2. Mine gatherer data for entity-to-entity connections ---
    gatherer = result.get("gatherer", {})
    for gtype, entities in gatherer.items():
        # Each gatherer entity type on this page means the page REFERENCES them
        singular = _singularize(gtype)
        for gid, gdata in entities.items():
            if gid == entity_id and singular == entity_type:
                continue  # Skip self-reference
            # The relationship is "this page references entity X"
            # More specific than href scanning because gatherer = Wowhead
            # explicitly registered the cross-reference
            detail = {}
            if "name_enus" in gdata:
                detail["name"] = gdata["name_enus"]
            if "icon" in gdata:
                detail["icon"] = gdata["icon"]
            if "quality" in gdata:
                detail["quality"] = gdata["quality"]
            add(singular, gid, "references", detail if detail else None)

    # --- 3. Mine spell formula refs (<!--spXXXXX-->) ---
    for sid in result.get("spell_formula_refs", []):
        add("spell", sid, "formula_dependency")

    # --- 4. Mine sound IDs ---
    for sid in result.get("sound_ids", []):
        add("sound", sid, "plays_sound")

    return edges


# == Universal Deep Parser =====================================================

def _deep_parse(html: str, entity_id: int) -> dict:
    """Universal greedy parser -- extracts EVERYTHING from any Wowhead page.

    Every entity-specific parser calls this first, then adds any
    entity-specific extraction logic on top.
    """
    result = {"id": entity_id}

    # 1. All WH.Listview data blocks (the richest data source)
    listviews = _extract_all_listviews(html)
    if listviews:
        result["listviews"] = listviews

    # 2. All $.extend(g_xxx) metadata blocks
    g_data = _extract_all_g_data(html)
    if g_data:
        result["g_data"] = g_data

    # 3. Infobox sidebar
    infobox = _extract_infobox(html)
    if infobox:
        result["infobox"] = infobox

    # 4. Spawn coordinates
    coords = _parse_coords(html)
    if coords:
        result["coords"] = coords

    # 5. All images
    images = _extract_all_images(html)
    if images:
        result["images"] = images

    # 6. Tooltip
    tooltip = _extract_tooltip(html)
    if tooltip:
        result["tooltip"] = tooltip

    # 7. All cross-referenced entity IDs
    related = _extract_related_ids(html)
    if related:
        result["related_ids"] = related

    # 8. WH.Gatherer.addData — the richest data source on ANY page
    # Contains name/icon/tooltip/stats for every referenced entity
    gatherer = _extract_gatherer_data(html)
    if gatherer:
        result["gatherer"] = gatherer

    # 9. JSON-LD structured data (Schema.org)
    json_ld = _extract_json_ld(html)
    if json_ld:
        result["json_ld"] = json_ld

    # 10. Page metadata (entity type, ID, name)
    page_info = _extract_page_info(html)
    if page_info:
        result["page_info"] = page_info

    # 11. YouTube videos
    videos = _extract_videos(html)
    if videos:
        result["videos"] = videos

    # 12. Rich markup sections (ability guides, phase breakdowns, etc.)
    markup_sections = _extract_markup_sections(html)
    if markup_sections:
        result["markup_sections"] = markup_sections

    # 13. Top user comments
    comments = _extract_comments(html)
    if comments:
        result["comments"] = comments

    # 14. Page title (entity name)
    title_m = re.search(r'<h1[^>]*class="heading-size-1"[^>]*>([^<]+)</h1>', html)
    if title_m:
        result["name"] = title_m.group(1).strip()
    else:
        title_m = re.search(r'<title>([^<]+?)(?:\s*-\s*(?:NPC|Item|Spell|Quest|Object|Achievement|Mount|Currency|Faction|Title|Zone)?\s*-?\s*Wowhead)?(?:\s*-\s*World of Warcraft)?</title>', html)
        if title_m:
            result["name"] = title_m.group(1).strip()

    # 15. Breadcrumb (category path)
    crumbs = re.findall(r'class="breadcrumb-item"[^>]*>([^<]+)', html)
    if crumbs:
        result["breadcrumb"] = [c.strip() for c in crumbs if c.strip()]

    # 16. Spell formula refs (<!--spXXXXX--> inline damage/coefficient placeholders)
    spell_refs = _extract_spell_formula_refs(html)
    if spell_refs:
        result["spell_formula_refs"] = spell_refs

    # 17. Sound IDs
    sound_ids = _extract_sound_ids(html)
    if sound_ids:
        result["sound_ids"] = sound_ids

    # 18. Relationship web — explicit typed edges from ALL data sources above
    web = _build_relationship_web(result)
    if web:
        result["relationship_web"] = web

    return result


# == Entity-Specific Parsers ===================================================
# Each calls _deep_parse() first, then promotes commonly-needed fields
# to top-level keys for convenience. The full data is always in listviews/g_data.

def parse_quest_page(html: str, entity_id: int) -> dict:
    result = _deep_parse(html, entity_id)

    # Promote quest-specific g_data fields
    g = result.get("g_data", {}).get("g_quests", {})
    for key in ("level", "reqlevel", "category", "side", "money", "xp",
                "name", "reqrace", "reqclass"):
        if key in g:
            result[key] = g[key]

    # Extract quest text sections
    for section, key in [("Progress", "progress_text"),
                         ("Completion", "completion_text"),
                         ("Description", "description_text")]:
        pat = re.compile(
            rf'<h[23][^>]*>.*?{section}.*?</h[23]>\s*(.*?)(?=<h[23]|<div\s+class="pad"|$)',
            re.DOTALL | re.IGNORECASE,
        )
        m = pat.search(html)
        if m:
            text = re.sub(r'<[^>]+>', ' ', m.group(1)).strip()
            text = re.sub(r'\s+', ' ', text)
            text = re.sub(r'\[/?[a-z]+[^\]]*\]', '', text)
            if text and len(text) > 3:
                result[key] = text

    # Promote start/end NPCs from listviews
    lv = result.get("listviews", {})
    for lv_id, key in [("starts", "start_npcs"), ("ends", "end_npcs"),
                        ("objectives", "objectives"), ("rewards", "rewards"),
                        ("provided-item", "provided_items"),
                        ("required-by", "required_by"),
                        ("leads-to", "leads_to")]:
        if lv_id in lv:
            result[key] = [e["id"] for e in lv[lv_id] if isinstance(e, dict) and "id" in e]

    return result


def parse_npc_page(html: str, entity_id: int) -> dict:
    result = _deep_parse(html, entity_id)

    # Promote NPC metadata
    g = result.get("g_data", {}).get("g_npcs", {})
    for key in ("minlevel", "maxlevel", "react", "type", "classification",
                "boss", "health", "displayId", "name", "tag",
                "npcFlags", "faction", "family"):
        if key in g:
            result[key] = g[key]

    # Promote key listview sections with full data (not just IDs)
    lv = result.get("listviews", {})
    for lv_id, key in [
        ("sells", "vendor_items"),
        ("drops", "drops"),
        ("abilities", "abilities"),
        ("teaches", "teaches"),
        ("teaches-recipe", "teaches_recipes"),
        ("skinning", "skinning"),
        ("pickpocketing", "pickpocketing"),
        ("starts", "quests_started"),
        ("ends", "quests_ended"),
        ("sounds", "sounds"),
        ("models", "models"),
        ("same-model-as", "same_model_as"),
        ("criteria-of", "criteria_of"),
        ("contains", "contains"),
        ("mining", "mining"),
        ("salvage", "salvage"),
        ("herbalism", "herbalism"),
    ]:
        if lv_id in lv:
            result[key] = lv[lv_id]

    return result


def parse_item_page(html: str, entity_id: int) -> dict:
    result = _deep_parse(html, entity_id)

    # Promote item metadata
    g = result.get("g_data", {}).get("g_items", {})
    for key in ("classs", "subclass", "quality", "level", "reqlevel", "slot",
                "name", "icon", "side", "flags", "flags2", "bonding",
                "sellprice", "buyprice", "maxcount", "stackable",
                "itemset", "displayid"):
        if key in g:
            result[key] = g[key]

    # Promote key listview sections
    lv = result.get("listviews", {})
    for lv_id, key in [
        ("sold-by", "sold_by"),
        ("dropped-by", "dropped_by"),
        ("reward-from-q", "reward_from_quests"),
        ("starts", "starts_quests"),
        ("contained-in-object", "contained_in_objects"),
        ("contained-in-item", "contained_in_items"),
        ("created-by", "created_by"),
        ("reagent-for", "reagent_for"),
        ("currency-for", "currency_for"),
        ("same-model-as", "same_model_as"),
        ("disenchanted-from", "disenchanted_from"),
        ("disenchants-into", "disenchants_into"),
        ("teaches", "teaches_spell"),
        ("objective-of-q", "objective_of_quests"),
        ("pick-up-by", "pick_up_by"),
        ("used-by-npc", "used_by_npcs"),
    ]:
        if lv_id in lv:
            result[key] = lv[lv_id]

    return result


def parse_spell_page(html: str, entity_id: int) -> dict:
    result = _deep_parse(html, entity_id)

    # Promote spell metadata
    g = result.get("g_data", {}).get("g_spells", {})
    for key in ("name", "icon", "school", "cat", "skill",
                "range", "cast", "gcd", "cooldown"):
        if key in g:
            result[key] = g[key]

    # Promote key listview sections
    lv = result.get("listviews", {})
    for lv_id, key in [
        ("taught-by-npc", "taught_by_npcs"),
        ("used-by-npc", "used_by_npcs"),
        ("cast-by-npc", "cast_by_npcs"),
        ("cast-by-object", "cast_by_objects"),
        ("teaches", "teaches"),
        ("taught-by-item", "taught_by_items"),
        ("reward-from-q", "reward_from_quests"),
        ("triggers", "triggers_spells"),
        ("triggered-by", "triggered_by_spells"),
        ("reagent-for", "reagent_for"),
        ("related", "related_spells"),
        ("modified-by", "modified_by"),
        ("modifies", "modifies_spells"),
        ("aura-of", "aura_of"),
        ("effect-of", "effect_of"),
        ("criteria-of", "criteria_of"),
        ("enchant-for", "enchant_for"),
        ("item-enchant", "item_enchants"),
    ]:
        if lv_id in lv:
            result[key] = lv[lv_id]

    # Extract spell effect descriptions from the page
    effects = []
    for m in re.finditer(r'<td[^>]*>Effect\s*#?\d*\s*</td>\s*<td[^>]*>(.*?)</td>', html, re.DOTALL):
        effect_text = re.sub(r'<[^>]+>', '', m.group(1)).strip()
        if effect_text:
            effects.append(effect_text)
    if effects:
        result["effects"] = effects

    return result


def parse_object_page(html: str, entity_id: int) -> dict:
    result = _deep_parse(html, entity_id)

    g = result.get("g_data", {}).get("g_objects", {})
    for key in ("type", "displayId", "name"):
        if key in g:
            result[key] = g[key]

    lv = result.get("listviews", {})
    for lv_id, key in [
        ("starts", "quests_started"),
        ("ends", "quests_ended"),
        ("contains", "contains_items"),
        ("mining", "mining"),
        ("herbalism", "herbalism"),
        ("opens", "opens"),
    ]:
        if lv_id in lv:
            result[key] = lv[lv_id]

    return result


def parse_achievement_page(html: str, entity_id: int) -> dict:
    result = _deep_parse(html, entity_id)

    g = result.get("g_data", {}).get("g_achievements", {})
    for key in ("points", "side", "category", "parentcat", "name", "icon"):
        if key in g:
            result[key] = g[key]

    lv = result.get("listviews", {})
    for lv_id, key in [
        ("criteria", "criteria"),
        ("reward-item", "reward_items"),
        ("reward-spell", "reward_spells"),
        ("reward-title", "reward_titles"),
        ("series", "series"),
        ("required-for", "required_for"),
        ("see-also", "see_also"),
    ]:
        if lv_id in lv:
            result[key] = lv[lv_id]

    return result


def parse_mount_page(html: str, entity_id: int) -> dict:
    result = _deep_parse(html, entity_id)

    # Mount spell ID
    spell_ids = re.findall(r'spell=(\d+)', html[:5000])
    if spell_ids:
        result["spell_id"] = int(spell_ids[0])

    lv = result.get("listviews", {})
    for lv_id, key in [
        ("dropped-by", "dropped_by"),
        ("sold-by", "sold_by"),
        ("reward-from-q", "reward_from_quests"),
        ("reward-from-a", "reward_from_achievements"),
        ("taught-by-item", "taught_by_items"),
    ]:
        if lv_id in lv:
            result[key] = lv[lv_id]

    return result


def parse_currency_page(html: str, entity_id: int) -> dict:
    result = _deep_parse(html, entity_id)

    lv = result.get("listviews", {})
    for lv_id, key in [
        ("sold-for", "purchases"),
        ("reward-from-q", "reward_from_quests"),
        ("reward-from-a", "reward_from_achievements"),
    ]:
        if lv_id in lv:
            result[key] = lv[lv_id]

    return result


def parse_transmog_set_page(html: str, entity_id: int) -> dict:
    result = _deep_parse(html, entity_id)

    lv = result.get("listviews", {})
    if "items" in lv:
        result["set_items"] = lv["items"]

    return result


def parse_questline_page(html: str, entity_id: int) -> dict:
    result = _deep_parse(html, entity_id)

    lv = result.get("listviews", {})
    if "quests" in lv:
        result["quest_list"] = lv["quests"]

    return result


def parse_event_page(html: str, entity_id: int) -> dict:
    result = _deep_parse(html, entity_id)

    lv = result.get("listviews", {})
    for lv_id, key in [
        ("quests", "event_quests"),
        ("achievements", "event_achievements"),
        ("items", "event_items"),
        ("npcs", "event_npcs"),
        ("spells", "event_spells"),
    ]:
        if lv_id in lv:
            result[key] = lv[lv_id]

    return result


def parse_faction_page(html: str, entity_id: int) -> dict:
    result = _deep_parse(html, entity_id)

    g = result.get("g_data", {}).get("g_factions", {})
    for key in ("name", "category", "side"):
        if key in g:
            result[key] = g[key]

    lv = result.get("listviews", {})
    for lv_id, key in [
        ("quests", "related_quests"),
        ("npcs", "related_npcs"),
        ("items", "purchasable_items"),
        ("reward-from-q", "reward_from_quests"),
    ]:
        if lv_id in lv:
            result[key] = lv[lv_id]

    return result


def parse_title_page(html: str, entity_id: int) -> dict:
    result = _deep_parse(html, entity_id)

    lv = result.get("listviews", {})
    for lv_id, key in [
        ("reward-from-a", "reward_from_achievements"),
        ("reward-from-q", "reward_from_quests"),
    ]:
        if lv_id in lv:
            result[key] = lv[lv_id]

    # Extract the title pattern (e.g., "%s the Kingslayer")
    m = re.search(r'<b[^>]*>Title:</b>\s*([^<]+)', html)
    if m:
        result["title_pattern"] = m.group(1).strip()

    return result


def parse_zone_page(html: str, entity_id: int) -> dict:
    result = _deep_parse(html, entity_id)

    g = result.get("g_data", {}).get("g_zones", {})
    for key in ("name", "category", "territory", "minlevel", "maxlevel",
                "instance", "nplayers"):
        if key in g:
            result[key] = g[key]

    lv = result.get("listviews", {})
    for lv_id, key in [
        ("npcs", "zone_npcs"),
        ("quests", "zone_quests"),
        ("objects", "zone_objects"),
        ("rares", "rare_npcs"),
        ("flight-paths", "flight_paths"),
        ("subzones", "subzones"),
    ]:
        if lv_id in lv:
            result[key] = lv[lv_id]

    return result


def parse_item_set_page(html: str, entity_id: int) -> dict:
    result = _deep_parse(html, entity_id)

    g = result.get("g_data", {}).get("g_itemsets", {})
    for key in ("name", "classs", "minlevel", "maxlevel", "type", "tag"):
        if key in g:
            result[key] = g[key]

    lv = result.get("listviews", {})
    if "items" in lv:
        result["set_items"] = lv["items"]

    # Extract set bonuses
    bonuses = []
    for m in re.finditer(r'<span class="q2">.*?\((\d+)\)\s*Set\s*:\s*(.*?)</span>', html, re.DOTALL):
        bonus_text = re.sub(r'<[^>]+>', '', m.group(2)).strip()
        if bonus_text:
            bonuses.append({"pieces": int(m.group(1)), "bonus": bonus_text})
    if bonuses:
        result["set_bonuses"] = bonuses

    return result


def parse_dungeon_page(html: str, entity_id: int) -> dict:
    result = _deep_parse(html, entity_id)

    lv = result.get("listviews", {})
    for lv_id, key in [
        ("bosses", "bosses"),
        ("loot", "loot_table"),
        ("quests", "dungeon_quests"),
        ("npcs", "dungeon_npcs"),
        ("achievements", "dungeon_achievements"),
    ]:
        if lv_id in lv:
            result[key] = lv[lv_id]

    return result


# Catch-all for entity types that don't need special handling
def parse_generic_page(html: str, entity_id: int) -> dict:
    return _deep_parse(html, entity_id)


# == Parser Registry ===========================================================

PARSERS = {
    # Core entities with specialized promotion logic
    "quest":            parse_quest_page,
    "npc":              parse_npc_page,
    "trainer":          parse_npc_page,
    "vendor":           parse_npc_page,
    "item":             parse_item_page,
    "spell":            parse_spell_page,
    "object":           parse_object_page,
    "achievement":      parse_achievement_page,
    "mount":            parse_mount_page,
    "currency":         parse_currency_page,
    "transmog_set":     parse_transmog_set_page,
    "questline":        parse_questline_page,
    "event":            parse_event_page,

    # All other targets use greedy generic extraction
    "transmog_item":    parse_generic_page,
    "class":            parse_generic_page,
    "race":             parse_generic_page,
    "specialization":   parse_generic_page,
    "profession":       parse_generic_page,
    "skill_ability":    parse_spell_page,     # same page structure as spells
    "profession_trait": parse_spell_page,     # same page structure as spells
    "battle_pet":       parse_npc_page,       # same page structure as NPCs
    "pet_family":       parse_generic_page,
    "garrison_mission": parse_generic_page,
    "garrison_building": parse_generic_page,
    "follower":         parse_generic_page,
    "dungeon":          parse_dungeon_page,
    "encounter":        parse_npc_page,       # encounters are NPC pages
    "zone":             parse_zone_page,
    "map":              parse_zone_page,       # maps use zone page structure
    "ui_map":           parse_zone_page,
    "flight_path":      parse_generic_page,
    "azerite_essence":  parse_generic_page,
    "azerite_power":    parse_generic_page,
    "icon":             parse_generic_page,
    "content_tuning":   parse_generic_page,
    "emote":            parse_generic_page,
    "item_set":         parse_item_set_page,
    "faction":          parse_faction_page,
    "title":            parse_title_page,
}
