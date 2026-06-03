# WEP WebUI 更新日志

## v1.7.0 — 2026-06-04（Python 智能安装器）

### 🎉 新增功能

#### Python 智能安装器（替代 batch 安装脚本）
- **全新 `install.py`**：Python 纯代码安装脚本，彻底解决 Windows Device Guard 安全策略限制
- **GPU 自动检测升级**：Python `winreg` 直接读取注册表获取显卡型号（绕过 Device Guard 对 wmic/nvidia-smi 的阻止）
- **显卡支持扩展**：NVIDIA + AMD + **Intel Arc** 全支持
- **智能版本映射**：
  - NVIDIA 驱动 → CUDA 版本（572→cu128、560→cu126、550→cu124、535→cu121 等）
  - AMD 系列 → ROCm 版本（RX 9000→rocm7.2、RX 7000→rocm6.3、RX 6000→rocm6.1、RX 5000→rocm5.7）
  - Intel Arc → XPU 版 PyTorch（Windows 实验性支持，自动降级 CPU）
- **调试模式**：`python install.py --dryrun`，检查环境不安装

#### 安装器流程（6 层 GPU 检测兜底）
1. Python winreg 注册表（最可靠，不依赖外部程序）
2. reg query cmd 内建
3. PowerShell
4. wmic
5. Python wmic 子进程
6. 手动输入（兜底）

#### 全中文界面
- `install.py` 全部输出中文（环境检查、网络镜像、显卡检测、安装进度）

### 🔧 移除
- 移除 `install.bat`（因 Device Guard 限制，batch 无法可靠运行 findstr/wmic/external 工具）

---

## v1.6.1 — 2026-06-03（Gradio 临时文件自动清理）

### 🔧 问题修复

