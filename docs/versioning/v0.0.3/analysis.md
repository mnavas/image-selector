# v0.0.3 — Implementation Analysis

## Version Scope

v0.0.3 adds **AI-assisted editing** powered by Claude. The user types a natural-language description of the look they want and Claude analyses the current image and translates that description into a concrete `EditState` — sliders, filter, and all — which is then applied live in the edit panel for the user to review before saving.

The feature is delivered in two phases that share the same underlying design:

**Phase 1 — In-app AI edit button**
An "✨ AI Edit" text field + button inside the edit panel. The user writes a prompt ("make this warmer and less flat", "cinematic street look", "overexposed, fix it"), presses the button, and the sliders update automatically. The Anthropic API is called directly from the app.

**Phase 2 — MCP server for Claude Code**
A standalone `mcp_server.py` that exposes the same capability as Claude Code tools. Claude Code can call `analyze_image(path, prompt)` and `apply_and_save(path, state_json, output_path)` without opening the app at all, using the existing `edit_ops.py` pipeline directly. This fulfils the architecture note carried since v0.0.2.

**In scope:**
- Phase 1: AI edit UI inside `EditPanel`
- Phase 1: Image downscaling + base64 encoding for API
- Phase 1: Prompt design — system prompt that maps natural language to `EditState`
- Phase 1: Response parsing and slider animation
- Phase 1: API key detection; graceful disable if absent
- Phase 2: `mcp_server.py` with three tools
- Phase 2: Claude Code registration instructions

**Deferred:**
- HEIC support (`pillow-heif`)
- RAW support (`rawpy`)
- Batch editing
- Streaming token display (show thinking in real time)

---

## Architecture Decision: Two Phases, One Design

Both phases send the same payload to the same model and parse the same JSON response. The difference is where the call originates:

```
Phase 1 — user triggers from within the running app
  EditPanel → AnthropicClient → Claude API → EditState JSON → sliders

Phase 2 — Claude Code triggers from outside the app
  Claude Code → MCP server → AnthropicClient → Claude API → EditState JSON
            → apply_pipeline(original_img, state) → save file
```

`edit_ops.apply_pipeline` has no Qt imports by design (established in v0.0.2). The MCP server imports it directly without needing a running app instance. No IPC required.

---

## New Dependency

```
anthropic>=0.40
```

Added to `requirements.txt`. The SDK is used only in `ai_edit.py` (Phase 1 shared logic) and `mcp_server.py` (Phase 2). Neither module is imported at app startup — they are imported on first use so the app still launches if the package is missing.

---

## Phase 1 — In-App AI Edit

### API key

Detected from the environment at EditPanel init:

```python
import os
_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
```

If `_API_KEY` is empty the AI button is disabled and its tooltip reads:
`"Set ANTHROPIC_API_KEY in your environment to enable AI editing"`.

No UI for entering the key. The user sets it before launching the app:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
bash launch.sh
```

### New UI in `EditPanel`

A collapsible AI row is added at the bottom of the right-side panel, below the Filters section:

```
┌────────────────────────────────────────┐
│  AI EDIT                               │
│  ┌──────────────────────────────────┐  │
│  │ describe the look you want...    │  │
│  └──────────────────────────────────┘  │
│  [✨ Apply]   ↺ busy spinner           │
└────────────────────────────────────────┘
```

- `QLineEdit` for the prompt (placeholder text: *"describe the look you want…"*)
- `QPushButton("✨ Apply")` — disabled while a request is in flight
- A `QLabel` used as a status indicator: empty at rest, "Thinking…" during the call, "Applied" on success, error message in red on failure

The row is part of the scrollable right panel, so it never crowds the filter list.

### Image encoding — `ai_edit.py`

A new module `ai_edit.py` handles the API call. No Qt imports.

```python
def encode_for_api(img: np.ndarray, max_side: int = 768) -> str:
    """Downscale img to max_side on its longest dimension, return base64 JPEG string."""
