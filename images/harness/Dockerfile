# Harness image: the runtime image plus provisioning and grading code (src/harness). Used only by a task's
# provisioning sidecar (which exits once the task is prepared), its object store, and the separate verifier.
# Agents never get a container from this image.
# Build from the repo root after the runtime image: docker build -f images/harness/Dockerfile -t bench/harness:dev .
ARG RUNTIME=bench/runtime:dev
FROM ${RUNTIME}
RUN uv pip install --system --python /usr/bin/python3.12 --no-cache pydantic==2.13.5
ARG SOURCE=unknown
COPY src/harness/ /opt/harness/harness/
COPY images/harness/entrypoint.sh /usr/local/bin/harness-entrypoint.sh
RUN chmod 0755 /usr/local/bin/harness-entrypoint.sh && echo "$SOURCE" > /opt/harness/VERSION \
    && python3 -m compileall -q /opt/harness
RUN set -eo pipefail; { rpm -qa | sort; uv pip freeze --system --python /usr/bin/python3.12; } \
        > /opt/harness/BUILD.txt && sha256sum /opt/harness/BUILD.txt | cut -c1-16 > /opt/harness/BUILD  # as in runtime
ENV PYTHONPATH=/opt/ocb:/opt/harness
ENTRYPOINT ["/usr/local/bin/harness-entrypoint.sh"]
