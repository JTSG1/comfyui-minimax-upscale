import os
from pathlib import Path
import shutil
import subprocess

import urllib

import runpod
import base64
import json
import socket
import time

COMFYUI_INPUT_DIR = Path("/comfyui/input")
COMFYUI_OUTPUT_DIR = Path("/comfyui/output")
PERSISTENT_OUTPUT_DIR = Path("/runpod-volume/outputs")

COMFYUI_INPUT_DIR.mkdir(parents=True, exist_ok=True)

# WORKFLOW_PATH = Path("/comfy-jobs/minimax+upscale.json")
WORKFLOW_PATH = Path("/comfy-jobs/minimax+lora.json")


def decode_input(input_data):

    # Decode the base64-encoded input data
    decoded_bytes = base64.b64decode(input_data)
    return decoded_bytes


def detect_image_type(decoded_bytes):
    if decoded_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return "PNG"
    elif decoded_bytes.startswith(b"\xff\xd8\xff"):
        return "JPEG"
    elif decoded_bytes.startswith((b"GIF87a", b"GIF89a")):
        return "GIF"
    else:
        return "Unknown"


def save_decoded_input(decoded_bytes, filename):
    # Save the decoded input to a file
    with open(filename, "wb") as f:
        f.write(decoded_bytes)