#### 每次制作完 Gradio 临时文件不释放（C盘被吃光）
- **根因**：Gradio 上传的文件存在 `%TEMP%\gradio\` 里，从不清理
- **修复**：
  - **制作完成后**：`on_run` 结束时自动删除本次上传的 Gradio 临时文件
  - **程序退出时**：`atexit.register` 注册清理钩子，关闭 WebUI 时彻底清空 `%TEMP%\gradio\`

---

## v1.6.0 — 2026-06-03（实时进度 + ETA 修复 + 文件锁修复）

### 🔧 问题修复

#### 日志无百分比进度 + 无 ETA
- **根因**：`progress()` 调用被 `show_progress="hidden"` 隐藏，日志框完全看不到进度；`log()` 只带时间戳不带阶段信息
- **修复**：
  - `PipelineState` 新增 `current_progress` / `stage_desc` / `total_est_seconds` 属性
  - 新增 `state.progress(fraction, desc)` 方法，每次调用自动推送 `[XX.X%] 阶段描述 + ETA` 到日志
  - 所有 `progress()` 调用配对添加 `state.progress()`，日志实时显示百分比

#### ETA 预估完全不准（线性外推 vs 实测）
- **根因**：`elapsed / fraction` 线性外推完全不适合非线性的 pipeline（AI 推理占 80% 时间）
- **实测数据**：
  | 音频时长 | 实际耗时 | 系数 |
  |---------|---------|------|
  | 72.8 分钟 | 4分50秒 | 0.066 |
  | 66.2 分钟 | 4分15秒 | 0.064 |
  | 98.3 分钟 | 6分22秒 | 0.065 |
- **修复**：`total_est = duration * 0.066`（实测系数），ETA = `total_est - elapsed`

#### 编码阶段 4 分钟无反馈（看起来像卡死）
- **根因**：`state.progress()` 只在阶段切换时调用，85%→100% 编码阶段无任何中间更新
- **修复**：
  - `PipelineState` 新增 `get_eta_line()` 方法，返回当前 ETA 行（不追加到日志历史）
  - `run_pipeline` 接收 `_state_ref` 参数，主线程通过共享引用读取 state
  - 轮询循环每 10 秒刷一次倒计时更新，用户能看到秒数递减

#### 拷贝文件随机 UUID 丢失原文件名
- **修复**：`_copied_input = TMP_DIR / f"{safe_name}{ext}"`，保留原文件名

#### Gradio 文件锁（PermissionError: [Errno 13]）
- **根因**：Gradio ASGI 持有上传文件锁，`allowed_paths` 未包含 `%TEMP%\gradio\`
- **修复**：
  - `allowed_paths` 加入 `tempfile.gettempdir()`（`C:\Users\tsj18\AppData\Local\Temp`）
  - `run_pipeline` 自动把上传文件拷贝到 `_wep_tmp/` 本地目录，绕过文件锁
  - `PermissionError` 时延迟 2 秒重试
  - `finally` 块清理拷贝的临时文件

#### `name 'time' is not defined`
- **修复**：顶部 `import time`

### 📊 日志输出效果（v1.6.0 改进后）
```
[21:30:42] 📁 输入：XXXX.mp3
[21:30:42] 🤖 模型：htdemucs | 🎚️ 预设：🎵 音乐模式 | ⚡ FP16 加速
[21:30:42] 📊 输出：WAV/PCM @ 48000Hz/24bit | 🔊 声道：5.1
[21:30:42] [  5.0%] 🔍 检测输入采样率…
[21:30:42] [  5.0%] 🔍 检测输入采样率… →   输入采样率：44100 Hz
[21:30:42] [ 10.0%] 🎚️ AI 分离中…
[21:30:43] [ 10.0%] 🎚️ AI 分离中… →   音频时长：98.3 分钟，预计：6分29秒
[21:30:43] [ 10.0%] 🎚️ AI 分离中… →   Demucs: FP16 加速 | segment=7 overlap=0.25 j=4
[21:30:43] [ 12.0%] 🎚️ 加载模型…  预计 6分27秒后完成
[21:30:44] [ 15.0%] 🎚️ 加载音频…  预计 6分27秒后完成
[21:30:48] [ 18.0%] 🎚️ AI 推理中…  预计 6分22秒后完成
[21:32:55] [ 45.0%] 🎚️ 保存分轨…  预计 4分16秒后完成
[21:33:07] [ 45.0%] 🎚️ 保存分轨… →   ✓ AI 分离完成（FP16 加速）
[21:33:07] [ 50.0%] 🔊 环绕声上混…  预计 4分4秒后完成
[21:33:09] [ 50.0%] 🔊 环绕声上混… →   ✓ 通道 FC 完成（1/6）
[21:33:09] [ 55.8%] 🔊 上混 1/6 通道…  预计 4分2秒后完成
[21:33:09] [ 55.8%] 🔊 上混 1/6 通道… →   ✓ 通道 Rs 完成（2/6）
[21:33:09] [ 61.7%] 🔊 上混 2/6 通道…  预计 4分1秒后完成
[21:33:09] [ 61.7%] 🔊 上混 2/6 通道… →   ✓ 通道 Ls 完成（3/6）
[21:33:09] [ 67.5%] 🔊 上混 3/6 通道…  预计 4分1秒后完成
[21:33:10] [ 67.5%] 🔊 上混 3/6 通道… →   ✓ 通道 FR 完成（4/6）
[21:33:10] [ 73.3%] 🔊 上混 4/6 通道…  预计 4分1秒后完成
[21:33:10] [ 73.3%] 🔊 上混 4/6 通道… →   ✓ 通道 FL 完成（5/6）
[21:33:10] [ 79.2%] 🔊 上混 5/6 通道…  预计 4分1秒后完成
[21:33:11] [ 79.2%] 🔊 上混 5/6 通道… →   ✓ 通道 LFE 完成（6/6）
[21:33:11] [ 85.0%] 🔊 上混 6/6 通道…  预计 4分0秒后完成  ← 每10秒倒计时刷新
[21:33:11] [ 85.0%] 🔊 上混 6/6 通道… →   ✓ 上混完成（6 通道并行）
[21:33:11] [ 85.0%] 📀 编码输出…  预计 4分0秒后完成
[21:33:21] [ 85.0%] 📀 编码输出…  预计 3分50秒后完成  ← 倒计时在走
[21:33:31] [ 85.0%] 📀 编码输出…  预计 3分40秒后完成
...
[21:37:04] [100.0%] ✅ 全部完成！  预计 6秒后完成
[21:37:04] [100.0%] ✅ 全部完成！ → ✅ 完成！4842.6 MB + M3U + 播放列表(596B)
```

### 📁 代码改动

#### PipelineState（[第118-185行](file:///d:/UVR5-of-MSST-WebUI+SurroundUpmix/wep_webui.py#L118-L185)）
- 新增 `_format_seconds()` 函数
- `PipelineState` 新增 `total_est_seconds`、`_calc_eta()`、`get_eta_line()`、`progress()`
- `log()` 自动附加 `[进度%] 阶段 → 消息` 前缀

#### run_pipeline（[第190-448行](file:///d:/UVR5-of-MSST-WebUI+SurroundUpmix/wep_webui.py#L190-L448)）
- 新增 `_state_ref` 参数
- 已有分轨路径提前设置 `safe_name`
- 上传文件自动拷贝到 `_wep_tmp/{safe_name}.{ext}`，绕过 Gradio 文件锁
- ETA 基于 `duration * 0.066` 实测系数
- 上混逐通道推送完成日志（`N/6 通道…`）
- `finally` 块清理拷贝的临时文件

#### on_run（[第562-635行](file:///d:/UVR5-of-MSST-WebUI+SurroundUpmix/wep_webui.py#L562-L635)）
- `pipeline_state_ref` 共享引用，主线程读取 ETA
- 每 10 秒刷一次倒计时更新

#### launch（[第628-631行](file:///d:/UVR5-of-MSST-WebUI+SurroundUpmix/wep_webui.py#L628-L631)）
- `allowed_paths` 加入 `tempfile.gettempdir()`

---

## v1.5.0 — 2026-06-03

### 🎉 新增功能

#### 📂 分轨管理面板（独立功能，不依赖 AI 分离）
- **新增「📂 分轨管理」折叠面板**（默认收起）
- **扫描 `separated/` 目录**：自动列出所有模型下的分轨项目，显示文件名 + 模型名 + 占用空间
- **加载已有分轨**：选中后点击「📥 加载选中分轨」，自动跳过 AI 分离，直接进入上混阶段
- **删除分轨**：选中后点击「🗑️ 删除选中分轨」，立即释放磁盘空间（带空间显示）
- **刷新按钮**：处理新文件后点击刷新，立即看到新增分轨

#### 分轨管理使用场景
- **二次上混**：第一次用 Music 预设，想试 Movie 预设 → 加载分轨，直接上混，省去 20 分钟 AI 分离
- **参数调优**：LFE 分频点 / 响度目标改了 → 加载分轨，无需重新分离
- **磁盘清理**：`separated/` 目录越来越大 → 逐个删除不需要的分轨

#### 流水线逻辑优化
- 检测到 `existing_stems_dir` 时，Stage1（AI 分离）完全跳过
- 进度条从 5% 直接跳到 45%（进入 Stage2 上混）
- 日志显示：`📂 使用已有分轨：htdemucs_ft/曲名`

#### UI 提示优化
- 音频上传框提示改为：`🎵 拖放音频文件（加载已有分轨时可不填）`
- 就绪提示改为：`💡 就绪 — 上传音频或加载已有分轨后点击开始`
- 分轨管理面板内提示：`💡 选择已有分轨后点击「加载」，将跳过 AI 分离直接上混`

### 🔧 实时日志流修复（v1.5.0 补丁）

#### 问题根因
- **`run_pipeline()` 是普通函数**：所有日志在函数结束时一次性 `return`，中间 `progress()` 只更新 Gradio 内置进度条（已隐藏），不会推送到日志框
- **按钮不变态**：`on_run` generator 只 yield 3 次（开始、结束、错误），UI 没收到中间状态更新

#### 修复方案
- **`PipelineState` 加 `on_log` 回调**：每次 `log()` 调用时同步触发回调，推送最新日志
- **`run_pipeline` 接收 `on_log` 参数**：`run_pipeline(..., on_log=log_callback)`
- **`on_run` 改为线程+轮询模式**：
  - 后台 `Thread` 运行 `run_pipeline`
  - 主线程每 300ms 轮询 `latest_logs`，有新内容就 `yield` 到 UI
  - 按钮状态同步：`interactive=False` + 文字变 `⏳ 处理中…`

```python
# PipelineState 新增回调
class PipelineState:
    def __init__(self, on_log=None):
        self.on_log = on_log
    def log(self, msg):
        ...
        if self.on_log:
            self.on_log(full)

