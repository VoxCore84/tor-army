#!/usr/bin/env python3
"""Generate DB2 Pre-Filtered ID Lists for Tor Army

Reads Wago DB2 CSVs (exported from https://wago.tools/) and outputs one
ID list per entity type. Only IDs that actually exist in the DB2 data are
included — this eliminates 35-40% of wasted requests vs brute-force ranges.

How to get the CSVs:
  1. Go to https://wago.tools/db2 and click "Export All" for each DB2 table
  2. Or use TACT/CASC extractors to dump client DB2 files to CSV
  3. Place CSVs in a directory (e.g. csv/enUS/)
  4. Run: python generate_id_lists.py --csv-dir csv/enUS/

CSV naming: {TableName}-enUS.csv (e.g. SpellName-enUS.csv, Creature-enUS.csv)

Output:
  id_lists/{target}.txt — one ID per line

Usage:
    python generate_id_lists.py --csv-dir path/to/csvs
    python generate_id_lists.py --csv-dir path/to/csvs --targets npc,quest
    python generate_id_lists.py --csv-dir path/to/csvs --stats
"""

import argparse
import csv
import os
import sys
from pathlib import Path

OUTPUT_DIR = Path(__file__).parent / "id_lists"

# CSV directory — set via --csv-dir flag or WAGO_CSV_DIR env var
WAGO_CSV_DIR: Path | None = None

_csv_cache: dict[str, dict] = {}


