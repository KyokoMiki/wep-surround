#!/usr/bin/env python3
"""
WEP Surround - 智能安装脚本
自动检测显卡型号、网络镜像源、安装依赖
用法: python install.py [/dryrun]
"""
import argparse
import os
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

# =========================================================================
#  配置
# =========================================================================
PROJECT_DIR = Path(__file__).parent.resolve()
VENV_DIR = PROJECT_DIR / ".venv"

PIP_MIRRORS = {
    "pypi 官方": "https://pypi.org/simple/",
    "清华镜像": "https://pypi.tuna.tsinghua.edu.cn/simple/",
    "阿里云镜像": "https://mirrors.aliyun.com/pypi/simple/",
    "腾讯云镜像": "https://mirrors.cloud.tencent.com/pypi/simple/",
}

TRUSTED_HOSTS = [
    "pypi.org",
    "pypi.tuna.tsinghua.edu.cn",
    "mirrors.aliyun.com",
    "mirrors.cloud.tencent.com",
    "download.pytorch.org",
    "pytorch-extension.intel.com",
]

# NVIDIA 驱动版本 → CUDA 版本映射
CUDA_MAP = [
    (572, "cu128"),
    (560, "cu126"),
    (550, "cu124"),
    (535, "cu121"),
    (525, "cu118"),
    (512, "cu118"),
    (0,   "cu117"),
]

# AMD 显卡系列 → ROCm 版本映射
ROCM_MAP = [
    ("RX 9", "rocm7.2"),   # RX 9000 系列
    ("RX 7", "rocm6.3"),   # RX 7000 系列
    ("RX 6", "rocm6.1"),   # RX 6000 系列
    ("RX 5", "rocm5.7"),   # RX 5000 系列
]

HF_MIRRORS = {
    "huggingface 国际":  ("https://huggingface.co", ""),
    "hf-mirror 国内":    ("https://hf-mirror.com", "hf-mirror.com"),
    "modelscope 魔搭":   ("https://modelscope.cn",  "modelscope.cn"),
}


# =========================================================================
#  工具函数
# =========================================================================
def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, **kwargs)
    except Exception as e:
        print(f"  [!] 命令执行失败: {e}")
        result = subprocess.CompletedProcess(cmd, -1, "", str(e))
        return result


def check_url(url: str, timeout: int = 5) -> bool:
    try:
        urllib.request.urlopen(url, timeout=timeout)
        return True
    except Exception:
        return False


def check_cmd(cmd: str) -> bool:
    return shutil.which(cmd) is not None


# =========================================================================
#  阶段1: 环境检查
# =========================================================================
def check_python():
    print("\n[检查] Python 版本...", end=" ")
    v = sys.version_info
    if v.major < 3 or (v.major == 3 and v.minor < 10):
        print(f"[错误] 需要 Python 3.10+, 当前是 {v.major}.{v.minor}.{v.micro}")
        sys.exit(1)
    print(f"[通过] {v.major}.{v.minor}.{v.micro}")


def detect_network() -> str:
    """自动检测最快可用的 pip 镜像源"""
    print("\n[检查] 网络环境...")
    for name, url in PIP_MIRRORS.items():
        print(f"  测试 {name}...", end=" ")
        if check_url(url):
            print("[可用]")
            print(f"  [通过] 使用镜像源: {name}")
            return url
        print("[不可用]")
    print("[错误] 所有镜像源均不可用！请检查网络连接。")
    sys.exit(1)


def check_ffmpeg():
    print("\n[检查] FFmpeg...", end=" ")
    if check_cmd("ffmpeg"):
        print("[通过] 已安装")
    else:
        print("[警告] 未安装，部分音频处理可能失败")


