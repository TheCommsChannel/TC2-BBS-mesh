# First stage: Base build environment
FROM debian:stable-slim AS build

# Install required dependencies
RUN apt-get update && \
    apt-get install -y git && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Ensure the 'games' directory exists
RUN mkdir -p /home/mesh/bbs/games

# Set working directory
WORKDIR /home/mesh/bbs

# Copy project files including 'games' directory
COPY . /home/mesh/bbs/

# Second stage: Final runtime environment
FROM python:alpine

# Add a non-root user for security
RUN adduser --disabled-password mesh

# Ensure working directory
RUN mkdir -p /home/mesh/bbs
WORKDIR /home/mesh/bbs

# Copy files from the build stage
COPY --from=build /home/mesh/bbs /home/mesh/bbs/

# Install Python dependencies
RUN pip install --no-cache-dir --break-system-packages -r requirements.txt

# Ensure the 'games' directory exists in runtime container
RUN mkdir -p /home/mesh/bbs/games

# Set user to mesh
USER mesh

# Expose necessary ports
EXPOSE 8080

# Start the server
CMD ["python", "server.py"]

