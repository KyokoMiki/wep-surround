<p align="center">
  <a href="README.md">🇨🇳 中文</a> | <strong>🇬🇧 English</strong>
</p>

---

# WEP Surround — AI-Powered Surround Sound Upmixer

Stereo Audio → AI Source Separation → 5.1/7.1 Surround Sound Upmix Workflow. Powered by Demucs deep learning model, one-click converts ordinary stereo music to car/theater-grade surround sound.

> **In a nutshell**: Open browser → Upload MP3/WAV/FLAC → Select parameters → Export 5.1/7.1 surround sound

WEP Surround is a deep-learning-based surround upmix tool that uses Demucs AI to automatically separate ordinary stereo audio (MP3/WAV/FLAC) into 4 stems (vocals, bass, drums, instruments), then remaps them to 5.1 or 7.1 multi-channel layouts through intelligent routing algorithms, producing car/ home theater-compatible surround sound files.

### Use Cases

- **Car Audio Upgrade**: Convert stereo music to 5.1 surround, plug-and-play for MIB2+ head units via USB
- **Home Theater**: Generate 7.1 surround for film scores / music videos, maximizing multi-channel speaker potential
- **Music Production**: Quickly create surround mix references for immersive audio composition

### Core Capabilities

- **AI Source Separation**: Demucs `htdemucs_ft` model, 4-stem parallel processing, FP16 mixed precision acceleration
- **Intelligent Upmix**: 4 stems → FL/FR/FC/LFE/Ls/Rs(+SL/SR) multi-channel, multiple preset algorithms
- **Multi-format Output**: WAV/PCM (24-bit default), FLAC lossless, AAC/m4a
- **One-Click UI**: Gradio WebUI, upload → select params → start, real-time progress + ETA countdown

### Performance Reference (RX 9070 XT, FP16)

| Audio Duration | Total Time |
|---------------|------------|
| 3 min         | ~17 sec    |
| 60 min        | ~4 min 20 sec |

---

## Features

- **AI Source Separation**: Based on Demucs deep learning model, automatically separates vocals, bass, drums, other (4 stems)
- **Surround Upmix**: 4 stems → 5.1/7.1 multi-channel output
- **Multiple Presets**: Music / Movie / Anime / PLIIx (Dolby Pro Logic IIx)
- **Loudness Normalization**: EBU R128 standard (-14 LUFS)
- **Web UI**: Gradio visual interface, real-time logging + percentage progress + ETA countdown
- **CLI Mode**: Command-line one-click processing with batch support
- **MIB2+ Compatible**: Auto-generates M3U playlists, USB plug-and-play for car audio

---

## System Requirements

- **Python 3.10+**
- **Dedicated GPU (required)**: NVIDIA RTX/GTX series, AMD Radeon RX series, or Intel Arc series
- **OS**: Windows 10/11, Linux, macOS
- **ffmpeg** (optional, required for some features)

---

## Quick Install

