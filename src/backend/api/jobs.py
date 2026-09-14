from __future__ import annotations
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional
from api.schemas import JobStatus, ParetoPoint
import asyncio
import time
import traceback
import uuid

@dataclass
class JobRecord:
    job_id: str
    state: str = "queued"                      # queued | running | done | failed
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    config_version: int = 0
    error: Optional[str] = None
    results: Optional[list] = None

    def to_schema(self) -> JobStatus:
        return JobStatus(
            job_id=self.job_id, state=self.state,
            created_at=self.created_at, started_at=self.started_at,
            finished_at=self.finished_at, config_version=self.config_version,
            error=self.error,
            results=[ParetoPoint(**r) for r in self.results] if self.results is not None else None,
        )


class JobManager:
    def __init__(self, max_concurrent_solves: int = 1):
        self._jobs: Dict[str, JobRecord] = {}
        self._dict_lock = asyncio.Lock()          # bảo vệ CẤU TRÚC dict (insert/list)
        self._solve_semaphore = asyncio.Semaphore(max_concurrent_solves)

    async def submit(self, config_version: int, blocking_fn: Callable[[], list]) -> str:
        job_id = uuid.uuid4().hex[:12]
        record = JobRecord(job_id=job_id, config_version=config_version)
        async with self._dict_lock:
            self._jobs[job_id] = record
        asyncio.create_task(self._run(record, blocking_fn))
        return job_id

    async def _run(self, record: JobRecord, blocking_fn: Callable[[], list]) -> None:
        async with self._solve_semaphore:
            record.state = "running"
            record.started_at = time.time()
            try:
                results = await asyncio.to_thread(blocking_fn)
                record.results = results
                record.state = "done"
            except Exception as exc:  # noqa: BLE001 — job nền, phải bắt hết để không "mất tích" job
                record.error = f"{exc}\n{traceback.format_exc(limit=3)}"
                record.state = "failed"
            finally:
                record.finished_at = time.time()

    async def get(self, job_id: str) -> Optional[JobRecord]:
        async with self._dict_lock:
            return self._jobs.get(job_id)

    async def list_recent(self, limit: int = 20) -> List[JobRecord]:
        async with self._dict_lock:
            return sorted(self._jobs.values(), key=lambda r: r.created_at, reverse=True)[:limit]