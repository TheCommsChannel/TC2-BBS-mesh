#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies =  [ 
#        "meshtastic", 
#        "pypubsub" ]
# ///

# You can use Astral UV to use this script.
# https://docs.astral.sh/uv/getting-started/installation/
# Then simply run uv run test_client.py

import logging
import time
import uuid
from datetime import datetime

from command_handlers import handle_help_command
from db_operations import get_db_connection, initialize_database
from message_processing import process_message
from utils import get_user_state, send_message

class MockInterface:
    def __init__(self):
        # Initialize with test nodes that match the BBS system structure
        self.nodes = {
            "!test1": {
                "num": 1234,
                "user": {"shortName": "TEST1", "longName": "Test Node 1"},
                "fromId": "!test1"
            },
            "!test2": {
                "num": 5678,
                "user": {"shortName": "TEST2", "longName": "Test Node 2"},
                "fromId": "!test2"
            }
        }
        # BBS nodes for syncing bulletins and mail
        self.bbs_nodes = ["!test1", "!test2"]
        self.messages_sent = []
        
        # Initialize database for testing
        initialize_database()

    class MockResponse:
        def __init__(self, id):
            self.id = id

    def sendText(self, text, destinationId, wantAck=True, wantResponse=False):
        message = {
            "text": text,
            "destinationId": destinationId,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "id": str(uuid.uuid4())
        }
        self.messages_sent.append(message)
        return self.MockResponse(message['id'])

    def get_sent_messages(self):
        return self.messages_sent

def run_interactive_test():
    # Initialize test environment
    interface = MockInterface()
    test_user_id = "!test1"

    def process_and_show_response(command):
        # Create a packet similar to what Meshtastic would send
        packet = {
            'from': interface.nodes[test_user_id]['num'],  # The sender's node number
            'fromId': test_user_id,    # The sender's node ID
            'decoded': {
                'portnum': 'TEXT_MESSAGE_APP',
                'payload': command.encode('utf-8')
            }
        }
        # Process the message using the packet
        process_message(packet['from'], command, interface)
        print("\nSystem Response:")
        for msg in interface.get_sent_messages():
            print(f"{msg['text']}")
        interface.messages_sent.clear()
        print("\n" + "-" * 50)

    print("\n=== Interactive BBS Test Client ===")
    print("You are logged in as TEST1 (Node ID: !test1)")
    print("\nAvailable Commands:")
    print("- 'x' for main menu")
    print("- Quick commands:")
    print("  * SM,,recipient,subject,message - Send mail")
    print("  * PB,,board,subject,message - Post bulletin")
    print("- 'quit' to exit")
    print("-" * 50)

    # Show initial menu
    process_and_show_response("x")

    while True:
        try:
            command = input("\nEnter command: ").strip()
            if command.lower() == 'quit':
                print("\nExiting test client...")
                break
            
            process_and_show_response(command)
            
        except KeyboardInterrupt:
            print("\nExiting test client...")
            break
        except Exception as e:
            print(f"Error: {str(e)}")

if __name__ == "__main__":
    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    try:
        run_interactive_test()
    except Exception as e:
        logging.error(f"Test failed with error: {str(e)}")
        print("\nTest client exited with error.")