#!/usr/bin/env python3

"""
TC²-BBS Server for Meshtastic by TheCommsChannel (TC²)
Date: 07/14/2024
Version: 0.1.6

Description:
The system allows for mail message handling, bulletin boards, and a channel
directory. It uses a configuration file for setup details and an SQLite3
database for data storage. Mail messages and bulletins are synced with
other BBS servers listed in the config.ini file.
"""

import logging
import time

import settings
from config_init import initialize_config, get_interface, init_cli_parser, merge_config
from database import Database
from js8_db import Js8Database
from js8call_integration import JS8CallClient
from message_processing import on_receive, check_timeouts
from pubsub import pub
from reconnect import Supervisor
from runtime import Runtime
from session import Session
from transport import MeshtasticTransport

# General logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# JS8Call logging
js8call_logger = logging.getLogger('js8call')
js8call_logger.setLevel(logging.DEBUG)
js8call_handler = logging.StreamHandler()
js8call_handler.setLevel(logging.DEBUG)
js8call_formatter = logging.Formatter('%(asctime)s - JS8Call - %(levelname)s - %(message)s', '%Y-%m-%d %H:%M:%S')
js8call_handler.setFormatter(js8call_formatter)
js8call_logger.addHandler(js8call_handler)

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
    args = init_cli_parser()
    config_file = None
    if args.config is not None:
        config_file = args.config
    system_config = initialize_config(config_file)

    merge_config(system_config, args)

    config = settings.load(system_config['config_file'])
    print(f"Configured to sync with the following BBS nodes: {config.bbs_nodes}")
    print(f"Nodes with Urgent board permissions: {config.allowed_nodes}")

    interface = get_interface(system_config)
    transport = MeshtasticTransport(interface)
    supervisor = Supervisor(transport, lambda: get_interface(system_config))
    pub.subscribe(supervisor.on_connection_lost, "meshtastic.connection.lost")
    database = Database()
    js8_database = Js8Database(config.js8.db_path)
    runtime = Runtime(config=config, database=database,
                      js8_database=js8_database, session=Session())

    logging.info(f"TC²-BBS is running on {system_config['interface_type']} interface...")

    database.initialize_schema()
    print("Database schema initialized.")

    def receive_packet(packet, interface):
        on_receive(packet, interface, runtime)

    pub.subscribe(receive_packet, system_config['mqtt_topic'])

    # Initialize and start JS8Call Client if configured. It listens on its own
    # thread, so this returns immediately and does nothing when unconfigured.
    js8call_client = JS8CallClient(transport, config.js8, js8_database)
    js8call_client.logger = js8call_logger
    js8call_client.start()

    try:
        while True:
            time.sleep(1)
            supervisor.check()
            check_timeouts(transport, runtime)

    except KeyboardInterrupt:
        logging.info("Shutting down the server...")
        transport.close()
        js8call_client.close()

if __name__ == "__main__":
    main()
