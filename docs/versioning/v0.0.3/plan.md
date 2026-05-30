# v0.0.3 — Implementation Plan

## Prerequisites

- v0.0.2 fully working
- `ANTHROPIC_API_KEY` set in the environment for manual testing
- New pip package: `anthropic>=0.40` — add to `requirements.txt`

---

## Phase 1 — `ai_edit.py` (pure Python, no Qt)

All the AI logic lives here. No Qt imports. Importable from both the app and the MCP server.

### Step 1 — Image encoding

```python
def encode_for_api(img: np.ndarray, max_side: int = 768) -> str:
    """Downscale img to max_side on longest dimension, return base64 JPEG string."""
```

- Resize with `cv2.resize` + `INTER_AREA`
- Encode with `cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 80])`
- Return `base64.b64encode(buf).decode()`

```python
def img_path_to_b64(path: str, max_side: int = 768) -> str:
    """Convenience wrapper: read from disk then encode."""
```

### Step 2 — System prompt constant

Define `SYSTEM_PROMPT` as a module-level string. It must instruct Claude to:
- Return ONLY a JSON object, no markdown, no prose
- Use the exact `EditState` field names and ranges
- List every valid `filter_name` value
- Set `rotation` to 0 unless explicitly asked
- Base decisions on both the image content and the user's text

### Step 3 — API call

```python
def call_api(img_b64: str, user_prompt: str, api_key: str,
             model: str = "claude-opus-4-7") -> str:
    """Send image + prompt to Claude, return raw response text."""
```

Uses `anthropic.Anthropic(api_key=api_key).messages.create()` with:
- `model` parameter
- `system=SYSTEM_PROMPT`
- One user message containing the base64 image block + text prompt

### Step 4 — Response parsing

```python
def parse_edit_state(text: str) -> dict:
    """Parse Claude's JSON response and clamp all values to valid ranges."""
```

- Strip optional ` ```json ` fences with `re.sub`
- `json.loads(text)`
- Clamp each numeric field to its valid range
- Validate `filter_name` against the known set; fall back to `"original"` if unknown
- Validate `rotation` is in `{0, 90, 180, 270}`; fall back to `0`
- Raise `ValueError` with a clear message if JSON cannot be parsed at all

**Checkpoint:** test `ai_edit.py` standalone — call it from a plain Python script with a real image path and prompt, print the returned dict. No Qt needed.

---

## Phase 2 — In-App AI Edit UI

All changes are inside `widgets/edit_panel.py`.

### Step 5 — `_AiWorker` thread

Add a `QThread` subclass inside `edit_panel.py`:

```python
class _AiWorker(QThread):
    result_ready = pyqtSignal(dict)
    error        = pyqtSignal(str)

    def __init__(self, img: np.ndarray, prompt: str, api_key: str): ...
    def run(self) -> None:
        # encode_for_api → call_api → parse_edit_state
        # emit result_ready(dict) on success, error(str) on any exception
```

### Step 6 — AI row in `EditPanel._build_ui`

Add a new `QGroupBox("AI EDIT")` section at the bottom of the scrollable right panel, below FILTERS:

```
┌─────────────────────────────────┐
│  AI EDIT                        │
│  ┌─────────────────────────┐    │
│  │ describe the look...    │    │
│  └─────────────────────────┘    │
│  [✨ Apply]   status label       │
└─────────────────────────────────┘
```

Widgets:
- `QLineEdit` — placeholder `"describe the look you want…"`; `returnPressed` triggers apply
- `QPushButton("✨ Apply")` — disabled if `ANTHROPIC_API_KEY` is not set or a request is in flight
- `QLabel` — status text: empty at rest / `"Thinking…"` during call / `"Applied ✓"` on success / error text in red on failure

API key is read once at `EditPanel.__init__`:
```python
import os
self._api_key = os.environ.get("ANTHROPIC_API_KEY", "")
```
If empty, the button is disabled and its tooltip reads:
`"Set ANTHROPIC_API_KEY in your environment to enable AI editing"`.

### Step 7 — Slots

```python
def _on_ai_apply(self) -> None:
    # guard: no image loaded → return
    # disable button, clear status, show "Thinking…"
    # create _AiWorker(self._preview_img, prompt_text, self._api_key)
    # connect result_ready → _on_ai_result
    # connect error → _on_ai_error
    # start worker

