"""PDF section 5.3 — one Word COM conversion at a time."""

import subprocess
import time
from contextlib import contextmanager

import msvcrt

from settings import SCRATCH

LOCK = SCRATCH / ".word.lock"
_warned = False


def close_word():
    # A stuck WINWORD.EXE blocks the next PDF save. This closes Word.
    global _warned
    if not _warned:
        print("Closing Microsoft Word if it is open, so the resume can be saved as PDF.")
        _warned = True
    subprocess.run(
        ["taskkill", "/f", "/im", "winword.exe"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )


@contextmanager
def word_lock():
    SCRATCH.mkdir(parents=True, exist_ok=True)
    handle = open(LOCK, "a+b")
    locked = False
    try:
        if handle.seek(0, 2) == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        started = time.time()
        while True:
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                locked = True
                break
            except OSError:
                if time.time() - started > 120:
                    raise TimeoutError("Timed out waiting for the Word lock")
                time.sleep(0.5)
        yield
    finally:
        if locked:
            handle.seek(0)
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            except OSError:
                pass
        handle.close()