def check_security():
    """检查 Windows Device Guard 状态"""
    print("\n[检查] Windows 安全策略...", end=" ")
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
            r"SYSTEM\CurrentControlSet\Control\DeviceGuard")
        val, _ = winreg.QueryValueEx(key, "EnableVirtualizationBasedSecurity")
        if val == 1:
            print("[警告] Device Guard 已启用")
            print("       可能阻止某些程序运行（findstr、nvidia-smi 等）")
            print("       Python 安装器会自动处理此问题\n")
        else:
            print("[通过] Device Guard 未启用")
    except Exception:
        print("[信息] Device Guard 状态未知")


# =========================================================================
#  阶段2: 显卡检测
# =========================================================================
def detect_gpu_registry() -> str | None:
    """方法1: 通过注册表读取显卡型号（Python 原生，不依赖外部程序）"""
    try:
        import winreg
        base = r"SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}"
        k = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, base)
        i = 0
        while True:
            try:
                sub = winreg.EnumKey(k, i)
                sk = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, base + "\\" + sub)
                v = winreg.QueryValueEx(sk, "DriverDesc")
                name = v[0].strip()
                # 跳过微软基础显示适配器
                if name and "Basic" not in name and "Basic Render" not in name:
                    return name
            except OSError:
                pass
            i += 1
    except Exception:
        return None


def detect_gpu_wmic() -> str | None:
    """方法2: 通过 wmic 检测（备选）"""
    try:
        out = subprocess.check_output(
            "wmic path win32_VideoController get name",
            shell=True, stderr=subprocess.DEVNULL, timeout=5
        ).decode("utf-8", errors="replace")
        for line in out.split("\n"):
            line = line.strip()
            if line and line != "Name":
                return line
    except Exception:
        return None


def detect_gpu_powershell() -> str | None:
    """方法3: 通过 PowerShell 检测（备选）"""
    try:
        out = subprocess.check_output(
            ['powershell', '-NoProfile', '-Command',
             '(Get-CimInstance Win32_VideoController | Select-Object -First 1).Name.Trim()'],
            stderr=subprocess.DEVNULL, timeout=10
        ).decode("utf-8", errors="replace").strip()
        return out if out else None
    except Exception:
        return None


def get_nvidia_driver_version() -> int | None:
    """获取 NVIDIA 驱动版本号"""
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader,nounits"],
            stderr=subprocess.DEVNULL, timeout=5
        ).decode("utf-8", errors="replace").strip()
        if out:
            return int(out.split(".")[0])
    except Exception:
        return None
    return None


def map_cuda_version(driver_major: int) -> str:
    """NVIDIA 驱动版本 → CUDA 版本"""
    for threshold, cuda in CUDA_MAP:
        if driver_major >= threshold:
            return cuda
    return "cu117"


def map_rocm_version(gpu_name: str) -> str:
    """AMD 显卡型号 → ROCm 版本"""
    for series, rocm in ROCM_MAP:
        if series in gpu_name.upper():
            return rocm
    return "rocm7.2"  # 不认识的就装最新版


