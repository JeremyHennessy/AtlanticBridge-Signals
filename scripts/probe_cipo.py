from __future__ import annotations

import json
from html.parser import HTMLParser
from urllib.request import Request, urlopen

URL = "https://ised-isde.canada.ca/cipo/trademark-search/srch?lang=eng"


class FormProbe(HTMLParser):
    def __init__(self):
        super().__init__()
        self.forms = []
        self.current = None
        self.current_select = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "form":
            self.current = {
                "method": attrs.get("method", ""),
                "action": attrs.get("action", ""),
                "inputs": [],
                "selects": [],
            }
            self.forms.append(self.current)
        elif self.current is not None and tag == "input":
            self.current["inputs"].append(
                {
                    "name": attrs.get("name", ""),
                    "type": attrs.get("type", ""),
                    "value": attrs.get("value", ""),
                }
            )
        elif self.current is not None and tag == "select":
            self.current_select = {
                "name": attrs.get("name", ""),
                "options": [],
            }
            self.current["selects"].append(self.current_select)
        elif self.current_select is not None and tag == "option":
            self.current_select["options"].append(
                {
                    "value": attrs.get("value", ""),
                    "selected": "selected" in attrs,
                }
            )

    def handle_endtag(self, tag):
        if tag == "select":
            self.current_select = None
        elif tag == "form":
            self.current = None
            self.current_select = None


request = Request(
    URL,
    headers={
        "User-Agent": (
            "AtlanticBridge-Signals/0.1 "
            "(public-data research; https://github.com/JeremyHennessy/AtlanticBridge-Signals)"
        )
    },
)
with urlopen(request, timeout=60) as response:
    html = response.read().decode(response.headers.get_content_charset() or "utf-8", errors="replace")

parser = FormProbe()
parser.feed(html)

interesting = []
for form in parser.forms:
    named_inputs = [x for x in form["inputs"] if x["name"]]
    named_selects = [x for x in form["selects"] if x["name"]]
    if any(
        token in (item["name"] or "").lower()
        for item in [*named_inputs, *named_selects]
        for token in ("search", "field", "criteria", "action", "result", "status")
    ):
        interesting.append(
            {
                "method": form["method"],
                "action": form["action"],
                "inputs": named_inputs,
                "selects": named_selects,
            }
        )

print(
    json.dumps(
        {
            "url": URL,
            "html_bytes": len(html.encode("utf-8")),
            "form_count": len(parser.forms),
            "interesting_forms": interesting,
        },
        indent=2,
        ensure_ascii=False,
        sort_keys=True,
    )
)