def load_wago_csv(name: str) -> dict[int, dict]:
    """Load a Wago CSV into a dict keyed by ID. Results are cached."""
    if name in _csv_cache:
        return _csv_cache[name]

    if WAGO_CSV_DIR is None:
        print(f"ERROR: No CSV directory set. Use --csv-dir or set WAGO_CSV_DIR env var.",
              file=sys.stderr)
        return {}

    path = WAGO_CSV_DIR / f"{name}-enUS.csv"
    if not path.exists():
        print(f"  [WARN] CSV not found: {path}", file=sys.stderr)
        _csv_cache[name] = {}
        return {}

    data = {}
    with open(path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                rid = int(row["ID"])
                data[rid] = row
            except (KeyError, ValueError):
                continue
    _csv_cache[name] = data
    return data

# ---------------------------------------------------------------------------
# Target -> DB2 table mappings
# ---------------------------------------------------------------------------
# Format: target_name -> (DB2_table_name, wowhead_url_pattern)
#
# Comprehensive list covering every Wowhead entity category.
# Some targets share the same URL pattern (e.g. trainer/vendor both use /npc=)
# but extract different data from the page.

TARGET_DB2_MAP = {
    # --- Core entities (individual page scrapes) ---
    "spell":              ("SpellName",              "/spell={id}"),
    "item":               ("ItemSparse",             "/item={id}"),
    "quest":              ("QuestV2",                "/quest={id}"),
    "object":             ("GameObjects",            "/object={id}"),
    "npc":                ("Creature",               "/npc={id}"),
    "achievement":        ("Achievement",            "/achievement={id}"),
    "mount":              ("Mount",                  "/mount={id}"),
    "currency":           ("CurrencyTypes",          "/currency={id}"),
    "faction":            ("Faction",                "/faction={id}"),
    "title":              ("CharTitles",             "/title={id}"),
    "questline":          ("QuestLine",              "/questline={id}"),
    "event":              ("Holidays",               "/event={id}"),
    "item_set":           ("ItemSet",                "/item-set={id}"),

    # --- Transmog & appearance ---
    "transmog_set":       ("TransmogSet",            "/transmog-set={id}"),
    "transmog_item":      ("ItemModifiedAppearance", "/transmog={id}"),

    # --- Classes, races, professions ---
    "class":              ("ChrClasses",             "/class={id}"),
    "race":               ("ChrRaces",               "/race={id}"),
    "specialization":     ("ChrSpecialization",      "/specialization={id}"),
    "profession":         ("SkillLine",              "/profession={id}"),
    "skill_ability":      ("SkillLineAbility",       "/skill-ability={id}"),
    "profession_trait":   ("TraitDefinition",        "/profession-trait={id}"),

    # --- Pet & mount related ---
    "battle_pet":         ("BattlePetSpecies",       "/pet={id}"),
    "pet_family":         ("CreatureFamily",         "/petfamily={id}"),

    # --- Garrison ---
    "garrison_mission":   ("GarrMission",            "/mission={id}"),
    "garrison_building":  ("GarrBuilding",           "/building={id}"),
    "follower":           ("GarrFollower",            "/follower={id}"),

    # --- Dungeon & encounter ---
    "dungeon":            ("JournalInstance",         "/dungeon={id}"),
    "encounter":          ("JournalEncounter",        "/npc={id}"),

    # --- Zones & maps ---
    "zone":               ("AreaTable",              "/zone={id}"),
    "map":                ("Map",                    "/map={id}"),
    "ui_map":             ("UiMap",                  "/zone={id}"),
    "flight_path":        ("TaxiNodes",              "/taxinode={id}"),

    # --- Azerite ---
    "azerite_essence":    ("AzeriteEssence",         "/azerite-essence={id}"),
    "azerite_power":      ("AzeriteEssencePower",    "/azerite-essence-power={id}"),

    # --- Icons (FileDataID-based) ---
    "icon":               ("ManifestInterfaceData",  "/icon={id}"),

    # --- Content tuning ---
    "content_tuning":     ("ContentTuning",          "/content-tuning={id}"),

    # --- Emotes ---
    "emote":              ("Emotes",                 "/emote={id}"),
}

# Targets whose URLs overlap with a parent target (no extra HTTP requests needed)
SUBSET_TARGETS = {
    "toy":      ("Toy",       "item"),     # /item= URLs, subset of "item" scrape
    "heirloom": ("Heirloom",  "item"),     # /item= URLs, subset of "item" scrape
}


# ---------------------------------------------------------------------------
# CSV loading (supports arbitrary directory for delta mode)
# ---------------------------------------------------------------------------

def load_csv_from_dir(table_name: str, csv_dir: Path) -> dict[int, dict]:
    """Load a DB2 CSV keyed by ID from a specific directory."""
    path = csv_dir / f"{table_name}-enUS.csv"
    if not path.exists():
        return {}

    data = {}
    with open(path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                rid = int(row["ID"])
                data[rid] = row
            except (KeyError, ValueError):
                continue
    return data


def find_csv_dir(build_number: int) -> Path | None:
    """Find the merged CSV directory for a given build number."""
    base = Path(__file__).parent
    # Try merged first (best source), then tact, then raw wago
    for pattern in [
        f"merged_csv/12.0.1.{build_number}/enUS",
        f"tact_csv/12.0.1.{build_number}/enUS",
        f"wago_csv/major_12/12.0.1.{build_number}/enUS",
    ]:
        d = base / pattern
        if d.exists():
            return d
    return None


# ---------------------------------------------------------------------------
# Full ID list generation
# ---------------------------------------------------------------------------

def generate_list(target: str) -> list[int]:
    """Load IDs from DB2 CSV for a target."""
    if target in TARGET_DB2_MAP:
        table_name, _ = TARGET_DB2_MAP[target]
    elif target in SUBSET_TARGETS:
        table_name, _ = SUBSET_TARGETS[target][:2]
    else:
        print(f"  [SKIP] Unknown target: {target}")
        return []

    data = load_wago_csv(table_name)
    if not data:
        print(f"  [WARN] No data for {table_name} (CSV missing at {WAGO_CSV_DIR})")
        return []

    return sorted(data.keys())


# ---------------------------------------------------------------------------
# Delta ID list generation (new + changed between builds)
# ---------------------------------------------------------------------------

def generate_delta_list(target: str, old_dir: Path) -> tuple[list[int], list[int]]:
    """Compare old build CSV vs new build CSV.

    Returns:
        (new_ids, changed_ids) — IDs only in new build, and IDs with different values.
    """
    if target in TARGET_DB2_MAP:
        table_name, _ = TARGET_DB2_MAP[target]
    elif target in SUBSET_TARGETS:
        table_name, _ = SUBSET_TARGETS[target][:2]
    else:
        return [], []

    new_data = load_wago_csv(table_name)
    old_data = load_csv_from_dir(table_name, old_dir)

    if not new_data:
        return [], []

    new_keys = set(new_data.keys())
    old_keys = set(old_data.keys())

    # IDs that exist in new build but not old
    new_ids = sorted(new_keys - old_keys)

    # IDs that exist in both but have different column values
    changed_ids = []
    common_keys = new_keys & old_keys
    for rid in sorted(common_keys):
        new_row = new_data[rid]
        old_row = old_data[rid]
        # Compare all shared columns
        for col in new_row:
            if col in old_row and new_row[col] != old_row[col]:
                changed_ids.append(rid)
                break

    return new_ids, changed_ids


# ---------------------------------------------------------------------------
# File I/O
# ---------------------------------------------------------------------------

def write_list(target: str, ids: list[int], out_dir: Path):
    """Write ID list to file."""
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{target}.txt"
    out_file.write_text("\n".join(str(i) for i in ids) + "\n", encoding="utf-8")
    return out_file


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def validate_sync():
    """Check that TARGET_DB2_MAP stays in sync with scraper_v4.py TARGET_CONFIGS."""
    try:
        scraper_path = Path(__file__).parent / "scraper_v4.py"
        if not scraper_path.exists():
            return
        text = scraper_path.read_text(encoding="utf-8")
        # Extract target names from TARGET_CONFIGS dict
        import re
        scraper_targets = set(re.findall(r'"(\w+)":\s*_cfg\(', text))
        our_targets = set(TARGET_DB2_MAP.keys()) | set(SUBSET_TARGETS.keys())

        missing_here = scraper_targets - our_targets
        missing_there = our_targets - scraper_targets

        if missing_here:
            print(f"  [SYNC WARN] Targets in scraper_v4.py but not in generate_id_lists.py:")
            for t in sorted(missing_here):
                print(f"    - {t}")
        if missing_there:
            print(f"  [SYNC WARN] Targets in generate_id_lists.py but not in scraper_v4.py:")
            for t in sorted(missing_there):
                print(f"    - {t}")
    except Exception:
        pass


def main():
    parser = argparse.ArgumentParser(description="Generate DB2 pre-filtered ID lists")
    parser.add_argument("--csv-dir", type=str, default=None,
                        help="Path to Wago DB2 CSVs (or set WAGO_CSV_DIR env var)")
    parser.add_argument("--targets", type=str, default=None,
                        help="Comma-separated targets (default: all)")
    parser.add_argument("--stats", action="store_true",
                        help="Show counts only, don't write files")
    parser.add_argument("--include-subsets", action="store_true",
                        help="Also generate lists for subset targets (toy, heirloom)")
    parser.add_argument("--build-delta", type=str, default=None, metavar="OLD_CSV_DIR",
                        help="Generate delta lists: only new/changed IDs vs OLD_CSV_DIR")
    parser.add_argument("--validate", action="store_true",
                        help="Validate ID range sanity")
    args = parser.parse_args()

    # Resolve CSV directory
    global WAGO_CSV_DIR
    csv_dir = args.csv_dir or os.environ.get("WAGO_CSV_DIR")
    if not csv_dir:
        print("ERROR: No CSV directory specified.")
        print("  Use: python generate_id_lists.py --csv-dir path/to/csvs/")
        print("  Or set the WAGO_CSV_DIR environment variable.")
        print()
        print("  CSVs can be exported from https://wago.tools/db2")
        print("  Expected naming: {TableName}-enUS.csv (e.g. SpellName-enUS.csv)")
        sys.exit(1)
    WAGO_CSV_DIR = Path(csv_dir)
    if not WAGO_CSV_DIR.exists():
        print(f"ERROR: CSV directory does not exist: {WAGO_CSV_DIR}")
        sys.exit(1)

    all_targets = list(TARGET_DB2_MAP.keys())
    if args.include_subsets:
        all_targets += list(SUBSET_TARGETS.keys())

    if args.targets:
        targets = [t.strip() for t in args.targets.split(",")]
    else:
        targets = all_targets

    # Delta mode setup
    old_dir = None
    if args.build_delta:
        old_dir = Path(args.build_delta)
        if not old_dir.exists():
            print(f"ERROR: Old CSV directory does not exist: {old_dir}")
            sys.exit(1)
        out_dir = OUTPUT_DIR / "delta"
        print(f"BUILD DELTA MODE")
        print(f"  Old CSVs: {old_dir}")
        print(f"  New CSVs: {WAGO_CSV_DIR}")
        print(f"  Output:   {out_dir}")
    else:
        out_dir = OUTPUT_DIR
        print(f"DB2 Pre-Filter ID List Generator")
        print(f"  CSV source: {WAGO_CSV_DIR}")
        print(f"  Output dir: {out_dir}")

    # Cross-check target lists stay in sync
    validate_sync()

    print()

    total_new = 0
    total_changed = 0
    total_full = 0
    targets_with_data = 0
    targets_empty = 0
    id_range_issues = []

    for target in sorted(targets):
        is_subset = target in SUBSET_TARGETS

        if args.build_delta:
            new_ids, changed_ids = generate_delta_list(target, old_dir)
            combined = sorted(set(new_ids + changed_ids))
            total_new += len(new_ids)
            total_changed += len(changed_ids)

            subset_note = f" (subset of {SUBSET_TARGETS[target][1]})" if is_subset else ""

            if args.stats:
                print(f"  {target:25s}: {len(new_ids):>6} new  {len(changed_ids):>6} changed"
                      f"  = {len(combined):>6} total{subset_note}")
            else:
                if combined:
                    out_file = write_list(target, combined, out_dir)
                    print(f"  {target:25s}: {len(new_ids):>6} new  {len(changed_ids):>6} changed"
                          f"  = {len(combined):>6} total -> {out_file.name}{subset_note}")
                    targets_with_data += 1
                else:
                    print(f"  {target:25s}:      0 new       0 changed  (no delta)")
                    targets_empty += 1
        else:
            ids = generate_list(target)
            count = len(ids)
            total_full += count

            subset_note = f" (subset of {SUBSET_TARGETS[target][1]})" if is_subset else ""

            if args.stats or args.validate:
                # Show ID range for validation
                if ids:
                    id_min, id_max = ids[0], ids[-1]
                    density = count / max(id_max - id_min + 1, 1) * 100
                    range_info = f"  range={id_min}-{id_max}  density={density:.1f}%"
                    if density < 5:
                        id_range_issues.append((target, density, id_min, id_max, count))
                else:
                    range_info = ""
                print(f"  {target:25s}: {count:>9,} IDs{range_info}{subset_note}")
            else:
                if ids:
                    out_file = write_list(target, ids, out_dir)
                    print(f"  {target:25s}: {count:>9,} IDs -> {out_file.name}{subset_note}")
                    targets_with_data += 1
                else:
                    print(f"  {target:25s}:         0 IDs (skipped)")
                    targets_empty += 1

    print()
    if args.build_delta:
        total_combined = total_new + total_changed
        print(f"  New IDs:      {total_new:>9,}")
        print(f"  Changed IDs:  {total_changed:>9,}")
        print(f"  Total delta:  {total_combined:>9,}")
    else:
        print(f"  Total IDs:    {total_full:>9,}")
        if not args.stats:
            print(f"  Targets:      {targets_with_data} with data, {targets_empty} empty")

    if id_range_issues:
        print(f"\n  [WARN] Low-density ID ranges (may indicate sparse DB2 data):")
        for target, density, id_min, id_max, count in id_range_issues:
            print(f"    {target:25s}: {count:>7,} IDs across {id_max - id_min + 1:>9,} "
                  f"range ({density:.1f}% dense)")


if __name__ == "__main__":
    main()
