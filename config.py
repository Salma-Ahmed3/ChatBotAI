"""Configuration settings for the ChatBotMobile application.

This module centralizes all configuration settings and environment variables.
"""
import os

# Base directory of the project
BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# File paths
FAQ_PATH = os.path.join(BASE_DIR, "faq.json")
USER_DATA_PATH = os.path.join(BASE_DIR, "user_data.json")
USER_HISTORY_PATH = os.path.join(BASE_DIR, "user_history.json")
USER_STATE_PATH = os.path.join(BASE_DIR, "user_state.json")
SESSION_HISTORY_PATH = os.path.join(BASE_DIR, "session_history.json")
SERVICE_FOR_SERVICE_PATH = os.path.join(BASE_DIR, "ServiceForService.json")
HOURLY_SERVICES_SHIFT_PATH = os.path.join(BASE_DIR, "HourlyServicesShift.json")

# Flask configuration
class Config:
    """Flask application configuration."""
    SECRET_KEY = os.environ.get("SECRET_KEY") or "dev-key-please-change-in-production"
    DEBUG = os.environ.get("FLASK_DEBUG", "").lower() == "true"
    PORT = int(os.environ.get("FLASK_PORT", 5000))
    
    # API configurations
    API_TIMEOUT = 30  # seconds
    
    # Logging configuration
    LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
    LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"