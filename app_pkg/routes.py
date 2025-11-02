"""Blueprint containing the HTTP routes for the ChatBotMobile app.

This module defines all HTTP endpoints and their handlers, utilizing the error
handling and logging systems for robust operation.
"""
from flask import Blueprint, jsonify, request, send_from_directory, current_app
import json
import os
from typing import Any

from app_pkg.logger import setup_logger
from app_pkg.errors import InvalidInputError, ResourceNotFoundError
from config import FAQ_PATH, SERVICE_FOR_SERVICE_PATH, HOURLY_SERVICES_SHIFT_PATH
from services.get_best_answer import get_best_answer
from services.pretty_log_question_answer import pretty_log_question_answer
from services.state import get_session_history, clear_session_history

# Set up route-specific logger
logger = setup_logger(__name__)


bp = Blueprint("main", __name__)


@bp.route("/upload_faq", methods=["GET", "POST"])
def upload_faq() -> Any:
    """Handle FAQ data upload and retrieval.
    
    GET: Retrieve current FAQ data
    POST: Upload new FAQ data and reinitialize the memory
    
    Returns:
        JSON response with success/error message
    """
    if request.method == "GET":
        if not os.path.exists(FAQ_PATH):
            logger.warning("FAQ file not found")
            raise ResourceNotFoundError("❌ لا يوجد بيانات بعد.")
            
        try:
            with open(FAQ_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            logger.info("FAQ data retrieved successfully")
            return jsonify(data)
        except Exception as e:
            logger.error(f"Error reading FAQ file: {str(e)}", exc_info=True)
            raise

    # Handle POST request
    data = request.json
    if not data:
        logger.warning("No data provided in upload request")
        raise InvalidInputError("لم يتم إرسال أي بيانات.")
        
    if not isinstance(data, list):
        logger.warning("Invalid data format provided - expected list")
        raise InvalidInputError("البيانات يجب أن تكون قائمة (list) من العناصر.")

    try:
        with open(FAQ_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        # Reinitialize in-memory index
        from services.initialize_memory import initialize_memory
        initialize_memory()
        
        logger.info(f"Successfully uploaded {len(data)} FAQ items")
        return jsonify({"message": f"✅ تم رفع وحفظ {len(data)} موضوع بنجاح."}), 200

    except Exception as e:
        logger.error(f"Error processing FAQ upload: {str(e)}", exc_info=True)
        raise


@bp.route("/chat", methods=["POST"])
def chat() -> Any:
    """Handle chat messages and return appropriate responses.
    
    Expects a JSON payload with a 'message' field containing the user's input.
    
    Returns:
        JSON response containing the chatbot's reply
    """
    if not request.is_json:
        logger.warning("Non-JSON payload received")
        raise InvalidInputError("يجب أن تكون البيانات بتنسيق JSON.")

    data = request.get_json(silent=True)
    if not data or 'message' not in data:
        logger.warning("Missing message field in request")
        raise InvalidInputError("الرجاء إدخال الرسالة في حقل 'message'.")

    try:
        user_input = data.get("message", "").strip()
        if not user_input:
            logger.warning("Empty message received")
            raise InvalidInputError("الرجاء إدخال رسالة غير فارغة.")
            
        logger.info(f"Processing chat request: {user_input[:50]}...")
        reply = get_best_answer(user_input)
        pretty_log_question_answer(user_input, reply)
        
        logger.debug(f"Generated reply: {reply[:50]}...")
        return jsonify({"reply": reply})
        
    except Exception as e:
        logger.error(f"Error processing chat request: {str(e)}", exc_info=True)
        raise


@bp.route('/favicon.ico')
def favicon():
    return send_from_directory('static', 'favicon.ico')


@bp.route('/session_history', methods=['GET'])
def session_history() -> Any:
    """Retrieve the current session history.
    
    Returns the conversation history from the current session,
    which is cleared when the application restarts.
    
    Returns:
        JSON response containing the session history
    """
    logger.info("Retrieving session history")
    try:
        data = get_session_history()
        logger.debug(f"Found {len(data)} history items")
        return jsonify({"history": data}), 200
    except Exception as e:
        logger.error(f"Error retrieving session history: {str(e)}", exc_info=True)
        raise


@bp.route('/clear_session_history', methods=['POST'])
def clear_history() -> Any:
    """Clear the session history and related persisted files.
    
    Clears both the in-memory session history and resets specific JSON
    files to empty objects.
    
    Returns:
        JSON response indicating success and listing cleared files
    """
    logger.info("Clearing session history and related files")
    
    try:
        # Clear in-memory session + persisted session file
        clear_session_history()
        logger.debug("In-memory session history cleared")

        files_to_clear = [
            SERVICE_FOR_SERVICE_PATH,
            HOURLY_SERVICES_SHIFT_PATH
        ]
        
        cleared = []
        for path in files_to_clear:
            try:
                # Overwrite with empty JSON object; create file if missing
                with open(path, "w", encoding="utf-8") as f:
                    json.dump({}, f, ensure_ascii=False, indent=2)
                cleared.append(os.path.basename(path))
                logger.debug(f"Cleared file: {path}")
            except Exception as e:
                logger.error(f"Failed to clear file {path}: {str(e)}", exc_info=True)

        logger.info(f"Successfully cleared {len(cleared)} files")
        return jsonify({
            "message": "تم مسح سجل المحادثة بنجاح",
            "cleared_files": cleared
        }), 200
        
    except Exception as e:
        logger.error(f"Error during history cleanup: {str(e)}", exc_info=True)
        raise