def submit_workflow_direct(workflow):
    payload = json.dumps({
        "prompt": workflow
    }).encode("utf-8")

    request = urllib.request.Request(
        "http://127.0.0.1:8188/prompt",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8")
            print(f"Comfy response: {body}", flush=True)
            return json.loads(body)

    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")

        print(
            f"Comfy HTTP {e.code}: {body}",
            flush=True
        )

        raise RuntimeError(
            f"Comfy HTTP {e.code}: {body}"
        ) from e


def wait_for_comfyui_prompt(prompt_id, timeout=7200):
    print(f"Waiting for Comfy prompt {prompt_id}...", flush=True)
    start_time = time.time()

    while time.time() - start_time < timeout:
        url = f"http://127.0.0.1:8188/history/{prompt_id}"

        with urllib.request.urlopen(url, timeout=30) as response:
            history = json.loads(response.read().decode("utf-8"))

        prompt_history = history.get(prompt_id)

        if prompt_history:
            status = prompt_history.get("status", {})
            status_str = status.get("status_str")

            # Fail immediately
            if status_str in ("error", "failed"):
                raise RuntimeError(
                    f"Comfy workflow failed: "
                    f"{json.dumps(prompt_history)}"
                )

            # Success
            if status.get("completed"):
                if status_str != "success":
                    raise RuntimeError(
                        f"Comfy workflow ended unexpectedly: "
                        f"{json.dumps(prompt_history)}"
                    )

                print(
                    f"Comfy prompt completed: {status_str}",
                    flush=True
                )
                return prompt_history

        time.sleep(1)

    raise TimeoutError(
        f"Comfy prompt {prompt_id} did not complete "
        f"within {timeout} seconds."
    )


def invoke_comfyui_workflow(
    job_id,
    generation_prompt,
    image_0_filename,
    image_1_filename,
    audio_0_filename,
    megapixels=1,
    length=10
):
    with open(WORKFLOW_PATH, "r") as f:
        workflow = json.load(f)

    # Inject generation prompt
    workflow["138"]["inputs"]["value"] = generation_prompt

    # Give this job a unique output path
    workflow["92"]["inputs"]["filename_prefix"] = (
        f"video/{job_id}/MiniMax_H3"
    )

    # Inject actual input filenames
    workflow["137"]["inputs"]["image"] = image_0_filename
    workflow["139"]["inputs"]["image"] = image_1_filename
    workflow["142"]["inputs"]["audio"] = audio_0_filename
    workflow["115"]["inputs"]["megapixels"] = megapixels
    workflow["132"]["inputs"]["value"] = length

    result = submit_workflow_direct(workflow)

    prompt_id = result["prompt_id"]

    print(f"Submitted Comfy prompt: {prompt_id}", flush=True)

    wait_for_comfyui_prompt(prompt_id)

    print(f"Comfy prompt finished: {prompt_id}", flush=True)


def get_workflow_output(job_id):
    output_dir = COMFYUI_OUTPUT_DIR / "video" / str(job_id)

    outputs = list(
        output_dir.glob("MiniMax_H3_*")
    )

    if not outputs:
        raise FileNotFoundError(
            f"No output found for job {job_id}"
        )

    return max(
        outputs,
        key=lambda path: path.stat().st_mtime
    )


def process_input(
    input_data,
    job_id,
    input_name,
    file_extension,
    is_image=True
):
    if input_data is None:
        raise ValueError(f"'{input_name}' is missing.")

    decoded_input = decode_input(input_data)

    if is_image and detect_image_type(decoded_input) == "Unknown":
        raise ValueError(f"'{input_name}' is not a valid image format.")

    filename = f"{job_id}_{input_name}.{file_extension}"

    save_decoded_input(
        decoded_input,
        COMFYUI_INPUT_DIR / filename
    )

    print(f"Decoded {input_name} and saved to {filename}")

    return filename


def copy_output_to_persistent_storage(job_id, output_file):
    persistent_job_dir = PERSISTENT_OUTPUT_DIR / str(job_id)
    persistent_job_dir.mkdir(parents=True, exist_ok=True)

    persistent_output = persistent_job_dir / output_file.name

    shutil.copy2(
        output_file,
        persistent_output
    )

    print(f"Persistent output: {persistent_output}")

    return persistent_output


def wait_for_comfyui(
    host="127.0.0.1",
    port=8188,
    timeout=120
):
    print("Waiting for ComfyUI to become ready...")

    start_time = time.time()

    while time.time() - start_time < timeout:
        try:
            with socket.create_connection((host, port), timeout=1):
                print("ComfyUI is ready.")
                return
        except OSError:
            time.sleep(1)

    raise TimeoutError(
        f"ComfyUI did not become ready within {timeout} seconds."
    )


def handler(job):

    job_id = job["id"]

    generation_prompt = job["input"].get(
        "generation_prompt",
        None
    )

    ref_image_0 = job["input"].get(
        "ref_image_0",
        None
    )

    ref_image_1 = job["input"].get(
        "ref_image_1",
        None
    )

    ref_audio_0 = job["input"].get(
        "ref_audio_0",
        None
    )

    megapixels = float(job["input"].get(
        "megapixels",
        1.0
    ))

    length = int(job["input"].get(
        "length",
        10
    ))

    if generation_prompt is None:
        return {
            "job_id": job_id,
            "status": "error",
            "error": "'generation_prompt' is missing."
        }

    try:
        image_0_filename = process_input(
            ref_image_0,
            job_id,
            "ref_image_0",
            "dat",
            is_image=True
        )

        image_1_filename = process_input(
            ref_image_1,
            job_id,
            "ref_image_1",
            "dat",
            is_image=True
        )

        audio_0_filename = process_input(
            ref_audio_0,
            job_id,
            "ref_audio_0",
            "wav",
            is_image=False
        )

    except ValueError as e:
        return {
            "job_id": job_id,
            "status": "error",
            "error": str(e)
        }

    invoke_comfyui_workflow(
        job_id,
        generation_prompt,
        image_0_filename,
        image_1_filename,
        audio_0_filename,
        megapixels,
        length
    )

    output_file = get_workflow_output(job_id)

    print(f"Output file: {output_file}")

    persistent_output = copy_output_to_persistent_storage(
        job_id,
        output_file
    )

    return {
        "job_id": job_id,
        "status": "completed",
        "output_file": str(persistent_output)
    }


wait_for_comfyui()

runpod.serverless.start({
    "handler": handler
})