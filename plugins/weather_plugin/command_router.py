from utils import send_message, update_user_state
from .weather import get_weather_by_zip, format_weather_response

def handle_weather_command(sender_id, interface):
    """Handle the weather command from the main menu."""
    response = "🌡️  Weather Service 🌡️\n\nEnter a ZIP code (89115) to get the current weather, or 'X' to exit:"
    send_message(response, sender_id, interface)
    update_user_state(sender_id, {'command': 'WEATHER', 'step': 1})

def handle_weather_steps(sender_id, message, step, interface):
    """Handle the steps for getting weather information."""
    message = message.strip().upper()
    
    if message == 'X':
        from command_handlers import handle_help_command
        handle_help_command(sender_id, interface)
        return
        
    if step == 1:
        if not message.isdigit() or len(message) != 5:
            send_message("Please enter a valid 5-digit ZIP code, or 'X' to exit.", sender_id, interface)
            return
            
        weather_data = get_weather_by_zip(message)
        response = format_weather_response(weather_data)
        send_message(response, sender_id, interface)
        
        from command_handlers import handle_help_command
        handle_help_command(sender_id, interface) 