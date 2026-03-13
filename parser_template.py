"""Template: Writing a parser for a non-Wowhead site.

Each parser is a function that takes raw HTML and an entity ID,
extracts structured data, and returns a dict.  Register it in
the PARSERS dict at the bottom of parsers.py so the scraper
automatically routes pages to your function.
"""

import re
from bs4 import BeautifulSoup


def parse_mysite_page(html: str, entity_id: int) -> dict:
    """Parse a page from mysite.example.com and return structured data.

    Args:
        html:       Full page HTML as a string (already decoded).
        entity_id:  The numeric ID being scraped (used for output keying).

    Returns:
        Dict with extracted fields.  At minimum, include 'id' and 'name'.
        Add whatever fields the site exposes -- the scraper stores the
        entire dict as JSON, so be greedy.
    """
    soup = BeautifulSoup(html, "html.parser")
    result: dict = {"id": entity_id}

    # -- Name: grab from the page title or a heading --------------------------
    heading = soup.select_one("h1.entry-title, h1.page-title, h1")
    if heading:
        result["name"] = heading.get_text(strip=True)

    # -- Sidebar / infobox key-value pairs ------------------------------------
    infobox: dict = {}
    for row in soup.select("table.infobox tr"):
        cells = row.find_all("td")
        if len(cells) == 2:
            key = cells[0].get_text(strip=True).rstrip(":").lower().replace(" ", "_")
            val = cells[1].get_text(strip=True)
            infobox[key] = val
    if infobox:
        result["infobox"] = infobox

    # -- Embedded JSON data (common pattern: JS variable in a <script>) -------
    #    Many sites embed data like:  var pageData = { ... };
    #    Use regex to pull the JSON blob, then json.loads() it.
    import json
    for script in soup.find_all("script"):
        text = script.string or ""
        m = re.search(r"var\s+pageData\s*=\s*(\{.+?\})\s*;", text, re.DOTALL)
        if m:
            try:
                result["page_data"] = json.loads(m.group(1))
            except json.JSONDecodeError:
                pass  # skip malformed blobs -- don't crash the scraper

    return result


# ---- Registration -----------------------------------------------------------
# In parsers.py, add your parser to the PARSERS dict:
#
#   PARSERS = {
#       ...
#       "mysite_entity":  parse_mysite_page,   # <-- add this line
#   }
#
# The dict key must match the target name used in generate_id_lists.py
# so the scraper knows which parser handles which target's HTML.
