# WEP Surround — AI 环绕声智能上混系统

立体声音频 → AI 音源分离 → 5.1/7.1 环绕声上混工作流

> **目标**：打开浏览器 → 上传音频 → 选参数 → 一键生成 5.1/7.1 环绕声

WEP Surround 是一个基于深度学习的环绕声上混工具，利用 Demucs AI 模型将普通立体声音频（MP3/WAV/FLAC）自动分离为人声、贝斯、鼓、乐器 4 个音轨（stems），再通过智能路由算法重映射到 5.1 或 7.1 多声道布局，输出车机/家庭影院兼容的环绕声文件。

### 适用场景

- **车载音响升级**：将普通立体声音乐转为 5.1 环绕声，MIB2+ 车机 U 盘直插播放
- **家庭影院**：为电影配乐 / MV 生成 7.1 环绕声，发挥多声道音响系统潜力
- **音乐制作**：快速生成环绕声混音参考，辅助沉浸式音频创作

### 核心能力

- **AI 音源分离**：Demucs `htdemucs_ft` 模型，4 stems 并行分离，支持 FP16 混合精度加速
- **智能上混**：4 stems → FL/FR/FC/LFE/Ls/Rs(+SL/SR) 多声道，多种预设算法
- **多格式输出**：WAV/PCM（24-bit 默认）、FLAC 无损、AAC/m4a
- **一键操作**：Gradio WebUI，上传 → 选参数 → 开始，实时进度 + ETA 倒计时

### 性能参考（RX 9070 XT, FP16）

| 音频时长 | 总计耗时 |
|----------|----------|
| 3 分钟 | ~17 秒 |
| 60 分钟 | ~4 分 20 秒 |

---

## 功能

- **AI 音源分离**: 基于 Demucs 深度学习模型，自动分离人声、贝斯、鼓、其他（4 stems）
- **环绕声上混**: 4 stems → 5.1/7.1 多声道输出
- **多种预设**: Music（音乐）/ Movie（电影）/ Anime（动漫）/ PLIIx（杜比模式）
- **响度归一化**: EBU R128 标准（-14 LUFS）
- **Web UI**: Gradio 可视化界面，实时日志 + 百分比进度 + ETA 倒计时
- **CLI 模式**: 命令行一键处理，支持批量
- **MIB2+ 车机兼容**: 自动生成 M3U 播放列表，U 盘直插车载音响

---

## 环境要求

- **Python 3.10+**
- **独立显卡**（必须）: NVIDIA RTX/GTX 系列、AMD Radeon RX 系列 或 Intel Arc 系列
- **系统**: Windows 10/11, Linux, macOS
- **ffmpeg**（可选，部分功能需要）

---

## 快速安装

