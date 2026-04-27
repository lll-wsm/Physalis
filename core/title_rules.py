"""Per-domain title extraction rule manager.

Loads title extraction rules from ``title_rules.json`` in the config directory
and generates JavaScript for extracting titles from page DOM.
"""

import json
from pathlib import Path
from urllib.parse import urlparse

from core.config import _config_dir

DEFAULT_RULES: dict = {
    "default": {
        "selectors": [
            {"type": "meta", "property": "og:title"},
            {"type": "jsonld", "path": "name"},
            {"type": "jsonld", "path": "headline"},
            {"type": "meta", "property": "og:description"},
            {"type": "dom", "selector": "h1, h2, [class*=video-title], [class*=VideoTitle], .dy-title, .dy-desc, .desc, .detail-title, .article-title, .video-info, .short-video-title"},
            {"type": "url_path"},
            {"type": "document_title"},
        ],
        "min_length": 4,
    },
    "douyin.com": {
        "selectors": [
            {"type": "meta", "property": "og:title"},
            {"type": "jsonld", "path": "name"},
            {"type": "dom", "selector": ".video-info-title"},
            {"type": "dom", "selector": ".dy-title"},
            {"type": "dom", "selector": ".desc"},
            {"type": "dom", "selector": "h1"},
            {"type": "document_title"},
        ],
        "min_length": 4,
    },
    "bilibili.com": {
        "selectors": [
            {"type": "meta", "property": "og:title"},
            {"type": "jsonld", "path": "name"},
            {"type": "dom", "selector": ".video-title"},
            {"type": "dom", "selector": "#video-title"},
            {"type": "dom", "selector": "h1"},
            {"type": "document_title"},
        ],
        "min_length": 2,
    },
    "youtube.com": {
        "selectors": [
            {"type": "meta", "property": "og:title"},
            {"type": "jsonld", "path": "name"},
            {"type": "dom", "selector": "h1"},
            {"type": "dom", "selector": "#title"},
            {"type": "document_title"},
        ],
        "min_length": 2,
    },
    "weibo.com": {
        "selectors": [
            {"type": "meta", "property": "og:title"},
            {"type": "dom", "selector": ".WB_text"},
            {"type": "document_title"},
        ],
        "min_length": 2,
    },
    "xiaohongshu.com": {
        "selectors": [
            {"type": "meta", "property": "og:title"},
            {"type": "dom", "selector": ".title"},
            {"type": "dom", "selector": "h1"},
            {"type": "document_title"},
        ],
        "min_length": 2,
    },
    "kuaishou.com": {
        "selectors": [
            {"type": "meta", "property": "og:title"},
            {"type": "dom", "selector": ".video-title"},
            {"type": "dom", "selector": "h1"},
            {"type": "document_title"},
        ],
        "min_length": 4,
    },
    "tiktok.com": {
        "selectors": [
            {"type": "meta", "property": "og:title"},
            {"type": "jsonld", "path": "name"},
            {"type": "dom", "selector": "h1"},
            {"type": "document_title"},
        ],
        "min_length": 2,
    },
}


def _domain_from_url(url: str) -> str:
    """Extract the registrable domain (last two parts) from a URL."""
    try:
        host = urlparse(url).hostname or ""
        parts = host.split(".")
        return ".".join(parts[-2:]).lower() if len(parts) >= 2 else host.lower()
    except Exception:
        return ""


def _escape_js(s: str) -> str:
    """Escape a string for embedding as a JS string literal (single-quoted)."""
    s = s.replace("\\", "\\\\")
    s = s.replace("'", "\\'")
    s = s.replace("\n", "\\n")
    s = s.replace("\r", "\\r")
    s = s.replace("\t", "\\t")
    return s


