"""Background subprocess execution and Tk-safe output streaming."""

from __future__ import annotations

import os
import queue
import signal
import subprocess
import threading
import tkinter as tk
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple


class ProcessRunner:
    """Run subprocesses on a background thread and stream output back to Tk."""

    def __init__(self) -> None:
        self.process: Optional[subprocess.Popen] = None
        self.reader_threads: List[threading.Thread] = []
        self.wait_thread: Optional[threading.Thread] = None
        self.widget: Optional[tk.Widget] = None
        self.queue: queue.Queue[Tuple[str, Any]] = queue.Queue()
        self.after_id: Optional[str] = None
        self.on_line: Optional[Callable[[str, str], None]] = None
        self.on_exit: Optional[Callable[[int], None]] = None
        self._lock = threading.Lock()
        self._stopping = False

    def run(
        self,
        widget: tk.Widget,
        cmd: List[str],
        cwd: Optional[Path] = None,
        env: Optional[Dict[str, str]] = None,
        on_line: Optional[Callable[[str, str], None]] = None,
        on_exit: Optional[Callable[[int], None]] = None,
    ) -> None:
        with self._lock:
            if self.process:
                raise RuntimeError("Process already running")
            self.widget = widget
            self.on_line = on_line
            self.on_exit = on_exit
            self.queue = queue.Queue()
            self.reader_threads = []
            self.wait_thread = None
            self._stopping = False
            popen_kwargs: Dict[str, Any] = {
                "stdout": subprocess.PIPE,
                "stderr": subprocess.PIPE,
                "stdin": subprocess.PIPE,
                "text": True,
                "bufsize": 1,
                "universal_newlines": True,
            }
            if cwd:
                popen_kwargs["cwd"] = str(cwd)
            if env:
                popen_kwargs["env"] = env
            if os.name == "nt":
                popen_kwargs["creationflags"] = getattr(
                    subprocess, "CREATE_NEW_PROCESS_GROUP", 0
                )
            else:
                popen_kwargs["preexec_fn"] = os.setsid  # type: ignore[attr-defined]
            self.process = subprocess.Popen(cmd, **popen_kwargs)
        if self.process.stdout:
            self._start_reader(self.process.stdout, "info")
        if self.process.stderr:
            self._start_reader(self.process.stderr, "error")
        self.wait_thread = threading.Thread(target=self._wait_for_process, daemon=True)
        self.wait_thread.start()
        self._schedule_drain()

    def stop(self) -> None:
        with self._lock:
            proc = self.process
        if not proc:
            return
        self._stopping = True
        try:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )
            else:
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                except ProcessLookupError:
                    pass
        except OSError:
            pass
        try:
            proc.terminate()
        except OSError:
            pass

    def cancel(self) -> None:
        """Cancel any pending Tk callbacks."""
        if self.after_id and self.widget:
            try:
                self.widget.after_cancel(self.after_id)
            except tk.TclError:
                pass
        self.after_id = None

    def is_running(self) -> bool:
        with self._lock:
            return self.process is not None

    def stop_requested(self) -> bool:
        return self._stopping

    def send_input(self, data: str) -> None:
        with self._lock:
            proc = self.process
            stdin = proc.stdin if proc else None  # type: ignore[assignment]
        if not proc or not stdin:
            raise RuntimeError("Process is not running")
        text = data if data.endswith("\n") else f"{data}\n"
        try:
            stdin.write(text)
            stdin.flush()
        except Exception as exc:  # pragma: no cover - interactive fallback
            raise RuntimeError(f"Failed to send input: {exc}") from exc

    def _start_reader(self, stream: Any, level: str) -> None:
        def _reader() -> None:
            for raw_line in iter(stream.readline, ""):
                line = raw_line.rstrip("\r\n")
                self.queue.put(("line", level, line))
            try:
                stream.close()
            except Exception:
                pass

        thread = threading.Thread(target=_reader, daemon=True)
        self.reader_threads.append(thread)
        thread.start()

    def _wait_for_process(self) -> None:
        proc: Optional[subprocess.Popen]
        with self._lock:
            proc = self.process
        if not proc:
            return
        return_code = proc.wait()
        for thread in self.reader_threads:
            thread.join()
        self.queue.put(("exit", return_code))

    def _schedule_drain(self) -> None:
        if not self.widget:
            return
        if self.after_id:
            return
        self.after_id = self.widget.after(100, self._drain_queue)

    def _drain_queue(self) -> None:
        self.after_id = None
        exit_code: Optional[int] = None
        while True:
            try:
                item = self.queue.get_nowait()
            except queue.Empty:
                break
            kind = item[0]
            if kind == "line":
                _, level, message = item
                if self.on_line:
                    self.on_line(level, message)
            elif kind == "exit":
                exit_code = item[1]
        if exit_code is not None:
            self._cleanup_process_handles()
            if self.on_exit:
                self.on_exit(exit_code)
        if (self.process is not None) or (not self.queue.empty()):
            self._schedule_drain()

    def _cleanup_process_handles(self) -> None:
        proc: Optional[subprocess.Popen]
        with self._lock:
            proc = self.process
            self.process = None
        if not proc:
            return
        for stream in (proc.stdout, proc.stderr, proc.stdin):
            if stream:
                try:
                    stream.close()
                except Exception:
                    pass

