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
    """
    Converts a JSON-formatted string into a dictionary.

    This method attempts to parse a JSON-formatted string and convert it into a Python dictionary.
    If the content is not valid JSON, it returns an empty dictionary.

    Parameters:
    -----------
    content : str
        The JSON-formatted string to be converted into a dictionary.

    Returns:
    --------
    dict
        A dictionary representation of the JSON content. If the content is not valid JSON, an empty
        dictionary is returned.
    """
    try:
        return json.loads(content)
    except ValueError:
        return {}

def to_message(typ, value='', params=None):
    """
    Converts data into a JSON-formatted string for messaging.

    This method creates a dictionary with the provided type, value, and parameters, and then converts it
    into a JSON-formatted string. The resulting string is suitable for sending as a message to the JS8Call server.

    Parameters:
    -----------
    type : str
        The type of the message. This is a required field.
    
    value : str, optional
        The value or content of the message. Default is an empty string.
    
    params : dict, optional
        Additional parameters for the message. Default is an empty dictionary if not provided.

    Returns:
    --------
    str
        A JSON-formatted string representing the message.
    """
    if params is None:
        params = {}
    return json.dumps({'type': typ, 'value': value, 'params': params})


class JS8CallClient:
    """
    JS8CallClient integrates with the JS8Call server to handle messaging.

    This class establishes a connection with the JS8Call server, processes incoming messages,
    and provides methods to send messages and store them in a SQLite database. It handles different
    types of messages, such as individual, group, and urgent messages.

    Attributes:
    -----------
    interface : object
        The communication interface used to interact with the user.
    
    logger : logging.Logger
        The logger for the client, used to log information, warnings, and errors.
    
    config : configparser.ConfigParser
        The configuration parser to read settings from the config file.
    
    server : tuple
        The server address and port for the JS8Call server.
    
    db_file : str
        The file path for the SQLite database.
    
    js8groups : list
        The list of group names for JS8Call group messages.
    
    store_messages : bool
        Flag indicating whether to store regular messages in the database.
    
    js8urgent : list
        The list of group names for JS8Call urgent messages.
    
    connected : bool
        Flag indicating whether the client is connected to the JS8Call server.
    
    sock : socket.socket
        The socket used for the connection to the JS8Call server.
    
    db_conn : sqlite3.Connection
        The SQLite database connection.

    Methods:
    --------
    from_message(content):
        Converts message content from JSON format.
    
    to_message(type, value='', params=None):
        Converts data to JSON message format.
    
    create_tables():
        Creates necessary tables in the database if they do not already exist.
    
    insert_message(sender, receiver, message):
        Inserts a message into the 'messages' table in the database.
    
    insert_group(sender, groupname, message):
        Inserts a group message into the 'groups' table in the database.
    
    insert_urgent(sender, groupname, message):
        Inserts an urgent message into the 'urgent' table in the database.
    
    process(message):
        Processes a received message from the JS8Call server.
    
    send(*args, **kwargs):
        Sends a message to the JS8Call server.
    
    connect():
        Establishes a connection to the JS8Call server.
    
    close():
        Closes the connection to the JS8Call server.
    """
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
        """
        Creates necessary tables in the database if they do not already exist.

        This method sets up the 'messages', 'groups', and 'urgent' tables in the database.
        Each table is created with columns for storing relevant information about messages.
        If the database connection is not available, it logs an error message.

        Tables:
        -------
        - messages: Stores individual messages with sender, receiver, and message content.
        - groups: Stores group messages with sender, group name, and message content.
        - urgent: Stores urgent messages with sender, group name, and message content.
        """
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
        """
        Inserts a message into the 'messages' table in the database.

        This method saves a message along with its sender and receiver into the 'messages'
        table. If the database connection is not available, it logs an error message.

        Parameters:
        -----------
        sender : str
            The meshtastic node identifier of the sender who issued the command
        
        receiver : str
            The identifier of the receiver of the message. This is typically the user's node id
        
        message : str
            The content of the urgent message.
        """        
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
        """
        Inserts a group message into the 'groups' table in the database.

        Parameters:
        -----------
        sender : str
            The meshtastic node identifier of the sender who issued the command
        
        groupname : str
            The name of the group to which the urgent message belongs.
        
        message : str
            The content of the urgent message.
        """
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
        """
        Inserts an urgent message into the 'urgent' table in the database.

        Parameters:
        -----------
        sender : str
            The meshtastic node identifier of the sender who issued the command
        
        groupname : str
            The name of the group to which the urgent message belongs.
        
        message : str
            The content of the urgent message.
        """
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
        """
        Processes a received message from the JS8Call server.

        This method handles various types of messages received from the JS8Call server.
        It categorizes messages based on their type and performs the necessary actions
        such as logging, storing in the database, or sending notifications.

        Parameters:
        -----------
        message : dict
            The message dictionary received from the JS8Call server. It should contain
            the following message portions:
            - 'type' (str): The type of the message (e.g., 'RX.DIRECTED').
            - 'value' (str): The content of the message, which may include the sender,
                             receiver, and the message body.
            - 'params' (dict): Additional parameters associated with the message (optional).

        For 'RX.DIRECTED' messages, the method extracts the sender, receiver, and message
        content, and performs specific actions based on the receiver's role:
        - If the receiver is in the urgent list, the message is stored in the urgent messages
          table and a notification is sent.
        - If the receiver is in the group list, the message is stored in the group messages table.
        - If message storage is enabled, the message is stored in the regular messages table.
        """

        # Extract 'type', 'value', and 'params' from the message
        typ = message.get('type', '')
        value = message.get('value', '')
        params = message.get('params', {})

        if not typ:
            return

        # Only handle these message types
        rx_types = [
            'RX.ACTIVITY', 'RX.DIRECTED', 'RX.SPOT', 'RX.CALL_ACTIVITY',
            'RX.CALL_SELECTED', 'RX.DIRECTED_ME', 'RX.ECHO', 'RX.DIRECTED_GROUP',
            'RX.META', 'RX.MSG', 'RX.PING', 'RX.PONG', 'RX.STREAM'
        ]
        if typ not in rx_types:
            return

        if typ == 'RX.DIRECTED' and value:
            # Split the message string into an array
            parts = value.split(' ')
            # Make sure we have at least 3 elements in the array
            if len(parts) < 3:
                self.logger.warning(f"Unexpected message format: {value}")
                return

            sender = parts[0]
            receiver = parts[1]
            msg = ' '.join(parts[2:]).strip()

            self.logger.info(f"Received JS8Call message: {sender} to {receiver} - {msg}")

            # Receiver is in the urgent list, insert the message into the urgent table and notify
            if receiver in self.js8urgent:
                self.insert_urgent(sender, receiver, msg)
                notification_message = f"💥 URGENT JS8Call Message Received 💥\nFrom: {sender}\nCheck BBS for message"
                send_message(notification_message, BROADCAST_NUM, self.interface)
            # Receiver is in the groups list, insert the message into the groups table
            elif receiver in self.js8groups:
                self.insert_group(sender, receiver, msg)
            # If storing messages is enabled, insert the message into the messages table
            elif self.store_messages:
                self.insert_message(sender, receiver, msg)
        else:
            pass


    def send(self, *args, **kwargs):
        """
        Sends a message to the JS8Call server.

        This method formats the given arguments into a JSON message and sends it to the JS8Call server
        over a socket connection. Each message is assigned a unique ID if not provided.

        Parameters:
        *args : tuple
            Positional arguments that represent the components of the message to be sent.
            These typically include the message type and value.

        **kwargs : dict
            Keyword arguments that provide additional parameters for the message. The 'params' key
            is expected to be a dictionary of parameters to include in the message. If the '_ID' key
            is not present in 'params', it is generated automatically.

            - 'params' (dict): Optional dictionary of additional parameters to include in the message.
                               If not provided, an empty dictionary is used.
                               Example: {'TO': 'CALLSIGN'}
        """

        # Retrieve the 'params' dictionary from the keyword arguments, or initialize it as an empty dictionary if not provided
        params = kwargs.get('params', {})

        # If '_ID' is not in the params dictionary, generate a unique ID based on the current time in milliseconds
        if '_ID' not in params:
            params['_ID'] = '{}'.format(int(time.time() * 1000))
            kwargs['params'] = params

        # Convert the provided arguments and keyword arguments to a JSON message
        message = to_message(*args, **kwargs)

        # Send the JSON message to the JS8Call server by adding a newline character and encoding it to UTF-8
        self.sock.send((message + '\n').encode('utf-8'))

    def connect(self):
        """
        Establishes a connection to the JS8Call server.

        This method attempts to connect to the JS8Call server using the host and port
        specified in the configuration file. Once connected, it sends a status request
        to the server and continuously listens for incoming messages. If the connection
        is refused or an error occurs, it logs the appropriate message.

        The method will keep the connection open and process any received messages until
        the connection is closed or an error occurs.
        """

        if not self.server[0] or not self.server[1]:
            self.logger.info("JS8Call server configuration not found. Skipping JS8Call connection.")
            return

        self.logger.info(f"Connecting to {self.server}")
        self.sock = socket(AF_INET, SOCK_STREAM)
        try:
            self.sock.connect(self.server)
            self.connected = True
            self.send("STATION.GET_STATUS")

            # Continuously listen for incoming messages while connected
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
    """
    Handles the initial JS8Call command.

    This method sends a JS8Call menu to the specified sender, providing options for
    group messages, station messages, urgent messages, and all messages. It also updates
    the user state to indicate that the JS8Call menu has been presented.

    Parameters:
    -----------
    sender_id : str
        The meshtastic node identifier of the sender who issued the command
    
    interface : object
        The interface through which messages are sent. This is typically an instance
        of the communication interface used to interact with the user.
    """
    response = "JS8Call Menu:\n[G]roup Messages\n[S]tation Messages\n[U]rgent Messages\nE[X]IT"
    send_message(response, sender_id, interface)
    update_user_state(sender_id, {'command': 'JS8CALL_MENU', 'step': 1})