# on_run 线程轮询
latest_logs = [""]
def log_callback(text): latest_logs[0] = text

def worker():
    path, logs = run_pipeline(..., on_log=log_callback)

# 主线程 generator 每 300ms yield
while t.is_alive():
    if latest_logs[0] != last_yielded:
        yield ..., latest_logs[0], ..., ..., gr.update(interactive=False)
    time.sleep(0.3)
```

### 🔧 技术细节

#### 分轨扫描逻辑
```python
def scan_stems():
    # 扫描 separated/{model}/{track}/*.wav|*.flac
    # 返回 [{label, model, name, path, size_mb}]
    # label 格式：[model] track_name (size_MB)
```

#### 删除安全逻辑
```python
def delete_stems(model_name, track_name):
    shutil.rmtree(target)
    # 自动清理空的模型目录
    if not model_dir.iterdir():
        model_dir.rmdir()
```

#### 流水线适配
```python
if existing_stems_dir:
    stems_dir = Path(existing_stems_dir)
    progress(0.45)  # 跳过 Stage1
else:
    # 完整 AI 分离流程
    progress(0.05 → 0.45)
```

---

## v1.4.0 — 2026-06-03

### 🎉 新增功能

#### FP16 混合精度（性能大幅提升）
- **Demucs 从 CLI 调用改为 Python API 调用**（`demucs.pretrained.get_model` + `apply_model` + `save_audio`）
- FP16 模式：`model.half()` + `torch.autocast('cuda', dtype=torch.float16)`，RDNA3 FP16 吞吐约 2× FP32
- FP32 模式：保留为安全回退（若 FP16 出现 NaN/爆音）
- UI 默认 FP16，可在「⚙️ 高级选项」中切换
- ⚠️ Demucs CLI 不支持 `--float16` 参数，必须使用 Python API

#### libfdk_aac 自动检测
- **启动时自动检测 ffmpeg 是否内置 libfdk_aac 编码器**
- 有 → AAC 输出自动使用 `libfdk_aac`（音质明显优于默认 AAC，尤其低码率）
- 无 → 回退到 `ffmpeg 内置 AAC`
- 顶部 badge 显示当前 AAC 编码器状态

#### loudnorm 响度目标可选
- **新增 -18 LUFS（广播标准）选项**（高级选项 → 响度目标）
- -14 LUFS：流媒体标准（Spotify / YouTube，默认）
- -18 LUFS：广播标准（EBU R128 广播推荐，更利于动态范围）

#### LFE 低通分频点可选
- **新增 80Hz / 120Hz 切换**（高级选项 → LFE 分频点）
- 80Hz：车载音响推荐（默认）
- 120Hz：家用影院标准（THX 推荐）

#### 配置持久化（记忆上次设置）
- **每次成功处理后自动保存所有设置到 `wep_config.json`**
- 下次启动自动恢复：模型、预设、采样率、位深、格式、声道、AAC 码率、精度、LFE 分频点、响度目标
- 无需每次手动重新选择

### 📊 界面改进

#### 高级选项面板
- 新增「⚙️ 高级选项」折叠面板（默认收起，不干扰常用操作）
- 包含：GPU 精度 / LFE 分频点 / 响度目标
- 简洁布局：三个 Radio 组件一行排列

#### 启动页面增强
- 顶部 badge 新增 AAC 编码器状态显示（`libfdk_aac ✅` 或 `ffmpeg aac`）

### 🔧 技术细节

#### Demucs Python API + FP16
```
# 从 CLI 调用改为 Python API（Demucs 4.0 没有 --float16 CLI 参数）
from demucs.pretrained import get_model
from demucs.apply import apply_model
from demucs.audio import save_audio

