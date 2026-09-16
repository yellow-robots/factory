# The image `check` runs the checkout's tests in: python and the checkout's own locked dependencies,
# nothing else. The checkout is the build context, so the lock that is installed here is the lock
# the checkout ships; the image name is the hash of this file and that lock, so a change to either
# is a different image. The checkout itself is not copied in: it is mounted read-only at /w at run
# time, with no network.
FROM python:3.12-slim
# git, because the checkout's own tests drive git (the record's diff.patch is made with it); the
# container has no network, so nothing here can fetch anything.
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /lock
COPY pyproject.toml uv.lock ./
RUN pip install --no-cache-dir uv \
    && uv export --frozen --no-hashes --no-dev -o /tmp/req.txt \
    && pip install --no-cache-dir -r /tmp/req.txt
WORKDIR /w
