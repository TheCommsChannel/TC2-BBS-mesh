"""
Weather Module for TC² BBS

This module provides weather information using the OpenWeather API.
"""

import logging
import os
import requests
import time
from datetime import datetime, timedelta
from configparser import ConfigParser
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# OpenWeather API configuration
config = ConfigParser()
config_path = os.path.join(os.path.dirname(__file__), 'weather.ini')

if not os.path.exists(config_path):
    logging.error(f"Weather configuration file not found at {config_path}")
    raise FileNotFoundError(f"Weather configuration file not found at {config_path}")

try:
    config.read(config_path)
except Exception as e:
    logging.error(f"Error reading weather configuration: {e}")
    raise

OPENWEATHER_API_KEY = config.get('openweather', 'api_key', fallback='')
WEATHER_API_URL = "http://api.openweathermap.org/data/2.5/weather"

# Rate limiting configuration
MAX_CALLS_PER_MINUTE = int(config.get('openweather', 'max_calls_per_minute', fallback='30'))
MAX_CALLS_PER_DAY = int(config.get('openweather', 'max_calls_per_day', fallback='500'))

# Create a session object for better connection handling
session = requests.Session()
retry_strategy = Retry(
    total=3,  # number of retries
    backoff_factor=1,  # wait 1, 2, 4 seconds between retries
    status_forcelist=[500, 502, 503, 504]  # HTTP status codes to retry on
)
adapter = HTTPAdapter(max_retries=retry_strategy)
session.mount("http://", adapter)
session.mount("https://", adapter)

# Rate limiting state
minute_calls = 0
day_calls = 0
last_minute = datetime.now().replace(second=0, microsecond=0)
last_day = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

def check_rate_limits():
    """
    Check if we're within rate limits. Updates counters and resets them when needed.
    
    Returns:
        bool: True if we can make a call, False if we've hit a limit
    """
    global minute_calls, day_calls, last_minute, last_day
    
    now = datetime.now()
    current_minute = now.replace(second=0, microsecond=0)
    current_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Reset minute counter if we're in a new minute
    if current_minute > last_minute:
        minute_calls = 0
        last_minute = current_minute
    
    # Reset day counter if we're in a new day
    if current_day > last_day:
        day_calls = 0
        last_day = current_day
    
    # Check if we've hit any limits
    if minute_calls >= MAX_CALLS_PER_MINUTE:
        logging.warning(f"Weather API minute limit reached ({MAX_CALLS_PER_MINUTE} calls)")
        return False
    
    if day_calls >= MAX_CALLS_PER_DAY:
        logging.warning(f"Weather API daily limit reached ({MAX_CALLS_PER_DAY} calls)")
        return False
    
    # We're good to make a call
    minute_calls += 1
    day_calls += 1
    return True

def kelvin_to_fahrenheit(kelvin):
    """Convert Kelvin to Fahrenheit."""
    return (kelvin - 273.15) * 9/5 + 32

def get_weather_by_zip(zip_code, country_code='US'):
    """
    Get weather information from OpenWeather API by zip code.
    
    Args:
        zip_code: ZIP code to get weather for
        country_code: Country code (default: US)
    
    Returns:
        dict: Weather data if successful, None if failed
    """
    if not OPENWEATHER_API_KEY:
        logging.error("OpenWeather API key not configured")
        return None
        
    # Check rate limits before making the call
    if not check_rate_limits():
        logging.error("Weather API rate limit exceeded")
        return None
        
    try:
        params = {
            'zip': f"{zip_code},{country_code}",
            'appid': OPENWEATHER_API_KEY
        }
        response = session.get(WEATHER_API_URL, params=params, timeout=5)
        response.raise_for_status()
        return response.json()
    except requests.Timeout:
        logging.error(f"Weather API request timed out after 5 seconds for zip code {zip_code}")
        return {"error": "Request timed out - weather service is taking too long to respond"}
    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching weather data: {e}")
        return None

def format_weather_response(weather_data):
    """Format weather data into a user-friendly message."""
    if not weather_data:
        return "❌ Failed to get weather data."
        
    if "error" in weather_data:
        return f"❌ {weather_data['error']}"
        
    try:
        temp = kelvin_to_fahrenheit(weather_data['main']['temp'])
        feels_like = kelvin_to_fahrenheit(weather_data['main']['feels_like'])
        humidity = weather_data['main']['humidity']
        description = weather_data['weather'][0]['description'].capitalize()
        city = weather_data['name']
        
        response = f"🌡️ Weather for {city} 🌡️\n\n"
        response += f"Temperature: {temp:.1f}°F\n"
        response += f"Feels like: {feels_like:.1f}°F\n"
        response += f"Humidity: {humidity}%\n"
        response += f"Conditions: {description}\n"
        
        return response
    except (KeyError, IndexError) as e:
        logging.error(f"Error formatting weather data: {e}")
        return "❌ Error processing weather data" 