**Prerequisites**: [Python 3.10+](https://www.python.org/downloads/) must be installed (check "Add Python to PATH" during installation)

### Windows Installation

```bash
# Download and extract the project
# Prerequisite: Python 3.10+ installed (with "Add Python to PATH")
# Auto-detect GPU and install matching version
python install.py
```

The installer automatically handles (pure Python, bypasses Device Guard security restrictions):
- Auto-detect NVIDIA / AMD / Intel Arc GPU model (reads Windows Registry directly)
- Auto-match PyTorch version (CUDA / ROCm / XPU) based on GPU model
- Auto-select fastest pip mirror (PyPI / Tsinghua / Aliyun / Tencent Cloud)
- Auto-select fastest model download source (hf-mirror / ModelScope / HuggingFace)
- Create virtual environment `vep_venv`
- Install full dependency stack (demucs, gradio, librosa, MSST models, etc.)
- Pre-download Demucs AI models

### Dry Run Mode

```bash
# Check environment only, nothing installed (safe verification)
python install.py --dryrun
```

Dry run checks:
- Python version, network mirrors, FFmpeg, Windows security policy
- GPU model and matching PyTorch version
- HuggingFace model mirrors
- Outputs environment summary for review before actual installation

### Linux / macOS

```bash
# Prerequisite: Python 3.10+ installed
chmod +x install.sh
./install.sh

# Manual installation
git clone https://github.com/Mark007007/wep-surround.git
cd wep-surround
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install .             # Base version
pip install .[cuda]       # NVIDIA GPU version
pip install .[rocm]       # AMD ROCm version
pip install .[full]       # Full version (includes all MSST models)
```

---

## Usage

### WebUI Mode (Recommended)

```bash
# Windows: Double-click to launch
一键环绕声.bat

# Or command line
wep-webui
# Or
python wep_webui.py
```

Open http://127.0.0.1:7860 in your browser after launch.

**Steps**:
1. Upload audio (MP3/WAV/FLAC, drag-and-drop supported)
2. Select AI model (`htdemucs_ft` high quality / `htdemucs` fast)
3. Select preset (Music / Movie / Anime / PLIIx)
4. Select sample rate (44.1k / **48k recommended** / 96k)
5. Select bit depth (16 / **24 recommended** / 32-float)
6. Select output format (FLAC / **WAV/PCM** / AAC/m4a)
7. Select channel layout (**7.1** / 5.1 / Stereo)
8. Click "🚀 Start"
9. Watch real-time logs, percentage progress, and ETA countdown

**AAC Bitrate Options** (shown only for AAC format):
128k / 256k / 320k / **512k recommended** / 768k / 1024k

### Command Line

```bash
# Basic usage
wep-cli "song.mp3"

# Specify preset and channel layout
wep-cli "song.flac" --preset Movie --layout 7.1

# Skip AI separation (use existing stems)
wep-cli "song.wav" --skip-separate --stems-from ./separated/htdemucs/MyTrack
```

### Python API

```python
from oneclick_WEP import run_pipeline

run_pipeline(
    input_file="song.mp3",
    preset="Music",
    layout="5.1",
)
```

---

## Configuration

Edit `wep_config.json`:

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

## Preset Parameters

| Preset   | centre_db | decorr_l | decorr_r | Use Case                  |
|----------|-----------|----------|----------|---------------------------|
| **Music** | +1        | 15ms     | 17ms     | Pure music, wide surround |
| **Movie** | +2        | 10ms     | 12ms     | Film scores, clear dialog |
| **Anime** | +3        | 12ms     | 14ms     | Anime BGM, prominent vocals |
| **PLIIx** | +1        | 20ms     | 23ms     | General, extremely wide   |

> centre_db: center channel gain offset (Music=1.3×, Movie=1.4×, Anime=1.5×, PLIIx=1.3×)

---

## Key Technical Details

### Demucs Parameters

```
Model: htdemucs_ft (trained with max segment=7.8s)
--segment 7       ← integer, ≤7.8, 8 will error FATAL
--overlap 0.25    ← balance quality/speed
-j 4              ← 4 stems parallel
--float16         ← FP16 precision (~2-3× GPU acceleration)
-d cuda           ← GPU (AMD ROCm / NVIDIA CUDA both supported)
```

### Pre-resampling Optimization (v1.3.0+)

- **Problem**: With 192kHz input, Demucs runs at full sample rate, wasting ~4× GPU compute
- **Fix**: Detect sample rate with ffprobe before Stage 1; resample with ffmpeg (CPU fast) if mismatch
- **Effect**: 56 min @192kHz dropped from ~15 min to ~3.5 min (pre-resample + FP16)

### Output Sample Rate Alignment

- Every ffmpeg command explicitly passes `-ar <sr>`, ensuring consistent sample rate across stem upmix and final output

---

## Performance Reference (FP16 GPU, AMD 9070XT)

| Audio Duration | Separation | Upmix+Encode | Total    |
|---------------|------------|--------------|----------|
| 3 min         | ~12 sec    | ~5 sec       | ~17 sec  |
| 5 min         | ~20 sec    | ~8 sec       | ~28 sec  |
| 30 min        | ~2 min     | ~15 sec      | ~2 min 15 sec |
| 60 min        | ~4 min     | ~20 sec      | ~4 min 20 sec |
| 90 min        | ~6 min     | ~25 sec      | ~6 min 25 sec |

> Factor: duration × 0.066 (FP16), upmix+encode ~15-30 sec additional

---

## MIB2+ Car Integration

### Auto-generated Files

- WAV 5.1/7.1 output auto-generates `.m3u` file in same directory
- MIB2+ head units: **M3U required for 5.1 PCM recognition**, otherwise forced 6→2 downmix
- Maintains `output/5.1_playlist.m3u` master playlist (deduplicated)

### USB Copy Instructions

1. **Format as NTFS or exFAT** (FAT32 has 4GB file limit, 5.1 WAV typically 3-5GB)
2. **Copy files**: Copy `.5.1.wav` / `.5.1.m3u` / `.7.1.wav` / `.7.1.m3u` from `output/` to USB **root or same folder**
3. **WAV + M3U pairing required**: `track.5.1.wav` and `track.5.1.m3u` must be in same directory
4. **M3U content**: First line `#EXTM3U`, second line filename (e.g., `track.5.1.wav`)
5. **Format**: Must be WAV/PCM 5.1 (6ch), not FLAC or AAC (head unit won't recognize)
6. **Sample rate**: 48kHz recommended (car standard), 44.1kHz works but some models don't support
7. **Plug into car**: USB port → wait for scan → MIB2+ auto-detects 5.1 surround output

### Common Failure Troubleshooting

| Symptom | Cause | Solution |
|---------|-------|----------|
| Head unit plays stereo only | Missing `.m3u` file | Recopy M3U to same directory |
| "Format not supported" error | FAT32 or FLAC | Switch to NTFS/exFAT + WAV |
| Playback stuttering/noise | Sample rate not 48kHz | Change output sample rate to 48000 |
| Only front 2 channels active | Wrong M3U content or file pairing | Check M3U second line matches WAV filename |

---

## FAQ

### Installation Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| `python install.py` says "Python not found" | Python not installed or not in PATH | Reinstall Python, check "Add Python to PATH", restart terminal |
| Installer crashes / `findstr' is not recognized` | Windows Device Guard blocks commands | Python installer bypasses via registry, unaffected by security policy |
| GPU detection fails | Device Guard blocks wmic/nvidia-smi | Python installer auto-detects via registry; manual GPU model entry as fallback |
| pip download timeout/slow | Network issues | Switch to Tsinghua mirror: `python -m pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple` |
| `pip install .[cuda]` still uses CPU | PyTorch CUDA version not installed | `pip uninstall torch torchaudio` then `pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu121` |
| `pip install .[rocm]` fails | ROCm not installed or version mismatch | Install ROCm first, see AMD official docs |
| `libsndfile` missing (soundfile error) | Windows missing C library | `pip install soundfile` auto-downloads, or manual from https://github.com/libsndfile/libsndfile/releases |
| `ffmpeg` missing | Not installed | `winget install ffmpeg` or download from https://ffmpeg.org/download.html |

### Runtime Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| `ModuleNotFoundError: No module named 'demucs'` | Virtual env not activated | Double-click `一键环绕声.bat` (auto-activates), or manually `call vep_venv\Scripts\activate.bat` |
| WebUI starts but browser can't connect | Port conflict or firewall | Check http://127.0.0.1:7860; disable firewall or change port |
| WebUI hangs after separation | Demucs model not downloaded | First run auto-downloads model (~2GB), wait; check network |
| Encoding phase freezes | Normal, ffmpeg takes time | Watch ETA countdown in logs, don't click around |
| `PermissionError: Permission denied` | Gradio file lock | Fixed in latest version, ensure up-to-date |
| C drive space filling up | Gradio temp files not cleaned | Fixed, auto-cleans on exit; manual: delete `%TEMP%\gradio\` |
| Low GPU utilization (<10%) | Demucs segment limit | Normal, `htdemucs_ft` max segment is 7.8s, can't increase GPU usage further |

### Output Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| Output smaller than input | Compression (FLAC/AAC) | Normal, FLAC ~50% compression, AAC by bitrate |
| Output is stereo not 5.1 | 5.1/7.1 layout not selected | Ensure channel layout is 5.1 or 7.1 in WebUI |
| Car plays stereo only | Missing M3U playlist | WAV output auto-generates .m3u, ensure both in same directory |
| Wrong output sample rate | Target sample rate not set | Select 48000 (recommended) in WebUI |

### Performance Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| Processing too slow | CPU mode or FP32 | Enable GPU + FP16 (AMD/NVIDIA both supported) |
| Low AMD GPU utilization | ROCm optimization | Normal, FP16 improves 2-3× speed |
| Long audio takes too long | Demucs inference is GPU-intensive | See performance table: 60 min audio ~4 min (FP16 AMD 9070XT) |

---

## Known Issues

1. **AMD ROCm Performance**: RX 9070 XT FP32实测 ~1.5 TFLOPS (theoretical 22 TFLOPS). PyTorch 2.9+ROCm 7.2 on gfx1201 is suboptimal — functional but doesn't max out the card. Use FP16 mode.
2. **Demucs Segment Limit**: `htdemucs_ft` trained with max 7.8s, `--segment` integer max = 7, cannot further increase via segment size.
3. **EBU R128 Loudness Normalization**: CPU-bound, ~5 sec for 2.6 min audio, longer durations take proportionally more time.

---

## Project Structure

```
├── wep_webui.py              # Web UI entry point
├── oneclick_WEP.py           # CLI one-click script
├── simple_upmix_51.py        # Simplified upmix script
├── oneclick_51.py            # 5.1 dedicated script
├── MSST-WebUI/               # Subproject: MSST training WebUI
├── install.py                # Python smart installer (GPU detection, mirror check, deps)
├── install.sh                # Linux/macOS one-click installer
├── 一键环绕声.bat             # Quick launch (auto-activate venv)
├── pyproject.toml            # pip package config
├── wep_config.json           # Default configuration
├── CHANGELOG.md              # Changelog
└── output/                   # Surround output directory
```

---

## Changelog

See [CHANGELOG.md](CHANGELOG.md)

---

## Documentation

Detailed operation guide, parameter descriptions, car compatibility, etc., see [环绕声流水线.md](环绕声流水线.md)

---

## License

MIT