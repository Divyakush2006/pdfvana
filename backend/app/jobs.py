"""Job queue with progress tracking, per-client limits, process isolation and automatic deletion."""
from __future__ import annotations

import logging
import shutil
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from .config import DATA_DIR, JOB_TTL_SECONDS, MAX_ACTIVE_JOBS_PER_CLIENT, MAX_QUEUED_JOBS, WORKERS
from .tools import InputFile
from .worker import run_isolated

log = logging.getLogger("jobs")
GENERIC_ERROR = ("Something went wrong while processing your file. It may be damaged, encrypted or unusual — "
                 "please try another file.")


@dataclass
class Job:
    id: str
    tool: str
    dir: Path
    inputs: list[InputFile]
    extras: dict[str, InputFile]
    options: dict
    client: str = ""
    status: str = "queued"  # queued | running | done | error
    progress: float = 0.0
    stage: str = "Waiting in queue"
    message: str = ""
    error: str = ""
    result: Path | None = None
    input_bytes: int = 0
    created: float = field(default_factory=time.time)
    finished: float | None = None

    def public(self) -> dict:
        d = {
            "id": self.id, "tool": self.tool, "status": self.status, "progress": round(self.progress, 3),
            "stage": self.stage, "message": self.message, "error": self.error,
            "expires_in": max(0, int(self.created + JOB_TTL_SECONDS - time.time())),
            "input_bytes": self.input_bytes,
        }
        if self.result and self.result.exists():
            d["result"] = {"name": self.result.name, "size": self.result.stat().st_size}
        if self.finished:
            d["seconds"] = round(self.finished - self.created, 1)
        return d


class BusyError(Exception):
    """The server or this client has too much work queued."""


class JobStore:
    def __init__(self) -> None:
        self.jobs: dict[str, Job] = {}
        self.lock = threading.Lock()
        self.pool = ThreadPoolExecutor(max_workers=WORKERS, thread_name_prefix="job")
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        for leftover in DATA_DIR.iterdir():  # nothing survives a restart
            shutil.rmtree(leftover, ignore_errors=True)
        threading.Thread(target=self._janitor, daemon=True, name="janitor").start()

    def new_dir(self) -> tuple[str, Path]:
        jid = uuid.uuid4().hex
        d = DATA_DIR / jid
        (d / "in").mkdir(parents=True)
        (d / "work").mkdir()
        return jid, d

    def check_capacity(self, client: str) -> None:
        with self.lock:
            active = [j for j in self.jobs.values() if j.status in ("queued", "running")]
        if len(active) >= MAX_QUEUED_JOBS:
            raise BusyError("The service is very busy right now. Please try again in a minute.")
        if sum(1 for j in active if j.client == client) >= MAX_ACTIVE_JOBS_PER_CLIENT:
            raise BusyError("You already have several files processing. Wait for them to finish, then try again.")

    def submit(self, job: Job) -> Job:
        with self.lock:
            self.jobs[job.id] = job
        self.pool.submit(self._run, job)
        return job

    def get(self, jid: str) -> Job | None:
        with self.lock:
            return self.jobs.get(jid)

    def delete(self, jid: str) -> bool:
        with self.lock:
            job = self.jobs.pop(jid, None)
        if job:
            shutil.rmtree(job.dir, ignore_errors=True)
        return job is not None

    def _run(self, job: Job) -> None:
        job.status, job.stage, job.progress = "running", "Starting", 0.02

        def progress(frac: float, stage: str) -> None:
            job.progress = max(job.progress, min(0.99, float(frac)))
            job.stage = stage

        try:
            out = run_isolated(job.tool, job.inputs, job.extras, job.options, job.dir / "work", progress)
            result = Path(out.result) if out.ok and out.result else None
            work = (job.dir / "work").resolve()
            if out.ok and result and result.exists() and work in result.resolve().parents:
                job.result, job.message = result, out.message
                job.status, job.progress, job.stage = "done", 1.0, "Done"
            elif out.ok:
                job.status, job.error = "error", "Processing produced no output."
            elif out.user_error:
                job.status, job.error = "error", out.error
                if out.message:
                    log.warning("job %s (%s) stopped: %s", job.id, job.tool, out.message)
            else:
                log.error("job %s (%s) failed: %s", job.id, job.tool, out.error)
                job.status, job.error = "error", GENERIC_ERROR
        except Exception:  # never let a worker thread die silently
            log.exception("job %s (%s) crashed", job.id, job.tool)
            job.status, job.error = "error", GENERIC_ERROR
        finally:
            job.finished = time.time()
            shutil.rmtree(job.dir / "in", ignore_errors=True)  # inputs are no longer needed

    def _janitor(self) -> None:
        while True:
            time.sleep(30)
            try:
                cutoff = time.time() - JOB_TTL_SECONDS
                with self.lock:
                    expired = [j for j in self.jobs.values() if j.created < cutoff and j.status in ("done", "error")]
                    for j in expired:
                        self.jobs.pop(j.id, None)
                for j in expired:
                    shutil.rmtree(j.dir, ignore_errors=True)
                known = set(self.jobs)
                for d in DATA_DIR.iterdir():
                    if d.name not in known and d.name != "tmp" and d.stat().st_mtime < cutoff:
                        shutil.rmtree(d, ignore_errors=True)
            except Exception:
                log.exception("janitor error")

    def stats(self) -> dict:
        with self.lock:
            states = [j.status for j in self.jobs.values()]
        return {s: states.count(s) for s in ("queued", "running", "done", "error")}
