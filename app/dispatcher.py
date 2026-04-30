"""Background dispatcher: pops pending jobs and sends them to a tmux pane.

Strategy:
  - Wait until the target pane is idle (its current command is a shell).
  - Write a per-job YAML config that scopes locations_to_monitor to the
    selected conveyor only, so the python script processes just that path.
  - tmux send-keys "cd <wd> && <cmd> ; touch <done_marker> ; echo __JOB_DONE__"
  - Watch for the done marker file (cheap, robust) to mark the job finished.
"""
from __future__ import annotations

import os
import shlex
import subprocess
import threading
import time
from typing import List

import yaml

from queue_store import QueueStore


class Dispatcher(threading.Thread):
    daemon = True

    def __init__(self, store: QueueStore, app_conf: dict):
        super().__init__(name="job-dispatcher")
        self.store = store
        self.conf = app_conf
        self._stop = threading.Event()
        os.makedirs(self.conf["per_job_config_dir"], exist_ok=True)
        self._marker_dir = os.path.join(self.conf["per_job_config_dir"], "markers")
        os.makedirs(self._marker_dir, exist_ok=True)

    def stop(self) -> None:
        self._stop.set()

    # ---- tmux helpers ----
    def _tmux_pane_command(self) -> str:
        target = self.conf["tmux_target"]
        try:
            out = subprocess.check_output(
                ["tmux", "display-message", "-p", "-t", target,
                 "#{pane_current_command}"],
                stderr=subprocess.STDOUT,
            ).decode().strip()
            return out
        except subprocess.CalledProcessError as e:
            return f"__error__:{e.output.decode().strip()}"
        except FileNotFoundError:
            return "__error__:tmux not installed"

    def _pane_is_idle(self) -> bool:
        cmd = self._tmux_pane_command()
        return cmd in self.conf["idle_commands"]

    def _tmux_send(self, line: str) -> None:
        target = self.conf["tmux_target"]
        subprocess.check_call(
            ["tmux", "send-keys", "-t", target, line, "Enter"]
        )

    # ---- per-job config ----
    def _write_per_job_config(self, job: dict) -> str:
        base_path = self.conf["base_extract_config"]
        wd = self.conf["job_working_dir"]
        full_base = base_path if os.path.isabs(base_path) else os.path.join(wd, base_path)

        with open(full_base) as f:
            base = yaml.safe_load(f)

        base["locations_to_monitor"] = [job["location_path"]]

        out_name = f"job_{job['id']}.yaml"
        out_path = os.path.join(self.conf["per_job_config_dir"], out_name)
        with open(out_path, "w") as f:
            yaml.safe_dump(base, f, sort_keys=False)
        return out_path

    # ---- main loop ----
    def run(self) -> None:
        poll = self.conf.get("dispatch_poll_interval", 5)
        active_marker: str | None = None
        active_job_id: str | None = None

        while not self._stop.is_set():
            try:
                if active_job_id and active_marker:
                    if os.path.exists(active_marker):
                        self.store.update_job(
                            active_job_id, status="done",
                            finished_at=time.time(),
                        )
                        try:
                            os.remove(active_marker)
                        except OSError:
                            pass
                        active_job_id = None
                        active_marker = None
                    else:
                        # still running — confirm pane is busy. If pane went idle
                        # without the marker, the command failed.
                        if self._pane_is_idle():
                            self.store.update_job(
                                active_job_id, status="failed",
                                finished_at=time.time(),
                                error="Pane went idle without success marker.",
                            )
                            active_job_id = None
                            active_marker = None
                        else:
                            time.sleep(poll)
                            continue

                if not self._pane_is_idle():
                    time.sleep(poll)
                    continue

                job = self.store.next_pending()
                if not job:
                    time.sleep(poll)
                    continue

                cfg_path = self._write_per_job_config(job)
                marker = os.path.join(self._marker_dir, f"{job['id']}.done")
                if os.path.exists(marker):
                    os.remove(marker)

                template = " ".join(self.conf["job_command_template"].split())
                cmd = template.format(
                    config_path=shlex.quote(cfg_path),
                    recording_date=shlex.quote(job["recording_date"]),
                )
                wd = self.conf["job_working_dir"]
                full_line = (
                    f"cd {shlex.quote(wd)} && {cmd} "
                    f"&& touch {shlex.quote(marker)}"
                )

                self.store.update_job(
                    job["id"], status="running",
                    started_at=time.time(), command=full_line,
                )
                self._tmux_send(full_line)
                active_job_id = job["id"]
                active_marker = marker
                # give tmux a moment so subsequent idle-check sees `python` running
                time.sleep(2)

            except Exception as e:  # noqa: BLE001
                if active_job_id:
                    self.store.update_job(
                        active_job_id, status="failed",
                        finished_at=time.time(), error=str(e),
                    )
                    active_job_id = None
                    active_marker = None
                time.sleep(poll)
