"""Custom exceptions and error handling for the ChatBotMobile application.

This module defines custom exceptions and error handlers used throughout the application.
"""
from typing import Any, Dict, Optional, Type
from flask import jsonify

class ChatBotException(Exception):
    """Base exception class for ChatBotMobile application."""
    status_code = 500
    message = "حدث خطأ في النظام"
    
    def __init__(self, message: Optional[str] = None, status_code: Optional[int] = None):
        super().__init__()
        if message is not None:
            self.message = message
        if status_code is not None:
            self.status_code = status_code
            
    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary format for JSON response."""
        return {"error": self.message}


class InvalidInputError(ChatBotException):
    """Exception raised for invalid input data."""
    status_code = 400
    message = "البيانات المدخلة غير صحيحة"


class ResourceNotFoundError(ChatBotException):
    """Exception raised when a requested resource is not found."""
    status_code = 404
    message = "المورد المطلوب غير موجود"


class APIError(ChatBotException):
    """Exception raised for API-related errors."""
    status_code = 503
    message = "حدث خطأ في الاتصال بالخدمة"


def register_error_handlers(app: Any) -> None:
    """Register error handlers with the Flask application.
    
    Args:
        app: The Flask application instance
    """
    def handle_chatbot_exception(error: ChatBotException) -> Any:
        """Handle ChatBotMobile custom exceptions."""
        response = jsonify(error.to_dict())
        response.status_code = error.status_code
        return response
    
    def handle_generic_exception(error: Exception) -> Any:
        """Handle any unhandled exceptions."""
        app.logger.error(f"Unhandled exception: {str(error)}", exc_info=True)
        return jsonify({
            "error": "حدث خطأ غير متوقع في النظام"
        }), 500
    
    # Register handlers for custom exceptions
    app.register_error_handler(ChatBotException, handle_chatbot_exception)
    
    # Register handler for unhandled exceptions
    app.register_error_handler(Exception, handle_generic_exception)