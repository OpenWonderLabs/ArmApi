#!/usr/bin/env bash
# =============================================================================
# install_riscv_dependencies.sh — 一次性把 OneroArm 的第三方依赖装到 RISC-V 板子
#
# 背景：conda-forge 没有 riscv64 的 OneroArm 运行时依赖包。RISC-V 用户需要
# 在目标板本机把 hpp-fcl / pinocchio 等第三方库编译到固定前缀
# （默认 /opt/onero-deps），之后即可直接安装 Python wheel，或编译链接 C/C++
# 随包的 liboneroarm.so。
#
# 这个脚本在板子上**跑一次**即可（除非依赖版本变了）。它幂等：已安装的会跳过。
#
# 用法：
#   sudo PREFIX=/opt/onero-deps ./scripts/install_riscv_dependencies.sh
#
# 依赖版本须与随包 liboneroarm.so 的 ABI/SONAME 匹配：
#   pinocchio 3.1.0   hpp-fcl 2.4.4   eigen 3.4   boost 1.8x   urdfdom 4.0
# =============================================================================
set -euo pipefail

PREFIX="${PREFIX:-/opt/onero-deps}"
SRC_DIR="${SRC_DIR:-/tmp/onero-deps-src}"
JOBS="${JOBS:-$(nproc)}"
HPPFCL_TAG="${HPPFCL_TAG:-v2.4.4}"
PINOCCHIO_TAG="${PINOCCHIO_TAG:-v3.1.0}"

echo "==> PREFIX=$PREFIX  SRC_DIR=$SRC_DIR  JOBS=$JOBS"
echo "==> hpp-fcl=$HPPFCL_TAG  pinocchio=$PINOCCHIO_TAG"

# 必须在 riscv64 上运行
arch="$(uname -m)"
if [[ "$arch" != "riscv64" ]]; then
  echo "WARNING: 当前架构是 $arch，不是 riscv64。本脚本用于在 riscv 板子上预置依赖。" >&2
fi

# -----------------------------------------------------------------------------
# 1. 发行版包（能 apt 拿的简单依赖）。包名以 Debian/Ubuntu(ports) 为准，
#    其它发行版按需替换。pinocchio 需要 urdfdom；hpp-fcl 需要 octomap/assimp/qhull。
#    wheel 发布固定为 cp312；Bianbu apt 源可能没有 python3.12，因此这里不把
#    python3.12* 混进同一条 apt 命令，避免一个无候选包中断全部依赖安装。
#    同时保留源码编译 Python 3.12 常用的 dev 包，便于用户补装解释器后重跑。
# -----------------------------------------------------------------------------
echo "==> [1/3] apt 安装基础工具链与可直接获取的依赖"
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends \
  ca-certificates git build-essential cmake ninja-build pkg-config patchelf \
  python3 python3-dev python3-pip python3-venv \
  libeigen3-dev libboost-all-dev liburdfdom-dev libssl-dev zlib1g-dev \
  libffi-dev libbz2-dev libreadline-dev libsqlite3-dev liblzma-dev \
  liboctomap-dev libassimp-dev libqhull-dev libconsole-bridge-dev

if ! command -v python3.12 >/dev/null 2>&1; then
  echo "ERROR: python3.12 未安装或不在 PATH。RISC-V wheel 需要 cp312；请先源码编译/安装 Python 3.12。" >&2
  exit 1
fi

PY312_VENV_SMOKE="$(mktemp -d)"
if ! python3.12 -m venv "$PY312_VENV_SMOKE" >/dev/null 2>&1; then
  rm -rf "$PY312_VENV_SMOKE"
  echo "ERROR: python3.12 无法创建 venv。请确认源码编译时启用了 ensurepip/venv 相关模块。" >&2
  exit 1
fi
rm -rf "$PY312_VENV_SMOKE"
echo "==> Python wheel 解释器就绪：$(python3.12 --version)"

# CMake 找我们自建前缀时也要能回链到系统包
export CMAKE_PREFIX_PATH="$PREFIX:${CMAKE_PREFIX_PATH:-}"
export PKG_CONFIG_PATH="$PREFIX/lib/pkgconfig:${PKG_CONFIG_PATH:-}"
export LD_LIBRARY_PATH="$PREFIX/lib:${LD_LIBRARY_PATH:-}"

mkdir -p "$SRC_DIR" "$PREFIX"

# -----------------------------------------------------------------------------
# 1.5 Boost.System 实体 stub（Bianbu 4.0 / Boost 1.90）
#     必须早于 pinocchio 的 CMake 配置阶段。
#
#     Boost 1.90 把 Boost.System header-only 化，不再装 libboost_system.so 实体。
#     但 pinocchioConfig.cmake 写死 SET(Boost_NO_BOOST_CMAKE ON)，强制走老式
#     module-mode FindBoost（只扫 .so 文件，不读 cmake-config），于是
#     find_package(Boost COMPONENTS system) 失败：Could NOT find Boost (missing: system)。
#     Boost.System 自 1.66 header-only，造一个空 stub .so 喂给 module-mode 即可，
#     运行期不缺符号。只在缺 libboost_system.so 且确为 1.90 时补。
# -----------------------------------------------------------------------------
BOOST_LIBDIR="/usr/lib/$(uname -m)-linux-gnu"
if [[ "$arch" == "riscv64" ]] && [[ ! -e "$BOOST_LIBDIR/libboost_system.so" ]] \
   && ls "$BOOST_LIBDIR"/libboost_filesystem.so.1.90.* >/dev/null 2>&1; then
  echo "==> [1.5/3] 补 Boost.System 实体 stub（Boost 1.90 header-only，无 libboost_system.so）"
  STUB_C="$(mktemp --suffix=.c)"
  printf '/* boost.system header-only since 1.66; empty stub for module-mode FindBoost on Boost 1.90 */\n' > "$STUB_C"
  cc -shared -fPIC -Wl,-soname,libboost_system.so.1.90.0 \
     -o "$BOOST_LIBDIR/libboost_system.so.1.90.0" "$STUB_C"
  ln -sf libboost_system.so.1.90.0 "$BOOST_LIBDIR/libboost_system.so"
  rm -f "$STUB_C"
  ldconfig
  echo "    已装 $BOOST_LIBDIR/libboost_system.so{,.1.90.0}"
