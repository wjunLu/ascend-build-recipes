# flash-attention-npu recipe

Builds a `flash_attn_npu` wheel from source with the same steps the vLLM Ascend Dockerfiles currently use.

| Item | Value |
| --- | --- |
| Source | `https://github.com/MinghuasLab/flash-attention-npu.git` |
| Pinned ref | `9c9f00648fa150e84228a9b757990485fc670df3` |
| Output | `flash_attn_npu-*.whl` |
| Default runner | `ubuntu-22.04-arm` |
| Default container | `quay.io/ascend/cann:9.2.1-910b-ubuntu22.04-py3.12` |

## What the recipe does

1. Sources the Ascend toolkit, ATB, and CANN environment scripts.
2. Installs the pinned `torch` / `torch-npu` pair, `setuptools`, `wheel`, `packaging`, and `psutil`.
3. Clones the source at the pinned commit and initializes all submodules.
4. Sets `FLASH_ATTENTION_FORCE_BUILD=TRUE` so `setup.py` compiles from source instead of downloading a prebuilt wheel.
5. Runs `python3 setup.py bdist_wheel` and copies `dist/*.whl` into `$ARTIFACT_DIR`.

`MAX_JOBS` defaults to `nproc`.

## Inputs

`component.env` sets the defaults:

| Variable | Default | Description |
| --- | --- | --- |
| `TORCH_VERSION` | `2.10.0` | PyTorch version installed for the build |
| `TORCH_NPU_VERSION` | `2.10.0.post7` | torch-npu version installed for the build |
| `FLASH_ATTN_BUILD_VERSION` | `all` | Upstream FA version selector (`v2`, `v3`, `v4`, or `all`) |
| `FLASH_ATTN_BUILD_NPU` | `all` | NPU target selector (`910`, `950`, or `all`) |

To build a different source revision without editing the branch, set the pipeline input `source_ref`. To change the torch baseline, update `component.env` on this branch.

## Running

```bash
gh workflow run build.yaml \
  -R wjunLu/ascend-build-recipes \
  -f component=flash-attention-npu \
  -f push_to_obs=false
```

## Notes

- The source tree is cloned into `$SOURCE_DIR` at build time; this branch only stores the recipe.
- The default configuration builds every FA API generation (v2, v3, v4) and NPU target and is therefore a long compile. Narrow `FLASH_ATTN_BUILD_VERSION` / `FLASH_ATTN_BUILD_NPU` on a private branch if a smaller artifact is enough.
- The resulting wheel is uploaded as the `build-output` GitHub artifact, and to OBS when `push_to_obs` is enabled and the OBS settings are configured on the repository.
