# mooncake recipe

Builds the Mooncake NPU transfer engine wheel with the same steps as the upstream `release-npu.yaml` workflow.

| Item | Value |
| --- | --- |
| Source | `https://github.com/kvcache-ai/Mooncake.git` |
| Pinned ref | `v0.3.14-pre-3` |
| HIXL source | `https://gitcode.com/cann/hixl.git` |
| Output | `mooncake_transfer_engine_npu-*.whl` |
| Default runner | `ubuntu-22.04-arm` |
| Default container | `quay.io/ascend/cann:9.2.1-910b-ubuntu22.04-py3.12` |

## What the recipe does

1. Sources the CANN environment.
2. Clones and builds HIXL, installs it into `/usr/local/Ascend`, and reloads the CANN environment.
3. Clones Mooncake at the pinned tag and runs `dependencies.sh -y` plus `scripts/ascend/dependencies_ascend_installation.sh`.
4. Configures CMake with `USE_ASCEND_DIRECT`, `USE_ETCD`, and `STORE_USE_ETCD`, builds with `-j2` by default, and installs the result.
5. Runs `NPU_BUILD=1 PYTHON_VERSION=<x.y> OUTPUT_DIR=dist-npu-py<x><y> ./scripts/build_wheel.sh` and copies the wheel from `mooncake-wheel/dist-npu-py<x><y>/` into `$ARTIFACT_DIR`.

The CMake build is the slow part. The default `-j2` matches upstream to keep memory use bounded; raise `MOONCAKE_BUILD_JOBS` only if the runner has enough RAM.

## Inputs

`component.env` sets the defaults:

| Variable | Default | Description |
| --- | --- | --- |
| `HIXL_REPO` | `https://gitcode.com/cann/hixl.git` | HIXL repository |
| `HIXL_REF` | empty | Optional HIXL commit/tag; empty uses the default branch |
| `MOONCAKE_BUILD_JOBS` | `2` | CMake build parallelism |

To build a different Mooncake revision without editing the branch, set the pipeline input `source_ref`. To change HIXL or the job count, update `component.env` on this branch.

## Running

```bash
gh workflow run build.yaml \
  -R wjunLu/ascend-build-recipes \
  -f component=mooncake \
  -f push_to_obs=false
```

The default 360-minute job timeout may be tight on a hosted runner. If the build is consistently slower, use a self-hosted runner:

```bash
gh workflow run build.yaml \
  -R wjunLu/ascend-build-recipes \
  -f component=mooncake \
  -f runs_on='["self-hosted","linux","arm64","ascend-build"]'
```

The CANN version can be changed with `-f container_image=...`; use an image whose CANN version matches the Mooncake/HIXL baseline.

## Notes

- The source trees are cloned into `$SOURCE_DIR` and `/tmp` at build time; this branch only stores the recipe.
- `dependencies.sh -y` and the Ascend dependency script install system packages and write outside the repository. The build job therefore runs in a disposable container.
- The resulting wheel is uploaded as the `build-output` GitHub artifact, and to OBS when `push_to_obs` is enabled and the OBS settings are configured on the repository.
