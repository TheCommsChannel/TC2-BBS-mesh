#!/usr/bin/env python3

"""
TC²-BBS Server for Meshtastic by TheCommsChannel (TC²)
Date: 06/25/2024
Version: 0.1.0

Description:
The system allows for mail message handling, bulletin boards, and a channel
directory. It uses a configuration file for setup details and an SQLite3
database for data storage. Mail messages and bulletins are synced with
other BBS servers listed in the config.ini file.
"""

import logging

from config_init import initialize_config, get_interface
from db_operations import initialize_database
from message_processing import on_receive
from pubsub import pub

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def display_banner():
    banner = """
████████╗ ██████╗██████╗       ██████╗ ██████╗ ███████╗
╚══██╔══╝██╔════╝╚════██╗      ██╔══██╗██╔══██╗██╔════╝
   ██║   ██║      █████╔╝█████╗██████╔╝██████╔╝███████╗
   ██║   ██║     ██╔═══╝ ╚════╝██╔══██╗██╔══██╗╚════██║
   ██║   ╚██████╗███████╗      ██████╔╝██████╔╝███████║
   ╚═╝    ╚═════╝╚══════╝      ╚═════╝ ╚═════╝ ╚══════╝
Meshtastic Version
"""
    print(banner)

def main():
    display_banner()
    config, interface_type, hostname, port, bbs_nodes = initialize_config()
    interface = get_interface(interface_type, hostname, port)
    interface.bbs_nodes = bbs_nodes

    logging.info(f"TC²-BBS is running on {interface_type} interface...")

    initialize_database()

    def receive_packet(packet):
        on_receive(packet, interface)

    pub.subscribe(receive_packet, 'meshtastic.receive')

    try:
        while True:
            pass
    except KeyboardInterrupt:
        logging.info("Shutting down the server...")
        interface.close()

if __name__ == "__main__":
    main()
