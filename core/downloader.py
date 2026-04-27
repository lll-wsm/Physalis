import json
import os
import re
import shutil
from collections import deque
from pathlib import Path

from PyQt6.QtCore import QObject, QProcess, QProcessEnvironment, pyqtSignal

from core.config import Config, _config_dir
from core.task import DownloadTask, TaskStatus


def _find_ytdlp() -> str:
    path = shutil.which("yt-dlp")
    if path:
        return path
    bundled = Path(__file__).parent.parent / "bin" / "yt-dlp"
    if bundled.exists():
        return str(bundled)
    return "yt-dlp"


class VideoInfo:
    __slots__ = ("url", "title", "duration", "id", "playlist_index", "thumbnail")

    def __init__(self, url="", title="", duration="", vid="", playlist_index="", thumbnail=""):
        self.url = url
        self.title = title
        self.duration = duration
        self.id = vid
        self.playlist_index = playlist_index
        self.thumbnail = thumbnail


class Downloader(QObject):
    task_progress = pyqtSignal(DownloadTask)
    task_completed = pyqtSignal(DownloadTask)
    task_failed = pyqtSignal(DownloadTask)
    task_cancelled = pyqtSignal(DownloadTask)
    probe_finished = pyqtSignal(list)   # list[VideoInfo]
    probe_failed = pyqtSignal(str)      # error message

    _PROGRESS_RE = re.compile(
        r"(\d+(?:\.\d+)?)%"
        r"(?:\s+of\s+~?\s*([\d.]+\w+))?"
        r"(?:\s+at\s+([\d.]+\w+/s))?"
        r"(?:\s+ETA\s+(\S+))?"
    )
    _MERGING_RE = re.compile(r"\[Merger\]|\[ffmpeg\] Merging")
    _DESTINATION_RE = re.compile(r"\[download\] Destination: (.+)")
    _ERROR_RE = re.compile(r"ERROR:\s+(.+)")
    _TITLE_RE = re.compile(r"\[download\] (.+) has already been downloaded")
    # For live/unknown-size downloads yt-dlp may omit the percentage:
    #   [download] 10.50MiB at  1.50MiB/s ETA 00:05
    _SIZE_SPEED_RE = re.compile(
        r"([\d.]+\w+)\s+at\s+([\d.]+\w+/s)"
        r"(?:\s+ETA\s+(\S+))?"
    )
    # ffmpeg progress (used by yt-dlp for m3u8/hls via external downloader)
    #   frame=  130 fps=129 q=-1.0 size=     512KiB time=00:00:04.29 bitrate= 977.3kbits/s speed=4.25x elapsed=0:00:01.00
    _FFMPEG_PROGRESS_RE = re.compile(
        r"frame=\s*\d+\s+"
        r"fps=\s*[\d.]+\s+"
        r"q=[\d.-]+\s+"
        r"size=\s*([\d.]+\w+)\s+"
        r"time=\S+\s+"
        r"bitrate=[\s\d.]+\w+/s\s+"
        r"speed=\s*([\d.]+)x"
    )

    def __init__(self, parent=None):
        super().__init__(parent)
        self._config = Config()
        self._ytdlp = _find_ytdlp()
        self._active: dict[str, tuple[QProcess, DownloadTask]] = {}
        self._queue: deque[DownloadTask] = deque()
        self._stderr_buf: dict[str, str] = {}
        self._tasks: dict[str, DownloadTask] = {}
        self._history_path = _config_dir() / "tasks_history.json"

    def get_task(self, task_id: str) -> DownloadTask | None:
        return self._tasks.get(task_id)

    @property
    def tasks(self) -> list[DownloadTask]:
        """Return a list of all current tasks."""
        return list(self._tasks.values())

    def probe_url(self, url: str):
        """解析URL中的所有视频，不下载，只返回列表"""
        args = [
            "--no-warnings",
            "--no-check-certificates",
            "--flat-playlist",
            "--print", "%(id)s\t%(title)s\t%(duration)s\t%(url)s\t%(playlist_index)s\t%(thumbnail)s\t%(thumbnails.-1.url|)s",
            url,
        ]
        process = QProcess(self)
        process.setProcessChannelMode(QProcess.ProcessChannelMode.SeparateChannels)
        process.readyReadStandardOutput.connect(
            lambda: self._on_probe_stdout(process)
        )
        process.readyReadStandardError.connect(
            lambda: self._on_probe_stderr(process)
        )
        process.finished.connect(
            lambda code, status: self._on_probe_finished(process, code)
        )
        self._probe_output = ""
        self._probe_stderr = ""
        process.start(self._ytdlp, args)

    def add_task(self, task: DownloadTask):
        self._tasks[task.id] = task
        if len(self._active) < self._config.max_concurrent:
            self._start(task)
        else:
            self._queue.append(task)

    def remove_task(self, task_id: str):
        """Physically remove a task from internal storage and update history."""
        # Cancel first if it's active
        self.cancel_task(task_id)
        # Remove from main storage
        if task_id in self._tasks:
            self._tasks.pop(task_id)
            self.save_history()

    def clear_finished(self):
        """Remove all finished tasks (completed, failed, or cancelled) from history."""
        to_remove = [tid for tid, t in self._tasks.items() if t.is_finished]
        for tid in to_remove:
            self._tasks.pop(tid)
        self.save_history()

    def cancel_task(self, task_id: str):
        if task_id in self._active:
            process, task = self._active[task_id]
            task.mark_cancelled()
            self.task_cancelled.emit(task)
            # Kill yt-dlp and any child processes (e.g. ffmpeg)
            pid = process.processId()
            if pid and pid > 0:
                try:
                    # Kill child processes first (ffmpeg etc.)
                    children = os.popen(f"pgrep -P {pid}").read().strip().split()
                    for cpid in children:
                        if cpid:
                            os.kill(int(cpid), 9)
                except Exception:
                    pass
                try:
                    os.kill(pid, 9)
                except Exception:
                    pass
            process.kill()
        for t in list(self._queue):
            if t.id == task_id:
                t.mark_cancelled()
                self._queue.remove(t)
                self.task_cancelled.emit(t)
                break
        self.save_history()

    def _start(self, task: DownloadTask):
        task.mark_downloading()
        self.task_progress.emit(task)

        cmd_args = self._build_args(task)
        process = QProcess(self)
        process.setProcessChannelMode(QProcess.ProcessChannelMode.SeparateChannels)
        # Force Python (yt-dlp) to flush stdout/stderr line-by-line so we get
        # real-time progress updates instead of full-buffer lag.
        env = QProcessEnvironment.systemEnvironment()
        env.insert("PYTHONUNBUFFERED", "1")
        process.setProcessEnvironment(env)
        process.readyReadStandardOutput.connect(
            lambda: self._on_stdout(task.id, process)
        )
        process.readyReadStandardError.connect(
            lambda: self._on_stderr(task.id, process)
        )
        process.finished.connect(
            lambda code, status: self._on_finished(task.id, code)
        )

        self._active[task.id] = (process, task)
        self._stderr_buf[task.id] = ""
        process.start(self._ytdlp, cmd_args)

    def _build_args(self, task: DownloadTask) -> list[str]:
        # Use page-extracted title when available (sniffed downloads);
        # fall back to yt-dlp's %(title)s for direct URL downloads.
        if task.title:
            safe = re.sub(r'[\\/*?:"<>|]', "_", task.title).strip()
            if not safe:
                safe = "%(title)s"
            out = str(self._config.download_dir / f"{safe}.%(ext)s")
        else:
            out = str(self._config.download_dir / "%(title)s.%(ext)s")

        args = [
            "--no-warnings",
            "--newline",
            "--no-check-certificates",
            "-o", out,
        ]

        if task.cookies_file:
            args.extend(["--cookies", task.cookies_file])
        if task.referer:
            args.extend(["--referer", task.referer])

        quality = self._config.preferred_quality
        if quality == "best":
            args.extend(["-f", "bestvideo[height<=1080]+bestaudio/best"])
        elif quality != "original":
            args.extend(["-f", quality])

        args.append(task.url)
        return args

    def _on_stdout(self, task_id: str, process: QProcess):
        data = process.readAllStandardOutput().data().decode("utf-8", errors="replace")
        for line in data.split("\n"):
            line = line.strip()
            if not line:
                continue
            # DEBUG
            with open("/tmp/physalis_ytdlp.log", "a", encoding="utf-8") as f:
                f.write(f"[OUT] {line}\n")

            entry = self._active.get(task_id)
            if not entry:
                continue
            _, task = entry

            if task.status == TaskStatus.CANCELLED:
                continue

            m = self._PROGRESS_RE.search(line)
            if m:
                pct = float(m.group(1))
                size_total = m.group(2) or ""
                speed = m.group(3) or ""
                eta = m.group(4) or ""
                task.update_progress(pct, speed, eta, size_total)
                self.task_progress.emit(task)
                # DEBUG
                with open("/tmp/physalis_ytdlp.log", "a", encoding="utf-8") as f:
                    f.write(f"  -> PROGRESS pct={pct} size={size_total} speed={speed} eta={eta}\n")
                continue

            # Live / unknown-size streams: no percentage, just size + speed
            m = self._SIZE_SPEED_RE.search(line)
            if m:
                size_downloaded = m.group(1)
                speed = m.group(2) or ""
                eta = m.group(3) or ""
                # Keep existing progress (likely 0) but update size/speed
                task.update_progress(task.progress, speed, eta, size_total=size_downloaded, size_downloaded=size_downloaded)
                self.task_progress.emit(task)
                with open("/tmp/physalis_ytdlp.log", "a", encoding="utf-8") as f:
                    f.write(f"  -> SIZE_SPEED dl={size_downloaded} speed={speed} eta={eta}\n")
                continue

            if self._MERGING_RE.search(line):
                task.mark_merging()
                self.task_progress.emit(task)
                continue

            m = self._DESTINATION_RE.match(line)
            if m and not task.title:
                task.title = Path(m.group(1).strip()).stem
                self.task_progress.emit(task)
                continue

            m = self._TITLE_RE.match(line)
            if m and not task.title:
                task.title = m.group(1).strip()

    def _on_stderr(self, task_id: str, process: QProcess):
        data = process.readAllStandardError().data().decode("utf-8", errors="replace")
        self._stderr_buf[task_id] += data

        entry = self._active.get(task_id)
        if not entry:
            return
        _, task = entry

        # Ignore stderr after cancellation
        if task.status == TaskStatus.CANCELLED:
            return

        for line in data.split("\n"):
            line = line.strip()
            if not line:
                continue
            # DEBUG
            with open("/tmp/physalis_ytdlp.log", "a", encoding="utf-8") as f:
                f.write(f"[ERR] {line}\n")

            # yt-dlp outputs download progress to stderr
            m = self._PROGRESS_RE.search(line)
            if m:
                pct = float(m.group(1))
                size_total = m.group(2) or ""
                speed = m.group(3) or ""
                eta = m.group(4) or ""
                task.update_progress(pct, speed, eta, size_total)
                self.task_progress.emit(task)
                with open("/tmp/physalis_ytdlp.log", "a", encoding="utf-8") as f:
                    f.write(f"  -> PROGRESS pct={pct} size={size_total} speed={speed} eta={eta}\n")
                continue

            m = self._SIZE_SPEED_RE.search(line)
            if m:
                size_downloaded = m.group(1)
                speed = m.group(2) or ""
                eta = m.group(3) or ""
                task.update_progress(task.progress, speed, eta, size_total=size_downloaded, size_downloaded=size_downloaded)
                self.task_progress.emit(task)
                with open("/tmp/physalis_ytdlp.log", "a", encoding="utf-8") as f:
                    f.write(f"  -> SIZE_SPEED dl={size_downloaded} speed={speed} eta={eta}\n")
                continue

            # ffmpeg external-downloader progress for HLS/m3u8
            m = self._FFMPEG_PROGRESS_RE.search(line)
            if m:
                size_downloaded = m.group(1)
                speed = f"{m.group(2)}x" if m.group(2) else ""
                task.update_progress(task.progress, speed, "", size_total=size_downloaded, size_downloaded=size_downloaded)
                self.task_progress.emit(task)
                with open("/tmp/physalis_ytdlp.log", "a", encoding="utf-8") as f:
                    f.write(f"  -> FFMPEG dl={size_downloaded} speed={speed}\n")
                continue

            if self._MERGING_RE.search(line):
                task.mark_merging()
                self.task_progress.emit(task)
                continue

            m = self._DESTINATION_RE.match(line)
            if m and not task.title:
                task.title = Path(m.group(1).strip()).stem
                self.task_progress.emit(task)
                continue

            m = self._TITLE_RE.match(line)
            if m and not task.title:
                task.title = m.group(1).strip()

            m = self._ERROR_RE.search(line)
            if m:
                task.mark_failed(m.group(1).strip())
                process.kill()
                self.task_failed.emit(task)
                return

    def _on_finished(self, task_id: str, exit_code: int):
        entry = self._active.pop(task_id, None)
        if not entry:
            return

        process, task = entry
        stderr = self._stderr_buf.pop(task_id, "")

        if task.status in (TaskStatus.CANCELLED, TaskStatus.FAILED):
            pass
        elif exit_code == 0:
            task.mark_completed()
            self.task_completed.emit(task)
        else:
            error_msg = stderr.strip() or f"yt-dlp exited with code {exit_code}"
            for line in stderr.split("\n"):
                m = self._ERROR_RE.search(line)
                if m:
                    error_msg = m.group(1).strip()
                    break
            task.mark_failed(error_msg)
            self.task_failed.emit(task)

        # Clean up temp cookie file
        if task.cookies_file:
            try:
                os.unlink(task.cookies_file)
            except OSError:
                pass

        self.save_history()
        self._start_next()

    def _start_next(self):
        while self._queue and len(self._active) < self._config.max_concurrent:
            task = self._queue.popleft()
            self._start(task)

    def save_history(self):
        """Persist finished tasks to JSON so they survive a restart."""
        finished = []
        for t in self._tasks.values():
            if not t.is_finished:
                continue
            finished.append({
                "id": t.id,
                "url": t.url,
                "title": t.title,
                "status": t.status.value,
                "progress": t.progress,
                "error": t.error,
                "size_total": t.size_total,
                "size_downloaded": t.size_downloaded,
                "speed": t.speed,
                "eta": t.eta,
                "thumbnail": t.thumbnail,
                "referer": t.referer,
                "format_hint": t.format_hint,
                "created_at": t.created_at,
                "completed_at": t.completed_at,
                "output_path": t.output_path,
            })
        # Keep at most the last 200 entries
        if len(finished) > 200:
            finished = finished[-200:]
        self._history_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._history_path, "w", encoding="utf-8") as f:
            json.dump(finished, f, indent=2, ensure_ascii=False)

    def load_history(self) -> list[DownloadTask]:
        """Restore finished task objects from ``tasks_history.json``."""
        if not self._history_path.exists():
            return []

        try:
            with open(self._history_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            return []

        tasks = []
        for item in data:
            try:
                task = DownloadTask(
                    id=item.get("id", ""),
                    url=item.get("url", ""),
                    title=item.get("title", ""),
                    status=TaskStatus(item.get("status", "failed")),
                    progress=item.get("progress", 0.0),
                    error=item.get("error", ""),
                    size_total=item.get("size_total", ""),
                    size_downloaded=item.get("size_downloaded", ""),
                    speed=item.get("speed", ""),
                    eta=item.get("eta", ""),
                    thumbnail=item.get("thumbnail", ""),
                    referer=item.get("referer", ""),
                    format_hint=item.get("format_hint", ""),
                    created_at=item.get("created_at", 0.0),
                    completed_at=item.get("completed_at", 0.0),
                    output_path=item.get("output_path", ""),
                )
                tasks.append(task)
            except Exception:
                continue
        return tasks

    # --- Probe ---

    def _on_probe_stdout(self, process: QProcess):
        data = process.readAllStandardOutput().data().decode("utf-8", errors="replace")
        self._probe_output += data

    def _on_probe_stderr(self, process: QProcess):
        data = process.readAllStandardError().data().decode("utf-8", errors="replace")
        self._probe_stderr += data

    def _on_probe_finished(self, process: QProcess, exit_code: int):
        if exit_code != 0:
            error = self._probe_stderr.strip() or f"yt-dlp exited with code {exit_code}"
            for line in self._probe_stderr.split("\n"):
                m = self._ERROR_RE.search(line)
                if m:
                    error = m.group(1).strip()
                    break
            self.probe_failed.emit(error)
            return

        videos = []
        for line in self._probe_output.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            parts = line.split("\t")
            if len(parts) < 4:
                continue
            thumb = parts[5] if len(parts) > 5 and parts[5] != "NA" else ""
            if not thumb and len(parts) > 6 and parts[6] not in ("NA", ""):
                thumb = parts[6]
            info = VideoInfo(
                vid=parts[0],
                title=parts[1],
                duration=parts[2] if parts[2] != "NA" else "",
                url=parts[3],
                playlist_index=parts[4] if len(parts) > 4 and parts[4] != "NA" else "",
                thumbnail=thumb,
            )
            videos.append(info)

        if not videos:
            self.probe_failed.emit("未找到视频")
            return

        self.probe_finished.emit(videos)
