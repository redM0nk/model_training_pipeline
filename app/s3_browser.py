"""S3 directory browser for the Production/ tree.

Layout assumed:
  s3://<bucket>/<root>/<customer>/<location>/<conveyor>/1/Videos/<date>/...
  s3://<bucket>/<root>/<customer>/<location>/<conveyor>/1/Images/Original/RGB/<date>/...
"""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import List, Tuple

import boto3
from botocore.config import Config


@dataclass
class DateEntry:
    date: str
    has_videos: bool
    has_images: bool
    video_file_count: int = 0
    video_total_size: int = 0
    image_folder_count: int = 0

    @property
    def ready(self) -> bool:
        return self.has_videos and not self.has_images


class S3Browser:
    def __init__(self, bucket: str, root_prefix: str,
                 videos_subpath: str, images_subpath: str):
        self.bucket = bucket
        self.root_prefix = root_prefix.rstrip("/") + "/"
        self.videos_subpath = videos_subpath.strip("/") + "/"
        self.images_subpath = images_subpath.strip("/") + "/"
        self.client = boto3.client("s3", config=Config(retries={"max_attempts": 3}))

    def _list_prefixes(self, prefix: str) -> List[str]:
        out = []  # type: List[str]
        paginator = self.client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix, Delimiter="/"):
            for cp in page.get("CommonPrefixes") or []:
                p = cp["Prefix"]
                name = p[len(prefix):].rstrip("/")
                if name:
                    out.append(name)
        return sorted(out)

    def _prefix_stats(self, prefix: str) -> Tuple[int, int]:
        """Return (file_count, total_bytes) for everything under `prefix`."""
        count = 0
        size = 0
        paginator = self.client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
            for obj in page.get("Contents") or []:
                if obj["Key"].endswith("/"):
                    continue
                count += 1
                size += int(obj.get("Size", 0))
        return count, size

    def _count_subfolders(self, prefix: str) -> int:
        """Number of immediate subfolders under `prefix`."""
        count = 0
        paginator = self.client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix, Delimiter="/"):
            count += len(page.get("CommonPrefixes") or [])
        return count

    VIDEO_EXTS = (".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi")
    VIDEO_MIME = {
        ".mp4": "video/mp4",
        ".m4v": "video/mp4",
        ".mov": "video/quicktime",
        ".webm": "video/webm",
        ".mkv": "video/x-matroska",
        ".avi": "video/x-msvideo",
    }

    def list_video_files(self, customer: str, location: str, conveyor: str,
                         date: str) -> List[dict]:
        base = (f"{self.root_prefix}{customer}/{location}/{conveyor}/"
                f"{self.videos_subpath}{date}/")
        out: List[dict] = []
        paginator = self.client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=base):
            for obj in page.get("Contents") or []:
                key = obj["Key"]
                if key.endswith("/"):
                    continue
                if not key.lower().endswith(self.VIDEO_EXTS):
                    continue
                out.append({
                    "key": key,
                    "name": key[len(base):],
                    "size": int(obj.get("Size", 0)),
                })
        out.sort(key=lambda x: x["name"])
        return out

    def presign(self, key: str, expires: int = 3600,
                content_type: str = None) -> str:
        params = {"Bucket": self.bucket, "Key": key}
        if content_type is None:
            for ext, mime in self.VIDEO_MIME.items():
                if key.lower().endswith(ext):
                    content_type = mime
                    break
        if content_type:
            params["ResponseContentType"] = content_type
            params["ResponseContentDisposition"] = "inline"
        return self.client.generate_presigned_url(
            "get_object",
            Params=params,
            ExpiresIn=expires,
        )

    def list_customers(self) -> List[str]:
        return self._list_prefixes(self.root_prefix)

    def list_locations(self, customer: str) -> List[str]:
        return self._list_prefixes("{}{}/".format(self.root_prefix, customer))

    def list_conveyors(self, customer: str, location: str) -> List[str]:
        return self._list_prefixes(
            "{}{}/{}/".format(self.root_prefix, customer, location))

    def list_dates(self, customer: str, location: str, conveyor: str) -> List[DateEntry]:
        base = f"{self.root_prefix}{customer}/{location}/{conveyor}/"
        videos_root = f"{base}{self.videos_subpath}"
        images_root = f"{base}{self.images_subpath}"
        video_dates = set(self._list_prefixes(videos_root))
        image_dates = set(self._list_prefixes(images_root))
        all_dates = sorted(video_dates | image_dates, reverse=True)

        def stats_for(date: str) -> Tuple[Tuple[int, int], int]:
            v = self._prefix_stats(f"{videos_root}{date}/") if date in video_dates else (0, 0)
            i = self._count_subfolders(f"{images_root}{date}/") if date in image_dates else 0
            return v, i

        entries: List[DateEntry] = []
        if not all_dates:
            return entries

        with ThreadPoolExecutor(max_workers=min(16, len(all_dates) * 2)) as ex:
            results = list(ex.map(stats_for, all_dates))

        for d, ((v_count, v_size), i_folder_count) in zip(all_dates, results):
            entries.append(DateEntry(
                date=d,
                has_videos=d in video_dates,
                has_images=d in image_dates,
                video_file_count=v_count,
                video_total_size=v_size,
                image_folder_count=i_folder_count,
            ))
        return entries

    def relative_location_path(self, customer: str, location: str, conveyor: str) -> str:
        """Return the path used in extract_frames_for_labeling.yaml's locations_to_monitor."""
        # The YAML keys are like: Production/<customer>/<location>/<conveyor>/1/Videos/
        # root_prefix = "Data/Modeling/Fact/Production/" — we want the part after "Data/Modeling/Fact/"
        prefix_after_fact = self.root_prefix.split("Data/Modeling/Fact/", 1)[-1]
        return f"{prefix_after_fact}{customer}/{location}/{conveyor}/{self.videos_subpath}"
