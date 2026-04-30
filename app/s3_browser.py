"""S3 directory browser for the Production/ tree.

Layout assumed:
  s3://<bucket>/<root>/<customer>/<location>/<conveyor>/1/Videos/<date>/...
  s3://<bucket>/<root>/<customer>/<location>/<conveyor>/1/Images/Original/RGB/<date>/...
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

import boto3
from botocore.config import Config


@dataclass
class DateEntry:
    date: str
    has_videos: bool
    has_images: bool

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
        out: List[str] = []
        paginator = self.client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix, Delimiter="/"):
            for cp in page.get("CommonPrefixes") or []:
                p = cp["Prefix"]
                name = p[len(prefix):].rstrip("/")
                if name:
                    out.append(name)
        return sorted(out)

    def list_customers(self) -> List[str]:
        return self._list_prefixes(self.root_prefix)

    def list_locations(self, customer: str) -> List[str]:
        return self._list_prefixes(f"{self.root_prefix}{customer}/")

    def list_conveyors(self, customer: str, location: str) -> List[str]:
        return self._list_prefixes(f"{self.root_prefix}{customer}/{location}/")

    def list_dates(self, customer: str, location: str, conveyor: str) -> List[DateEntry]:
        base = f"{self.root_prefix}{customer}/{location}/{conveyor}/"
        video_dates = set(self._list_prefixes(f"{base}{self.videos_subpath}"))
        image_dates = set(self._list_prefixes(f"{base}{self.images_subpath}"))
        all_dates = sorted(video_dates | image_dates, reverse=True)
        return [
            DateEntry(date=d,
                      has_videos=d in video_dates,
                      has_images=d in image_dates)
            for d in all_dates
        ]

    def relative_location_path(self, customer: str, location: str, conveyor: str) -> str:
        """Return the path used in extract_frames_for_labeling.yaml's locations_to_monitor."""
        # The YAML keys are like: Production/<customer>/<location>/<conveyor>/1/Videos/
        # root_prefix = "Data/Modeling/Fact/Production/" — we want the part after "Data/Modeling/Fact/"
        prefix_after_fact = self.root_prefix.split("Data/Modeling/Fact/", 1)[-1]
        return f"{prefix_after_fact}{customer}/{location}/{conveyor}/{self.videos_subpath}"