```

768 px is the working size:
- Sufficient for Claude to read composition, tones, colour casts, and exposure
- Produces a JPEG of ~40–80 KB — fast to encode and cheap on token count
- The preview image (`_preview_img`, already ≤ 1600 px) is the source; no disk read

Encoding steps:
1. `cv2.resize` to fit within 768×768 (INTER_AREA, preserves colour)
2. `cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 80])`
3. `base64.b64encode(buf).decode()`

### Prompt design

The system prompt is a constant string in `ai_edit.py`. It must reliably produce valid JSON with no prose around it:

```
You are a photo editing assistant.
The user will describe the look they want for the attached image.
Your job is to return ONLY a JSON object that matches this schema exactly,
with no markdown, no explanation, no code fences:

{
  "brightness":   <float -100 to 100>,
  "contrast":     <float -100 to 100>,
  "exposure":     <float -3.0 to 3.0>,
  "saturation":   <float -100 to 100>,
  "shadows":      <float -100 to 100>,
  "highlights":   <float -100 to 100>,
  "filter_name":  <one of: "original", "provia", "velvia", "astia",
                   "classic_chrome", "classic_neg", "acros", "eterna",
                   "sepia", "faded", "cross_process", "fortia_sp",
                   "neopan_1600", "t64", "pro_800z", "pro_400h",
                   "pro_160c", "pro_160s", "superia_1600",
                   "superia_400", "superia_100",
                   "normalize", "auto_levels", "auto_tone", "auto_wb">,
  "rotation":     <one of: 0, 90, 180, 270>
}

Rules:
- All numeric values must be within range. Do not invent new fields.
- Set "rotation" to 0 unless the user explicitly asks to rotate.
- Set "filter_name" to "original" if no film simulation is needed.
- Analyse the image carefully before deciding on values.
- Base your response on both the image content AND the user's description.
```

User message:

```
[base64 image attached]
User request: <user's text from the QLineEdit>
```

Model: `claude-opus-4-7` for Phase 1 (best image reasoning). Can be made configurable later.

### Response parsing

Claude's response is expected to be a bare JSON object. To handle edge cases (model wraps in ```json blocks despite instructions):

```python
import json, re

def parse_edit_state(text: str) -> dict:
    text = text.strip()
    # Strip optional markdown code fences
    text = re.sub(r'^```[a-z]*\n?', '', text)
    text = re.sub(r'\n?```$', '', text)
    data = json.loads(text)
    # Clamp values to valid ranges
    data["brightness"]  = max(-100, min(100, float(data.get("brightness", 0))))
    data["contrast"]    = max(-100, min(100, float(data.get("contrast", 0))))
    data["exposure"]    = max(-3.0, min(3.0, float(data.get("exposure", 0))))
    data["saturation"]  = max(-100, min(100, float(data.get("saturation", 0))))
    data["shadows"]     = max(-100, min(100, float(data.get("shadows", 0))))
    data["highlights"]  = max(-100, min(100, float(data.get("highlights", 0))))
    valid_filters = {*FILM_SIMS.keys(), "normalize", "auto_levels", "auto_tone",
                     "auto_wb", "original"}
    if data.get("filter_name") not in valid_filters:
        data["filter_name"] = "original"
    data["rotation"] = data.get("rotation", 0) if data.get("rotation") in (0,90,180,270) else 0
    return data
```

On `json.JSONDecodeError` or any exception the error message is shown in the status label and the sliders are not touched.

### API call — threading

The Anthropic call runs in a `QThread` worker to keep the UI responsive. The button is disabled and "Thinking…" is shown while the thread runs. On completion the thread emits a signal carrying either the parsed dict or an error string. The main thread applies the result to the sliders.

```
_AiWorker(QThread)
  run() → encode_for_api() → anthropic.messages.create() → parse_edit_state()
  signals: result_ready(dict) | error(str)
