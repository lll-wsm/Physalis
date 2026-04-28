import json
import os
import sys
from pathlib import Path


def _default_download_dir() -> Path:
    return Path.home() / "Downloads" / "Physalis"


def _config_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "Physalis"


class Config:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load()
        return cls._instance

    def _load(self):
        self._path = _config_dir() / "config.json"
        defaults = {
            "download_dir": str(_default_download_dir()),
            "max_concurrent": 3,
            "preferred_quality": "best",
            "language": "zh_CN",
            "sniff_filter_types": "application/json,text/html,text/javascript,text/css,application/x-protobuf",
            "filter_empty_type": False,
            "sniff_images": False,
            "sniff_scripts": False,
            "sniff_fonts": False,
        }
        if self._path.exists():
            with open(self._path, "r", encoding="utf-8") as f:
                saved = json.load(f)
            defaults.update(saved)
        self._data = defaults

    def _save(self):
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2, ensure_ascii=False)

    @property
    def download_dir(self) -> Path:
        return Path(self._data["download_dir"])

    @download_dir.setter
    def download_dir(self, value: Path):
        self._data["download_dir"] = str(value)
        self._save()

    @property
    def max_concurrent(self) -> int:
        return self._data["max_concurrent"]

    @max_concurrent.setter
    def max_concurrent(self, value: int):
        self._data["max_concurrent"] = max(1, min(value, 10))
        self._save()

    @property
    def preferred_quality(self) -> str:
        return self._data["preferred_quality"]

    @preferred_quality.setter
    def preferred_quality(self, value: str):
        self._data["preferred_quality"] = value
        self._save()

    @property
    def language(self) -> str:
        return self._data["language"]

    @language.setter
    def language(self, value: str):
        self._data["language"] = value
        self._save()

    @property
    def sniff_filter_types(self) -> str:
        return self._data.get("sniff_filter_types", "")

    @sniff_filter_types.setter
    def sniff_filter_types(self, value: str):
        self._data["sniff_filter_types"] = value
        self._save()

    @property
    def filter_empty_type(self) -> bool:
        return self._data.get("filter_empty_type", False)

    @filter_empty_type.setter
    def filter_empty_type(self, value: bool):
        self._data["filter_empty_type"] = value
        self._save()

    @property
    def sniff_images(self) -> bool:
        return self._data.get("sniff_images", False)

    @sniff_images.setter
    def sniff_images(self, value: bool):
        self._data["sniff_images"] = value
        self._save()

    @property
    def sniff_scripts(self) -> bool:
        return self._data.get("sniff_scripts", False)

    @sniff_scripts.setter
    def sniff_scripts(self, value: bool):
        self._data["sniff_scripts"] = value
        self._save()

    @property
    def sniff_fonts(self) -> bool:
        return self._data.get("sniff_fonts", False)

    @sniff_fonts.setter
    def sniff_fonts(self, value: bool):
        self._data["sniff_fonts"] = value
        self._save()
