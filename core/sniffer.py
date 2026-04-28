import time
from dataclasses import dataclass, field
from urllib.parse import urlparse, urlunparse

from PyQt6.QtWebEngineCore import QWebEngineUrlRequestInfo, QWebEngineUrlRequestInterceptor
from PyQt6.QtCore import pyqtSignal


@dataclass
class SniffedVideo:
    url: str
    page_url: str
    referer: str
    format_hint: str     # "m3u8" / "mp4" / "dash" / "flv" / "m4s" / "webm" / "media"
    quality: str = ""    # Reserved for future quality extraction from URL
    page_title: str = "" # Page title set by BrowserWindow when available
    content_length: int = 0  # Bytes from Content-Length header (HEAD probe)
    content_type: str = ""   # MIME type from server response
    timestamp: float = field(default_factory=time.time)


# URL suffixes that indicate media content (.ts excluded — too many false positives with JS bundles)
_MEDIA_SUFFIXES = (".m3u8", ".mp4", ".flv", ".m4s", ".webm", ".mpd")

# Image suffixes to explicitly reject (some sites load posters/thumbs via XHR with /video/ paths)
_IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".ico", ".bmp")

# Non-media suffixes to reject — JSON API responses that happen to match path keywords
_NON_MEDIA_SUFFIXES = (".json", ".xml", ".js", ".css", ".php", ".aspx", ".jsp", ".html", ".htm")

# Path keywords that indicate media content (kept conservative to avoid false positives)
_MEDIA_PATH_KEYWORDS = (
    "/manifest/", "/aweme/v1/", "/vod/", "/video/", "/api/v1/play",
)

# Suffix → format_hint mapping
_SUFFIX_FORMAT = {
    ".m3u8": "m3u8",
    ".mp4": "mp4",
    ".flv": "flv",
    ".m4s": "m4s",
    ".webm": "webm",
    ".mpd": "dash",
    ".png": "img",
    ".jpg": "img",
    ".jpeg": "img",
    ".gif": "img",
    ".webp": "img",
    ".svg": "img",
    ".ico": "img",
    ".bmp": "img",
    ".js": "js",
    ".css": "css",
    ".woff2": "font",
    ".woff": "font",
    ".ttf": "font",
}

# Segment-based suffixes: dedup by directory, not individual segments
_SEGMENT_SUFFIXES = (".ts", ".m4s")


def _classify_url(url: str, conf=None) -> str | None:
    """Return format_hint if URL looks like media, else None."""
    parsed = urlparse(url)
    path_lower = parsed.path.lower()

    # 1. Image Check
    for suffix in _IMAGE_SUFFIXES:
        if path_lower.endswith(suffix):
            if conf and conf.sniff_images:
                return _SUFFIX_FORMAT.get(suffix, "img")
            return None

    # 2. Scripts & Styles Check
    if path_lower.endswith(".js") or path_lower.endswith(".css"):
        if conf and conf.sniff_scripts:
            return _SUFFIX_FORMAT.get(".js" if path_lower.endswith(".js") else ".css")
        return None

    # 3. Fonts Check
    for suffix in (".woff2", ".woff", ".ttf"):
        if path_lower.endswith(suffix):
            if conf and conf.sniff_fonts:
                return "font"
            return None

    # 4. Standard Non-Media rejection (others)
    others = (".json", ".xml", ".php", ".aspx", ".jsp", ".html", ".htm")
    for suffix in others:
        if path_lower.endswith(suffix):
            return None

    # 5. Media Check
    for suffix in _MEDIA_SUFFIXES:
        if path_lower.endswith(suffix):
            return _SUFFIX_FORMAT.get(suffix, "media")

    # .ts segments: only match if path looks like HLS (inside a stream directory)
    for seg_suffix in _SEGMENT_SUFFIXES:
        if path_lower.endswith(seg_suffix):
            dir_name = parsed.path.rsplit("/", 1)[0].rsplit("/", 1)[-1]
            # HLS segments typically live in directories named like "stream", "seg", "chunk"
            if dir_name in ("stream", "seg", "segment", "chunks", "video"):
                if seg_suffix == ".ts":
                    return "ts"
                return _SUFFIX_FORMAT.get(seg_suffix, "media")

    for kw in _MEDIA_PATH_KEYWORDS:
        if kw in path_lower:
            return "media"

    return None


