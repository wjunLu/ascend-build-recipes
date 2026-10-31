#!/usr/bin/env python3
"""Create a build manifest for artifacts produced by a component recipe."""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


def sha256sum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts-dir", required=True)
    parser.add_argument("--artifact-pattern", default="*.whl")
    parser.add_argument("--output", required=True)
    parser.add_argument("--component", required=True)
    parser.add_argument("--source-repo", required=True)
    parser.add_argument("--source-ref", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--python-version", required=True)
    parser.add_argument("--python-tag", required=True)
    parser.add_argument("--arch", required=True)
    parser.add_argument("--cann-version", default="")
    parser.add_argument("--container-image", default="")
    parser.add_argument("--component-branch", required=True)
    parser.add_argument("--component-commit", required=True)
    parser.add_argument("--recipes-commit", required=True)
    parser.add_argument("--obs-prefix", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    artifacts_dir = Path(args.artifacts_dir)
    if not artifacts_dir.is_dir():
        print(
            f"error: artifacts directory not found: {artifacts_dir}",
            file=sys.stderr,
        )
        return 1
    artifacts = sorted(
        path
        for path in artifacts_dir.iterdir()
        if path.is_file()
        and path.name != "manifest.json"
        and fnmatch.fnmatch(path.name, args.artifact_pattern)
    )
    if not artifacts:
        print(
            f"error: no files matching {args.artifact_pattern!r} in {artifacts_dir}",
            file=sys.stderr,
        )
        return 1
    server = os.getenv("GITHUB_SERVER_URL", "https://github.com")
    repository = os.getenv("GITHUB_REPOSITORY", "")
    run_id = os.getenv("GITHUB_RUN_ID", "")
    run_url = (
        f"{server}/{repository}/actions/runs/{run_id}"
        if repository and run_id
        else ""
    )
    manifest = {
        "schema_version": 1,
        "component": args.component,
        "source": {
            "repository": args.source_repo,
            "ref": args.source_ref,
            "commit": args.source_commit,
        },
        "recipe": {
            "branch": args.component_branch,
            "commit": args.component_commit,
        },
        "build": {
            "python_version": args.python_version,
            "python_tag": args.python_tag,
            "arch": args.arch,
            "cann_version": args.cann_version,
            "container_image": args.container_image,
            "recipes_commit": args.recipes_commit,
            "workflow": {
                "repository": repository,
                "run_id": run_id,
                "run_url": run_url,
            },
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
        "obs_prefix": args.obs_prefix,
        "artifacts": [
            {
                "name": path.name,
                "size": path.stat().st_size,
                "sha256": sha256sum(path),
            }
            for path in artifacts
        ],
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {output}")
    for artifact in manifest["artifacts"]:
        print(f"{artifact['sha256']}  {artifact['name']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