```

### Applying the result to sliders

`EditPanel._on_ai_result(state_dict)`:
1. Block all slider signals
2. Set each slider value from `state_dict`
3. Set filter radio button from `state_dict["filter_name"]`
4. Unblock signals
5. Call `_on_state_changed()` once to trigger the pipeline
6. Set status label to "Applied ✓"

No animation in Phase 1 — sliders jump to the new position. Smooth animation can be added later with `QPropertyAnimation`.

### `crop_rect` and `rotation` via AI

`crop_rect` is not included in the AI response — the crop tool is spatial and requires the user to see the result interactively. The AI can set `rotation` (0/90/180/270) if the user asks.

---

## Phase 2 — MCP Server

### File: `mcp_server.py`

A standalone script using the `mcp` Python SDK (or raw JSON-RPC over stdio if the SDK is not available — TBD at implementation time based on Claude Code MCP requirements).

The server imports `edit_ops`, `film_luts`, and `ai_edit` directly. No Qt, no running app instance.

### Tools exposed

**`get_image_info(image_path: str) -> dict`**
Returns width, height, file size, and a base64 JPEG thumbnail (400px, for Claude to inspect without another tool call).

```json
{ "width": 4000, "height": 3000, "file_size_kb": 5400, "thumbnail_b64": "..." }
```

**`suggest_edits(image_path: str, prompt: str) -> str`**
Calls `ai_edit.call_api(image_path, prompt)` and returns the EditState JSON string.
Claude Code can inspect the JSON, modify values, and pass it to `apply_and_save`.

**`apply_and_save(image_path: str, state_json: str, output_path: str) -> str`**
Parses `state_json`, calls `apply_pipeline(cv2.imread(image_path), state)`, and writes the result atomically (tempfile + rename, same pattern as `AppController.save_edit`). Returns `"Saved: <output_path>"` on success or an error description.

### Registration with Claude Code

```bash
claude mcp add image-selector -- python /path/to/image-selector/mcp_server.py
```

After registration, Claude Code can be used directly from the terminal to edit images:

```
> use the image at ~/Photos/DSC_0042.jpg — it looks hazy and underexposed.
  make it look like a Velvia slide.
```

Claude Code calls:
1. `get_image_info("~/Photos/DSC_0042.jpg")` — confirms it can see the image
2. `suggest_edits("~/Photos/DSC_0042.jpg", "hazy and underexposed, Velvia slide look")` — gets EditState
3. Reviews the JSON, optionally adjusts values, calls `apply_and_save(...)` with a new filename

---

## New Module: `ai_edit.py`

Pure Python, no Qt. Shared between Phase 1 and Phase 2.

```python
SYSTEM_PROMPT: str             # constant — the schema prompt above
EDIT_MODEL: str = "claude-opus-4-7"

def encode_for_api(img: np.ndarray, max_side: int = 768) -> str: ...
def call_api(img_b64: str, user_prompt: str, api_key: str) -> str:
    """Call Anthropic API and return raw response text."""
def parse_edit_state(text: str) -> dict:
    """Parse and clamp the JSON response to a valid EditState dict."""
def img_path_to_b64(path: str, max_side: int = 768) -> str:
    """Convenience: read image from path and encode."""
```

---

## Changes to Existing Modules

| Module | Change |
|--------|--------|
| `requirements.txt` | Add `anthropic>=0.40` |
| `widgets/edit_panel.py` | Add AI row to right panel; add `_AiWorker` thread class; add `_on_ai_result` / `_on_ai_error` slots |
| `config.py` | Add optional `ai_model: str` field (defaults to `"claude-opus-4-7"`) so the model can be changed without code edits |

`edit_ops.py`, `film_luts.py`, `app_controller.py`, `main_window.py` — **no changes required**.

---

## Data Flow: Phase 1 end-to-end

```
User types "flat and cold, make it warm and filmic" → presses ✨ Apply
  → EditPanel._on_ai_apply()
      → disable button, show "Thinking…"
      → _AiWorker(preview_img, prompt, api_key).start()
           → ai_edit.encode_for_api(preview_img)   # 768px JPEG, base64
           → ai_edit.call_api(b64, prompt, api_key)
                → anthropic.messages.create(model, system, [image+text])
                → returns text: '{"brightness":15,"contrast":20,"exposure":0.3,
                                   "saturation":25,"shadows":15,"highlights":-10,
                                   "filter_name":"velvia","rotation":0}'
           → ai_edit.parse_edit_state(text)        # clamp + validate
           → emit result_ready(state_dict)
  → EditPanel._on_ai_result(state_dict)
      → block slider signals
      → set slider values + filter radio button
      → unblock, call _on_state_changed()
           → debounce 50ms → apply_pipeline(preview_img, state) → set_array(out)
      → show "Applied ✓"