def _dedup_key(url: str) -> str:
    """Normalize URL for dedup to prevent duplicates with dynamic tokens."""
    parsed = urlparse(url)
    path_lower = parsed.path.lower()

    # 1. Handle segment-based formats (.ts, .m4s) by directory
    for seg_suffix in _SEGMENT_SUFFIXES:
        if path_lower.endswith(seg_suffix):
            dir_path = parsed.path.rsplit("/", 1)[0]
            return f"{parsed.scheme}://{parsed.netloc}{dir_path}/*{seg_suffix}"

    # 2. Extract unique video ID from query params if available (Douyin, etc.)
    params = {}
    if parsed.query:
        for pair in parsed.query.split("&"):
            if "=" in pair:
                k, v = pair.split("=", 1)
                params[k] = v
    
    uid = params.get("video_id") or params.get("vid") or params.get("id")
    if uid:
        return f"UID:{uid}"

    # 3. For media-keyword paths, check if path itself contains ID
    if any(kw in path_lower for kw in _MEDIA_PATH_KEYWORDS):
        # Try to find a long hex/alphanumeric string in path as ID
        # (Very common in VOD service URLs)
        import re
        m = re.search(r'/[0-9a-f]{20,}/', path_lower)
        if m: return m.group(0)
        return url

    # 4. Standard: Strip ALL query strings for suffix-matched formats
    # Most .mp4/.m3u8 duplicates differ only by auth tokens in query
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"


class NetworkSniffer(QWebEngineUrlRequestInterceptor):
    video_found = pyqtSignal(object)  # SniffedVideo

    def __init__(self, parent=None):
        super().__init__(parent)
        self._seen: set[str] = set()
        from core.config import Config
        self._config = Config()

    def interceptRequest(self, info):
        # This runs on the Chromium IO thread; any uncaught exception aborts
        # the whole process. Wrap everything in try/except as a safety net.
        try:
            self._intercept_request(info)
        except Exception:
            pass

    def _intercept_request(self, info):
        # Skip common non-media resource types, unless explicitly allowed in config
        rt = info.resourceType()
        
        should_skip = False
        if rt in (
            QWebEngineUrlRequestInfo.ResourceType.ResourceTypeMainFrame,
            QWebEngineUrlRequestInfo.ResourceType.ResourceTypeSubFrame,
            QWebEngineUrlRequestInfo.ResourceType.ResourceTypeFavicon,
            QWebEngineUrlRequestInfo.ResourceType.ResourceTypePing,
            QWebEngineUrlRequestInfo.ResourceType.ResourceTypeCspReport,
        ):
            should_skip = True
        elif rt == QWebEngineUrlRequestInfo.ResourceType.ResourceTypeImage and not self._config.sniff_images:
            should_skip = True
        elif rt in (QWebEngineUrlRequestInfo.ResourceType.ResourceTypeScript, QWebEngineUrlRequestInfo.ResourceType.ResourceTypeStylesheet) and not self._config.sniff_scripts:
            should_skip = True
        elif rt == QWebEngineUrlRequestInfo.ResourceType.ResourceTypeFontResource and not self._config.sniff_fonts:
            should_skip = True
            
        if should_skip:
            return

        url = info.requestUrl().toString()
        fmt = _classify_url(url, self._config)

        if fmt is None:
            return

        key = _dedup_key(url)
        if key in self._seen:
            return
        self._seen.add(key)

        page_url = info.firstPartyUrl().toString()
        referer = ""
        headers = info.httpHeaders()
        for raw_header, raw_value in headers.items():
            header_str = bytes(raw_header).decode("ascii", errors="replace").lower()
            if header_str == "referer":
                referer = bytes(raw_value).decode("utf-8", errors="replace")
                break

        video = SniffedVideo(
            url=url,
            page_url=page_url,
            referer=referer,
            format_hint=fmt,
        )
        self.video_found.emit(video)

    def clear(self):
        self._seen.clear()
