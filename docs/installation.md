# Installation Guide

## Prerequisites

- **Python 3.11 or newer** — [python.org/downloads](https://www.python.org/downloads/)
- **pip** (bundled with Python 3.11+)
- **git** (to clone the repository)

---

## Linux

### 1 — System dependencies

PyQt6 requires a few system libraries that may not be present on a minimal install.

**Ubuntu / Debian:**
```bash
sudo apt update
sudo apt install python3-dev libxcb-cursor0 libgl1
```

**Fedora / RHEL:**
```bash
sudo dnf install python3-devel xcb-util-cursor mesa-libGL
```

**Arch:**
```bash
sudo pacman -S xcb-util-cursor mesa
```

> If you see `qt.qpa.plugin: could not load the Qt platform plugin "xcb"` on launch, the `libxcb-cursor0` package is likely missing.

### 2 — Clone and install

```bash
git clone https://github.com/mnavas/image-selector.git
cd image-selector
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3 — Run

```bash
source .venv/bin/activate   # if not already active
python main.py
```

Or use the included launcher script (activates the venv automatically):

```bash
bash launch.sh
```

### 4 — Desktop launcher (optional)

Create a `.desktop` entry so the app appears in your application menu:

```bash
cat > ~/.local/share/applications/image-selector.desktop << EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=Image Selector
Comment=Keyboard-driven photo triage and editing tool
Exec=/absolute/path/to/image-selector/launch.sh
Icon=shotwell
Terminal=false
Categories=Graphics;Photography;
StartupNotify=true
EOF
```

Replace `/absolute/path/to/image-selector` with the actual path where you cloned the repo, then:

```bash
chmod +x /absolute/path/to/image-selector/launch.sh
update-desktop-database ~/.local/share/applications/
```

---

## macOS

### 1 — Clone and install

```bash
git clone https://github.com/mnavas/image-selector.git
cd image-selector
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2 — Run

```bash
source .venv/bin/activate
python main.py
```

> **Accessibility prompt:** macOS may ask for accessibility permissions the first time you run — this is normal for desktop apps that handle keyboard events globally.

---

## Windows

### 1 — Clone and install

Open **PowerShell** or **Command Prompt**:

```powershell
git clone https://github.com/mnavas/image-selector.git
cd image-selector
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### 2 — Run

```powershell
.venv\Scripts\activate
python main.py
```

> **First launch:** Windows may show a security prompt the first time. Click **Allow access** to proceed.

---

## AI Edit feature

The **✨ AI Edit** button works with either an Anthropic API key **or** a locally running Ollama instance. Everything else in the app works normally without either.

### Option 1 — Anthropic API (Claude)

Requires a paid API key from [console.anthropic.com](https://console.anthropic.com):

```bash
export ANTHROPIC_API_KEY=sk-ant-...
bash launch.sh
```

Cost is roughly $0.01–0.02 per edit suggestion. The key is never stored on disk.

### Option 2 — Ollama (free, local)

Requires [Ollama](https://ollama.com) installed with a vision-capable model. No account or internet connection needed after the initial model download.

**Install Ollama:**

```bash
curl -fsSL https://ollama.com/install.sh | sh   # Linux / macOS
```

Windows: download the installer from [ollama.com](https://ollama.com).

**Pull a vision model:**

```bash
ollama pull gemma3n    # recommended — good quality, reasonable speed
# alternatives: llava, moondream, llava-phi3
```

**Launch the app** — Ollama server is detected automatically:

```bash
bash launch.sh
```

Override the model or host if needed:

```bash
export OLLAMA_MODEL=llava
export OLLAMA_HOST=http://localhost:11434
bash launch.sh
```

If Ollama is running when the app starts, the AI Edit button is enabled with no further configuration.

---

## Claude Code MCP integration

The included `mcp_server.py` lets Claude Code edit images directly from the terminal without opening the app.

### Register the server

```bash
claude mcp add image-selector -- python /absolute/path/to/image-selector/mcp_server.py
```

The server also needs the API key in its environment:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

### Available tools

| Tool | What it does |
|------|-------------|
| `get_image_info(image_path)` | Returns dimensions and a thumbnail for Claude to inspect |
| `suggest_edits(image_path, prompt)` | Returns a JSON `EditState` based on the image and your prompt |
| `apply_and_save(image_path, state_json, output_path)` | Applies the edits at full resolution and saves the result |

### Example session

```
> analyse ~/Photos/DSC_0042.jpg — it looks flat and overexposed.
  Save the result as ~/Photos/DSC_0042_edit.jpg
```

Claude Code will call `get_image_info`, then `suggest_edits`, show you the proposed values, then call `apply_and_save`. The original file is never modified.

---

## Dependencies

All Python dependencies are pinned in `requirements.txt`:

| Package | Version | Purpose |
|---------|---------|---------|
| `PyQt6` | ≥ 6.6 | UI framework |
| `opencv-python` | ≥ 4.9 | Image loading, editing, and saving |
| `Pillow` | ≥ 10.0 | EXIF reading |
| `send2trash` | ≥ 1.8 | Safe delete to system trash |
| `anthropic` | ≥ 0.40 | Anthropic API client (AI Edit feature) |
| `mcp` | ≥ 1.0 | MCP server SDK (Claude Code integration) |
| `numpy` | (pulled by OpenCV) | Array operations in the edit pipeline |

---

## First launch

On first launch you will be asked to choose two folders:

1. **Library folder** — your incoming photos (camera card dump, dated folder, etc.)
2. **Album folder** — the destination where selected photos go

These paths are saved to `~/.config/image_selector/config.json` and reused on the next launch. You can change them at any time via **File → Change Library Folder…** or **File → Change Album Folder…**.

See [user-guide.md](user-guide.md) for the full usage documentation.
