"""System stats (CPU, memory, disk) using stdlib only."""
import shutil
import threading


class CPUSampler:
    """Computes CPU usage % from successive /proc/stat samples."""

    def __init__(self):
        self._lock = threading.Lock()
        self._prev = None  # (total, idle)

    @staticmethod
    def _read():
        with open("/proc/stat") as f:
            parts = f.readline().split()
        # parts = ["cpu", user, nice, system, idle, iowait, irq, softirq, steal, ...]
        nums = [int(x) for x in parts[1:]]
        idle = nums[3] + (nums[4] if len(nums) > 4 else 0)  # idle + iowait
        total = sum(nums)
        return total, idle

    def sample(self):
        total, idle = self._read()
        with self._lock:
            prev = self._prev
            self._prev = (total, idle)
        if prev is None:
            return None
        dt = total - prev[0]
        di = idle - prev[1]
        if dt <= 0:
            return None
        return max(0.0, min(100.0, 100.0 * (dt - di) / dt))


def read_memory():
    """Returns (total_bytes, used_bytes) from /proc/meminfo."""
    info = {}
    with open("/proc/meminfo") as f:
        for line in f:
            k, _, rest = line.partition(":")
            v = rest.strip().split()
            if v:
                info[k] = int(v[0]) * 1024  # kB -> bytes
    total = info.get("MemTotal", 0)
    avail = info.get("MemAvailable", info.get("MemFree", 0))
    return total, max(0, total - avail)


def read_disk(path: str = "/"):
    u = shutil.disk_usage(path)
    return u.total, u.used


def collect(cpu_sampler: CPUSampler, disk_path: str = "/") -> dict:
    cpu_pct = cpu_sampler.sample()
    mem_total, mem_used = read_memory()
    disk_total, disk_used = read_disk(disk_path)
    return {
        "cpu_percent": cpu_pct,
        "memory": {
            "total": mem_total,
            "used": mem_used,
            "percent": (100.0 * mem_used / mem_total) if mem_total else None,
        },
        "disk": {
            "path": disk_path,
            "total": disk_total,
            "used": disk_used,
            "percent": (100.0 * disk_used / disk_total) if disk_total else None,
        },
    }
