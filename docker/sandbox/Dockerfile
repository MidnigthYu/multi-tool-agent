# syntax=docker/dockerfile:1
FROM python:3.12-slim

LABEL maintainer="multi-tool-agent" \
      description="Python 3.12 sandbox for secure code execution"

# Install pre-approved libraries
RUN pip install --no-cache-dir numpy pandas

# Remove network tools and package manager for security
RUN apt-get update \
    && apt-get remove -y wget curl netcat-openbsd telnet ftp socat 2>/dev/null || true \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/* /usr/share/doc /usr/share/man

# Create non-root sandbox user
RUN groupadd -r sandbox && useradd -r -g sandbox -m -d /home/sandbox -s /sbin/nologin sandbox \
    && chmod 755 /home/sandbox

# Create tmp directory for code files
RUN mkdir -p /tmp && chmod 777 /tmp

# Remove dangerous system binaries
RUN rm -f /usr/bin/apt /usr/bin/apt-get /usr/bin/dpkg /usr/bin/dpkg-deb 2>/dev/null || true

# Copy entrypoint
COPY docker/sandbox/entrypoint.py /entrypoint.py
RUN chmod 755 /entrypoint.py && chown root:root /entrypoint.py

# Set unbuffered output
ENV PYTHONUNBUFFERED=1 \
    SANDBOX_SOFT_TIMEOUT_S=20 \
    SANDBOX_MAX_OUTPUT_CHARS=10000

USER sandbox
WORKDIR /home/sandbox

ENTRYPOINT ["python3", "-u", "/entrypoint.py"]
