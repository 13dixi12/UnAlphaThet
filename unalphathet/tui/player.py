"""Preview playback behind a small Protocol so the TUI (and a future GTK app) never talk to mpv
directly."""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import tempfile
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol


class PlayerError(RuntimeError):
    pass


class Player(Protocol):
    @property
    def current(self) -> Path | None: ...
    @property
    def paused(self) -> bool: ...
    def load(self, path: Path, start_fraction: float = 0.0) -> None: ...
    def toggle(self) -> None: ...
    def seek(self, seconds: float) -> None: ...
    def seek_to(self, fraction: float) -> None: ...
    def position(self) -> tuple[float, float]: ...
    def stop(self) -> None: ...
    def close(self) -> None: ...


class NullPlayer:
    """Does nothing, remembers everything. For tests and `--no-audio`."""

    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self._current: Path | None = None
        self._paused = False

    @property
    def current(self) -> Path | None:
        return self._current

    @property
    def paused(self) -> bool:
        return self._paused

    def load(self, path: Path, start_fraction: float = 0.0) -> None:
        self.calls.append(("load", path, start_fraction))
        self._current, self._paused = path, False

    def toggle(self) -> None:
        self.calls.append(("toggle",))
        self._paused = not self._paused

    def seek(self, seconds: float) -> None:
        self.calls.append(("seek", seconds))

    def seek_to(self, fraction: float) -> None:
        self.calls.append(("seek_to", fraction))

    def position(self) -> tuple[float, float]:
        return (0.0, 0.0)

    def stop(self) -> None:
        self.calls.append(("stop",))
        self._current = None

    def close(self) -> None:
        self.stop()


class MpvPlayer:
    """mpv in idle mode, driven over its JSON IPC socket (mpv >= 0.38 loadfile signature)."""

    def __init__(self, extra_args: Sequence[str] = ()) -> None:
        exe = shutil.which("mpv")
        if not exe:
            raise PlayerError("mpv not found in PATH")
        self._dir = tempfile.mkdtemp(prefix="uat-mpv-")
        self._sock_path = os.path.join(self._dir, "mpv.sock")
        self._proc = subprocess.Popen(
            [
                exe,
                "--idle=yes",
                "--no-video",
                "--no-terminal",
                "--really-quiet",
                f"--input-ipc-server={self._sock_path}",
                *extra_args,
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        deadline = time.time() + 5
        while True:
            try:
                self._sock.connect(self._sock_path)
                break
            except (FileNotFoundError, ConnectionRefusedError):
                if time.time() > deadline or self._proc.poll() is not None:
                    raise PlayerError("mpv did not open its IPC socket") from None
                time.sleep(0.02)
        self._sock.settimeout(2.0)
        self._buf = b""
        self._req = 0
        self._current: Path | None = None

    # --- IPC plumbing ---------------------------------------------------------------
    def _send(self, *command) -> dict:
        self._req += 1
        rid = self._req
        msg = json.dumps({"command": list(command), "request_id": rid}).encode() + b"\n"
        self._sock.sendall(msg)
        while True:
            while b"\n" not in self._buf:
                chunk = self._sock.recv(65536)
                if not chunk:
                    raise PlayerError("mpv closed the IPC socket")
                self._buf += chunk
            line, self._buf = self._buf.split(b"\n", 1)
            if not line.strip():
                continue
            reply = json.loads(line)
            if reply.get("request_id") == rid:
                if reply.get("error") not in (None, "success"):
                    raise PlayerError(f"mpv: {reply['error']} for {command}")
                return reply
            # else: an event or an older reply; drop it

    def _get(self, prop: str, default=None):
        try:
            return self._send("get_property", prop).get("data", default)
        except PlayerError:
            return default

    # --- Player ---------------------------------------------------------------------
    @property
    def current(self) -> Path | None:
        return self._current

    @property
    def paused(self) -> bool:
        return bool(self._get("pause", False))

    def load(self, path: Path, start_fraction: float = 0.0) -> None:
        start = f"start={max(0.0, min(start_fraction, 0.99)) * 100:.1f}%"
        self._send("loadfile", str(path), "replace", -1, start)
        self._send("set_property", "pause", False)
        self._current = path

    def toggle(self) -> None:
        self._send("cycle", "pause")

    def seek(self, seconds: float) -> None:
        self._send("seek", seconds, "relative")

    def seek_to(self, fraction: float) -> None:
        self._send("seek", max(0.0, min(fraction, 1.0)) * 100, "absolute-percent")

    def position(self) -> tuple[float, float]:
        pos = self._get("time-pos", 0.0) or 0.0
        dur = self._get("duration", 0.0) or 0.0
        return float(pos), float(dur)

    def stop(self) -> None:
        try:
            self._send("stop")
        except PlayerError:
            pass
        self._current = None

    def close(self) -> None:
        try:
            self._send("quit")
        except (PlayerError, OSError):
            pass
        try:
            self._sock.close()
        finally:
            if self._proc.poll() is None:
                self._proc.terminate()
                try:
                    self._proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self._proc.kill()
            shutil.rmtree(self._dir, ignore_errors=True)