else
  echo "==> [1.5/3] Boost.System stub 跳过（已有 libboost_system.so 或非 Boost 1.90 riscv64）"
fi

# -----------------------------------------------------------------------------
# 2. hpp-fcl 2.4.4（源码编 → $PREFIX），关掉自带 python 绑定与测试减负
#    产物 SONAME: libhpp-fcl.so（与 SDK 的 DT_NEEDED 对齐）
# -----------------------------------------------------------------------------
if [[ -f "$PREFIX/lib/libhpp-fcl.so" ]] || ls "$PREFIX"/lib/libhpp-fcl.so* >/dev/null 2>&1; then
  echo "==> [2/3] hpp-fcl 已存在于 $PREFIX，跳过"
else
  echo "==> [2/3] 源码编译 hpp-fcl $HPPFCL_TAG"
  rm -rf "$SRC_DIR/hpp-fcl"
  git clone --branch "$HPPFCL_TAG" --depth 1 --recursive \
    https://github.com/humanoid-path-planner/hpp-fcl "$SRC_DIR/hpp-fcl"
  cmake -S "$SRC_DIR/hpp-fcl" -B "$SRC_DIR/hpp-fcl/build" -G Ninja \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_INSTALL_PREFIX="$PREFIX" \
    -DCMAKE_PREFIX_PATH="$PREFIX" \
    -DBUILD_PYTHON_INTERFACE=OFF \
    -DBUILD_TESTING=OFF \
    -DHPP_FCL_HAS_QHULL=ON
  cmake --build "$SRC_DIR/hpp-fcl/build" -j "$JOBS"
  cmake --install "$SRC_DIR/hpp-fcl/build"
fi

# -----------------------------------------------------------------------------
# 3. pinocchio 3.1.0（源码编 → $PREFIX）
#    ★ BUILD_WITH_COLLISION_SUPPORT=ON 对应 C_API 里写死的 PINOCCHIO_WITH_HPP_FCL
#    产物 SONAME: libpinocchio_default.so.3.1.0 / libpinocchio_parsers.so.3.1.0
# -----------------------------------------------------------------------------
if ls "$PREFIX"/lib/libpinocchio_default.so* >/dev/null 2>&1; then
  echo "==> [3/3] pinocchio 已存在于 $PREFIX，跳过"
else
  echo "==> [3/3] 源码编译 pinocchio $PINOCCHIO_TAG（开启 collision/urdf 支持）"
  rm -rf "$SRC_DIR/pinocchio"
  git clone --branch "$PINOCCHIO_TAG" --depth 1 --recursive \
    https://github.com/stack-of-tasks/pinocchio "$SRC_DIR/pinocchio"
  cmake -S "$SRC_DIR/pinocchio" -B "$SRC_DIR/pinocchio/build" -G Ninja \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_INSTALL_PREFIX="$PREFIX" \
    -DCMAKE_PREFIX_PATH="$PREFIX" \
    -DBUILD_WITH_COLLISION_SUPPORT=ON \
    -DBUILD_WITH_URDF_SUPPORT=ON \
    -DBUILD_PYTHON_INTERFACE=OFF \
    -DBUILD_TESTING=OFF \
    -DBUILD_BENCHMARK=OFF
  cmake --build "$SRC_DIR/pinocchio/build" -j "$JOBS"
  cmake --install "$SRC_DIR/pinocchio/build"
fi

# -----------------------------------------------------------------------------
# 4. 自检：列出关键 SONAME
# -----------------------------------------------------------------------------
echo "==> 依赖安装完成。$PREFIX/lib 下关键库："
ls -1 "$PREFIX"/lib/libpinocchio_default.so* \
      "$PREFIX"/lib/libpinocchio_parsers.so* \
      "$PREFIX"/lib/libhpp-fcl.so* 2>/dev/null || {
  echo "ERROR: 关键库缺失，依赖安装未成功" >&2; exit 1; }

cat <<EOF

================================================================================
依赖已就位：$PREFIX

后续使用前建议在当前 shell 中设置：
  export LD_LIBRARY_PATH=$PREFIX/lib:\$LD_LIBRARY_PATH

Python:
  python3.12 -m venv .venv_oneroarm
  . .venv_oneroarm/bin/activate
  python -m pip install --no-deps ./python/wheels/linux-riscv64/oneroarm-*.whl
  python -c "import oneroarm; print('OK,', oneroarm.__file__)"

C/C++:
  编译链接随包 c/linux/linux-riscv64 或 c++/linux/linux-riscv64 下的 liboneroarm.so。
  运行前确保 LD_LIBRARY_PATH 包含 $PREFIX/lib。
================================================================================
EOF
