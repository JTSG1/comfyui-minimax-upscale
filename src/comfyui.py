from pathlib import Path
import json
import socket
import time
import urllib.error
import urllib.request

COMFYUI_OUTPUT_DIR = Path("/comfyui/output")

# WORKFLOW_PATH = Path("/comfy-jobs/minimax+upscale.json")
WORKFLOW_PATH = Path("/comfy-jobs/minimax+lora.json")


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

            if status_str in ("error", "failed"):
                raise RuntimeError(
                    f"Comfy workflow failed: "
                    f"{json.dumps(prompt_history)}"
                )

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
    megapixels=1.0,
    length=10
):
    with open(WORKFLOW_PATH, "r") as f:
        workflow = json.load(f)

    workflow["138"]["inputs"]["value"] = generation_prompt
    workflow["92"]["inputs"]["filename_prefix"] = (
        f"video/{job_id}/MiniMax_H3"
    )
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
    outputs = list(output_dir.glob("MiniMax_H3_*"))

    if not outputs:
        raise FileNotFoundError(
            f"No output found for job {job_id}"
        )

    return max(
        outputs,
        key=lambda path: path.stat().st_mtime
    )


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