def detect_gpu():
    """综合检测显卡：返回 (名称, 类型, torch索引地址)"""
    print("\n[检查] 显卡检测...")

    # 方法1: 注册表（最可靠，不依赖外部程序）
    gpu_name = detect_gpu_registry()
    source = "注册表"

    # 方法2: wmic
    if not gpu_name:
        gpu_name = detect_gpu_wmic()
        source = "wmic"

    # 方法3: PowerShell
    if not gpu_name:
        gpu_name = detect_gpu_powershell()
        source = "PowerShell"

    # 兜底: 手动输入
    if not gpu_name:
        print("  [!] 自动检测失败（可能被安全策略阻止）")
        user_input = input("  请输入显卡厂商 (NVIDIA/AMD/INTEL): ").strip().lower()
        if user_input == "nvidia":
            return "手动输入 NVIDIA", "NVIDIA", None
        elif user_input == "amd":
            return "手动输入 AMD", "AMD", None
        elif user_input == "intel":
            return "手动输入 Intel Arc", "INTEL", None
        else:
            print("[错误] 未指定有效显卡")
            sys.exit(1)

    print(f"  [通过] 检测到 ({source}): {gpu_name}")

    name_upper = gpu_name.upper()

    # NVIDIA
    if "NVIDIA" in name_upper:
        driver_ver = get_nvidia_driver_version()
        if driver_ver:
            cuda_ver = map_cuda_version(driver_ver)
            torch_url = f"https://download.pytorch.org/whl/{cuda_ver}"
            print(f"  [通过] NVIDIA 驱动版本 {driver_ver}")
            print(f"  [通过] 将安装 CUDA {cuda_ver} 版 PyTorch")
        else:
            torch_url = "https://download.pytorch.org/whl/cu121"
            print(f"  [警告] 无法读取驱动版本，默认使用 CUDA 12.1")
        return gpu_name, "NVIDIA", torch_url

    # AMD
    if "AMD" in name_upper:
        rocm_ver = map_rocm_version(gpu_name)
        torch_url = f"https://download.pytorch.org/whl/{rocm_ver}"
        rocm_num = rocm_ver.replace("rocm", "")
        print(f"  [通过] AMD {gpu_name}")
        print(f"  [通过] 将安装 ROCm {rocm_num} 版 PyTorch")
        return gpu_name, "AMD", torch_url

    # Intel Arc 独显
    if "ARC" in name_upper:
        print("  [通过] Intel Arc 独显")
        print("  [提示] Windows 原生 XPU 支持为实验性功能")
        print("         建议使用 WSL2 + Ubuntu 以获得完整 XPU 支持")
        print("         本机 Windows 将使用 CPU 版 PyTorch\n")
        return gpu_name, "INTEL", None

    # Intel 集成显卡（不支持）
    if "INTEL" in name_upper:
        print("[错误] Intel 集成显卡不支持")
        print("本项目需要独立显卡 (NVIDIA/AMD/Intel Arc)")
        sys.exit(1)

    # 未知显卡
    print(f"[错误] 未检测到支持的显卡: {gpu_name}")
    print("支持的显卡: NVIDIA GeForce RTX/GTX、AMD Radeon RX 5000+、Intel Arc")
    sys.exit(1)


# =========================================================================
#  阶段3: HuggingFace 镜像检测
# =========================================================================
def detect_hf_mirror() -> tuple[str, str | None]:
    """自动检测可用的 HuggingFace 镜像"""
    print("\n[检查] HuggingFace 镜像...")
    for name, (url, endpoint) in HF_MIRRORS.items():
        print(f"  测试 {name}...", end=" ")
        if check_url(url):
            print("[可用]")
            return url, endpoint
        print("[不可用]")
    print("[警告] 无可用镜像，模型下载可能失败")
    return "https://huggingface.co", None


# =========================================================================
#  阶段4: 安装
# =========================================================================
def setup_pip(pip_index: str):
    """配置 pip 索引源"""
    print("\n[1/5] 配置 pip...")
    for host in TRUSTED_HOSTS:
        run([sys.executable, "-m", "pip", "config", "set", "global.trusted-host", host])
    run([sys.executable, "-m", "pip", "config", "set", "global.index-url", pip_index])
    run([sys.executable, "-m", "pip", "config", "set", "global.extra-index-url",
         "https://download.pytorch.org/whl/cu121"])


def create_venv():
    """创建虚拟环境"""
    print("\n[2/5] 创建虚拟环境...")
    if VENV_DIR.exists():
        print("  [通过] 虚拟环境已存在")
    else:
        result = run([sys.executable, "-m", "venv", str(VENV_DIR)])
        if result.returncode != 0 or not VENV_DIR.exists():
            print(f"[错误] 创建虚拟环境失败:\n{result.stderr}")
            sys.exit(1)
        print("  [通过] 虚拟环境已创建")

    if sys.platform == "win32":
        venv_python = VENV_DIR / "Scripts" / "python.exe"
        venv_pip = VENV_DIR / "Scripts" / "pip.exe"
    else:
        venv_python = VENV_DIR / "bin" / "python"
        venv_pip = VENV_DIR / "bin" / "pip"
    return str(venv_python), str(venv_pip)


