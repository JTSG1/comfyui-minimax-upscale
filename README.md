# MiniMax H3 reference-to-video

RunPod Serverless worker for generating MiniMax H3 videos from two reference
images, one reference audio file, and a text prompt. The worker runs ComfyUI
inside the Docker image and submits the active workflow from
`comfy-jobs/minimax+lora.json`.

## Deploy on RunPod

1. Connect this repository at <https://runpod.io/console/serverless>.
2. Create an endpoint and select **Deploy from GitHub**.
3. Select the `main` branch.
4. RunPod builds the `Dockerfile` and hosts the resulting image.

If the workflow uses gated Hugging Face or CivitAI models, provide the tokens
as build arguments:

```bash
docker build \
    --build-arg HF_TOKEN="$HF_TOKEN" \
    --build-arg CIVITAI_API_KEY="$CIVITAI_API_KEY" \
    -t my-comfy-workflow .
```

## Run locally

```bash
docker build -t my-comfy-workflow .
docker run --rm --gpus all -p 8188:8188 my-comfy-workflow
```

## Worker input

Submit a RunPod job with the following `input` object. Image and audio values
must be base64-encoded file contents.

```json
{
    "generation_prompt": "Describe the video to generate",
    "ref_image_0": "base64-encoded reference image",
    "ref_image_1": "base64-encoded reference image",
    "ref_audio_0": "base64-encoded reference audio",
    "megapixels": 1.0,
    "length": 10
}
```

`generation_prompt`, `ref_image_0`, `ref_image_1`, and `ref_audio_0` are
required. `megapixels` defaults to `1.0`, and `length` defaults to `10`.

The worker returns the generated video path under `/runpod-volume/outputs/`.

## Submit with the CLI

The helper in `util/submit.py` submits the same input contract and prints an
AWS CLI command for downloading the result from RunPod object storage.

```bash
export RUNPOD_API_KEY=...
python util/submit.py \
    --output ./outputs \
    --prompt ./prompt.txt \
    --ref-image-0 ./reference-0.png \
    --ref-image-1 ./reference-1.png \
    --ref-audio-0 ./reference.wav \
    --length 10
```

## Repository files

- `Dockerfile` - ComfyUI image and model setup.
- `handler.py` - RunPod handler, input decoding, workflow execution, and output persistence.
- `comfy-jobs/minimax+lora.json` - Active ComfyUI API workflow used by the handler.
- `comfy-jobs/minimax+upscale.json` - Alternate ComfyUI API workflow.
- `workflow.json` - Original ComfyUI workflow export.
- `util/submit.py` - Command-line submission and result polling utility.