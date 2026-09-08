# Clean base image containing ComfyUI, comfy-cli and ComfyUI-Manager
FROM runpod/worker-comfyui:5.8.4-base


# ---------------------------------------------------------------------------
# ComfyUI installation
# ---------------------------------------------------------------------------

RUN pip install --no-cache-dir --upgrade comfy-cli

RUN comfy --workspace /comfyui update comfy --version 0.33.0

# Reinstall the Manager dependencies required by this ComfyUI release
RUN pip install --no-cache-dir \
    -r /comfyui/manager_requirements.txt


# ---------------------------------------------------------------------------
# Application Python dependencies
# ---------------------------------------------------------------------------

COPY requirements.txt /requirements.txt

RUN pip install --no-cache-dir \
    -r /requirements.txt


# ---------------------------------------------------------------------------
# Worker application
# ---------------------------------------------------------------------------

COPY handler.py /handler.py

COPY extra_model_paths.yaml /comfyui/extra_model_paths.yaml

COPY comfy-jobs/ /comfy-jobs/

RUN ls -lah /comfy-jobs/


# ---------------------------------------------------------------------------
# Build-time credentials
#
# Pass with:
# docker build --build-arg HF_TOKEN="$HF_TOKEN" ...
#
# This argument is not persisted as an environment variable in the image.
# ---------------------------------------------------------------------------

ARG HF_TOKEN=""


# ---------------------------------------------------------------------------
# Custom ComfyUI nodes
# ---------------------------------------------------------------------------

RUN comfy node install \
    --exit-on-fail \
    vsaan212-workflow-utilities \
    --mode remote

# RUN git clone \
#     https://github.com/BetaDoggo/comfyui-rtx-simple \
#     /comfyui/custom_nodes/comfyui-rtx-simple

# RUN pip install --no-cache-dir \
#     -r /comfyui/custom_nodes/comfyui-rtx-simple/requirements.txt


# ---------------------------------------------------------------------------
# Final PyTorch installation
#
# Install this after all ordinary requirements so they cannot replace the
# intended CUDA 13 PyTorch build.
# ---------------------------------------------------------------------------

RUN pip install --no-cache-dir --force-reinstall \
    torch==2.10.0 \
    torchvision==0.25.0 \
    torchaudio==2.10.0 \
    --index-url https://download.pytorch.org/whl/cu130


# ---------------------------------------------------------------------------
# CUDA/PyTorch memory management
#
# This can reduce fragmentation for the variable and very large allocations
# produced by video generation.
# ---------------------------------------------------------------------------

ENV PYTORCH_CUDA_ALLOC_CONF="expandable_segments:True"


RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        python3-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

ENV CC="/usr/bin/gcc"
ENV CXX="/usr/bin/g++"

# ---------------------------------------------------------------------------
# SageAttention
#
# RTX 5090 and RTX Pro 6000 Blackwell use compute capability 12.0.
# SageAttention must be built after the final PyTorch installation.
# ---------------------------------------------------------------------------

ENV TORCH_CUDA_ARCH_LIST="12.0"

RUN pip install --no-cache-dir \
    ninja \
    packaging

RUN pip install --no-cache-dir \
    sageattention==1.0.6


# ---------------------------------------------------------------------------
# Enable SageAttention in the inherited RunPod startup script
#
# The base image starts both ComfyUI and the RunPod handler through /start.sh.
# This modifies only the ComfyUI invocation and preserves the rest of the
# inherited worker lifecycle.
#
# The initial grep deliberately fails the build if RunPod changes the startup
# command in a future base-image release.
# ---------------------------------------------------------------------------

RUN grep -qE 'python(3)?( -u)? /comfyui/main.py' /start.sh \
    && sed -Ei \
        's|(python(3)?( -u)? /comfyui/main.py)|\1 --use-sage-attention|g' \
        /start.sh \
    && grep -n -- "--use-sage-attention " /start.sh

#--highvram add this for higher vram workloads, but it may cause issues with some nodes. If you encounter problems, remove this flag.

# ---------------------------------------------------------------------------
# Build-time verification
# ---------------------------------------------------------------------------

RUN python - <<'PY'
import torch
import torchvision
import torchaudio
import sageattention

print("PyTorch:", torch.__version__)
print("CUDA:", torch.version.cuda)
print("Torchvision:", torchvision.__version__)
print("Torchaudio:", torchaudio.__version__)
print("SageAttention:", sageattention.__file__)

assert torch.__version__.startswith("2.10.0"), torch.__version__
assert torch.version.cuda == "13.0", torch.version.cuda
PY

# Confirm this version of ComfyUI supports the launch flag
RUN cd /comfyui \
    && python main.py --help | grep -- "--use-sage-attention"