def upgrade_pip(venv_python: str):
    """升级 pip"""
    print("\n[3/5] 升级 pip...")
    run([venv_python, "-m", "pip", "install", "--upgrade", "pip"])
    print("  [通过] pip 已升级")


def install_core(venv_python: str, project_dir: str):
    """安装核心依赖"""
    print("\n[4/5] 安装 WEP 核心依赖...")
    print("  可能需要 5-15 分钟，请耐心等待...")
    result = run([venv_python, "-m", "pip", "install", "-e", project_dir],
                 cwd=project_dir)
    if result.returncode != 0:
        print(f"[错误] pip 安装失败:\n{result.stderr}")
        sys.exit(1)
    print("  [通过] 核心依赖安装完成")


def install_torch_backend(venv_python: str, gpu_type: str, torch_index: str | None):
    """根据显卡类型安装对应 PyTorch"""
    print("\n[5/5] 安装显卡对应 PyTorch...")

    if gpu_type == "NVIDIA" and torch_index:
        print(f"  安装 CUDA PyTorch: {torch_index}")
        result = run([
            venv_python, "-m", "pip", "install", "--upgrade",
            "torch", "torchaudio", "--index-url", torch_index
        ])
        if result.returncode == 0:
            print("  [通过] CUDA PyTorch 安装完成")
        else:
            print("  [警告] CUDA 安装失败，降级到 CPU 版")
            install_cpu_torch(venv_python)

    elif gpu_type == "AMD" and torch_index:
        print(f"  安装 ROCm PyTorch: {torch_index}")
        result = run([
            venv_python, "-m", "pip", "install", "--upgrade",
            "torch", "torchaudio", "--index-url", torch_index
        ])
        if result.returncode == 0:
            print("  [通过] ROCm PyTorch 安装完成")
        else:
            print("  [警告] ROCm 安装失败，降级到 CPU 版")
            install_cpu_torch(venv_python)

    elif gpu_type == "INTEL":
        xpu_index = ("https://pytorch-extension.intel.com/release-whl/stable/xpu/us/"
                     if check_url("https://pytorch-extension.intel.com/")
                     else "https://pytorch-extension.intel.com/release-whl/stable/xpu/cn/")
        print(f"  安装 Intel XPU PyTorch: {xpu_index}")
        result = run([
            venv_python, "-m", "pip", "install", "--upgrade",
            "torch", "torchaudio", "--extra-index-url", xpu_index
        ])
        if result.returncode == 0:
            print("  [通过] Intel XPU PyTorch 安装完成")
        else:
            print("  [警告] XPU 安装失败，降级到 CPU 版")
            install_cpu_torch(venv_python)
    else:
        install_cpu_torch(venv_python)


def install_cpu_torch(venv_python: str):
    """安装 CPU 版 PyTorch"""
    print("  安装 CPU 版 PyTorch...")
    run([venv_python, "-m", "pip", "install", "--upgrade", "torch", "torchaudio"])
    print("  [通过] CPU PyTorch 安装完成")


def download_models(venv_python: str, hf_endpoint: str | None):
    """下载 Demucs 模型"""
    print("\n[额外] 下载 Demucs 模型...")
    env = os.environ.copy()
    if hf_endpoint:
        env["HF_ENDPOINT"] = hf_endpoint

    result = run([venv_python, "-c", """
import torch
try:
    from demucs import pretrained
    for model_name in ['htdemucs', 'htdemucs_ft', 'hdemucs_mmi']:
        print(f'  下载 {model_name}...')
        pretrained.get_model(model_name)
        print(f'  [通过] {model_name} 下载完成')
except Exception as e:
    print(f'  [警告] 模型下载失败: {e}')
    print('  模型将在首次使用时自动下载')
"""], env=env)

    if result.returncode == 0:
        print("  [通过] 模型就绪")
    else:
        print("  [警告] 模型将在首次使用时下载")