```

## Data Flow: Phase 2 end-to-end

```
Claude Code: "fix the exposure on DSC_0042.jpg and save as DSC_0042_edit.jpg"
  → tool: get_image_info("DSC_0042.jpg")
      → returns dimensions + thumbnail
  → tool: suggest_edits("DSC_0042.jpg", "fix exposure, looks underexposed")
      → ai_edit.img_path_to_b64(path) + ai_edit.call_api(...) + parse
      → returns '{"exposure": 1.2, "highlights": -15, ...}'
  → (Claude Code may show the JSON and let user tweak)
  → tool: apply_and_save("DSC_0042.jpg", state_json, "DSC_0042_edit.jpg")
      → cv2.imread original (full resolution)
      → apply_pipeline(img, state)
      → tempfile write → atomic rename
      → os.utime (preserve original timestamps)
      → returns "Saved: DSC_0042_edit.jpg"
```

---

## Error Cases

| Situation | Behaviour |
|-----------|-----------|
| `ANTHROPIC_API_KEY` not set | Button disabled with tooltip |
| API rate limit / network error | Status label shows error; sliders unchanged |
| Claude returns invalid JSON | `json.JSONDecodeError` caught; error shown; sliders unchanged |
| Claude returns out-of-range values | `parse_edit_state` clamps silently |
| Image unreadable by cv2 | Error before API call; shown in status label |
| MCP server: output path directory missing | `apply_and_save` returns error string; no file written |

---

## Prompt Engineering Notes

A few edge cases to handle in the system prompt:

- **"Black and white"** — should map to `filter_name: "acros"` or `"neopan_1600"`, not `saturation: -100`
- **"Rotate left"** — `rotation: 270` (same as -90 CW)
- **"Fix white balance"** — `filter_name: "auto_wb"` or a specific blue/warm adjustment
- **Vague prompts** ("make it nice") — Claude should interpret based on the image content and pick reasonable values; the user can adjust sliders afterwards
- **Conflicting intent** ("dark and bright") — Claude should resolve sensibly; no special handling needed

The system prompt will be iterated on during implementation based on test results across different image types and prompt styles.

---

## Implementation Tasks

| # | Task | Phase | Notes |
|---|------|-------|-------|
| 1 | `ai_edit.py` — `encode_for_api`, `call_api`, `parse_edit_state` | 1 | Unit-testable, no Qt |
| 2 | `_AiWorker` thread class inside `edit_panel.py` | 1 | QThread subclass |
| 3 | AI row UI in `EditPanel._build_ui` | 1 | QLineEdit + button + status label |
| 4 | `_on_ai_apply`, `_on_ai_result`, `_on_ai_error` slots | 1 | Wire thread signals |
| 5 | API key detection + button enable/disable | 1 | At `__init__` time |
| 6 | Manual prompt testing across image types | 1 | Portraits, landscapes, indoor, B&W |
| 7 | Refine system prompt based on test results | 1 | Iterate |
| 8 | Add `anthropic>=0.40` to `requirements.txt` | both | |
| 9 | `mcp_server.py` — `get_image_info` tool | 2 | |
| 10 | `mcp_server.py` — `suggest_edits` tool | 2 | Reuses `ai_edit.py` |
| 11 | `mcp_server.py` — `apply_and_save` tool | 2 | Reuses `edit_ops.apply_pipeline` |
| 12 | MCP registration instructions in `docs/installation.md` | 2 | |
| 13 | Update `docs/user-guide.md` with AI Edit section | both | |
| 14 | Update `docs/architecture.md` with new modules | both | |

---

## Decisions

1. **Model** — `claude-opus-4-7` for Phase 1. Best image understanding. Cost is acceptable for single-image interactive use. Phase 2 can expose `ai_model` as a config option.
2. **Image size for API** — 768px longest side. Enough visual information; keeps JPEG under 100 KB; faster round-trip than 1600px.
3. **No streaming in Phase 1** — The JSON response is short (< 200 tokens). Streaming adds complexity without UX benefit. Add if model latency becomes a problem.
4. **`crop_rect` excluded from AI response** — Spatial crop requires seeing the result interactively; a coordinates guess from Claude would rarely be useful without visual feedback.
5. **MCP server is standalone** — No IPC with the running Qt app. If the user has the app open and also uses Claude Code, they are two separate workflows. A future version could add a file-watcher in the app to pick up externally applied edits.
6. **API key via environment only** — No in-app key entry. Avoids storing secrets in the config file. The `launch.sh` script is the natural place for users to export the key.
