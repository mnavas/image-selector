# v0.0.3 — Changelog

## New features

### AI Edit (in-app)

- Added **AI EDIT** section at the bottom of the right-hand panel in edit mode
- User types a natural-language prompt (e.g. "warm cinematic look", "too dark fix it") and presses **✨ Apply**
- Claude (`claude-opus-4-7`) analyses a 768 px JPEG of the current image and returns a complete `EditState` as JSON
- All sliders and the active filter update automatically; the user can tweak manually before saving
- The API call runs in a `QThread` (`_AiWorker`) — UI stays responsive during the request
- The **✨ Apply** button is disabled with an explanatory tooltip if `ANTHROPIC_API_KEY` is not set in the environment
- Status label shows `Thinking…` during the call, `Applied ✓` on success, or the error message in red on failure
- `Enter` in the prompt field also triggers the call

### MCP server for Claude Code (`mcp_server.py`)

- New standalone MCP server that exposes the edit pipeline to Claude Code without opening the app
- Three tools:
  - `get_image_info(image_path)` — width, height, file size, 400 px base64 thumbnail
  - `suggest_edits(image_path, prompt)` — calls Claude and returns the EditState JSON string
  - `apply_and_save(image_path, state_json, output_path)` — applies the pipeline at full resolution and saves atomically (tempfile + rename + timestamp preserve)
- Register with: `claude mcp add image-selector -- python /path/to/mcp_server.py`
- No Qt dependency — imports `edit_ops` and `ai_edit` directly

### `ai_edit.py` (new module)

- Pure Python, no Qt — shared between the in-app button and the MCP server
- `encode_for_api(img, max_side=768)` — downscale + JPEG encode → base64
- `call_api(img_b64, prompt, api_key, model)` — Anthropic API call with vision
- `parse_edit_state(text)` — strips markdown fences, parses JSON, clamps all values to valid ranges, validates `filter_name` and `rotation`
- `SYSTEM_PROMPT` constant — instructs Claude to return a bare JSON object with the exact `EditState` schema

## Changes to existing files

| File | Change |
|------|--------|
| `widgets/edit_panel.py` | Added `_AiWorker` thread class; added AI EDIT group box (QLineEdit + button + status label) to the scrollable right panel; added `_on_ai_apply`, `_on_ai_result`, `_on_ai_error` slots; added `QLineEdit` and `QThread` imports |
| `requirements.txt` | Added `anthropic>=0.40` and `mcp>=1.0` |
| `docs/user-guide.md` | Added **AI Edit** section with setup instructions, usage, and example prompts |
| `docs/architecture.md` | Added `ai_edit.py` and `mcp_server.py` to module map; added `ai_edit.py`, `_AiWorker`, and `mcp_server.py` to Key Classes section |
| `docs/installation.md` | Added **AI Edit feature** section (API key setup) and **Claude Code MCP integration** section (registration, tools, example session); updated dependencies table |

## Implementation notes

- `anthropic` is imported lazily inside `ai_edit.call_api` — the app starts normally even if the package is missing
- The MCP server reads `ANTHROPIC_API_KEY` from the environment and raises a clear `EnvironmentError` if absent
- `crop_rect` is intentionally excluded from the AI response — spatial crop requires interactive feedback
- `rotation` is included but only applied when the user explicitly asks to rotate