def _build_selector_js(sel: dict) -> str:
    """Generate the JS code block for a single selector dict.

    Returns a JS snippet that defines an IIFE returning the extracted text
    or an empty string.
    """
    stype = sel.get("type", "")
    if stype == "meta":
        prop = sel.get("property", "")
        name = sel.get("name", "")
        if prop:
            attr = f'property="{_escape_js(prop)}"'
        elif name:
            attr = f'name="{_escape_js(name)}"'
        else:
            return ""
        return f"""(function(){{var m=document.querySelector('meta[{attr}]');if(m&&(m.content||"").trim()){{var t=m.content.trim();if(_a(t))return t;}}}})()"""

    elif stype == "jsonld":
        path = sel.get("path", "name")
        spath = _escape_js(path)
        return f"""(function(){{var s=document.querySelectorAll('script[type="application/ld+json"]');for(var i=0;i<s.length;i++){{try{{var d=JSON.parse(s[i].textContent||s[i].innerText||"");var items=d["@graph"]||[d];for(var j=0;j<items.length;j++){{var t=items[j].{spath}||"";t=(typeof t==="string"?t:"").trim();if(_a(t))return t;}}}}catch(e){{}}}}}})()"""

    elif stype == "dom":
        selector = sel.get("selector", "")
        if not selector:
            return ""
        ss = _escape_js(selector)
        return f"""(function(){{var e=document.querySelector('{ss}');if(e){{var t=(e.textContent||"").trim();if(_a(t))return t;}}}})()"""

    elif stype == "url_path":
        return """(function(){var p=window.location.pathname.replace(/\\/+$/,'').split('/').pop()||'';if(p&&p.length>4&&_a(p))return p;})()"""

    elif stype == "document_title":
        return """(function(){var t=document.title.replace(/\\s*[-|–—]\\s*.*$/,'').trim();if(_a(t))return t;})()"""

    return ""


def _build_full_js(selectors: list[dict], min_length: int) -> str:
    """Build complete title extraction JS from a list of selector dicts.

    The generated code returns the first acceptable result, or ``""``.
    """
    if not selectors:
        return "(function(){return '';})()"

    parts = [f"(function(){{function _a(t){{return t&&t.length>={min_length}&&t.length<200;}}"]
    for sel in selectors:
        block = _build_selector_js(sel)
        if block:
            parts.append(f"var r={block};if(r)return r;")
    parts.append("return '';})()")
    return "\n".join(parts)


def _build_test_js(sel: dict) -> str:
    """Build JS to test a single selector and return the extracted text."""
    stype = sel.get("type", "")

    if stype == "dom":
        selector = sel.get("selector", "")
        if not selector:
            return "(function(){return '';})()"
        ss = _escape_js(selector)
        return f"(function(){{try{{var e=document.querySelector('{ss}');return e?(e.textContent||'').trim():'';}}catch(e){{return '';}}}})()"
    elif stype == "meta":
        prop = sel.get("property", "")
        name = sel.get("name", "")
        if prop:
            attr = f'property="{_escape_js(prop)}"'
        elif name:
            attr = f'name="{_escape_js(name)}"'
        else:
            return "(function(){return '';})()"
        return f"(function(){{try{{var m=document.querySelector('meta[{attr}]');return m?(m.content||'').trim():'';}}catch(e){{return '';}}}})()"
    elif stype == "jsonld":
        path = sel.get("path", "name")
        spath = _escape_js(path)
        return f"(function(){{try{{var s=document.querySelectorAll('script[type=\"application/ld+json\"]');for(var i=0;i<s.length;i++){{try{{var d=JSON.parse(s[i].textContent||s[i].innerText||'');var items=d['@graph']||[d];for(var j=0;j<items.length;j++){{var t=items[j].{spath}||'';t=(typeof t==='string'?t:'').trim();if(t&&t.length>0)return t;}}}}catch(e){{}}}}}}catch(e){{}}return '';}})()"
    elif stype == "url_path":
        return "(function(){try{var p=window.location.pathname.replace(/\\/+$/,'').split('/').pop()||'';return p||'';}catch(e){return '';}})()"
    elif stype == "document_title":
        return "(function(){try{var t=document.title.replace(/\\s*[-|–—]\\s*.*$/,'').trim();return t||'';}catch(e){return '';}})()"
    return "(function(){return '';})()"


