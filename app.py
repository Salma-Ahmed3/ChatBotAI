"""Top-level runner for the ChatBotMobile Flask app.

This file provides the main entry point for running the Flask application,
configuring logging, and initializing required services.
"""
from app_pkg import create_app
from app_pkg.logger import setup_logger
from config import Config

# Set up application-level logger
logger = setup_logger(__name__)

app = create_app()

if __name__ == "__main__":
    logger.info("Starting ChatBotMobile application...")
    app.run(
        host="0.0.0.0",
        port=Config.PORT,
        debug=Config.DEBUG
    )