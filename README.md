# Ascend source build recipes

A branch-per-component repository for building Ascend wheels from source with one manually triggered GitHub Actions pipeline and publishing them to Huawei Cloud OBS.

The `main` branch contains only the shared pipeline. Each additional branch contains the recipe for exactly one component:

| Branch | Component | Output |
| --- | --- | --- |
| `flash-attention-npu` | [MinghuasLab/flash-attention-npu](https://github.com/MinghuasLab/flash-attention-npu) | `flash_attn_npu-*.whl` |
| `mooncake` | [kvcache-ai/Mooncake](https://github.com/kvcache-ai/Mooncake) with the NPU transfer engine | `mooncake_transfer_engine_npu-*.whl` |

The recipes mirror the source-compilation steps currently embedded in the vLLM Ascend Dockerfiles. Building them here makes the output reusable: once a wheel is published to OBS, a Dockerfile can install it instead of running a full toolchain during the image build.

## Pipeline

[.github/workflows/build.yaml](.github/workflows/build.yaml) is started with `workflow_dispatch`. It does not run on pushes or pull requests.

Inputs:

| Input | Default | Description |
| --- | --- | --- |
| `component` | (required) | Component branch to build, for example `flash-attention-npu` |
| `source_ref` | empty | Commit or tag override; empty means the value in the component's `component.env` |
| `runs_on` | `["ubuntu-22.04-arm"]` | Runner labels as a JSON array |
| `container_image` | `quay.io/ascend/cann:9.2.1-910b-ubuntu22.04-py3.12` | CANN build container |
| `push_to_obs` | `false` | Upload the artifacts to OBS after a successful build |
| `obs_prefix` | empty | OBS key prefix override; empty means the value in `component.env` |

Jobs:

1. `build` runs on the requested runner inside the CANN container. It checks out `main` (for the pipeline scripts) and the component branch (for the recipe), runs `build.sh`, verifies that the expected artifacts exist, writes `manifest.json`, and uploads everything as the `build-output` GitHub artifact.
2. `publish` runs only when `push_to_obs` is true. It runs on a clean `ubuntu-latest` runner, downloads the artifact, and uploads it to OBS. This job is the only place OBS credentials are exposed; the build job never receives them.

The component branch and the source repository are cloned at build time, so neither source tree is stored in this repository.

## Running a build

From the Actions tab, select **Build component**, choose **Run workflow**, and fill in the inputs. From the CLI:

```bash
gh workflow run build.yaml \
  -R wjunLu/ascend-build-recipes \
  -f component=flash-attention-npu \
  -f runs_on='["ubuntu-22.04-arm"]' \
  -f push_to_obs=false
```

Watch the run and download the wheel:

```bash
gh run list -R wjunLu/ascend-build-recipes --workflow build.yaml
gh run watch -R wjunLu/ascend-build-recipes <run-id>
gh run download -R wjunLu/ascend-build-recipes <run-id> -n build-output -D ./artifacts
```

`push_to_obs` stays `false` until the OBS secrets and variables below are configured. The wheel is still available as a GitHub Actions artifact for 14 days.

## OBS configuration

The repository does not contain OBS credentials. Before enabling `push_to_obs`, configure:

Repository secrets:

| Name | Description |
| --- | --- |
| `OBS_ACCESS_KEY_ID` | OBS access key ID |
| `OBS_SECRET_ACCESS_KEY` | OBS secret access key |

Repository variables:

| Name | Example | Description |
| --- | --- | --- |
| `OBS_ENDPOINT` | `https://obs.cn-north-4.myhuaweicloud.com` | OBS endpoint |
| `OBS_BUCKET` | `<bucket-name>` | Destination bucket |

The values are only used by the `publish` job. A run started with `push_to_obs=true` and missing credentials fails before any upload, with a message naming the missing setting.

### Object layout

```text
<prefix>/<component>/<source-commit-12>/<arch>/py<major-minor>/<artifact>
<prefix>/<component>/<source-commit-12>/<arch>/py<major-minor>/manifest.json
```

For example:

```text
source-builds/flash-attention-npu/9c9f00648fa1/aarch64/py312/flash_attn_npu-<version>-cp312-cp312-linux_aarch64.whl
```

`<prefix>` defaults to `source-builds` and can be overridden per component (`OBS_PREFIX` in `component.env`) or per run (`obs_prefix` input). Rebuilding the same commit on the same architecture and Python version overwrites the previous objects; the SHA-256 checksums are recorded in `manifest.json`.

The public URL printed by the publish job is `https://<bucket>.<endpoint-host>/<key>`. If the bucket is private, use an authorized download mechanism instead of that URL.

## Component branch contract

Every component branch is an orphan branch containing three files:

```text
component.env   # metadata and defaults
build.sh        # executable build recipe
README.md       # component-specific notes
```

The pipeline provides these environment variables to `build.sh`:

| Variable | Description |
| --- | --- |
| `SOURCE_DIR` | Empty directory; clone the source repository here |
| `ARTIFACT_DIR` | Directory for the final artifacts; the pipeline verifies and uploads it |
| `SOURCE_REF_OVERRIDE` | Requested source commit/tag, or empty |
| `PYTHON_VERSION` | Container Python version, for example `3.12` |
| `PYTHON_TAG` | Wheel tag, for example `cp312` |
| `ARCH` | `uname -m` value, for example `aarch64` |

`component.env` sets:

| Variable | Required | Description |
| --- | --- | --- |
| `COMPONENT` | yes | Component name; also used in the OBS path |
| `SOURCE_REPO` | yes | Git URL of the source repository |
| `SOURCE_REF` | yes | Default commit or tag |
| `OBS_PREFIX` | no | OBS prefix; defaults to `source-builds` |
| `ARTIFACT_PATTERN` | no | Glob for expected files in `ARTIFACT_DIR`; defaults to `*.whl` |

Rules for `build.sh`:

- It must honor `SOURCE_REF_OVERRIDE` when it is non-empty.
- It must place the final files directly in `ARTIFACT_DIR` (no subdirectories).
- It must source the CANN environment it needs; the pipeline does not do that per component.
- It must not expect network restrictions beyond those of the runner.
- It must not read, print, or write secrets. The build job has none.
- It runs as root inside the CANN container, but should use `sudo` only when it is not root so it also works on a self-hosted runner without a container.

## Adding a component

```bash
git checkout --orphan my-component
# add component.env, build.sh, README.md
chmod +x build.sh
git add component.env build.sh README.md
git commit -s -m "[my-component] Add build recipe"
git push origin my-component
```

The branch name is the `component` input. The branch cannot be the default branch. Add a row to the table above if the component should be discoverable.

Only repository maintainers should be able to push component branches: their `build.sh` is executed in CI with the runner's permissions. The pipeline checks out a component branch only after confirming it exists; it does not run code from arbitrary refs.

## Runners and container

The default runner is `ubuntu-22.04-arm`, a GitHub-hosted ARM64 runner available to public repositories. Compilation needs the CANN toolchain but no NPU device.

To build on a self-hosted runner, pass its labels as a JSON array, for example:

```bash
-f runs_on='["self-hosted","linux","arm64","ascend-build"]'
```

To change the CANN version, pass a different `container_image`. The image must contain `python3`, `git`, and the CANN environment scripts the recipe sources.

Mooncake is a long build and needs a large working disk; a self-hosted ARM64 runner is likely to be more reliable than a hosted runner for it. The job timeout is 360 minutes.

## Notes and limitations

- This repository publishes artifacts only. The vLLM Ascend Dockerfiles still compile these components from source and are not changed by this repository.
- OBS credentials are intentionally absent; `push_to_obs` defaults to `false`.
- The pipeline does not verify wheel signatures or run smoke tests on the built wheel. Each component's `README.md` describes what the recipe builds and which upstream revision it pins.
- Artifact retention in GitHub Actions is 14 days.
