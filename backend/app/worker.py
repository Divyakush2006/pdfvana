"""Process isolation for jobs.

Every job runs in its own child process (started from a pre-loaded fork server) with:

* a hard memory ceiling (``RLIMIT_DATA``) and maximum output file size (``RLIMIT_FSIZE``),
* no core dumps,
* its own process group, so on timeout the job *and every tool it started* are killed.

A malicious or malformed file can therefore crash, hang or exhaust only its own job — never the
API server or other users' jobs.
"""
from __future__ import annotations

import multiprocessing as mp
import os
import queue as queue_mod
import signal
import time
import traceback
from dataclasses import dataclass
from pathlib import Path

from .config import JOB_MEMORY_MB, JOB_TIMEOUT_SECONDS, MAX_OUTPUT_MB

_ctx = mp.get_context("forkserver")
_ctx.set_forkserver_preload(["app.tools", "app.convert", "app.media", "app.ops"])


@dataclass
class Outcome:
    ok: bool
    result: str | None = None
    message: str = ""
    error: str = ""
    user_error: bool = False


def _limit_resources() -> None:
    import resource

    os.setpgrp()  # own process group: lets the parent kill the whole tree
    mem = JOB_MEMORY_MB * 1024 * 1024
    for res, value in ((resource.RLIMIT_DATA, mem), (resource.RLIMIT_FSIZE, MAX_OUTPUT_MB * 1024 * 1024),
                       (resource.RLIMIT_CORE, 0)):
        try:
            resource.setrlimit(res, (value, value))
        except (ValueError, OSError):
            pass


def _child(tool_id: str, inputs, extras, options, workdir: str, q) -> None:
    _limit_resources()
    from .tools import TOOLS_BY_ID, Ctx
    from .util import ToolError

    def progress(frac: float, stage: str) -> None:
        try:
            q.put_nowait(("progress", float(frac), str(stage)[:200]))
        except Exception:
            pass

    try:
        ctx = Ctx(inputs, extras, options, Path(workdir), progress)
        result = TOOLS_BY_ID[tool_id].handler(ctx)
        if not result or not Path(result).exists():
            raise ToolError("Processing produced no output.")
        q.put(("done", str(result), ctx.message))
    except ToolError as exc:
        q.put(("error", str(exc), True))
    except MemoryError:
        q.put(("error", "This file needs more memory than is allowed per task. Try a smaller file.", True))
    except Exception as exc:  # unexpected: details go to the log only
        q.put(("error", f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}", False))


def _kill(proc) -> None:
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(proc.pid, sig)
        except (ProcessLookupError, PermissionError):
            return
        proc.join(timeout=3)
        if not proc.is_alive():
            return


def run_isolated(tool_id: str, inputs, extras, options, workdir: Path, on_progress) -> Outcome:
    q = _ctx.Queue()
    proc = _ctx.Process(target=_child, args=(tool_id, inputs, extras, options, str(workdir), q), daemon=True)
    proc.start()
    deadline = time.monotonic() + JOB_TIMEOUT_SECONDS
    outcome: Outcome | None = None
    try:
        while outcome is None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                _kill(proc)
                return Outcome(False, error=f"Processing took longer than {JOB_TIMEOUT_SECONDS // 60} minutes and was "
                                             "stopped. Try a smaller file.", user_error=True)
            try:
                kind, a, b = q.get(timeout=min(1.0, remaining))
            except queue_mod.Empty:
                if not proc.is_alive():
                    # died without reporting: killed by a resource limit or crashed in native code
                    code = proc.exitcode
                    return Outcome(False, error="This file could not be processed safely (the task ran out of memory or "
                                                "crashed). It may be damaged or too large.", user_error=True,
                                   message=f"exit code {code}")
                continue
            if kind == "progress":
                on_progress(a, b)
            elif kind == "done":
                outcome = Outcome(True, result=a, message=b)
            else:
                outcome = Outcome(False, error=a, user_error=bool(b))
        proc.join(timeout=10)
        return outcome
    finally:
        if proc.is_alive():
            _kill(proc)
        q.close()