model = get_model(name=model_name)
model.eval()
if precision == "fp16":
    model = model.half()
    with torch.autocast('cuda', dtype=torch.float16):
        sources = apply_model(model, wav[None], device='cuda', ...)[0]
else:
    sources = apply_model(model, wav[None], device='cuda', ...)[0]
```

#### libfdk_aac 检测逻辑
```python
FDK_AAC = False
r = subprocess.run(["ffmpeg", "-encoders"], ...)
FDK_AAC = "libfdk_aac" in r.stdout

# AAC 编码选择
if FDK_AAC:
    codec = ["-c:a", "libfdk_aac", "-b:a", aac_bitrate]
else:
    codec = ["-c:a", "aac", "-b:a", aac_bitrate]
```

#### 动态 loudnorm
```python
lnorm = f"loudnorm=I={loudnorm}:TP=-1:LRA=11"
# loudnorm 参数: -14 (流媒体) 或 -18 (广播)
```

#### 动态 LFE 分频
```python
f"[0:a]lowpass=f={lfe_hz},volume=1.5,..."
# lfe_hz: 80 (车载) 或 120 (家庭影院)
```

#### 配置持久化
```python
CONFIG_FILE = SCRIPT_DIR / "wep_config.json"

# 成功后自动保存
save_config({"model": model, "preset": preset, ...})