def _on_ai_result(self, state_dict: dict) -> None:
    # block all slider signals
    # set each slider value from state_dict
    # set filter radio button
    # unblock signals
    # call _on_state_changed() once to trigger pipeline
    # re-enable button, set status "Applied ✓"

def _on_ai_error(self, message: str) -> None:
    # re-enable button, set status label to message in red
```

**Checkpoint:** open a photo in edit mode, type "make it black and white with high contrast", press Apply. Sliders should update and preview should change. Verify the button is disabled and re-enabled correctly.

---

## Phase 3 — MCP Server

### Step 8 — `mcp_server.py`

Standalone script in the project root. Uses the `mcp` Python SDK (add `mcp>=1.0` to `requirements.txt`).

Imports: `ai_edit`, `edit_ops`, `film_luts`, `cv2`, `numpy`, `base64`, `json`, `os`, `shutil`, `tempfile`. No Qt.

**Tool 1 — `get_image_info`**

```python
@server.tool()
def get_image_info(image_path: str) -> dict:
    # cv2.imread → get width, height, file_size
    # encode_for_api(img, max_side=400) → thumbnail_b64
    # return {"width", "height", "file_size_kb", "thumbnail_b64"}
```

**Tool 2 — `suggest_edits`**

```python
@server.tool()
def suggest_edits(image_path: str, prompt: str) -> str:
    # img_path_to_b64(image_path)
    # call_api(b64, prompt, api_key)
    # parse_edit_state(response) → dict
    # return json.dumps(dict, indent=2)
```

API key is read from `os.environ["ANTHROPIC_API_KEY"]` — raises a clear error if missing.

**Tool 3 — `apply_and_save`**

```python
@server.tool()
def apply_and_save(image_path: str, state_json: str, output_path: str) -> str:
    # json.loads(state_json) → build EditState dataclass
    # cv2.imread(image_path) full resolution
    # apply_pipeline(img, state)
    # os.stat(image_path) → capture timestamps
    # tempfile.mkstemp in output_path parent dir
    # cv2.imwrite(tmp, out)
    # shutil.move(tmp → output_path)
    # os.utime(output_path, original_timestamps)
    # return f"Saved: {output_path}"
```

Server entry point:

```python
if __name__ == "__main__":
    import mcp
    mcp.run(server)
```

**Checkpoint:** register the server with Claude Code, open a terminal, ask Claude to analyze and edit an image using natural language. Verify the output file is correct.

```bash
claude mcp add image-selector -- python /path/to/image-selector/mcp_server.py
```

---

## Phase 4 — Integration & Polish

### Step 9 — Manual test matrix

| Scenario | Expected |
|----------|----------|
| Prompt: "too dark, fix it" | `exposure` > 0, possibly `brightness` > 0 |
| Prompt: "convert to black and white" | `filter_name` = `"acros"` or `"neopan_1600"` |
| Prompt: "cinematic warm look" | `filter_name` = `"eterna"` or `"velvia"`, warm adjustments |
| Prompt: "fix white balance, too yellow" | `filter_name` = `"auto_wb"` or negative `saturation` + blue push |
| Prompt: "rotate left" | `rotation` = 270 |
| Prompt: gibberish / very vague | Should return valid JSON without crashing |
| No API key set | Button disabled, tooltip visible |
| Network error mid-call | Error shown in status label, sliders unchanged |
| MCP: suggest → tweak JSON → apply_and_save | Output file exists and looks correct |

### Step 10 — System prompt iteration

Run the test matrix above and adjust `SYSTEM_PROMPT` in `ai_edit.py` based on failures. The prompt is a constant — no code changes needed to the rest of the app.

### Step 11 — Docs update

- `docs/user-guide.md` — add **AI Edit** section: how to set the API key, how to use the text field, what kinds of prompts work well
- `docs/architecture.md` — add `ai_edit.py` and `mcp_server.py` to module map and key classes
- `docs/installation.md` — add MCP registration instructions under a new **Claude Code Integration** section
- `docs/versioning/v0.0.3/changelog.md` — write changelog once all tasks are done

---

## Deliverables

| File | Status |
|------|--------|
| `ai_edit.py` | pending |
| `mcp_server.py` | pending |
| `widgets/edit_panel.py` (AI row + worker) | pending |
| `requirements.txt` (anthropic, mcp) | pending |
| `docs/user-guide.md` | pending |
| `docs/architecture.md` | pending |
| `docs/installation.md` | pending |
| `docs/versioning/v0.0.3/changelog.md` | pending |
