#!/usr/bin/env python3
"""Upload build artifacts and their manifest to Huawei Cloud OBS."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlparse


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--bucket", default=os.getenv("OBS_BUCKET", ""))
    parser.add_argument("--endpoint", default=os.getenv("OBS_ENDPOINT", ""))
    parser.add_argument("--root-prefix", default="")
    parser.add_argument("--github-summary", default="")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def object_prefix(manifest: dict, root_prefix: str) -> str:
    source = manifest["source"]
    version = (source.get("commit") or source.get("ref") or "unknown")[:12]
    build = manifest["build"]
    python_tag = build["python_tag"]
    python_label = f"py{python_tag[2:]}" if python_tag.startswith("cp") else python_tag
    root = (root_prefix or manifest.get("obs_prefix") or "source-builds").strip("/")
    return f"{root}/{manifest['component']}/{version}/{build['arch']}/{python_label}"


def main() -> int:
    args = parse_args()
    artifacts_dir = Path(args.dir)
    manifest_path = Path(args.manifest)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    prefix = object_prefix(manifest, args.root_prefix)
    files = [artifacts_dir / item["name"] for item in manifest["artifacts"]]
    files.append(manifest_path)
    missing = [str(path) for path in files if not path.is_file()]
    if missing:
        print(
            "error: missing artifact files: " + ", ".join(missing),
            file=sys.stderr,
        )
        return 1

    access_key = os.getenv("OBS_ACCESS_KEY_ID", "")
    secret_key = os.getenv("OBS_SECRET_ACCESS_KEY", "")
    dry_run = args.dry_run or not access_key or not secret_key

    if not dry_run and (not args.bucket or not args.endpoint):
        print(
            "error: OBS bucket and endpoint are required for a real upload",
            file=sys.stderr,
        )
        return 1

    rows: list[tuple[str, str]] = []
    if dry_run:
        for path in files:
            rows.append((f"{prefix}/{path.name}", "(dry-run)"))
    else:
        from obs import ObsClient

        client = ObsClient(
            access_key_id=access_key,
            secret_access_key=secret_key,
            server=args.endpoint,
        )
        host = urlparse(args.endpoint).netloc
        try:
            for path in files:
                key = f"{prefix}/{path.name}"
                response = client.putFile(args.bucket, key, str(path))
                if response.status >= 300:
                    print(
                        f"error: upload failed for {path.name}: "
                        f"{response.errorCode} {response.errorMessage}",
                        file=sys.stderr,
                    )
                    return 1
                rows.append((key, f"https://{args.bucket}.{host}/{key}"))
        finally:
            client.close()

    for key, url in rows:
        print(f"{key}\t{url}")

    if args.github_summary:
        lines = [
            "## OBS upload",
            "",
            "| Object | URL |",
            "| --- | --- |",
        ]
        lines.extend(f"| `{key}` | {url} |" for key, url in rows)
        with Path(args.github_summary).open("a", encoding="utf-8") as summary:
            summary.write("\n".join(lines) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
