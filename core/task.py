import enum
import time
import uuid
from dataclasses import dataclass, field


class TaskStatus(enum.Enum):
    PENDING = "pending"
    DOWNLOADING = "downloading"
    MERGING = "merging"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class DownloadTask:
    url: str
    title: str = ""
    status: TaskStatus = TaskStatus.PENDING
    progress: float = 0.0
    speed: str = ""
    eta: str = ""
    size_total: str = ""
    size_downloaded: str = ""
    error: str = ""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    created_at: float = field(default_factory=time.time)
    completed_at: float = 0.0
    output_path: str = ""
    cookies_file: str = ""
    referer: str = ""
    thumbnail: str = ""
    format_hint: str = ""   # "m3u8" / "mp4" / "webm" / "flv" / "dash" / etc.

    @property
    def is_active(self) -> bool:
        return self.status in (TaskStatus.DOWNLOADING, TaskStatus.MERGING)

    @property
    def is_finished(self) -> bool:
        return self.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED)

    def mark_downloading(self):
        self.status = TaskStatus.DOWNLOADING
        self.progress = 0.0

    def update_progress(self, progress: float, speed: str = "", eta: str = "",
                        size_total: str = "", size_downloaded: str = ""):
        self.progress = progress
        if speed:
            self.speed = speed
        if eta:
            self.eta = eta
        if size_total:
            self.size_total = size_total
        if size_downloaded:
            self.size_downloaded = size_downloaded

    def mark_merging(self):
        self.status = TaskStatus.MERGING

    def mark_completed(self, output_path: str = ""):
        self.status = TaskStatus.COMPLETED
        self.progress = 100.0
        self.completed_at = time.time()
        if output_path:
            self.output_path = output_path

    def mark_failed(self, error: str = ""):
        self.status = TaskStatus.FAILED
        self.error = error

    def mark_cancelled(self):
        self.status = TaskStatus.CANCELLED
