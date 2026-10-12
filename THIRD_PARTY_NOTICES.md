# Third-party notices

The repository's own code is Apache-2.0 (LICENSE, NOTICE). The images `make image` builds include the following
third-party components, each under its own license (checked at the source on 2026-10-02).

| Component | Where | License | Source |
|---|---|---|---|
| Slurm 26.05.2 | runtime image (controller, nodes, workstation clients) | GPL-2.0-or-later, with an OpenSSL linking exception | https://github.com/SchedMD/slurm/tree/slurm-26-05-2-1 |
| slurm-docker-cluster | runtime image (base layout) | MIT | https://github.com/giovtorres/slurm-docker-cluster |
| PyTorch 2.14.1 (CPU; CUDA build for the GPU track) | runtime image | BSD-3-Clause style | https://github.com/pytorch/pytorch |
| py-spy | runtime image | MIT | https://github.com/benfred/py-spy |
| uv | image builds | Apache-2.0 or MIT | https://github.com/astral-sh/uv |
| llama.cpp server (pinned by digest) | serve image | MIT | https://github.com/ggml-org/llama.cpp |
| SmolLM2-135M-Instruct, Q8_0 GGUF (pinned by revision) | serve image | Apache-2.0 | https://huggingface.co/HuggingFaceTB/SmolLM2-135M-Instruct, https://huggingface.co/bartowski/SmolLM2-135M-Instruct-GGUF |

Python packages installed into the images are listed, with versions, in each image's build (`uv.lock` for the host
tools); their licenses are permissive (MIT, BSD, Apache-2.0). Slurm is distributed in binary form inside the runtime
image; its complete corresponding source is at the tag above.
