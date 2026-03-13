"""Shared fixtures for parser smoke tests."""

import pytest


@pytest.fixture
def npc_html():
    """Synthetic HTML mimicking a Wowhead NPC page (e.g. npc=29004)."""
    return """
    <html><head><title>Frost Vrykul (Type C) - NPC - World of Warcraft</title></head>
    <body>
    <h1 class="heading-size-1">Frost Vrykul (Type C)</h1>

    <script>
    $.extend(g_npcs[29004], {"classification":0,"displayName":"Frost Vrykul (Type C)",
        "id":29004,"name":"Frost Vrykul (Type C)","type":7});
    </script>

    <script>
    WH.markup.printHtml("[ul][li]Level: 30[/li][li]Type: Humanoid[/li][li]Health: 12,000[/li][/ul]", "infobox-contents-0", {});
    </script>

    <script>
    WH.Listview({id:'drops', data:[{"id":12345,"name":"Frostweave Cloth","count":5,"outof":100}]});
    WH.Listview({id:'abilities', data:[{"id":67890,"name":"Frost Bolt"}]});
    </script>

    <script>
    g_mapperData = [{"uiMapId": 115, "coords": [[45.2, 62.1], [46.0, 63.5]]}];
    </script>

    <script>
    WH.Gatherer.addData(1, 0, {"29004": {"name_enus": "Frost Vrykul (Type C)", "icon": "inv_misc_head_troll_01"}});
    </script>

    <script type="application/ld+json">{"@type": "BreadcrumbList", "name": "test"}</script>

    <script>g_pageInfo = {type: 1, typeId: 29004, name: "Frost Vrykul (Type C)"};</script>

    <img src="https://wow.zamimg.com/images/wow/icons/large/inv_misc_head_troll_01.jpg">
    <img src="https://wow.zamimg.com/uploads/screenshots/normal/123456.jpg">
    <a href="/spell=67890/frost-bolt">Frost Bolt</a>
    <a href="/item=12345/frostweave-cloth">Frostweave Cloth</a>
    </body></html>
    """


@pytest.fixture
def spell_html():
    """Synthetic HTML mimicking a Wowhead spell page."""
    return """
    <html><head><title>Fireball - Spell - World of Warcraft</title></head>
    <body>
    <h1 class="heading-size-1">Fireball</h1>

    <script>
    $.extend(g_spells[133], {"name":"Fireball","icon":"spell_fire_flamebolt",
        "school":2,"cat":0,"skill":[8,4],"range":40,"cast":2500,"gcd":1500,"cooldown":0});
    </script>

    <script>
    WH.markup.printHtml("[ul][li]School: Fire[/li][li]Mechanic: n/a[/li][/ul]", "infobox-contents-0", {});
    </script>

    <script>
    WH.Listview({id:'cast-by-npc', data:[{"id":100,"name":"Fire Elemental"}]});
    WH.Listview({id:'triggers', data:[{"id":12654,"name":"Ignite"}]});
    </script>

    <!--sp133--><!--sp12654-->

    <td>Effect #1</td><td>School Damage (Fire)</td>
    </body></html>
    """


@pytest.fixture
def item_html():
    """Synthetic HTML mimicking a Wowhead item page."""
    return """
    <html><head><title>Thunderfury - Item - World of Warcraft</title></head>
    <body>
    <h1 class="heading-size-1">Thunderfury, Blessed Blade of the Windseeker</h1>

    <script>
    $.extend(g_items[19019], {"classs":2,"subclass":7,"quality":5,"level":80,
        "name":"Thunderfury, Blessed Blade of the Windseeker","icon":"inv_sword_39",
        "slot":13,"sellprice":255442});
    </script>

    <script>
    WH.Listview({id:'dropped-by', data:[{"id":12435,"name":"Razorgore the Untamed"}]});
    WH.Listview({id:'same-model-as', data:[{"id":30000,"name":"Some Sword"}]});
    </script>

    <script>
    WH.markup.printHtml("[ul][li]Item Level: 80[/li][li]Binds when picked up[/li][/ul]", "infobox-contents-0", {});
    </script>
    </body></html>
    """


@pytest.fixture
def empty_html():
    """Minimal HTML with no Wowhead data structures."""
    return "<html><head><title>Empty</title></head><body></body></html>"
