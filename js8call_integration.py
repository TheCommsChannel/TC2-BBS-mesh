from socket import socket, AF_INET, SOCK_STREAM
import json
import time
import sqlite3
import configparser
import logging

from meshtastic import BROADCAST_NUM

from command_handlers import handle_help_command
from utils import send_message, update_user_state

config_file = 'config.ini'

def from_message(content):
    try:
        return json.loads(content)
    except ValueError:
        return {}

def to_message(typ, value='', params=None):
    if params is None:
        params = {}
    return json.dumps({'type': typ, 'value': value, 'params': params})


class JS8CallClient:
    def __init__(self, interface, logger=None):
        self.logger = logger or logging.getLogger('js8call')
        self.logger.setLevel(logging.INFO)
        self.logger.propagate = False

        self.config = configparser.ConfigParser()
        self.config.read(config_file)

        self.server = (
            self.config.get('js8call', 'host', fallback=None),
            self.config.getint('js8call', 'port', fallback=None)
        )
        self.db_file = self.config.get('js8call', 'db_file', fallback=None)
        self.js8groups = self.config.get('js8call', 'js8groups', fallback='').split(',')
        self.store_messages = self.config.getboolean('js8call', 'store_messages', fallback=True)
        self.js8urgent = self.config.get('js8call', 'js8urgent', fallback='').split(',')
        self.js8groups = [group.strip() for group in self.js8groups]
        self.js8urgent = [group.strip() for group in self.js8urgent]

        self.connected = False
        self.sock = None
        self.db_conn = None
        self.interface = interface

        if self.db_file:
            self.db_conn = sqlite3.connect(self.db_file)
            self.create_tables()
        else:
            self.logger.info("JS8Call configuration not found. Skipping JS8Call integration.")

    def create_tables(self):
        if not self.db_conn:
            return

        with self.db_conn:
            self.db_conn.execute('''
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sender TEXT,
                    receiver TEXT,
                    message TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            self.db_conn.execute('''
                CREATE TABLE IF NOT EXISTS groups (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sender TEXT,
                    groupname TEXT,
                    message TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            self.db_conn.execute('''
                CREATE TABLE IF NOT EXISTS urgent (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sender TEXT,
                    groupname TEXT,
                    message TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
        self.logger.info("Database tables created or verified.")

    def insert_message(self, sender, receiver, message):
        if not self.db_conn:
            self.logger.error("Database connection is not available.")
            return

        try:
            with self.db_conn:
                self.db_conn.execute('''
                    INSERT INTO messages (sender, receiver, message)
                    VALUES (?, ?, ?)
                ''', (sender, receiver, message))
        except sqlite3.Error as e:
            self.logger.error(f"Failed to insert message into database: {e}")

    def insert_group(self, sender, groupname, message):
        if not self.db_conn:
            self.logger.error("Database connection is not available.")
            return

        try:
            with self.db_conn:
                self.db_conn.execute('''
                    INSERT INTO groups (sender, groupname, message)
                    VALUES (?, ?, ?)
                ''', (sender, groupname, message))
        except sqlite3.Error as e:
            self.logger.error(f"Failed to insert group message into database: {e}")

    def insert_urgent(self, sender, groupname, message):
        if not self.db_conn:
            self.logger.error("Database connection is not available.")
            return

        try:
            with self.db_conn:
                self.db_conn.execute('''
                    INSERT INTO urgent (sender, groupname, message)
                    VALUES (?, ?, ?)
                ''', (sender, groupname, message))
        except sqlite3.Error as e:
            self.logger.error(f"Failed to insert urgent message into database: {e}")

    def process(self, message):
        typ = message.get('type', '')
        value = message.get('value', '')
        params = message.get('params', {})

        if not typ:
            return

        rx_types = [
            'RX.ACTIVITY', 'RX.DIRECTED', 'RX.SPOT', 'RX.CALL_ACTIVITY',
            'RX.CALL_SELECTED', 'RX.DIRECTED_ME', 'RX.ECHO', 'RX.DIRECTED_GROUP',
            'RX.META', 'RX.MSG', 'RX.PING', 'RX.PONG', 'RX.STREAM'
        ]

        if typ not in rx_types:
            return

        if typ == 'RX.DIRECTED' and value:
            parts = value.split(' ')
            if len(parts) < 3:
                self.logger.warning(f"Unexpected message format: {value}")
                return

            sender = parts[0]
            receiver = parts[1]
            msg = ' '.join(parts[2:]).strip()

            self.logger.info(f"Received JS8Call message: {sender} to {receiver} - {msg}")

            if receiver in self.js8urgent:
                self.insert_urgent(sender, receiver, msg)
                notification_message = f"💥 URGENT JS8Call Message Received 💥\nFrom: {sender}\nCheck BBS for message"
                send_message(notification_message, BROADCAST_NUM, self.interface)
            elif receiver in self.js8groups:
                self.insert_group(sender, receiver, msg)
            elif self.store_messages:
                self.insert_message(sender, receiver, msg)
        else:
            pass

    def send(self, *args, **kwargs):
        params = kwargs.get('params', {})
        if '_ID' not in params:
            params['_ID'] = '{}'.format(int(time.time() * 1000))
            kwargs['params'] = params
        message = to_message(*args, **kwargs)
        self.sock.send((message + '\n').encode('utf-8'))  # Convert to bytes

    def connect(self):
        if not self.server[0] or not self.server[1]:
            self.logger.info("JS8Call server configuration not found. Skipping JS8Call connection.")
            return

        self.logger.info(f"Connecting to {self.server}")
        self.sock = socket(AF_INET, SOCK_STREAM)
        try:
            self.sock.connect(self.server)
            self.connected = True
            self.send("STATION.GET_STATUS")

            while self.connected:
                content = self.sock.recv(65500).decode('utf-8')  # Decode received bytes to string
                if not content:
                    continue  # Skip empty content

                try:
                    message = json.loads(content)
                except ValueError:
                    continue  # Skip invalid JSON content

                if not message:
                    continue  # Skip empty message

                self.process(message)
        except ConnectionRefusedError:
            self.logger.error(f"Connection to JS8Call server {self.server} refused.")
        finally:
            self.sock.close()

    def close(self):
        self.connected = False


def handle_js8call_command(sender_id, interface):
    response = "JS8Call Menu:\n[G]roup Messages\n[S]tation Messages\n[U]rgent Messages\nE[X]IT"
    send_message(response, sender_id, interface)
    update_user_state(sender_id, {'command': 'JS8CALL_MENU', 'step': 1})


def handle_js8call_steps(sender_id, message, step, interface, state):
    message = message.lower().strip()
    if len(message) == 2 and message[1] == 'x':
        message = message[0]

    if step == 1:
        choice = message
        if choice == 'x':
            handle_help_command(sender_id, interface, 'bbs')
            return
        elif choice == 'g':
            handle_group_messages_command(sender_id, interface)
        elif choice == 's':
            handle_station_messages_command(sender_id, interface)
        elif choice == 'u':
            handle_urgent_messages_command(sender_id, interface)
        else:
            send_message("Invalid option. Please choose again.", sender_id, interface)
            handle_js8call_command(sender_id, interface)



def handle_group_messages_command(sender_id, interface):
    conn = sqlite3.connect('js8call.db')
    c = conn.cursor()
    c.execute("SELECT DISTINCT groupname FROM groups")
    groups = c.fetchall()
    if groups:
        response = "Group Messages Menu:\n" + "\n".join([f"[{i}] {group[0]}" for i, group in enumerate(groups)])
        send_message(response, sender_id, interface)
        update_user_state(sender_id, {'command': 'GROUP_MESSAGES', 'step': 1, 'groups': groups})
    else:
        send_message("No group messages available.", sender_id, interface)
        handle_js8call_command(sender_id, interface)

def handle_station_messages_command(sender_id, interface):
    conn = sqlite3.connect('js8call.db')
    c = conn.cursor()
    c.execute("SELECT sender, receiver, message, timestamp FROM messages")
    messages = c.fetchall()
    if messages:
        response = "Station Messages:\n" + "\n".join([f"[{i+1}] {msg[0]} -> {msg[1]}: {msg[2]} ({msg[3]})" for i, msg in enumerate(messages)])
        send_message(response, sender_id, interface)
    else:
        send_message("No station messages available.", sender_id, interface)
    handle_js8call_command(sender_id, interface)

def handle_urgent_messages_command(sender_id, interface):
    conn = sqlite3.connect('js8call.db')
    c = conn.cursor()
    c.execute("SELECT sender, groupname, message, timestamp FROM urgent")
    messages = c.fetchall()
    if messages:
        response = "Urgent Messages:\n" + "\n".join([f"[{i+1}] {msg[0]} -> {msg[1]}: {msg[2]} ({msg[3]})" for i, msg in enumerate(messages)])
        send_message(response, sender_id, interface)
    else:
        send_message("No urgent messages available.", sender_id, interface)
    handle_js8call_command(sender_id, interface)

def handle_group_message_selection(sender_id, message, step, state, interface):
    groups = state['groups']
    try:
        group_index = int(message)
        groupname = groups[group_index][0]

        conn = sqlite3.connect('js8call.db')
        c = conn.cursor()
        c.execute("SELECT sender, message, timestamp FROM groups WHERE groupname=?", (groupname,))
        messages = c.fetchall()

        if messages:
            response = f"Messages for group {groupname}:\n" + "\n".join([f"[{i+1}] {msg[0]}: {msg[1]} ({msg[2]})" for i, msg in enumerate(messages)])
            send_message(response, sender_id, interface)
        else:
            send_message(f"No messages for group {groupname}.", sender_id, interface)
    except (IndexError, ValueError):
        send_message("Invalid group selection. Please choose again.", sender_id, interface)
        handle_group_messages_command(sender_id, interface)

    handle_js8call_command(sender_id, interface)