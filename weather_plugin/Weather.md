# Weather Plugin Documentation

## Overview
The Weather Plugin provides weather information for the EDC LV BBS system using the OpenWeather API. It allows users to query current weather conditions by ZIP code.

## Structure
```
weather_plugin/
├── __init__.py         # Plugin exports and initialization
├── weather.py          # Core weather functionality and API interaction
├── command_router.py   # Command handling and user interaction
├── menu.py            # Menu text and options
└── weather.ini        # Configuration file
```

## Components

### weather.py
Core functionality:
- OpenWeather API integration
- Rate limiting (per minute and daily)
- HTTP request handling with retries
- Temperature conversion (Kelvin to Fahrenheit)
- Weather data formatting

Key features:
- Configurable API rate limits
- Robust error handling
- Request retries for reliability
- Session management for connection reuse

### command_router.py
User interaction:
- Handles weather command from main menu
- Processes ZIP code input
- Manages user state
- Returns formatted weather responses

### menu.py
Menu integration:
- Provides menu text for weather option
- Defines menu item identifier

### Configuration (weather.ini)
Settings:
- OpenWeather API key
- Rate limiting parameters:
  - Max calls per minute
  - Max calls per day
- Plugin enabled/disabled flag

## Usage Flow
1. User selects "[WE]ather" from main menu
2. System prompts for ZIP code
3. User enters 5-digit ZIP code
4. System checks rate limits
5. Makes API request if within limits
6. Returns formatted weather data:
   - Temperature
   - Feels like temperature
   - Humidity
   - Weather conditions
   - City name

## Error Handling
- Invalid ZIP codes
- API rate limiting
- Network timeouts
- Missing configuration
- API errors

## Dependencies
- requests: HTTP client library
- configparser: Configuration file handling
- utils: BBS system utilities 