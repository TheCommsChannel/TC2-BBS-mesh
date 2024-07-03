#!/usr/bin/env python3

"""
TC²-BBS Server for Meshtastic by TheCommsChannel (TC²)
Date: 03/07/2024
Yorkshire BBS Edition
Version: 0.1.04_Dev

Description:
The system allows for mail message handling, bulletin boards, and a channel
directory. It uses a configuration file for setup details and an SQLite3
database for data storage. Mail messages and bulletins are synced with
other BBS servers listed in the config.ini file.
"""

import logging

from config_init import initialize_config, get_interface, init_cli_parser, merge_config
from db_operations import initialize_database
from message_processing import on_receive
from pubsub import pub
import time

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
Yorkshire BBS Edition
Version: 0.1.04_Dev
"""
    print(banner)



def main():
    display_banner()
    # config, interface_type, hostname, port, bbs_nodes = initialize_config()
    args = init_cli_parser()
    config_file = None
    if args.config is not None:
        config_file = args.config
    system_config = initialize_config(config_file)
    
    merge_config(system_config, args)
    
    # print(f"{system_config=}")
    
    interface = get_interface(system_config)
    interface.bbs_nodes = system_config['bbs_nodes']
    interface.disabled = system_config['disabled']

    logging.info(f"TC²-BBS is running on {system_config['interface_type']} interface...")

    initialize_database()

    def receive_packet(packet, interface):
        on_receive(packet, interface)

    pub.subscribe(receive_packet, system_config['mqtt_topic'])

    try:
        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        logging.info("Shutting down the server...")
        interface.close()

if __name__ == "__main__":
    main()
