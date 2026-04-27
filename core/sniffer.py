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
    timestamp: float = field(default_factory=time.time)


# URL suffixes that indicate media content (.ts excluded — too many false positives with JS bundles)
_MEDIA_SUFFIXES = (".m3u8", ".mp4", ".flv", ".m4s", ".webm", ".mpd")

# Image suffixes to explicitly reject (some sites load posters/thumbs via XHR with /video/ paths)
_IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".ico", ".bmp")

# Non-media suffixes to reject — JSON API responses that happen to match path keywords
_NON_MEDIA_SUFFIXES = (".json", ".xml")

# Path keywords that indicate media content (kept conservative to avoid false positives)
_MEDIA_PATH_KEYWORDS = (
    "/manifest/", "/aweme/v1/", "/vod/",
)

# Suffix → format_hint mapping
_SUFFIX_FORMAT = {
    ".m3u8": "m3u8",
    ".mp4": "mp4",
    ".flv": "flv",
    ".m4s": "m4s",
    ".webm": "webm",
    ".mpd": "dash",
}

# Segment-based suffixes: dedup by directory, not individual segments
_SEGMENT_SUFFIXES = (".ts", ".m4s")


def _classify_url(url: str) -> str | None:
    """Return format_hint if URL looks like media, else None."""
    parsed = urlparse(url)
    path_lower = parsed.path.lower()

    for suffix in _IMAGE_SUFFIXES:
        if path_lower.endswith(suffix):
            return None

    for suffix in _NON_MEDIA_SUFFIXES:
        if path_lower.endswith(suffix):
            return None

    for suffix in _MEDIA_SUFFIXES:
        if path_lower.endswith(suffix):
            return _SUFFIX_FORMAT[suffix]

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
    """Normalize URL for dedup.

    For segment-based formats (.ts, .m4s), collapse all segments in the same
    directory to one key.
    For media-keyword matched paths (e.g. /aweme/v1/), include query params
    so different videos with IDs in query strings are not collapsed together.
    For other suffix-matched formats, strip query parameters.
    """
    parsed = urlparse(url)
    path_lower = parsed.path.lower()

    for seg_suffix in _SEGMENT_SUFFIXES:
        if path_lower.endswith(seg_suffix):
            dir_path = parsed.path.rsplit("/", 1)[0]
            return f"{parsed.scheme}://{parsed.netloc}{dir_path}/*{seg_suffix}"

    # For media-keyword paths (typically no extension, video ID in query),
    # use the full URL so different video_ids get distinct entries.
    if any(kw in path_lower for kw in _MEDIA_PATH_KEYWORDS):
        return url

    # Strip query string for suffix-matched formats
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, "", ""))


class NetworkSniffer(QWebEngineUrlRequestInterceptor):
    video_found = pyqtSignal(object)  # SniffedVideo

    def __init__(self, parent=None):
        super().__init__(parent)
        self._seen: set[str] = set()

    def interceptRequest(self, info):
        # This runs on the Chromium IO thread; any uncaught exception aborts
        # the whole process. Wrap everything in try/except as a safety net.
        try:
            self._intercept_request(info)
        except Exception:
            pass

    def _intercept_request(self, info):
        # Skip page document loads (main/sub frames). Otherwise the page URL
        # itself can match heuristics like "/video/" and get reported as media.
        rt = info.resourceType()
        if rt in (
            QWebEngineUrlRequestInfo.ResourceType.ResourceTypeMainFrame,
            QWebEngineUrlRequestInfo.ResourceType.ResourceTypeSubFrame,
            QWebEngineUrlRequestInfo.ResourceType.ResourceTypeStylesheet,
            QWebEngineUrlRequestInfo.ResourceType.ResourceTypeScript,
            QWebEngineUrlRequestInfo.ResourceType.ResourceTypeImage,
            QWebEngineUrlRequestInfo.ResourceType.ResourceTypeFontResource,
        ):
            return

        url = info.requestUrl().toString()
        fmt = _classify_url(url)

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