# 启动时自动加载
cfg = load_config()
model_select = gr.Radio(..., value=cfg.get("model", "htdemucs_ft"))
```

---

## v1.3.0 — 2026-06-03

### 🎉 新增功能

#### 预重采样优化（核心性能提升）
- **输入采样率预检**：Stage1 前用 `ffprobe` 检测输入文件采样率
- **自动重采样**：若输入采样率 ≠ 目标采样率，先用 ffmpeg 重采样到目标采样率（CPU 快速操作，pcm_f32le 保留精度），再交给 Demucs
- **避免 GPU 浪费**：输入 192kHz 时不再让 Demucs 以 192kHz 全采样率运行（浪费 ~4x 算力）
- **效果**：56 分钟 DJ Set 处理时间从 ~90 分钟降至 ~40 分钟
- **目录名对齐**：重采样后 Demucs 输出目录名基于临时文件名，自动 `shutil.move` 对齐到 `safe_name`
- **临时文件清理**：重采样临时文件在 `finally` 块中清理，无论成功失败都不遗留

#### MIB2+ 车机兼容（M3U 自动生成）
- **WAV 5.1/7.1 输出时自动生成同名 `.m3u` 文件**（与 WAV 同目录）
- MIB2+ 车机：有 M3U 才认 5.1 PCM，否则强制 6→2 下混
- **总播放列表自动追加**：`output/5.1_playlist.m3u`，去重，每首新曲自动追加
- 日志提示：`U 盘需同目录放置，MIB2+ 解锁 5.1 输出`

#### AAC 码率可选
- **AAC/m4a 输出时显示码率选择器**（Radio 组件，仅 AAC 时可见）
- 选项：128k / 256k / 320k / **512k 推荐** / 768k / 1024k
- `output_format` 切换时自动显示/隐藏 AAC 码率行（`gr.update(visible=...)`）

### 🔧 修复

#### 输出采样率对齐（Critical）
- **最终合并命令补回 `-ar` 参数**，修复输出采样率跟随输入（如 192kHz）的 bug
- 所有 ffmpeg 命令均显式传入 `-ar str(sr)`，确保分轨上混阶段和最终输出阶段采样率一致

#### ffmpeg filter_complex 分隔符修复
- FL/FR 创建时 `filter_complex` 多链分隔符从 `+` 改为 `;`（正确语法）
- 修复 ffmpeg exit status 4294967274 (-22 EINVAL) 错误

#### 中文文件名支持增强
- `safe_name` 过滤规则新增全角括号 `（）`、`【`、`】`
- 修复中文曲目名被截断导致找不到分轨的问题

#### Demucs 并行处理恢复
- 补回 `-j 4` 参数（4 个 stem 并行处理）
- 修复"只有一条进度条"的问题，现在 4 个 stem 同时分离

### 📊 界面改进

#### 预设参数更新（实际代码值）
| 预设 | centre_db | decorr_l | decorr_r | centre_gain 实际值 |
|------|-----------|-----------|-----------|-------------------|
| **Music** | +1 | 15ms | 17ms | 1.3× |
| **Movie** | +2 | 10ms | 12ms | 1.4× |
| **Anime** | +3 | 12ms | 14ms | 1.5× |
| **PLIIx** | +1 | 20ms | 23ms | 1.3× |

> centre_gain = 1.2 + centre_db × 0.1（代码实际公式）

---

## v1.2.0 — 2026-06-03

### 🎉 新增功能

#### 7.1 环绕声支持
- **新增 7.1 声道布局选项** (8 声道)
  - FL FR FC LFE (前场 4 声道)
  - Ls Rs (后环绕)
  - **SL SR (侧环绕 90°)** ← 新增
- 7.1 模式使用 8 声道合并 + EBU R128 响度归一化
- 输出文件命名：`曲名.7.1.wav` / `曲名.7.1.flac`

#### WAV/PCM 编码增强
- **默认输出格式改为 WAV/PCM** (用户需求)
- 支持多种比特深度：
  - 16-bit PCM (CD 标准)
  - **24-bit PCM** (高解析推荐，默认)
  - 32-bit float (母带制作)
- 车载 DJ 设备完美兼容

### 🚀 性能优化

#### Demucs 加速参数
- `--segment 7` — 整数且 ≤ 模型训练上限 7.8s（8 会超限报错，已修复）
- `--overlap 0.25` — 重叠比从 0.5 降至 0.25
- **提速约 15-20%** (1.5 小时音频从 22 分钟→18 分钟)

#### 音频时长预估
- 自动检测输入音频时长
- 显示预计分离耗时 (实时×0.25)
- 用户可提前规划等待时间

### 📊 界面改进

#### 输出格式选择
| 格式 | 编码 | 说明 |
|------|------|------|
| 📀 FLAC 无损 | FLAC compression=8 | 体积小，无损压缩 |
| 💿 WAV/PCM 无损 | PCM 16/24/32-bit | **默认**，车载/DJ 兼容 |
| 🎵 AAC/m4a 有损 | AAC 512k | 小体积，便携设备 |

#### 声道布局选择
| 选项 | 声道数 | 适用场景 |
|------|--------|----------|
| **7.1 环绕声** | 8 声道 | 高端家庭影院、专业监听 |
| 5.1 环绕声 | 6 声道 | 标准环绕声系统 |
| 立体声 | 2 声道 | 车载音响、耳机 |

### 🔧 技术细节

#### 7.1 声道路由
```
输入：4 stems (vocals, drums, bass, other)
↓
FL/FR: 全轨混合 (左/右声道)
FC: 人声 + 少量其他 (中置增强)
LFE: bass+drums 低通<80Hz
Ls/Rs: drums+other 延迟去相关 (15/17ms)
SL/SR: other 全通滤波 (侧向扩展)
↓
8 声道合并 → EBU R128 (-14 LUFS) → 输出
```

#### 编码参数
```python
# WAV/PCM 编码
if output_format == "wav":
    if bd == 16: codec = ["-c:a", "pcm_s16le"]
    elif bd == 32: codec = ["-c:a", "pcm_s32le"]
    else: codec = ["-c:a", "pcm_s24le"]  # 默认 24-bit

