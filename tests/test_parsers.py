"""Smoke tests for Wowhead page parsers."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from parsers import (
    PARSERS,
    _extract_all_listviews,
    _extract_all_g_data,
    _extract_infobox,
    _extract_mapper_data,
    _extract_all_images,
    _extract_tooltip,
    _extract_related_ids,
    _extract_gatherer_data,
    _extract_json_ld,
    _extract_page_info,
    _parse_js_value,
    _js_to_json,
    _safe_parse,
    parse_npc_page,
    parse_spell_page,
    parse_item_page,
)


# -- Shared extractor tests ---------------------------------------------------

def test_extract_all_listviews(npc_html):
    lv = _extract_all_listviews(npc_html)
    assert "drops" in lv
    assert "abilities" in lv
    assert lv["drops"][0]["id"] == 12345
    assert lv["abilities"][0]["id"] == 67890


def test_extract_all_g_data(npc_html):
    g = _extract_all_g_data(npc_html)
    assert "g_npcs" in g
    assert g["g_npcs"]["name"] == "Frost Vrykul (Type C)"


def test_extract_infobox(npc_html):
    info = _extract_infobox(npc_html)
    assert "level" in info or "type" in info
    assert info.get("type") == "Humanoid"


def test_extract_mapper_data(npc_html):
    mapper = _extract_mapper_data(npc_html)
    assert mapper is not None
    assert len(mapper) == 1
    assert mapper[0]["uiMapId"] == 115
    assert len(mapper[0]["coords"]) == 2


def test_extract_all_images(npc_html):
    imgs = _extract_all_images(npc_html)
    assert "icons" in imgs
    assert any("inv_misc_head_troll_01" in u for u in imgs["icons"])
    assert "screenshots" in imgs


def test_extract_related_ids(npc_html):
    rel = _extract_related_ids(npc_html)
    assert "spells" in rel
    assert 67890 in rel["spells"]
    assert "items" in rel
    assert 12345 in rel["items"]


def test_extract_gatherer_data(npc_html):
    gath = _extract_gatherer_data(npc_html)
    assert "npcs" in gath
    assert 29004 in gath["npcs"]
    assert gath["npcs"][29004]["name_enus"] == "Frost Vrykul (Type C)"


def test_extract_json_ld(npc_html):
    ld = _extract_json_ld(npc_html)
    assert len(ld) == 1
    assert ld[0]["@type"] == "BreadcrumbList"


def test_extract_page_info(npc_html):
    pi = _extract_page_info(npc_html)
    assert pi is not None
    assert pi["typeId"] == 29004


def test_extract_mapper_data_missing(empty_html):
    assert _extract_mapper_data(empty_html) is None


def test_extract_listviews_empty(empty_html):
    assert _extract_all_listviews(empty_html) == {}


def test_extract_infobox_empty(empty_html):
    assert _extract_infobox(empty_html) == {}


# -- Low-level helpers ---------------------------------------------------------

def test_parse_js_value_object():
    html = 'prefix {"key": "val"} suffix'
    result = _parse_js_value(html, 7, '{', '}')
    assert result == '{"key": "val"}'


def test_parse_js_value_nested():
    html = '[1, [2, 3], 4]'
    result = _parse_js_value(html, 0, '[', ']')
    assert result == '[1, [2, 3], 4]'


def test_js_to_json():
    assert '"name":' in _js_to_json('{name: "test"}')


def test_safe_parse_valid():
    assert _safe_parse('{"a": 1}') == {"a": 1}


def test_safe_parse_js_keys():
    result = _safe_parse('{name: "test", id: 5}')
    assert result is not None
    assert result["name"] == "test"


def test_safe_parse_garbage():
    assert _safe_parse("not json at all {{{") is None


# -- Parser registry -----------------------------------------------------------

EXPECTED_TARGETS = [
    "quest", "npc", "item", "spell", "object", "achievement",
    "mount", "currency", "transmog_set", "questline", "event",
    "zone", "faction", "title", "item_set", "dungeon",
]


def test_parsers_dict_populated():
    assert len(PARSERS) >= 30


def test_all_expected_targets_registered():
    for target in EXPECTED_TARGETS:
        assert target in PARSERS, f"{target} missing from PARSERS"


def test_all_parsers_callable():
    for name, func in PARSERS.items():
        assert callable(func), f"PARSERS['{name}'] is not callable"


# -- Entity-specific parser integration ----------------------------------------

def test_parse_npc_page(npc_html):
    result = parse_npc_page(npc_html, 29004)
    assert result["id"] == 29004
    assert result["name"] == "Frost Vrykul (Type C)"
    assert "drops" in result
    assert result["drops"][0]["id"] == 12345
    assert "abilities" in result
    assert "coords" in result
    assert len(result["coords"]) == 2
    assert "infobox" in result
    assert "relationship_web" in result


def test_parse_spell_page(spell_html):
    result = parse_spell_page(spell_html, 133)
    assert result["id"] == 133
    assert result["name"] == "Fireball"
    assert result.get("school") == 2
    assert "cast_by_npcs" in result
    assert "triggers_spells" in result
    assert "spell_formula_refs" in result
    assert 133 in result["spell_formula_refs"]
    assert 12654 in result["spell_formula_refs"]
    assert "effects" in result


def test_parse_item_page(item_html):
    result = parse_item_page(item_html, 19019)
    assert result["id"] == 19019
    assert result["quality"] == 5
    assert result["slot"] == 13
    assert "dropped_by" in result
    assert "same_model_as" in result
