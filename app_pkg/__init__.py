"""Application factory module for ChatBotMobile.

This module contains the application factory that creates and configures
the Flask application instance.
"""
from flask import Flask
from typing import Any

from app_pkg.routes import bp
from app_pkg.errors import register_error_handlers
from app_pkg.logger import setup_logger
from config import Config
from services.initialize_memory import initialize_memory


def create_app() -> Flask:
    """Create and configure the Flask application.
    
    Returns:
        A configured Flask application instance
    """
    app = Flask(__name__)
    
    # Load configuration
    app.config.from_object(Config)
    
    # Set up logging
    app.logger = setup_logger(__name__)
    
    # Register blueprints
    app.register_blueprint(bp)
    
    # Register error handlers
    register_error_handlers(app)
    
    # Initialize services
    initialize_memory()
    
    app.logger.info("Application initialized successfully")
    return app
