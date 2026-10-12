# syntax=docker/dockerfile:1.7
# Serving engine: llama.cpp server (pinned) + a pinned GGUF model + the config supervisor.
# Build from the repo root: docker build -f images/serve/Dockerfile -t bench/serve:dev .
FROM ghcr.io/ggml-org/llama.cpp:server@sha256:23fd59bc5e5b06ca68003a5772d441f0411fb723eeaff850b9111bcd2ac4fd33

ADD --checksum=sha256:5a1395716f7913741cc51d98581b9b1228d80987a9f7d3664106742eb06bba83 \
    https://huggingface.co/bartowski/SmolLM2-135M-Instruct-GGUF/resolve/09816acd5d99df7be770d85ea30822623dab342c/SmolLM2-135M-Instruct-Q8_0.gguf \
    /models/model.gguf
RUN chmod 0444 /models/model.gguf

COPY images/serve/supervisor.sh /usr/local/bin/engine-supervisor
RUN chmod 0755 /usr/local/bin/engine-supervisor && mkdir -p /opt/engine \
    && { dpkg-query -W; sha256sum /app/llama-server /app/*.so* /models/model.gguf /usr/local/bin/engine-supervisor; } \
        > /opt/engine/BUILD.txt \
    && sha256sum /opt/engine/BUILD.txt | cut -c1-16 > /opt/engine/BUILD
ENTRYPOINT ["/usr/local/bin/engine-supervisor"]
