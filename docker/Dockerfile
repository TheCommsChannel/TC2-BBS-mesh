# From original Dockerfile at https://github.com/TheCommsChannel/TC2-BBS-mesh
FROM debian:stable-slim AS build

RUN apt-get update && \
  apt-get install -y \
  git \
  && apt-get clean && rm -rf /var/lib/apt/lists/*

# Clone the repository
# RUN git clone https://github.com/TheCommsChannel/TC2-BBS-mesh.git
COPY ./ /home/mesh/bbs/

####

FROM --platform=$BUILDPLATFORM python:alpine

# Switch to non-root user
RUN adduser --disabled-password mesh
USER mesh
RUN mkdir -p /home/mesh/bbs
WORKDIR /home/mesh/bbs

# Install Python dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir --break-system-packages -r requirements.txt

# Copy over app code
COPY *.py ./

# Define config volume
VOLUME /home/mesh/bbs/config
WORKDIR /home/mesh/bbs/config
COPY example_config.ini ./config.ini
COPY fortunes.txt ./

# Define the command to run
ENTRYPOINT [ "python3", "/home/mesh/bbs/server.py" ]
