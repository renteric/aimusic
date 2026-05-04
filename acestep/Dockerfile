##
## acestep/Dockerfile — ACE-Step 1.5 music generation microservice
##
## Wraps ACEStepPipeline in a minimal FastAPI server (app.py).
## Exposes port 8001 on the internal Docker network only.
##
## CPU-only build: installs the PyTorch + torchvision CPU wheels to avoid
## CUDA toolkit bloat and the "operator torchvision::nms does not exist"
## crash that occurs when torchvision is pulled from the default PyPI index.
##
## Model weights (~10 GB) are downloaded from Hugging Face on first run and
## cached in the named Docker volume `acestep-models`.
##

FROM python:3.11-slim

# System deps: git (install from VCS), ffmpeg (audio I/O), curl (healthcheck)
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        git \
        ffmpeg \
        curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install CPU-only PyTorch, torchaudio, and torchvision from the CPU wheel
# index.  All three MUST come from the same index so their C++ extensions match.
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir \
        torch==2.5.1 torchaudio==2.5.1 torchvision==0.20.1 \
        --index-url https://download.pytorch.org/whl/cpu

# Install ACE-Step 1.5.  Torch/torchvision are already satisfied above so pip
# will not re-download them from the default index.
RUN pip install --no-cache-dir \
        "git+https://github.com/ace-step/ACE-Step.git"

# FastAPI + Uvicorn for our wrapper server.
RUN pip install --no-cache-dir fastapi "uvicorn[standard]"

# Model weight cache — mapped to the named Docker volume acestep-models.
ENV HF_HOME=/app/models
ENV HUGGINGFACE_HUB_CACHE=/app/models/hub
ENV TORCH_HOME=/app/models/torch

# ACE-Step runtime config.
ENV ACESTEP_CHECKPOINT_PATH=""
ENV ACESTEP_DTYPE="float32"

COPY app.py /app/app.py

EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=15s --start-period=300s --retries=5 \
    CMD curl -sf http://localhost:8001/health || exit 1

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8001"]
