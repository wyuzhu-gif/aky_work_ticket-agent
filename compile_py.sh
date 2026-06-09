#!/bin/bash
# ============================================================
# 作业票智能审查系统 - Python 源码编译脚本
# 将 .py 编译为 .so 二进制文件，编译后自动删除源码
# 
# !!! 必须在目标服务器上运行（.so 是平台相关的）!!!
# !!! 此脚本会删除所有 .py 源码，不可逆 !!!
# ============================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
API_DIR="$SCRIPT_DIR/api"
VENV_DIR="$API_DIR/venv"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo_info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
echo_warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
echo_error() { echo -e "${RED}[ERROR]${NC} $1"; }

echo ""
echo "=========================================="
echo "  Python 源码编译工具 (.py → .so)"
echo "  编译后源码将被删除，此操作不可逆！"
echo "=========================================="
echo ""

# ---------- 1. 检查并安装依赖 ----------
if [ ! -d "$VENV_DIR" ]; then
    echo_info "正在创建 Python 虚拟环境..."
    python3 -m venv "$VENV_DIR"
    echo_info "正在安装运行时依赖..."
    "$VENV_DIR/bin/pip" install -r "$API_DIR/requirements.txt" -q \
        -i https://pypi.tuna.tsinghua.edu.cn/simple
fi

echo_info "正在安装 Cython..."
"$VENV_DIR/bin/pip" install cython -q \
    -i https://pypi.tuna.tsinghua.edu.cn/simple

# ---------- 2. 生成编译脚本 ----------
COMPILE_SCRIPT="$SCRIPT_DIR/_compile_worker.py"

cat > "$COMPILE_SCRIPT" << 'PYEOF'
"""Cython 批量编译：所有 .py → .so（含 __init__.py）"""
import os, sys, subprocess, glob

SCRIPT_DIR = os.environ['SCRIPT_DIR']
API_DIR = os.path.join(SCRIPT_DIR, 'api')
COMMON_DIR = os.path.join(SCRIPT_DIR, 'common')
VENV_PYTHON = os.path.join(API_DIR, 'venv', 'bin', 'python')

SKIP_DIRS = {'venv', 'venv_old_x86', '__pycache__', '_build', 'www', 'www_lite',
             '.git', 'node_modules', 'app'}

def collect_py(root_dir):
    """收集目录下所有 .py 文件"""
    files = []
    for dirpath, dirnames, filenames in os.walk(root_dir):
        dirnames[:] = [d for d in dirnames
                       if d not in SKIP_DIRS and not d.startswith('.')]
        for f in filenames:
            if f.endswith('.py'):
                files.append(os.path.join(dirpath, f))
    return files

def compile_dir(root_dir, name):
    """编译一个目录下的所有 .py"""
    py_files = collect_py(root_dir)
    if not py_files:
        print(f"  {name}/: 无 .py 文件，跳过")
        return 0

    print(f"  {name}/: {len(py_files)} 个 .py 文件待编译")

    # 生成 setup.py
    setup_path = os.path.join(root_dir, '_build_setup.py')
    with open(setup_path, 'w') as f:
        f.write('from setuptools import setup, Extension\n')
        f.write('from Cython.Build import cythonize\n\n')
        f.write('extensions = [\n')
        for py_path in py_files:
            rel = os.path.relpath(py_path, root_dir)
            mod_name = rel[:-3].replace(os.sep, '.')
            f.write(f'    Extension("{mod_name}", sources=["{rel}"]),\n')
        f.write(']\n\n')
        f.write('setup(\n')
        f.write('    name="compiled",\n')
        f.write('    ext_modules=cythonize(extensions,\n')
        f.write('        compiler_directives={\n')
        f.write('            "language_level": "3",\n')
        f.write('            "embedsignature": False,\n')
        f.write('            "emit_code_comments": False,\n')
        f.write('        },\n')
        f.write('    ),\n')
        f.write(')\n')

    # 运行编译
    result = subprocess.run(
        [VENV_PYTHON, setup_path, 'build_ext', '--inplace'],
        cwd=root_dir,
        capture_output=True, text=True, timeout=300,
    )

    # 清理临时 setup.py
    os.remove(setup_path)

    if result.returncode != 0:
        print(f"  编译出错！")
        print(result.stderr[-2000:])
        return -1

    # 统计 .so
    so_count = 0
    for dirpath, dirnames, filenames in os.walk(root_dir):
        if any(s in dirpath for s in SKIP_DIRS):
            continue
        for fn in filenames:
            if fn.endswith('.so') or fn.endswith('.pyd'):
                so_count += 1
                print(f"    ✓ {os.path.relpath(os.path.join(dirpath, fn), root_dir)}")

    return so_count

