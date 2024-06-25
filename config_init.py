import configparser
import time
import meshtastic.serial_interface
import meshtastic.tcp_interface
import serial.tools.list_ports

def initialize_config():
    config = configparser.ConfigParser()
    config.read('config.ini')
    interface_type = config['interface']['type']
    hostname = config['interface'].get('hostname', None)
    port = config['interface'].get('port', None)
    bbs_nodes = config['sync']['bbs_nodes'].split(',')
    return config, interface_type, hostname, port, bbs_nodes

def get_interface(interface_type, hostname=None, port=None):
    while True:
        try:
            if interface_type == 'serial':
                if port:
                    return meshtastic.serial_interface.SerialInterface(port)
                else:
                    ports = list(serial.tools.list_ports.comports())
                    if len(ports) == 1:
                        return meshtastic.serial_interface.SerialInterface(ports[0].device)
                    elif len(ports) > 1:
                        port_list = ', '.join([p.device for p in ports])
                        raise ValueError(f"Multiple serial ports detected: {port_list}. Specify one with the 'port' argument.")
                    else:
                        raise ValueError("No serial ports detected.")
            elif interface_type == 'tcp':
                if not hostname:
                    raise ValueError("Hostname must be specified for TCP interface")
                return meshtastic.tcp_interface.TCPInterface(hostname=hostname)
            else:
                raise ValueError("Invalid interface type specified in config file")
        except PermissionError as e:
            print(f"PermissionError: {e}. Retrying in 5 seconds...")
            time.sleep(5)
