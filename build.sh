#!/usr/bin/env bash
# Build the Mooncake NPU transfer engine and place the wheel in "$ARTIFACT_DIR".
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
HIXL_REPO="${HIXL_REPO:?component.env must set HIXL_REPO}"
PYTHON_VERSION="${PYTHON_VERSION:-$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')}"
MOONCAKE_BUILD_JOBS="${MOONCAKE_BUILD_JOBS:-2}"

run_as_root() {
  if [ "$(id -u)" -eq 0 ]; then
    "$@"
  else
    sudo "$@"
  fi
}

# shellcheck disable=SC1091
source /usr/local/Ascend/cann/set_env.sh

# Build and install HIXL, following the upstream NPU release workflow.
rm -rf /tmp/hixl-build
git clone "$HIXL_REPO" /tmp/hixl-build
if [ -n "${HIXL_REF:-}" ]; then
  git -C /tmp/hixl-build checkout "$HIXL_REF"
fi
(
  cd /tmp/hixl-build
  bash build.sh -j"${HIXL_BUILD_JOBS:-$(nproc)}"
  # shellcheck disable=SC2086
  run_as_root ./build_out/cann-hixl_*.run --full --quiet --pylocal --install-path=/usr/local/Ascend
)
rm -rf /tmp/hixl-build
# shellcheck disable=SC1091
source /usr/local/Ascend/cann/set_env.sh

# Fetch the Mooncake source and install its system dependencies.
rm -rf "${SOURCE_DIR:?}"
mkdir -p "$SOURCE_DIR"
git clone "$SOURCE_REPO" "$SOURCE_DIR"
git -C "$SOURCE_DIR" checkout "$SOURCE_REF"
cd "$SOURCE_DIR"
run_as_root bash dependencies.sh -y
run_as_root bash scripts/ascend/dependencies_ascend_installation.sh
export PATH="/usr/local/go/bin:${PATH}"
# The dependency scripts can change the environment; reload CANN before CMake.
# shellcheck disable=SC1091
source /usr/local/Ascend/cann/set_env.sh

# Python tooling used by scripts/build_wheel.sh.
python3 -m pip install --quiet build setuptools wheel auditwheel numpy
if ! command -v patchelf >/dev/null 2>&1; then
  run_as_root apt-get update -y
  run_as_root apt-get install -y patchelf
fi

rm -rf build
mkdir build
cd build
cmake .. \
  -DUSE_ASCEND_DIRECT=ON \
  -DUSE_ETCD=ON \
  -DSTORE_USE_ETCD=ON \
  -DBUILD_UNIT_TESTS=OFF \
  -DCMAKE_BUILD_TYPE=Release \
  -DPython3_EXECUTABLE="$(command -v python3)" \
  -DCMAKE_INSTALL_RPATH_USE_LINK_PATH=OFF \
  -DCMAKE_BUILD_WITH_INSTALL_RPATH=OFF \
  -DCMAKE_SKIP_INSTALL_RPATH=ON
cmake --build . -j"$MOONCAKE_BUILD_JOBS"
run_as_root cmake --install .
cd "$SOURCE_DIR"

export LD_LIBRARY_PATH="${LD_LIBRARY_PATH:-}:/usr/local/lib"
export NPU_BUILD=1
export PYTHON_VERSION
OUTPUT_DIR="dist-npu-py${PYTHON_VERSION//./}"
export OUTPUT_DIR
bash scripts/build_wheel.sh

wheel_dir="$SOURCE_DIR/mooncake-wheel/${OUTPUT_DIR}"
mkdir -p "$ARTIFACT_DIR"
cp -f "$wheel_dir"/*.whl "$ARTIFACT_DIR/"
ls -l "$ARTIFACT_DIR"
