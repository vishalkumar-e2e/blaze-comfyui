import base64
import io
import json
import os
import time
import urllib.error
import urllib.request
import uuid
import wave

import numpy as np
from PIL import Image

try:
    import folder_paths
except ImportError:
    folder_paths = None

try:
    from comfy_api.input_impl import VideoFromFile
except ImportError:
    VideoFromFile = None

try:
    import comfy.model_management as model_management
except ImportError:
    model_management = None

DEFAULT_BASE_URL = "https://blaze.e2enetworks.net"
DEFAULT_MODEL = "MiniMaxAI/MiniMax-H3"
SIZES = ["768x1344", "1344x768", "768x768", "1024x768", "768x1024", "1344x576"]
POLL_SECONDS = 10
MAX_REQUEST_BYTES = 30 << 20


class BlazeError(RuntimeError):
    pass


def api_key():
    key = os.environ.get("BLAZE_API_KEY", "").strip()
    if not key:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "blaze_api_key.txt")
        if os.path.exists(path):
            with open(path) as handle:
                key = handle.read().strip()
    if not key:
        raise BlazeError("Blaze API key not found: set BLAZE_API_KEY or put it in custom_nodes/ComfyUI-Blaze/blaze_api_key.txt")
    return key


def call(method, url, key, body=None, timeout=120):
    headers = {"Authorization": "Bearer " + key}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    except urllib.error.HTTPError as error:
        raw = error.read()
        try:
            message = json.loads(raw)["error"]["message"]
        except Exception:
            message = raw.decode(errors="replace")[:300]
        raise BlazeError(f"Blaze API {error.code}: {message}") from None
    except urllib.error.URLError as error:
        raise BlazeError(f"Blaze API unreachable: {error.reason}") from None


def image_data_uri(image):
    pixels = np.clip(image.cpu().numpy() * 255.0, 0, 255).astype(np.uint8)
    buffer = io.BytesIO()
    Image.fromarray(pixels[..., :3]).save(buffer, format="JPEG", quality=95)
    return "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode()


def audio_data_uri(audio):
    waveform = audio["waveform"][0].cpu().float().numpy()
    if waveform.ndim == 1:
        waveform = waveform[None, :]
    samples = (np.clip(waveform.T, -1.0, 1.0) * 32767).astype("<i2")
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as out:
        out.setnchannels(samples.shape[1])
        out.setsampwidth(2)
        out.setframerate(int(audio["sample_rate"]))
        out.writeframes(samples.tobytes())
    return "data:audio/wav;base64," + base64.b64encode(buffer.getvalue()).decode()


def output_dir():
    root = folder_paths.get_output_directory() if folder_paths else os.path.join(os.getcwd(), "output")
    path = os.path.join(root, "blaze")
    os.makedirs(path, exist_ok=True)
    return path


def check_interrupted():
    if model_management is not None:
        model_management.throw_exception_if_processing_interrupted()


def build_request(prompt, seconds, size, seed, enhance_prompt, model, first_frame=None, last_frame=None, reference_images=None, voice=None):
    images = []
    if first_frame is not None:
        images.append({"url": image_data_uri(first_frame[0]), "type": "scene"})
    if last_frame is not None:
        images.append({"url": image_data_uri(last_frame[0]), "type": "end"})
    if reference_images is not None:
        images.extend({"url": image_data_uri(image), "type": "identity"} for image in reference_images)
    if len(images) > 9:
        raise BlazeError(f"At most 9 pictures per video; got {len(images)}")
    body = {"model": model, "prompt": prompt, "seconds": seconds, "size": size, "seed": seed,
            "enhance_prompt": enhance_prompt, "video_reference_key": "comfyui-" + uuid.uuid4().hex}
    if images:
        body["reference_images"] = images
    if voice is not None:
        body["audio_references"] = [{"url": audio_data_uri(voice)}]
    if len(json.dumps(body)) > MAX_REQUEST_BYTES:
        raise BlazeError("Pictures and voice together are too large (over 30 MB); use smaller pictures or a shorter voice clip")
    return body


def generate(base_url, body, timeout_minutes):
    key = api_key()
    base = base_url.rstrip("/")
    job = json.loads(call("POST", base + "/v1/videos", key, body))
    job_id = job["id"]
    deadline = time.time() + timeout_minutes * 60
    while job.get("status") not in ("succeeded", "failed", "cancelled"):
        if time.time() > deadline:
            raise BlazeError(f"Job {job_id} not finished after {timeout_minutes} minutes; check it later with GET /v1/videos/{job_id}")
        for _ in range(POLL_SECONDS):
            try:
                check_interrupted()
            except BaseException:
                try:
                    call("DELETE", f"{base}/v1/videos/{job_id}", key, timeout=15)
                except BlazeError:
                    pass
                raise
            time.sleep(1)
        job = json.loads(call("GET", f"{base}/v1/videos/{job_id}", key))
    if job["status"] != "succeeded":
        raise BlazeError(f"Job {job_id} {job['status']}: {job.get('error_code', '')} {job.get('error_message', '')}".strip())
    path = os.path.join(output_dir(), f"{job_id}.mp4")
    with open(path, "wb") as handle:
        handle.write(call("GET", f"{base}/v1/videos/{job_id}/content", key, timeout=600))
    return job_id, path


class BlazeVideo:
    CATEGORY = "Blaze"
    FUNCTION = "run"
    RETURN_TYPES = ("VIDEO", "STRING", "STRING")
    RETURN_NAMES = ("video", "video_path", "job_id")
    OUTPUT_NODE = True

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt": ("STRING", {"multiline": True, "default": ""}),
                "seconds": ("INT", {"default": 5, "min": 4, "max": 15}),
                "size": (SIZES, {"default": "768x1344"}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 2147483647}),
                "enhance_prompt": ("BOOLEAN", {"default": True}),
            },
            "optional": {
                "first_frame": ("IMAGE",),
                "last_frame": ("IMAGE",),
                "reference_images": ("IMAGE",),
                "voice": ("AUDIO",),
                "base_url": ("STRING", {"default": DEFAULT_BASE_URL}),
                "model": ("STRING", {"default": DEFAULT_MODEL}),
                "timeout_minutes": ("INT", {"default": 30, "min": 1, "max": 120}),
            },
        }

    def run(self, prompt, seconds, size, seed, enhance_prompt, first_frame=None, last_frame=None,
            reference_images=None, voice=None, base_url=DEFAULT_BASE_URL, model=DEFAULT_MODEL, timeout_minutes=30):
        if not prompt.strip():
            raise BlazeError("Prompt is empty")
        body = build_request(prompt, seconds, size, seed, enhance_prompt, model, first_frame, last_frame, reference_images, voice)
        job_id, path = generate(base_url, body, timeout_minutes)
        video = VideoFromFile(path) if VideoFromFile is not None else None
        return {"ui": {"text": [f"{job_id}: {path}"]}, "result": (video, path, job_id)}


NODE_CLASS_MAPPINGS = {"BlazeVideo": BlazeVideo}
NODE_DISPLAY_NAME_MAPPINGS = {"BlazeVideo": "Blaze Video (MiniMax H3)"}