class TitleRuleManager:
    """Manages per-domain title extraction rules in ``title_rules.json``."""

    def __init__(self):
        self._path = _config_dir() / "title_rules.json"
        self._rules: dict = {}
        self._load()

    def _load(self):
        if self._path.exists():
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    self._rules = json.load(f)
            except (json.JSONDecodeError, OSError):
                self._rules = {}
        self._ensure_default()

    def _save(self):
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(self._rules, f, indent=2, ensure_ascii=False)

    def _ensure_default(self):
        if "default" not in self._rules:
            self._rules["default"] = {
                "selectors": [
                    {"type": "meta", "property": "og:title"},
                    {"type": "jsonld", "path": "name"},
                    {"type": "jsonld", "path": "headline"},
                    {"type": "meta", "property": "og:description"},
                    {"type": "dom", "selector": "h1"},
                    {"type": "url_path"},
                    {"type": "document_title"},
                ],
                "min_length": 4,
            }

    def rule_for_url(self, url: str) -> dict:
        """Return the rule dict best matching *url*, falling back to ``"default"``."""
        domain = _domain_from_url(url)
        return self.rule_for_domain(domain) or self._rules.get("default", {})

    def rule_for_domain(self, domain: str) -> dict | None:
        """Look up a domain rule by direct key or subdomain matching."""
        domain = domain.lower()
        # Exact match
        if domain in self._rules:
            return self._rules[domain]
        # Subdomain: try stripping leftmost part step by step
        parts = domain.split(".")
        for i in range(1, len(parts) - 1):
            candidate = ".".join(parts[i:])
            if candidate in self._rules:
                return self._rules[candidate]
        # Partial suffix match
        for key in self._rules:
            if domain.endswith("." + key) or domain == key:
                return self._rules[key]
        return self._rules.get("default")

    def set_rule_for_domain(self, domain: str, rule: dict):
        """Set (overwrite) the entire rule for a domain and save."""
        self._rules[domain.lower()] = rule
        self._save()

    def add_selector_to_domain(self, domain: str, selector: dict):
        """Append a selector to a domain's rule list (creates domain rule if needed)."""
        domain = domain.lower()
        if domain not in self._rules:
            self._rules[domain] = {
                "selectors": [],
                "min_length": self._rules.get("default", {}).get("min_length", 4),
            }
        self._rules[domain]["selectors"].append(selector)
        self._save()

    def remove_selector_from_domain(self, domain: str, index: int):
        """Remove a selector at *index* from a domain's rule list."""
        domain = domain.lower()
        if domain in self._rules:
            selectors = self._rules[domain].get("selectors", [])
            if 0 <= index < len(selectors):
                selectors.pop(index)
                self._save()

    def delete_rule(self, domain: str):
        """Remove a domain rule entirely. Cannot remove ``"default"``."""
        if domain.lower() == "default":
            return
        self._rules.pop(domain.lower(), None)
        self._save()

    def reset_to_defaults(self):
        """Replace all rules with built-in defaults."""
        self._rules = dict(DEFAULT_RULES)
        self._save()

    def set_min_length(self, domain: str, value: int):
        """Update ``min_length`` for a domain."""
        domain = domain.lower()
        if domain not in self._rules:
            self._rules[domain] = {"selectors": [], "min_length": value}
        else:
            self._rules[domain]["min_length"] = max(1, min(value, 50))
        self._save()

    def generate_js(self, url: str) -> str:
        """Generate complete title extraction JS for *url*."""
        rule = self.rule_for_url(url)
        selectors = rule.get("selectors", [])
        min_length = rule.get("min_length", 4)
        return _build_full_js(selectors, min_length)

    def generate_test_js(self, type_: str, value: str) -> str:
        """Generate JS to test a single selector and return extracted text.

        *value* is interpreted based on *type_*:
        - ``"dom"`` → CSS selector
        - ``"meta"`` → ``property`` attribute
        - ``"jsonld"`` → field path
        - ``"url_path"``, ``"document_title"`` → *value* is ignored
        """
        if type_ == "dom":
            return _build_test_js({"type": "dom", "selector": value})
        elif type_ == "meta":
            return _build_test_js({"type": "meta", "property": value})
        elif type_ == "jsonld":
            return _build_test_js({"type": "jsonld", "path": value})
        elif type_ == "url_path":
            return _build_test_js({"type": "url_path"})
        elif type_ == "document_title":
            return _build_test_js({"type": "document_title"})
        return "(function(){return '';})()"

    @property
    def all_domains(self) -> list[str]:
        """Return sorted list of domain keys (``"default"`` first)."""
        keys = sorted(k for k in self._rules if k != "default")
        return ["default"] + keys
