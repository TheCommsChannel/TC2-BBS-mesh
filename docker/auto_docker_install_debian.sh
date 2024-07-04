#!/bin/bash
# Check if the script is run as root
if [ "$EUID" -ne 0 ]; then
    echo -e "\e[31mERROR: This script must be run as root. Please switch to root using 'sudo -i' or 'su - root' and try again.\e[0m"
    exit 1
fi
if ! systemctl status docker &> /dev/null; then
    echo -e "\e[32mINFO: Install Docker...\e[0m"
    apt-get install curl -y
    curl -fsSL https://get.docker.com | bash
fi
echo -e "\e[32mINFO: Docker is installed!\e[0m"
if [ -e "./TC2-BBS-mesh-docker/docker-compose.yaml" ]; then
    echo -e "\e[32mINFO: TC2-BBS-mesh-docker folder is already present!\e[0m"
else
        echo -e "\e[32mINFO: Installing TC2-BBS-mesh Docker Container in $(pwd)/TC2-BBS-mesh-docker ...\e[0m"
    mkdir ./TC2-BBS-mesh-docker
        cd TC2-BBS-mesh-docker
        cat << EOF > docker-compose.yaml
services:
  tc2-bbs-mesh:
    image: thealhu/tc2-bbs-mesh:latest
    restart: always
    volumes:
      - ./config:/config
    container_name: tc2-bbs-mesh
 # -- These parameters are optional and can be uncommented if needed. --
 #   devices:
 #     - /dev/ttyUSB0:/dev/ttyUSB0
 #     - /dev/ttyACM0:/dev/ttyACM0
EOF
        docker compose up
        echo "" &&      echo ""
        echo -e "\e[32mINFO: The TC2-BBS-mesh Docker container is now installed in $(pwd)/\e[0m"
        echo -e "\e[32mINFO: Please make your changes to the configuration and then run ""$""docker compose up -d in $(pwd)/\e[0m"
fi