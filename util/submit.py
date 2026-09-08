import os
import time
import base64
import shlex
from pathlib import Path

import click
import requests
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)

ENDPOINT_ID = "i4n1fzy61hw3de"
BASE_URL = f"https://api.runpod.ai/v2/{ENDPOINT_ID}"

S3_ENDPOINT_URL = os.environ.get("S3_ENDPOINT_URL", "https://s3.us-west-1.runpod.net")
S3_BUCKET = os.environ.get("S3_BUCKET", "2yo4q37bsd")

API_KEY = os.environ["RUNPOD_API_KEY"]

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
}


def read_base64_file(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def print_download_command(output_file, destination_dir):
    s3_key = output_file.removeprefix("/runpod-volume/")
    destination_path = Path(destination_dir) / Path(output_file).name
    command = [
        "aws",
        "s3",
        "cp",
        "--endpoint-url",
        S3_ENDPOINT_URL,
        f"s3://{S3_BUCKET}/{s3_key.lstrip('/')}",
        str(destination_path),
    ]
    print("\nDownload command:")
    print(" ".join(shlex.quote(argument) for argument in command))


def submit_job(prompt_path, ref_image_0_path, ref_image_1_path, ref_audio_0_path, length=10):
    with open(prompt_path, "r", encoding="utf-8") as f:
        generation_prompt = f.read()

    payload = {
        "input": {
            "generation_prompt": generation_prompt,
            "ref_image_0": read_base64_file(ref_image_0_path),
            "ref_image_1": read_base64_file(ref_image_1_path),
            "ref_audio_0": read_base64_file(ref_audio_0_path),
            "megapixels": 1.0,
            "length": length
        },
        "policy": {
            "executionTimeout": 7200000
        }
    }

    response = requests.post(
        f"{BASE_URL}/run",
        headers=HEADERS,
        json=payload,
        timeout=60,
    )

    if not response.ok:
        raise RuntimeError(
            f"RunPod rejected the job ({response.status_code}): "
            f"{response.text}"
        )

    result = response.json()

    job_id = result["id"]

    print(f"Submitted job: {job_id}")

    return job_id


def wait_for_job(job_id, poll_interval=10):
    observed_at = {}

    with Progress(
        SpinnerColumn(),
        TextColumn("{task.description}"),
        BarColumn(),
        TimeElapsedColumn(),
    ) as progress:
        task_id = progress.add_task("Checking job status", total=None)

        while True:
            response = requests.get(
                f"{BASE_URL}/status/{job_id}",
                headers=HEADERS,
                timeout=30,
            )

            response.raise_for_status()

            result = response.json()
            status = result.get("status")

            if status in {"IN_QUEUE", "IN_PROGRESS", "COMPLETED"}:
                observed_at.setdefault(status, time.monotonic())

            progress.update(task_id, description=f"{status}")

            if status == "COMPLETED":
                queued_to_progress = None
                progress_to_completed = None

                if "IN_QUEUE" in observed_at and "IN_PROGRESS" in observed_at:
                    queued_to_progress = (
                        observed_at["IN_PROGRESS"] - observed_at["IN_QUEUE"]
                    )

                if "IN_PROGRESS" in observed_at:
                    progress_to_completed = (
                        observed_at["COMPLETED"] - observed_at["IN_PROGRESS"]
                    )

                result["timing"] = {
                    "in_queue_to_in_progress_seconds": queued_to_progress,
                    "in_progress_to_completed_seconds": progress_to_completed,
                }

                print("Job completed!")
                print(
                    "IN_QUEUE -> IN_PROGRESS: "
                    f"{queued_to_progress:.1f}s"
                    if queued_to_progress is not None
                    else "IN_QUEUE -> IN_PROGRESS: unavailable"
                )
                print(
                    "IN_PROGRESS -> COMPLETED: "
                    f"{progress_to_completed:.1f}s"
                    if progress_to_completed is not None
                    else "IN_PROGRESS -> COMPLETED: unavailable"
                )
                return result

            if status in {
                "FAILED",
                "TIMED_OUT",
                "CANCELLED",
            }:
                raise RuntimeError(
                    f"Job ended with status {status}: {result}"
                )

            time.sleep(poll_interval)


@click.command()
@click.option(
    "--output",
    "output_path",
    type=click.Path(file_okay=False, path_type=str),
    required=True,
    help="Local directory where the generated file should be downloaded.",
)
@click.option(
    "--prompt",
    type=click.Path(exists=True, dir_okay=False, path_type=str),
    required=True,
    help="Path to the generation prompt file.",
)
@click.option(
    "--ref-image-0",
    type=click.Path(exists=True, dir_okay=False, path_type=str),
    required=True,
    help="Path to the first reference image.",
)
@click.option(
    "--ref-image-1",
    type=click.Path(exists=True, dir_okay=False, path_type=str),
    required=True,
    help="Path to the second reference image.",
)
@click.option(
    "--ref-audio-0",
    type=click.Path(exists=True, dir_okay=False, path_type=str),
    required=True,
    help="Path to the reference audio file.",
)
@click.option(
    "--length",
    type=int,
    default=10,
    help="Length of the generated video.",
)
def main(output_path, prompt, ref_image_0, ref_image_1, ref_audio_0, length):
    job_id = submit_job(prompt, ref_image_0, ref_image_1, ref_audio_0, length=length)

    result = wait_for_job(job_id)
    output_file = result["output"]["output_file"]
    print_download_command(output_file, output_path)

    print("\nResult:")
    print(result)


if __name__ == "__main__":
    main()