FROM alpine:latest

# Install required packages
RUN apk add --update --no-cache git python3 py3-pip

# Clone the repository
RUN git clone https://github.com/TheCommsChannel/TC2-BBS-mesh.git

# Install Python dependencies
RUN pip install --no-cache-dir --break-system-packages -r /TC2-BBS-mesh/requirements.txt

# Copy configuration script
COPY configini.sh /

# Set permissions for configuration script
RUN chmod +x /configini.sh

# Define config volume
VOLUME /config

# Define working directory
WORKDIR /config

# Define the command to run
CMD ["sh", "-c", " /configini.sh &&  python3 /TC2-BBS-mesh/server.py"]