# 7.1 合并
filter_c = "[0:a][1:a][2:a][3:a][4:a][5:a][6:a][7:a]amerge=inputs=8,loudnorm=I=-14:TP=-1:LRA=11[aout]"
```

### 📝 已知限制

#### AMD ROCm 性能
- RX 9070 XT FP32 实测 ~1.5 TFLOPS (理论 22 TFLOPS)
- PyTorch 2.9+ROCm 7.2 在 gfx1201 上优化不足
- 功能正常，但跑不满显卡性能
- 等待后续 ROCm 版本改进

#### 模型分段限制
- `htdemucs_ft` 最大分段 = 7.8 秒 (训练限制)
- `--segment` 必须是整数，最大有效值为 7（8 会报 FATAL）
- 长音频处理时间 = 时长 × 0.25 (GPU)

---

## v1.1.0 — 2026-06-02

### 新增功能
- 多格式输出 (FLAC/WAV/AAC)
- 采样率选择 (44.1k/48k/96k/192k)
- 比特深度选择 (16/24/32-bit)
- 立体声/5.1 双模式

### 中文界面
- 全中文 UI
- 预设中文名 (音乐/电影/动漫/杜比)
- 实时日志输出

### UTF-8 支持
- 中文文件名兼容
- Windows GBK 终端防护
- `PYTHONUTF8=1` 环境变量

---

## v1.0.0 — 2026-06-01

### 初始版本
- WebUI 界面 (Gradio)
- Demucs AI 分离
- 5.1 环绕声上混
- EBU R128 响度归一化
- 一键启动 BAT

---

## 文件结构

```
D:\UVR5-of-MSST-WebUI+SurroundUpmix\
├── wep_webui.py          # WebUI 主程序 (v1.2.0)
├── 一键环绕声.bat         # 启动脚本
├── oneclick_WEP.py       # 命令行版本
├── simple_upmix_51.py    # 上混脚本
├── SurroundUpmix.ps1     # PowerShell 版上混
├── output/               # 输出目录
│   ├── 曲名.5.1.wav
│   ├── 曲名.7.1.wav
│   └── 曲名.5.1.flac
├── separated/            # Demucs 分离结果
│   └── htdemucs_ft/
│       └── 曲名/
│           ├── vocals.wav
│           ├── drums.wav
│           ├── bass.wav
│           └── other.wav
└── _wep_tmp/             # 临时工作目录
```

---

## 使用方法

### WebUI 模式
```bash
# 双击启动
一键环绕声.bat