# =========================================================================
#  主流程
# =========================================================================
def print_header(dry_run: bool = False):
    print("=" * 45)
    print("   WEP Surround - 智能安装脚本")
    print("=" * 45)
    if dry_run:
        print("   *** 调试模式 - 不会对系统做任何更改 ***")
    print()


def print_summary(gpu_name: str, gpu_type: str, torch_index: str | None, pip_mirror: str):
    print()
    print("=" * 45)
    print("   调试完成 - 环境摘要")
    print("=" * 45)
    print()
    print(" 环境检查:")
    print(f"   [+] Python: {sys.version.split()[0]}")
    print(f"   [+] 显卡: {gpu_name} ({gpu_type})")
    if torch_index:
        print(f"   [+] PyTorch 后端: {torch_index}")
    print(f"   [+] pip 镜像: {pip_mirror}")
    print(f"   [+] FFmpeg: {'已安装' if check_cmd('ffmpeg') else '未找到'}")
    print()

    if gpu_type == "AMD":
        print(" 提示: Windows 上使用 ROCm 需要安装 AMD GPU 驱动")
        print("       参考: https://rocm.docs.amd.com/en/latest/deploy/windows/quick_start.html")
    elif gpu_type == "NVIDIA":
        print(" 提示: CUDA 工具包将从驱动版本自动检测")
    print()
    print(" 系统环境就绪，可以开始安装。")
    print(" 不带参数运行开始安装:")
    print("   python install.py")
    print()


def install(hf_endpoint: str | None, pip_mirror: str):
    """完整安装流程"""
    setup_pip(pip_mirror)

    venv_python, venv_pip = create_venv()

    upgrade_pip(venv_python)

    # 将 pip 配置复制到虚拟环境
    for host in TRUSTED_HOSTS:
        run([venv_pip, "config", "set", "global.trusted-host", host])
    run([venv_pip, "config", "set", "global.index-url", pip_mirror])

    install_core(venv_python, str(PROJECT_DIR))

    # 先安装 CPU PyTorch，再覆盖安装对应显卡的版本
    install_cpu_torch(venv_python)
    install_torch_backend(venv_python, GPU_TYPE, TORCH_INDEX)

    download_models(venv_python, hf_endpoint)

    print()
    print("=" * 45)
    print("   安装完成！")
    print("=" * 45)
    print()
    print(" 启动 WebUI:")
    print(f"   {PROJECT_DIR}\\一键环绕声.bat")
    print()
    input(" 按 Enter 键退出...")


def main():
    # 转换 /dryrun 为 --dryrun（兼容 batch 传参风格）
    sys.argv = ["--dryrun" if a in ("/dryrun", "--dryrun") else a for a in sys.argv]
    parser = argparse.ArgumentParser(description="WEP Surround 智能安装脚本")
    parser.add_argument("--dryrun", "-n", action="store_true", help="仅调试，不安装")
    args = parser.parse_args()

    dry_run = args.dryrun

    print_header(dry_run)

    # 阶段1: 环境
    check_python()
    pip_mirror = detect_network()
    check_ffmpeg()
    check_security()

    # 阶段2: 显卡
    global GPU_TYPE, TORCH_INDEX
    gpu_name, GPU_TYPE, TORCH_INDEX = detect_gpu()

    # 阶段3: HF 镜像
    hf_url, hf_endpoint = detect_hf_mirror()

    # 调试或安装
    if dry_run:
        print_summary(gpu_name, GPU_TYPE, TORCH_INDEX, pip_mirror)
    else:
        install(hf_endpoint, pip_mirror)


if __name__ == "__main__":
    GPU_TYPE = None
    TORCH_INDEX = None
    main()