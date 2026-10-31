#!/usr/bin/env python3
"""Copy OBS objects from a source bucket/endpoint to a destination bucket/endpoint.

Each object is downloaded to the runner and re-uploaded, so the source and
destination can live in different regions or different accounts.

Source credentials come from these environment variables:

    OBS_SOURCE_ACCESS_KEY_ID / OBS_SOURCE_SECRET_ACCESS_KEY
    OBS_SOURCE_ENDPOINT / OBS_SOURCE_BUCKET

Destination credentials come from the same variables as the build pipeline:

    OBS_ACCESS_KEY_ID / OBS_SECRET_ACCESS_KEY
    OBS_ENDPOINT / OBS_BUCKET
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlparse

CHUNK_SIZE = 1024 * 1024


def required(name: str) -> str:
    value = os.getenv(name, "")
    if not value:
        print(f"error: environment variable {name} is not set", file=sys.stderr)
        raise SystemExit(2)
    return value


def build_plan(source_keys, source_prefix: str, destination_prefix: str):
    """Map source keys to destination keys.

    Returns a list of (source_key, destination_key) tuples, preserving the
    relative path under the prefix. The function is separate so the mapping
    can be unit-tested without an OBS client.
    """
    source_prefix = (source_prefix or "").strip("/")
    destination_prefix = (destination_prefix or source_prefix).strip("/")
    plan = []
    for source_key in source_keys:
        if not source_prefix:
            relative = source_key
        else:
            relative = source_key[len(source_prefix):].lstrip("/")
        destination_key = (
            f"{destination_prefix}/{relative}".strip("/")
            if destination_prefix
            else relative
        )
        plan.append((source_key, destination_key))
    return plan


def list_objects(client, bucket: str, prefix: str):
    marker = None
    while True:
        kwargs = {"prefix": prefix, "max_keys": 1000}
        if marker:
            kwargs["marker"] = marker
        response = client.listObjects(bucket, **kwargs)
        if response.status >= 300:
            print(
                f"error: listing {prefix!r} in {bucket} failed: "
                f"{response.errorCode} {response.errorMessage}",
                file=sys.stderr,
            )
            raise SystemExit(1)
        body = response.body
        for content in body.contents:
            if content.key.endswith("/"):
                # Console-created folder marker, not an object.
                continue
            yield content.key, content.size
        if not body.is_truncated:
            return
        marker = body.next_marker
        if not marker:
            return


def destination_size(client, bucket: str, key: str):
    response = client.getObjectMetadata(bucket, key)
    if response.status == 404:
        return None
    if response.status >= 300:
        print(
            f"error: HEAD {key} in {bucket} failed: "
            f"{response.errorCode} {response.errorMessage}",
            file=sys.stderr,
        )
        raise SystemExit(1)
    try:
        return int(response.body.contentLength)
    except (AttributeError, TypeError, ValueError):
        return None


def download(client, bucket: str, key: str, destination: Path, expected_size):
    response = client.getObject(bucket, key, loadStreamInMemory=False)
    if response.status >= 300:
        raise RuntimeError(
            f"download of {key} failed: "
            f"{response.errorCode} {response.errorMessage}"
        )
    with destination.open("wb") as handle:
        stream = response.body.response
        while True:
            chunk = stream.read(CHUNK_SIZE)
            if not chunk:
                break
            handle.write(chunk)
    if destination.stat().st_size != expected_size:
        raise RuntimeError(
            f"size mismatch for {key}: expected {expected_size} bytes, "
            f"got {destination.stat().st_size}"
        )


def upload(client, bucket: str, key: str, source: Path):
    response = client.putFile(bucket, key, str(source))
    if response.status >= 300:
        raise RuntimeError(
            f"upload of {key} failed: "
            f"{response.errorCode} {response.errorMessage}"
        )


def make_client(access_key: str, secret_key: str, endpoint: str):
    from obs import ObsClient

    return ObsClient(
        access_key_id=access_key,
        secret_access_key=secret_key,
        server=endpoint,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-prefix", required=True)
    parser.add_argument(
        "--destination-prefix",
        default="",
        help="empty means the same path as the source prefix",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="overwrite destination objects even when a same-size object exists",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="list matching objects without copying",
    )
    parser.add_argument(
        "--github-summary",
        default=os.getenv("GITHUB_STEP_SUMMARY", ""),
    )
    args = parser.parse_args()

    source_client = make_client(
        required("OBS_SOURCE_ACCESS_KEY_ID"),
        required("OBS_SOURCE_SECRET_ACCESS_KEY"),
        required("OBS_SOURCE_ENDPOINT"),
    )
    source_bucket = required("OBS_SOURCE_BUCKET")
    destination_client = None
    try:
        objects = list(list_objects(source_client, source_bucket, args.source_prefix))

        if not objects:
            print(f"no objects found under {args.source_prefix!r} in {source_bucket}")
            return 0

        plan = build_plan(
            [key for key, _ in objects],
            args.source_prefix,
            args.destination_prefix,
        )
        sizes = {key: size for key, size in objects}
        rows: list[tuple[str, str, int, str]] = []
        if args.dry_run:
            for source_key, destination_key in plan:
                rows.append((source_key, destination_key, sizes[source_key], "dry-run"))
        else:
            destination_client = make_client(
                required("OBS_ACCESS_KEY_ID"),
                required("OBS_SECRET_ACCESS_KEY"),
                required("OBS_ENDPOINT"),
            )
            destination_bucket = required("OBS_BUCKET")
            destination_host = urlparse(os.getenv("OBS_ENDPOINT", "")).netloc
            with tempfile.TemporaryDirectory(prefix="obs-sync-") as tmp_dir:
                for index, (source_key, destination_key) in enumerate(plan):
                    size = sizes[source_key]
                    if not args.force:
                        existing = destination_size(
                            destination_client, destination_bucket, destination_key
                        )
                        if existing is not None and existing == size:
                            rows.append(
                                (source_key, destination_key, size, "skipped")
                            )
                            continue
                    local = Path(tmp_dir) / str(index) / Path(source_key).name
                    local.parent.mkdir(parents=True, exist_ok=True)
                    download(source_client, source_bucket, source_key, local, size)
                    upload(destination_client, destination_bucket, destination_key, local)
                    local.unlink(missing_ok=True)
                    rows.append((source_key, destination_key, size, "copied"))
    finally:
        source_client.close()
        if destination_client is not None:
            destination_client.close()

    for source_key, destination_key, size, status in rows:
        print(f"{status}\t{source_key}\t{destination_key}\t{size}")

    if args.github_summary:
        lines = [
            "## OBS sync",
            "",
            f"Source: `{source_bucket}/{args.source_prefix}`",
            "| Status | Source key | Destination key | Size |",
            "| --- | --- | --- | --- |",
        ]
        for source_key, destination_key, size, status in rows:
            lines.append(
                f"| {status} | `{source_key}` | `{destination_key}` | {size} |"
            )
        if not args.dry_run:
            lines.append("")
            for _, destination_key, _, status in rows:
                if status == "copied":
                    lines.append(
                        f"- https://{destination_bucket}.{destination_host}/{destination_key}"
                    )
        with Path(args.github_summary).open("a", encoding="utf-8") as summary:
            summary.write("\n".join(lines) + "\n")

    copied = sum(1 for _, _, _, status in rows if status == "copied")
    skipped = sum(1 for _, _, _, status in rows if status == "skipped")
    print(f"summary: {len(rows)} objects, {copied} copied, {skipped} skipped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