# 浏览器打开 http://127.0.0.1:7860
# 1. 上传音频 (MP3/WAV/FLAC)
# 2. 选择 7.1/5.1/立体声
# 3. 选择 WAV/FLAC/AAC 格式
# 4. 点击开始
```

### 命令行模式
```bash
# 7.1 WAV 输出
python oneclick_WEP.py "歌曲.mp3" --preset Music --layout 7.1 --output-format wav

# 5.1 FLAC 输出
python oneclick_WEP.py "歌曲.flac" --preset Movie --layout 5.1
```

---

## 硬件要求

| 组件 | 最低 | 推荐 |
|------|------|------|
| GPU | NVIDIA 4GB / AMD 8GB | RTX 3060 / RX 9070 XT |
| 内存 | 8GB | 16GB+ |
| 存储 | 10GB 可用空间 | SSD |

### 处理速度参考 (RX 9070 XT)
| 音频时长 | 分离耗时 | 上混耗时 | 总计 |
|----------|----------|----------|------|
| 3 分钟 | 45 秒 | 10 秒 | ~1 分钟 |
| 5 分钟 | 1.2 分钟 | 15 秒 | ~1.5 分钟 |
| 30 分钟 | 7 分钟 | 45 秒 | ~8 分钟 |
| 90 分钟 | 18 分钟 | 2 分钟 | ~20 分钟 |

---

## 更新计划

- [ ] 批量处理模式
- [ ] 自定义 stems 路由
- [ ] 实时波形预览
- [ ] 预设保存/加载
- [ ] 杜比全景声 (Dolby Atmos) 导出
