
from pathlib import Path
import shutil
import boto3
import runpod
import base64

from comfyui import (
    COMFYUI_OUTPUT_DIR,
    get_workflow_output,
    invoke_comfyui_workflow,
    wait_for_comfyui,
)

COMFYUI_INPUT_DIR = Path("/comfyui/input")
PERSISTENT_OUTPUT_DIR = Path("/runpod-volume/outputs")

COMFYUI_INPUT_DIR.mkdir(parents=True, exist_ok=True)


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

    try:

        persistent_job_dir = PERSISTENT_OUTPUT_DIR / str(job_id)
        persistent_job_dir.mkdir(parents=True, exist_ok=True)

        persistent_output = persistent_job_dir / output_file.name

        shutil.copy2(
            output_file,
            persistent_output
        )

        print(f"Persistent output: {persistent_output}")

    finally:
        # Clean up ComfyUI output directory
        try:
            shutil.rmtree(COMFYUI_OUTPUT_DIR / "video" / str(job_id))
            print(f"Cleaned up ComfyUI output for job {job_id}")
        except Exception as e:
            print(
                f"Failed to clean up ComfyUI output for job {job_id}: {e}",
                flush=True
            )

    return persistent_output


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