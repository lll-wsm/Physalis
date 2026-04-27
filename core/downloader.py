import os
import re
import json
import shutil
from collections import deque
from pathlib import Path

from PyQt6.QtCore import QObject, QProcess, pyqtSignal, QUrl
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkRequest

from core.config import Config, _config_dir
from core.task import DownloadTask, TaskStatus


class VideoInfo:
    def __init__(self, url="", title="", duration="", vid="", playlist_index="", thumbnail=""):
        self.url = url
        self.title = title
        self.duration = duration
        self.vid = vid
        self.playlist_index = playlist_index
        self.thumbnail = thumbnail


def _find_ytdlp() -> str:
    path = shutil.which("yt-dlp")
    if path:
        return path
    local = Path(__file__).parent.parent / "bin" / "yt-dlp"
    if local.exists():
        return str(local)
    return "yt-dlp"


class Downloader(QObject):
    task_progress = pyqtSignal(DownloadTask)
    task_completed = pyqtSignal(DownloadTask)
    task_failed = pyqtSignal(DownloadTask)
    task_cancelled = pyqtSignal(DownloadTask)
    task_paused = pyqtSignal(DownloadTask)
    task_resumed = pyqtSignal(DownloadTask)
    probe_finished = pyqtSignal(list)   # list[VideoInfo]
    probe_failed = pyqtSignal(str)      # error message

    _PROGRESS_RE = re.compile(
        r"(\d+(?:\.\d+)?)%"
    )
    _SIZE_RE = re.compile(r"of\s+~?\s*([\d.]+\w+)")
    _SPEED_RE = re.compile(r"at\s+([\d.]+\w+/s)")
    _ETA_RE = re.compile(r"ETA\s+(\d+:\d+)")
    _ERROR_RE = re.compile(r"ERROR:\s*(.+)")
    
    # ffmpeg progress
    _FFMPEG_PROGRESS_RE = re.compile(
        r"size=\s*([\d.]+\w+)\s+time=\S+\s+bitrate=[\s\d.]+\w+/s\s+speed=\s*([\d.]+)x"
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
        self._probe_output = ""
        self._probe_stderr = ""

    def get_task(self, task_id: str) -> DownloadTask | None:
        return self._tasks.get(task_id)

    @property
    def tasks(self) -> list[DownloadTask]:
        return list(self._tasks.values())

    def probe_url(self, url: str):
        self._probe_output = ""
        self._probe_stderr = ""
        args = [
            "--no-warnings", "--no-check-certificates", "--flat-playlist",
            "--print", "%(id)s\t%(title)s\t%(duration)s\t%(url)s\t%(playlist_index)s\t%(thumbnail)s\t%(thumbnails.-1.url|)",
            url,
        ]
        process = QProcess(self)
        process.readyReadStandardOutput.connect(lambda: self._on_probe_stdout(process))
        process.readyReadStandardError.connect(lambda: self._on_probe_stderr(process))
        process.finished.connect(lambda code: self._on_probe_finished(process, code))
        process.start(self._ytdlp, args)

    def add_task(self, task: DownloadTask):
        self._tasks[task.id] = task
        if len(self._active) < self._config.max_concurrent:
            self._start(task)
        else:
            self._queue.append(task)

    def remove_task(self, task_id: str):
        self.cancel_task(task_id)
        if task_id in self._tasks:
            self._tasks.pop(task_id)
            self.save_history()

    def clear_finished(self):
        to_remove = [tid for tid, t in self._tasks.items() if t.is_finished]
        for tid in to_remove:
            self._tasks.pop(tid)
        self.save_history()

    def cancel_task(self, task_id: str):
        if task_id in self._active:
            process, task = self._active[task_id]
            task.mark_cancelled()
            self.task_cancelled.emit(task)
            self._kill_process(process)
        for t in list(self._queue):
            if t.id == task_id:
                t.mark_cancelled()
                self._queue.remove(t)
                self.task_cancelled.emit(t)
                break
        self.save_history()

    def pause_task(self, task_id: str):
        if task_id in self._active:
            process, task = self._active[task_id]
            task.mark_paused()
            self._kill_process(process)
            self.task_paused.emit(task)
        elif any(t.id == task_id for t in self._queue):
            for t in list(self._queue):
                if t.id == task_id:
                    t.mark_paused(); self._queue.remove(t)
                    self.task_paused.emit(t); break
        self.save_history()

    def resume_task(self, task_id: str):
        task = self._tasks.get(task_id)
        if task and task.status == TaskStatus.PAUSED:
            task.status = TaskStatus.PENDING
            self.add_task(task)
            self.task_resumed.emit(task)

    def _kill_process(self, process: QProcess):
        pid = process.processId()
        if pid and pid > 0:
            try:
                children = os.popen(f"pgrep -P {pid}").read().strip().split()
                for cpid in children:
                    if cpid: os.kill(int(cpid), 9)
                os.kill(pid, 9)
            except Exception: pass
        process.kill()

    def _start(self, task: DownloadTask):
        task.mark_downloading()
        self.task_progress.emit(task)
        process = QProcess(self)
        process.setProcessChannelMode(QProcess.ProcessChannelMode.SeparateChannels)
        process.readyReadStandardOutput.connect(lambda: self._on_stdout(task.id, process))
        process.readyReadStandardError.connect(lambda: self._on_stderr(task.id, process))
        process.finished.connect(lambda code: self._on_finished(task.id, code))
        process.start(self._ytdlp, self._build_args(task))
        self._active[task.id] = (process, task)

    def _build_args(self, task: DownloadTask) -> list[str]:
        args = ["--newline", "--no-warnings", "--no-check-certificates"]
        if task.referer: args.extend(["--referer", task.referer])
        if task.cookies_file: args.extend(["--cookies", task.cookies_file])
        # Add output template
        out_tpl = str(Path(self._config.download_dir) / "%(title)s.%(ext)s")
        args.extend(["-o", out_tpl])
        args.append(task.url)
        return args

    def _on_stdout(self, task_id: str, process: QProcess):
        if task_id not in self._active: return
        task = self._active[task_id][1]
        line = process.readAllStandardOutput().data().decode("utf-8", errors="replace").strip()
        if not line: return
        
        m_prog = self._PROGRESS_RE.search(line)
        if m_prog:
            prog = float(m_prog.group(1))
            m_size = self._SIZE_RE.search(line)
            m_speed = self._SPEED_RE.search(line)
            m_eta = self._ETA_RE.search(line)
            task.update_progress(
                prog,
                speed=m_speed.group(1) if m_speed else "",
                eta=m_eta.group(1) if m_eta else "",
                size_total=m_size.group(1) if m_size else ""
            )
            self.task_progress.emit(task)

    def _on_stderr(self, task_id: str, process: QProcess):
        data = process.readAllStandardError().data().decode("utf-8", errors="replace")
        self._stderr_buf[task_id] = self._stderr_buf.get(task_id, "") + data

    def _on_finished(self, task_id: str, exit_code: int):
        entry = self._active.pop(task_id, None)
        if not entry: return
        process, task = entry
        if task.status in (TaskStatus.PAUSED, TaskStatus.CANCELLED):
            self._start_next(); return

        stderr = self._stderr_buf.pop(task_id, "")
        if exit_code == 0:
            task.mark_completed()
            self.task_completed.emit(task)
        else:
            msg = stderr.strip() or f"Exit {exit_code}"
            task.mark_failed(msg)
            self.task_failed.emit(task)
        self.save_history()
        self._start_next()

    def _start_next(self):
        while self._queue and len(self._active) < self._config.max_concurrent:
            self._start(self._queue.popleft())

    def save_history(self):
        finished = []
        for t in self._tasks.values():
            if t.is_finished or t.status == TaskStatus.PAUSED:
                finished.append({
                    "id": t.id, "url": t.url, "title": t.title, "status": t.status.value,
                    "progress": t.progress, "size_total": t.size_total, "thumbnail_local": t.thumbnail_local,
                    "referer": t.referer, "format_hint": t.format_hint
                })
        self._history_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._history_path, "w", encoding="utf-8") as f:
            json.dump(finished, f, indent=2, ensure_ascii=False)

    def load_history(self) -> list[DownloadTask]:
        if not self._history_path.exists(): return []
        try:
            with open(self._history_path, "r", encoding="utf-8") as f: data = json.load(f)
            tasks = []
            for item in data:
                t = DownloadTask(
                    id=item.get("id"), url=item.get("url"), title=item.get("title"),
                    status=TaskStatus(item.get("status", "failed")), progress=item.get("progress", 0.0),
                    size_total=item.get("size_total", ""), referer=item.get("referer", ""),
                    thumbnail_local=item.get("thumbnail_local", ""), format_hint=item.get("format_hint", "")
                )
                tasks.append(t); self._tasks[t.id] = t
            return tasks
        except Exception: return []

    def _on_probe_stdout(self, p): self._probe_output += p.readAllStandardOutput().data().decode("utf-8", errors="replace")
    def _on_probe_stderr(self, p): self._probe_stderr += p.readAllStandardError().data().decode("utf-8", errors="replace")
    def _on_probe_finished(self, p, code):
        if code != 0: self.probe_failed.emit(self._probe_stderr or "Error"); return
        videos = []
        for line in self._probe_output.strip().split("\n"):
            parts = line.split("\t")
            if len(parts) >= 4:
                videos.append(VideoInfo(vid=parts[0], title=parts[1], duration=parts[2], url=parts[3], thumbnail=parts[5] if len(parts)>5 else ""))
        self.probe_finished.emit(videos)
