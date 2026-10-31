#!/usr/bin/env bash
# Build flash-attn-npu from source and place the wheel in "$ARTIFACT_DIR".
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
set -a
# shellcheck disable=SC1091
source component.env
set +a

: "${ARTIFACT_DIR:?ARTIFACT_DIR is set by the pipeline}"
: "${SOURCE_DIR:?SOURCE_DIR is set by the pipeline}"

SOURCE_REPO="${SOURCE_REPO:?component.env must set SOURCE_REPO}"
SOURCE_REF="${SOURCE_REF:?component.env must set SOURCE_REF}"
SOURCE_REF="${SOURCE_REF_OVERRIDE:-$SOURCE_REF}"
MAX_JOBS="${MAX_JOBS:-$(nproc)}"

# Match the environment used by the Dockerfile source build.
# shellcheck disable=SC1091
source /usr/local/Ascend/ascend-toolkit/set_env.sh
if [ -f /usr/local/Ascend/nnal/atb/set_env.sh ]; then
  # shellcheck disable=SC1091
  source /usr/local/Ascend/nnal/atb/set_env.sh
fi
export ASCEND_TOOLKIT_HOME="${ASCEND_TOOLKIT_HOME:-/usr/local/Ascend/ascend-toolkit/latest}"

python3 -m pip install --quiet setuptools wheel packaging psutil
python3 -m pip install --quiet \
  --extra-index-url https://download.pytorch.org/whl/cpu \
  "torch==${TORCH_VERSION}" \
  "torch-npu==${TORCH_NPU_VERSION}"

rm -rf "${SOURCE_DIR:?}"
mkdir -p "$SOURCE_DIR"
git clone "$SOURCE_REPO" "$SOURCE_DIR"
git -C "$SOURCE_DIR" checkout "$SOURCE_REF"
git -C "$SOURCE_DIR" submodule update --init --recursive
cd "$SOURCE_DIR"

if [ -f /usr/local/Ascend/cann/set_env.sh ]; then
  # shellcheck disable=SC1091
  source /usr/local/Ascend/cann/set_env.sh
fi

# Compile instead of downloading the prebuilt wheel that setup.py would
# otherwise fetch, and build every NPU target by default.
export FLASH_ATTENTION_FORCE_BUILD=TRUE
# Submodules were initialized above; skip setup.py's second, shallow init.
export FLASH_ATTENTION_SKIP_SUBMODULE_INIT=1
export MAX_JOBS
FLASH_ATTN_BUILD_VERSION="${FLASH_ATTN_BUILD_VERSION:-all}" \
FLASH_ATTN_BUILD_NPU="${FLASH_ATTN_BUILD_NPU:-all}" \
  python3 setup.py bdist_wheel

mkdir -p "$ARTIFACT_DIR"
cp -f ./dist/*.whl "$ARTIFACT_DIR/"
ls -l "$ARTIFACT_DIR"