**前提条件**：必需先安装 [Python 3.10+](https://www.python.org/downloads/)（安装时勾选 "Add Python to PATH"）

### Windows 安装

```bash
# 完整下载该项目并解压
# 前提：已安装 Python 3.10+（安装时勾选 "Add Python to PATH"）
# 安装脚本（自动检测 GPU 并安装对应版本）
# 安装命令：python install.py
```

安装脚本自动完成（基于 Python，绕过 Device Guard 安全策略限制）：
- 自动检测 NVIDIA / AMD / Intel Arc 显卡型号（Python 直接读取注册表）
- 根据显卡型号自动匹配对应 CUDA / ROCm / XPU 版 PyTorch
- 自动选择最快的 pip 镜像源（PyPI/清华/阿里云/腾讯云）
- 自动选择最快的模型下载源（hf-mirror/魔搭/HuggingFace）
- 创建虚拟环境 `vep_venv`
- 安装完整版所有依赖（demucs, gradio, librosa, MSST 模型等）
- 预下载 Demucs AI 模型

### 调试模式

```bash
# 检查环境，不安装任何东西（安全验证用）
python install.py --dryrun
```

调试模式会检测以下内容：
- Python 版本、网络镜像、FFmpeg、Windows 安全策略
- 显卡型号和对应 PyTorch 版本
- HuggingFace 模型镜像
- 输出环境摘要，确认无误后再正式安装

### Linux / macOS

```bash
# 前提：已安装 Python 3.10+
chmod +x install.sh
./install.sh

# 手动安装
git clone https://gitcode.com/Mark007700/wep-surround.git
cd wep-surround
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install .             # 基础版
pip install .[cuda]       # NVIDIA GPU 版
pip install .[rocm]       # AMD ROCm 版
pip install .[full]       # 完整版（含 MSST 所有模型）
```

---

## 使用方法

### WebUI 模式（推荐）

```bash
# Windows: 双击启动
一键环绕声.bat

# 或命令行
wep-webui
# 或
python wep_webui.py
```

启动后浏览器打开 http://127.0.0.1:7860

**操作步骤**：
1. 上传音频（MP3/WAV/FLAC，支持拖放）
2. 选择 AI 模型（`htdemucs_ft` 高质量 / `htdemucs` 快速）
3. 选择预设（Music / Movie / Anime / PLIIx）
4. 选择采样率（44.1k / **48k 推荐** / 96k）
5. 选择位深（16 / **24 推荐** / 32-float）
6. 选择输出格式（FLAC / **WAV/PCM** / AAC/m4a）
7. 选择声道布局（**7.1** / 5.1 / 立体声）
8. 点击「🚀 开始制作」
9. 实时查看日志、进度百分比和 ETA 倒计时

**AAC 码率选项**（仅 AAC 格式时显示）：
128k / 256k / 320k / **512k 推荐** / 768k / 1024k

### 命令行

```bash
# 基本用法
wep-cli "歌曲.mp3"

# 指定预设和声道
wep-cli "歌曲.flac" --preset Movie --layout 7.1

# 跳过 AI 分离（使用已有 stems）
wep-cli "歌曲.wav" --skip-separate --stems-from ./separated/htdemucs/MyTrack
```

### Python API

```python
from oneclick_WEP import run_pipeline

run_pipeline(
    input_file="歌曲.mp3",
    preset="Music",
    layout="5.1",
)
```

---

## 配置

编辑 `wep_config.json`：

```json
{
  "model": "htdemucs",
  "preset": "Music",
  "sample_rate": "48000",
  "bit_depth": "24",
  "output_format": "flac",
  "channel_config": "5.1",
  "aac_bitrate": "512k",
  "precision": "fp16",
  "lfe_freq": "80",
  "loudnorm": "-14"
}
```

---

## 预设参数详解

| 预设 | centre_db | decorr_l | decorr_r | 适用场景 |
|------|-----------|----------|----------|---------|
| **Music** | +1 | 15ms | 17ms | 纯音乐，环绕较宽 |
| **Movie** | +2 | 10ms | 12ms | 电影配乐，对话清晰 |
| **Anime** | +3 | 12ms | 14ms | 动漫 BGM，人声突出 |
| **PLIIx** | +1 | 20ms | 23ms | 通用，环绕极宽 |

> centre_db：中置增益偏移（Music=1.3x、Movie=1.4x、Anime=1.5x、PLIIx=1.3x）

---

## 关键技术细节

### Demucs 参数

```
模型：htdemucs_ft（训练最大 segment=7.8s）
--segment 7       ← 整数，≤7.8，8 会报错 FATAL
--overlap 0.25    ← 平衡质量/速度
-j 4              ← 4 个 stem 并行处理
--float16         ← FP16 精度（GPU 加速约 2-3x）
-d cuda           ← GPU（AMD ROCm / NVIDIA CUDA 均支持）
```

### 预重采样优化（v1.3.0 新增）

- **问题**：输入 192kHz 音频时，Demucs 以全采样率运行，GPU 算力浪费 ~4x
- **修复**：Stage 1 前用 `ffprobe` 检测采样率，若 ≠ 目标则先用 ffmpeg 重采样（CPU 快速）
- **效果**：56 分钟 @192kHz 从 ~15 分钟降至 ~3.5 分钟（预重采样 + FP16）

### 输出采样率对齐

- 每个 ffmpeg 命令都显式传入 `-ar <sr>`，确保分轨上混和最终输出采样率一致

---

## 性能参考（FP16 GPU 模式 显卡为AMD 9070XT）

| 音频时长 | 分离耗时 | 上混+编码 | 总计 |
|----------|----------|----------|------|
| 3 分钟 | ~12秒 | ~5秒 | ~17秒 |
| 5 分钟 | ~20秒 | ~8秒 | ~28秒 |
| 30 分钟 | ~2分钟 | ~15秒 | ~2分15秒 |
| 60 分钟 | ~4分钟 | ~20秒 | ~4分20秒 |
| 90 分钟 | ~6分钟 | ~25秒 | ~6分25秒 |

> 实测系数：时长 × 0.066（FP16），上混+编码约 15-30 秒

---

## MIB2+ 车机兼容

### 自动生成文件

- WAV 5.1/7.1 输出时自动生成同名 `.m3u` 文件（与 WAV 同目录）
- MIB2+ 车机：**有 M3U 才认 5.1 PCM**，否则强制 6→2 下混成双声道
- 同时维护 `output/5.1_playlist.m3u` 总播放列表（去重追加）

### U 盘拷贝详细步骤

1. **格式化为 NTFS 或 exFAT**（FAT32 单文件限 4GB，5.1 WAV 通常 3-5GB）
2. **拷贝文件**：把 `output/` 下的 `.5.1.wav` / `.5.1.m3u` / `.7.1.wav` / `.7.1.m3u` 全部拷贝到 U 盘**根目录或同一文件夹**
3. **必须 WAV + M3U 配对**：`曲目.5.1.wav` 和 `曲目.5.1.m3u` 必须在同一目录
4. **M3U 内容**：第一行 `#EXTM3U`，第二行文件名（如 `曲目.5.1.wav`）
5. **编码要求**：必须 WAV/PCM 5.1 声道（6ch），不要 FLAC 或 AAC（车机不认）
6. **采样率**：推荐 48kHz（车机标准），44.1kHz 也能播但少数车型不支持
7. **插入车机**：USB 端口 → 等待扫描 → MIB2+ 自动识别 5.1 环绕输出

### 常见失败排查

| 现象 | 原因 | 解决 |
|------|------|------|
| 车机只放双声道 | 缺少同名 `.m3u` | 重新拷贝 M3U 到同目录 |
| 车机提示格式不支持 | FAT32 或 FLAC | 改为 NTFS/exFAT + WAV 格式 |
| 播放卡顿/杂音 | 采样率非 48kHz | 输出采样率改为 48000 |
| 只有前 2 声道有声音 | M3U 内容错误或文件配对 | 检查 M3U 第二行文件名是否与 WAV 一致 |

---

## 常见问题

### 安装问题

| 问题 | 原因 | 解决 |
|------|------|------|
| `python install.py` 提示"未检测到 Python" | 未安装 Python 或未添加 PATH | 安装 Python 时勾选 "Add Python to PATH"，重启命令行 |
| 安装脚本运行后闪退 / `findstr' 不是内部或外部命令` | Windows Device Guard 阻止命令执行 | Python 安装器会自动通过注册表检测，不受安全策略影响 |
| GPU 检测失败/未检测到显卡 | Device Guard 阻止 wmic/nvidia-smi | Python 安装器会自动通过注册表检测，如仍失败可手动输入显卡型号 |
| pip 下载依赖超时/极慢 | 网络问题 | 换清华源：`python -m pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple` |
| `pip install .[cuda]` 后仍用 CPU | PyTorch 未正确安装 CUDA 版 | 先 `pip uninstall torch torchaudio`，再 `pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu121` |
| `pip install .[rocm]` 失败 | ROCm 未安装或版本不匹配 | 先安装 ROCm，参见 AMD 官方文档 |
| 缺少 `libsndfile` (soundfile 报错) | Windows 缺少 C 库 | `pip install soundfile` 会自动下载，或手动下载 https://github.com/libsndfile/libsndfile/releases |
| 缺少 `ffmpeg` | 未安装 ffmpeg | `winget install ffmpeg` 或从 https://ffmpeg.org/download.html 下载 |

### 运行问题

| 问题 | 原因 | 解决 |
|------|------|------|
| `ModuleNotFoundError: No module named 'demucs'` | 未激活虚拟环境 | 双击 `一键环绕声.bat`（自动激活），或手动 `call vep_venv\Scripts\activate.bat` |
| WebUI 启动后浏览器打不开 | 端口被占用或防火墙拦截 | 检查 http://127.0.0.1:7860 是否可访问；关闭防火墙或换端口 |
| 分离后 WebUI 卡死/无响应 | Demucs 模型未下载完 | 首次使用会自动下载模型（~2GB），请耐心等待；检查网络连接 |
| 编码阶段长时间无反馈 | 正常现象，ffmpeg 编码需要时间 | 查看日志中的 ETA 倒计时，不要在窗口中点击 |
| `PermissionError: Permission denied` | Gradio 文件锁问题 | 已修复，确保使用最新版本 |
| C盘空间急剧减少 | Gradio 临时文件未清理 | 已修复，程序退出时自动清理；也可手动删除 `%TEMP%\gradio\` |
| GPU 利用率极低（<10%） | Demucs segment 参数限制 | 正常现象，`htdemucs_ft` 最大 segment 为 7.8s，无法进一步提高 GPU 占用 |

### 输出问题

| 问题 | 原因 | 解决 |
|------|------|------|
| 输出文件比输入还小 | 编码格式压缩（FLAC/AAC） | 正常现象，FLAC 压缩率约 50%，AAC 按码率压缩 |
| 输出是双声道不是 5.1 | 未勾选 5.1/7.1 声道布局 | WebUI 中确保声道布局选择 5.1 或 7.1 |
| 车机只播放双声道 | 缺少 M3U 播放列表 | WAV 输出会自动生成同名 .m3u，确保两者在同一目录 |
| 输出采样率不对 | 未设置目标采样率 | WebUI 中采样率选择 48000（推荐） |

### 性能问题

| 问题 | 原因 | 解决 |
|------|------|------|
| 处理速度太慢 | CPU 模式或 FP32 | 启用 GPU + FP16 模式（AMD/NVIDIA 均支持） |
| AMD 显卡利用率低 | ROCm 优化不足 | 正常现象，使用 FP16 可提升 2-3x 速度 |
| 长音频处理时间过长 | Demucs 推理是 GPU 密集型 | 参考性能表：60 分钟音频约需 4 分钟（FP16 AMD 9070XT GPU） |

---

## 已知问题

1. **AMD ROCm 性能**：RX 9070 XT FP32 实测 ~1.5 TFLOPS（理论 22 TFLOPS），PyTorch 2.9+ROCm 7.2 在 gfx1201 上优化不足，功能正常但跑不满显卡。建议使用 FP16 模式
2. **Demucs segment 限制**：`htdemucs_ft` 训练最大 7.8s，`--segment` 整数上限为 7，无法通过增大 segment 进一步加速
3. **EBU R128 响度归一化**：CPU 运算，2.6 分钟音频约 5 秒，长音频需注意

---

## 项目结构

```
├── wep_webui.py              # Web UI 入口
├── oneclick_WEP.py           # CLI 一键脚本
── simple_upmix_51.py        # 简化上混脚本
├── oneclick_51.py            # 5.1 专用脚本
├── MSST-WebUI/               # 子项目：MSST 训练 WebUI
── install.py                # Python 智能安装脚本（GPU 检测、镜像检测、依赖安装）
├── install.sh                # Linux/macOS 一键安装脚本
├── 一键环绕声.bat            # 快捷启动（自动激活虚拟环境）
├── pyproject.toml            # pip 包配置
├── wep_config.json           # 默认配置
├── CHANGELOG.md              # 更新日志
└── output/                   # 环绕声输出目录
```

---

## 更新日志

详见 [CHANGELOG.md](CHANGELOG.md)

---

## 使用说明

详细操作指南、参数说明、车机兼容等内容，详见 [环绕声流水线.md](环绕声流水线.md)

---

## 许可证

MIT
