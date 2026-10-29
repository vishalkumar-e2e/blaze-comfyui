# Blaze Video for ComfyUI

A ComfyUI custom node that makes videos with sound using the [Blaze](https://blaze.e2enetworks.net) Video API (MiniMax H3). Send a prompt, a first-frame picture and a voice clip, and get the finished MP4 back in your workflow.

## Install

**ComfyUI Manager:** Manager → **Install via Git URL** → `https://github.com/vishalkumar-e2e/blaze-comfyui.git` → Restart.

**By hand:**
```bash
cd ComfyUI/custom_nodes
git clone https://github.com/vishalkumar-e2e/blaze-comfyui.git
```
Then restart ComfyUI. No extra Python packages are needed.

## API key

The key is never a node field, because ComfyUI saves node fields into workflow files and image metadata. Use one of these:
- the environment variable `BLAZE_API_KEY`; or
- a file `custom_nodes/blaze-comfyui/blaze_api_key.txt` containing only the key (it is git-ignored).

## Use

1. Double-click the canvas, search **Blaze Video**, and add it.
2. Connect **Load Image** to `first_frame`. Optionally connect **Load Audio** to `voice`.
3. Write the prompt, and set seconds, size and seed. Keep `enhance_prompt` on.
4. Connect `video` to **Save Video** to watch the result.
5. Queue it. A 5 s clip usually takes 1 to 2 minutes.

```
Load Image ──► Blaze Video.first_frame
Load Audio ──► Blaze Video.voice            (optional)
Blaze Video.video ──► Save Video
```

## Inputs

| Input | Notes |
|---|---|
| `prompt` | The scene prompt |
| `seconds` | 4 to 15 |
| `size` | 768x1344 (9:16), 1344x768 (16:9), 768x768, 1024x768, 768x1024, 1344x576 |
| `seed` | Use the same seed across scenes for a consistent look |
| `enhance_prompt` | On (default): Blaze rewrites the prompt into the form the model works best with |
| `first_frame` | Optional. The clip opens exactly on this picture |
| `last_frame` | Optional. The clip ends on this picture |
| `reference_images` | Optional. Pictures that show how people and places look |
| `voice` | Optional. The speaker's voice clip |
| `base_url` | Default `https://blaze.e2enetworks.net` |
| `model` | Default `MiniMaxAI/MiniMax-H3` |
| `timeout_minutes` | Default 30 |

## Outputs

| Output | |
|---|---|
| `video` | ComfyUI VIDEO, for Save Video or Preview Video |
| `video_path` | `ComfyUI/output/blaze/<job_id>.mp4` |
| `job_id` | The Blaze job id |

## Notes

- Pictures and voice are sent inside the request: at most 9 pictures and about 30 MB in total.
- Cancelling the run in ComfyUI cancels the Blaze job if it has not started yet.
- Errors show the API's own message, for example `Blaze API 401` (key) or `Blaze API 429` (too many jobs queued).