def main():
    total_so = 0

    for root_dir, name in [(API_DIR, 'api'), (COMMON_DIR, 'common')]:
        if not os.path.exists(root_dir):
            continue
        print(f"\n编译 {name}/ ...")
        n = compile_dir(root_dir, name)
        if n < 0:
            print("编译失败，终止")
            sys.exit(1)
        total_so += n
        print(f"  生成 {n} 个 .so 文件")

    print(f"\n总计生成 {total_so} 个 .so 文件")

    # 清理 .c 中间文件
    for root_dir in [API_DIR, COMMON_DIR]:
        for c_file in glob.glob(os.path.join(root_dir, '**', '*.c'), recursive=True):
            if '/venv/' not in c_file:
                os.remove(c_file)

if __name__ == '__main__':
    main()
PYEOF

# ---------- 3. 运行编译 ----------
echo_info "正在编译（可能需要 2-5 分钟）..."
export SCRIPT_DIR="$SCRIPT_DIR"
"$VENV_DIR/bin/python" "$COMPILE_SCRIPT"

# ---------- 4. 确认删除源码 ----------
echo ""
echo_warn "=========================================="
echo_warn "  即将删除所有 Python 源码 (.py)"
echo_warn "  编译后的 .so 文件将替代源码运行"
echo_warn "  此操作不可逆！"
echo_warn "=========================================="
echo ""
read -p "确认删除源码？输入 yes 继续: " confirm

if [ "$confirm" != "yes" ]; then
    echo_info "已取消删除。.so 已生成，可稍后手动删除 .py："
    echo "  find $API_DIR -name '*.py' -not -path '*/venv/*' -delete"
    echo "  find $SCRIPT_DIR/common -name '*.py' -delete"
    # 清理临时编译脚本
    rm -f "$COMPILE_SCRIPT"
    exit 0
fi

echo_info "正在删除 .py 源码..."

# 删除 api/ 下 .py（排除 venv）
find "$API_DIR" -name "*.py" \
    -not -path "*/venv/*" \
    -not -path "*/_build/*" \
    -not -path "*/www/*" \
    -delete 2>/dev/null || true

# 删除 common/ 下 .py
find "$SCRIPT_DIR/common" -name "*.py" -delete 2>/dev/null || true

# 清理 __pycache__ 和临时文件
find "$SCRIPT_DIR" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
rm -f "$COMPILE_SCRIPT"
rm -rf "$SCRIPT_DIR/_build"

# ---------- 5. 验证 ----------
echo ""
echo_info "验证编译产物："
py_count=$(find "$API_DIR" "$SCRIPT_DIR/common" -name "*.py" -not -path "*/venv/*" 2>/dev/null | wc -l | tr -d ' ')
so_count=$(find "$API_DIR" "$SCRIPT_DIR/common" -name "*.so" -not -path "*/venv/*" 2>/dev/null | wc -l | tr -d ' ')

echo_info "  剩余 .py 文件: $py_count"
echo_info "  编译 .so 文件: $so_count"

if [ "$py_count" -eq 0 ] && [ "$so_count" -gt 0 ]; then
    echo ""
    echo_info "✓ 编译成功！所有源码已转为 .so 二进制"
    echo_info "✓ 现在可以启动服务: ./start_lite.sh"
elif [ "$py_count" -gt 0 ]; then
    echo_warn "仍有 $py_count 个 .py 文件残留"
fi
