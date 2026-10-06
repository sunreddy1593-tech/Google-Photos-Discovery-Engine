"""Serialize scheduled/catch-up research and publication across all three tasks."""
from __future__ import annotations

from contextlib import contextmanager
import ctypes
from ctypes import wintypes
from pathlib import Path
import subprocess
import sys
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
MUTEX_NAME = "Local\\GooglePhotosDiscovery-ScheduledPipeline"


@contextmanager
def scheduled_queue(name: str = MUTEX_NAME):
    """Windows releases the mutex even if its owning process is terminated."""
    if sys.platform != "win32":
        raise RuntimeError("Scheduled discovery queue requires Windows")
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
    api.CreateMutexW.restype = wintypes.HANDLE
    api.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    api.WaitForSingleObject.restype = wintypes.DWORD
    api.ReleaseMutex.argtypes = [wintypes.HANDLE]
    api.ReleaseMutex.restype = wintypes.BOOL
    api.CloseHandle.argtypes = [wintypes.HANDLE]
    api.CloseHandle.restype = wintypes.BOOL
    handle = api.CreateMutexW(None, False, name)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    owned = False
    try:
        # WAIT_OBJECT_0 or WAIT_ABANDONED both confer ownership.
        result = api.WaitForSingleObject(handle, 0xFFFFFFFF)
        if result not in (0, 0x80):
            raise ctypes.WinError(ctypes.get_last_error())
        owned = True
        yield
    finally:
        if owned:
            api.ReleaseMutex(handle)
        api.CloseHandle(handle)


def run_queued(project: Path, *, queue: Callable = scheduled_queue,
               run: Callable = subprocess.run) -> int:
    python = project / ".venv/Scripts/python.exe"
    with queue():
        research = run([str(python), str(project / "main.py"), "schedule"], cwd=project)
        if research.returncode:
            return research.returncode
        # Publication writes its own durable status; failure does not repeat
        # collection or change the completed research run's exit code.
        try:
            result = run([str(python), str(project / "scripts/publish_cloud_snapshots.py")], cwd=project)
            if result.returncode:
                print("Cloud publication failed; saved results are retained for a later publication attempt.")
        except OSError as exc:
            print("Cloud publication could not start: " + type(exc).__name__)
        return research.returncode


if __name__ == "__main__":
    raise SystemExit(run_queued(ROOT))