def handle_js8call_steps(sender_id, message, step, interface, state):
    """
    Handles the steps for the JS8Call command.

    Processes the user's input at each step of the JS8Call menu. Based on the user's choice, 
    it directs them to the appropriate sub-menu or handles invalid options

    Parameters:
    -----------
    sender_id : str
        Meshtastic node id
    
    message : str
        The message or input received from the user, representing their choice in the JS8Call menu.
    
    step : int
        The current step in the JS8Call menu navigation process.
    
    interface : object
        Instance of meshtastic interface of type specified by the configuration
        see get_interface for more details
    
    state : dict
        The current state of the user's interaction
    """
    if step == 1:
        choice = message.lower()
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
    """
    Handles the command to display group messages.

    This method retrieves distinct group names from the group messages database and presents
    a menu to the user with the available groups. If no group messages are available, it notifies
    the user and returns to the main JS8Call menu.

    Parameters:
    -----------
    sender_id : str
        Meshtastic node id
    
    interface : object
        Instance of meshtastic interface of type specified by the configuration
        see get_interface for more details
    """
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
    """
    Handles the command to display station messages.

    This method retrieves all messages from the 'messages' table in the database and presents
    them to the user. Each message includes the sender, receiver, and the message content.
    If no station messages are available, it notifies the user and returns to the main JS8Call menu.

    Parameters:
    -----------
    sender_id : str
        Meshtastic node id
    
    interface : object
        Instance of meshtastic interface of type specified by the configuration
        see get_interface for more details
    """
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
    """
    Handles the command to display urgent messages.

    This method retrieves all urgent messages from the 'urgent' table in the database and presents
    them to the user. Each message includes the sender, group name, and the message content.
    If no urgent messages are available, it notifies the user and returns to the main JS8Call menu.

    Parameters:
    -----------
    sender_id : str
        Meshtastic node id
    
    interface : object
        Instance of meshtastic interface of type specified by the configuration
        see get_interface for more details
    """
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
    """
    Handles the selection of a group from the group messages menu.

    This method processes the user's selection of a group and retrieves the messages
    for the selected group from the database. It then presents the messages to the user.
    If the selection is invalid, it prompts the user to choose again.

    Parameters:
    -----------
    sender_id : str
        Meshtastic node id
    
    message : str
        The message or input received from the user, representing their choice in the JS8Call menu.
    
    step : int
        The current step in the JS8Call menu navigation process.
    
    interface : object
        Instance of meshtastic interface of type specified by the configuration
        see get_interface for more details
    
    state : dict
        The current state of the user's interaction
    """
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