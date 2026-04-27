import json
from pathlib import Path

from PyQt6.QtCore import Qt, QDateTime, QObject, QTimer
from PyQt6.QtNetwork import QNetworkCookie

from core.config import _config_dir


_COOKIE_FILE = _config_dir() / "cookies.json"
_SAVE_DELAY_MS = 2000


def _cookie_to_dict(c: QNetworkCookie) -> dict:
    name = bytes(c.name()).decode("utf-8", errors="replace")
    value = bytes(c.value()).decode("utf-8", errors="replace")
    domain = c.domain() or ""
    path = c.path() or "/"
    secure = c.isSecure()
    httponly = c.isHttpOnly()

    expiry_dt = c.expirationDate()
    expiry = expiry_dt.toString(Qt.DateFormat.ISODate) if expiry_dt and expiry_dt.isValid() else None

    return {
        "domain": domain,
        "name": name,
        "value": value,
        "path": path,
        "secure": secure,
        "httponly": httponly,
        "expiry": expiry,
    }


def _dict_to_cookie(d: dict) -> QNetworkCookie | None:
    name = d.get("name", "")
    value = d.get("value", "")
    if not name:
        return None

    c = QNetworkCookie(name.encode("utf-8"), value.encode("utf-8"))

    domain = d.get("domain", "")
    if domain:
        c.setDomain(domain)

    path = d.get("path", "/")
    if path:
        c.setPath(path)

    if d.get("secure", False):
        c.setSecure(True)

    if d.get("httponly", False):
        c.setHttpOnly(True)

    expiry_str = d.get("expiry")
    if expiry_str:
        dt = QDateTime.fromString(expiry_str, Qt.DateFormat.ISODate)
        if dt.isValid():
            c.setExpirationDate(dt)
    # Session cookies (null expiry) are left as-is

    return c


class CookieManager(QObject):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._cookies: list[QNetworkCookie] = []
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.timeout.connect(self._do_save)

    # ── Public API ────────────────────────────────────────────────

    def add_cookie(self, cookie: QNetworkCookie):
        """Add or update a cookie."""
        self._remove_matching(cookie)
        self._cookies.append(QNetworkCookie(cookie))
        self._schedule_save()

    def remove_cookie(self, cookie: QNetworkCookie):
        """Remove an exact cookie match."""
        try:
            self._cookies.remove(cookie)
        except ValueError:
            self._remove_matching(cookie)
        self._schedule_save()

    def for_domain(self, domain: str) -> list[QNetworkCookie]:
        """Return cookies matching the given domain or its subdomains."""
        if not domain:
            return []
        result = []
        for c in self._cookies:
            cd = c.domain() or ""
            if cd == domain or cd.endswith("." + domain):
                result.append(QNetworkCookie(c))
        return result

    def remove_domain(self, domain: str):
        """Remove all cookies matching the domain and its subdomains."""
        self._cookies = [
            c for c in self._cookies
            if not (c.domain() == domain or c.domain().endswith("." + domain))
        ]
        self._schedule_save()

    def clear_all(self):
        """Remove all cookies."""
        self._cookies.clear()
        self._schedule_save()

    def has_any(self) -> bool:
        return len(self._cookies) > 0

    def all_cookies(self) -> list[QNetworkCookie]:
        return [QNetworkCookie(c) for c in self._cookies]

    # ── Persistence ───────────────────────────────────────────────

    def load(self, path: str | Path | None = None):
        """Load cookies from JSON file. Clears current in-memory state first."""
        p = Path(path) if path else _COOKIE_FILE
        if not p.exists():
            return

        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            return

        self._cookies.clear()
        for entry in data:
            c = _dict_to_cookie(entry)
            if c is not None:
                self._cookies.append(c)

    def save(self, path: str | Path | None = None):
        """Synchronously write cookies to JSON file."""
        p = Path(path) if path else _COOKIE_FILE
        data = [_cookie_to_dict(c) for c in self._cookies]
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            with open(p, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except OSError:
            pass

    # ── Internal ──────────────────────────────────────────────────

    def _schedule_save(self):
        self._save_timer.stop()
        self._save_timer.start(_SAVE_DELAY_MS)

    def _do_save(self):
        self.save()

    def _remove_matching(self, needle: QNetworkCookie):
        """Remove any cookie with the same domain/name/path."""
        nd = needle.domain() or ""
        nn = bytes(needle.name())
        np_ = needle.path() or "/"
        self._cookies = [
            c for c in self._cookies
            if not ((c.domain() or "") == nd
                    and bytes(c.name()) == nn
                    and (c.path() or "/") == np_)
        ]
