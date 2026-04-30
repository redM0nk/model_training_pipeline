"""Thread-safe JSON-backed queue for extraction jobs."""
from __future__ import annotations

import json
import os
import threading
import time
import uuid
from typing import Dict, List, Optional


STATUSES = ("pending", "running", "done", "failed", "cancelled")


class QueueStore:
    def __init__(self, path: str):
        self.path = path
        self._lock = threading.RLock()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if not os.path.exists(path):
            self._write({"jobs": []})

    def _read(self) -> dict:
        with open(self.path) as f:
            return json.load(f)

    def _write(self, data: dict) -> None:
        tmp = self.path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, self.path)

    def list_jobs(self) -> List[dict]:
        with self._lock:
            return list(self._read()["jobs"])

    def add_job(self, customer: str, location: str, conveyor: str,
                recording_date: str, location_path: str) -> dict:
        with self._lock:
            data = self._read()
            for j in data["jobs"]:
                if (j["status"] in ("pending", "running") and
                        j["customer"] == customer and
                        j["location"] == location and
                        j["conveyor"] == conveyor and
                        j["recording_date"] == recording_date):
                    return j
            job = {
                "id": uuid.uuid4().hex[:12],
                "customer": customer,
                "location": location,
                "conveyor": conveyor,
                "recording_date": recording_date,
                "location_path": location_path,
                "status": "pending",
                "created_at": time.time(),
                "started_at": None,
                "finished_at": None,
                "command": None,
                "error": None,
            }
            data["jobs"].append(job)
            self._write(data)
            return job

    def update_job(self, job_id: str, **fields) -> Optional[dict]:
        with self._lock:
            data = self._read()
            for j in data["jobs"]:
                if j["id"] == job_id:
                    j.update(fields)
                    self._write(data)
                    return j
            return None

    def next_pending(self) -> Optional[dict]:
        with self._lock:
            data = self._read()
            for j in data["jobs"]:
                if j["status"] == "pending":
                    return j
            return None

    def cancel(self, job_id: str) -> Optional[dict]:
        with self._lock:
            data = self._read()
            for j in data["jobs"]:
                if j["id"] == job_id and j["status"] == "pending":
                    j["status"] = "cancelled"
                    j["finished_at"] = time.time()
                    self._write(data)
                    return j
            return None
