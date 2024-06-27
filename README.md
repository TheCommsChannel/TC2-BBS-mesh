# TC²-BBS Meshtastic Version

[![ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/B0B1OZ22Z)

This is the TC²-BBS system integrated with Meshtastic devices. The system allows for message handling, bulletin boards, mail systems, and a channel directory.

## Setup

### Requirements

- Python 3.x
- Meshtastic
- pypubsub

### Installation

1. Clone the repository:

```sh
git clone https://github.com/TheCommsChannel/TC2-BBS-mesh.git
cd TC2-BBS-mesh
```

2. Set up a Python virtual environment:

```sh
python -m venv venv
```

3. Activate the virtual environment:
  

- On Windows:

```sh
venv\Scripts\activate
```

- On macOS and Linux:

```sh
source venv/bin/activate
```

4. Install the required packages:

```sh
pip install -r requirements.txt
```

5. Configuration
  - Copy config/config.init.sample to config/config.ini
  - Set up the configuration in `config.ini`:
   
  **[interface]**
  
  If using `type = serial` and you have multiple devices connected, you will need to uncomment the `port =` line and enter in the port of your device. 
  
  Linux Example:
  `port = /dev/ttyUSB0` 
  
  Windows Example:
  `port = COM3` 
  
  If using type = tcp you will need to uncomment the hostname = 192.168.x.x line and put in the IP address of your Meshtastic device 
  
  **[sync]**
  
  Enter in a list of other BBS nodes you would like to sync messages and bulletins with. Separate each by comma and no spaces as shown in the example below. 
  You can find the nodeID in the menu under `Radio Configuration > User` for each node, or use this script for getting nodedb data from a device:
  
  [Meshtastic-Python-Examples/print-nodedb.py at main · pdxlocations/Meshtastic-Python-Examples (github.com)](https://github.com/pdxlocations/Meshtastic-Python-Examples/blob/main/print-nodedb.py)

  Example Config:
```ini
[interface]
type = serial
# port = /dev/ttyUSB0 # or /dev/ttyACM0
# hostname = 192.168.x.x

[sync]
bbs_nodes = !f53f4abc,!f3abc123
```

### Running the Server

Run the server with:

```sh
python server.py
```

Be sure you've followed the Python virtual environment steps above and activated it before running.

## Docker
The docker entrypoint.sh will automatically copy config.ini.sample to config.ini
if you want to edit config, make sure you add the config directory as a docker volume.

Environment Variables: FORTUNE_FILE, DB_FILE, CONFIG_FILE

```sh
docker run -it --name tc2bbsmesh -v tc2bbsmesh-config:/app/config/ -v tc2bbsmesh-data:/app/data/  --device=/dev/ttyACM0 tc2-bbs-mesh
```

Tested on Orange Pi 3 LTS (Armbian), but should work on all linux distros.

## Features

- **Mail System**: Send and receive mail messages.
- **Bulletin Boards**: Post and view bulletins on various boards.
- **Channel Directory**: Add and view channels in the directory.
- **Statistics**: View statistics about nodes, hardware, and roles.
- **Wall of Shame**: View devices with low battery levels.
- **Fortune Teller**: Get a random fortune. Pulls from the fortunes.txt file. Feel free to edit this file remove or add more if you like.

## Thanks

Big thanks to [Meshtastic](https://github.com/meshtastic) and [pdxlocations](https://github.com/pdxlocations) for the great Python examples:

[python/examples at master · meshtastic/python (github.com)](https://github.com/meshtastic/python/tree/master/examples)

[pdxlocations/Meshtastic-Python-Examples (github.com)](https://github.com/pdxlocations/Meshtastic-Python-Examples)

## License

GNU General Public License v3.0
