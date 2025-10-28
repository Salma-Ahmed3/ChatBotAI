from flask import Flask, request, jsonify, send_from_directory
import json, os
from services.initialize_memory import initialize_memory
from services.get_best_answer import get_best_answer
from services.pretty_log_question_answer import pretty_log_question_answer
from services.state import FAQ_PATH, get_session_history, clear_session_history
from services.genai_config import API_KEY
initialize_memory()

app = Flask(__name__)

# Initialize memory from faq file

@app.route("/upload_faq", methods=["GET", "POST"])
def upload_faq():
    if request.method == "GET":
        if os.path.exists(FAQ_PATH):
            with open(FAQ_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            return jsonify(data)
        else:
            return jsonify({"message": "❌ لا يوجد بيانات بعد."}), 404

    try:
        data = request.json
        if not data:
            return jsonify({"error": "لم يتم إرسال أي بيانات."}), 400
        if not isinstance(data, list):
            return jsonify({"error": "البيانات يجب أن تكون قائمة (list) من العناصر."}), 400

        with open(FAQ_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        initialize_memory()
        return jsonify({"message": f"✅ تم رفع وحفظ {len(data)} موضوع بنجاح."}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/chat", methods=["POST"])
def chat():
    if not request.is_json:
        return jsonify({"error": "Payload must be in JSON format."}), 400

    data = request.get_json(silent=True)
    if not data or 'message' not in data:
        return jsonify({"error": "Missing 'message' field in JSON payload."}), 400

    user_input = data.get("message", "")
    reply = get_best_answer(user_input)
    pretty_log_question_answer(user_input, reply)
    return jsonify({"reply": reply})

@app.route('/favicon.ico')
def favicon():
    return send_from_directory('static', 'favicon.ico')


@app.route('/session_history', methods=['GET'])
def session_history():
    """Return the current in-memory session history (cleared on app restart)."""
    try:
        data = get_session_history()
        return jsonify({"history": data}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/clear_session_history', methods=['POST'])
def clear_history():
    """Clear the in-memory session history."""
    try:
        # clear in-memory session + persisted session file
        clear_session_history()

        files_to_clear = [
            # os.path.join(os.path.dirname(__file__), "user_data.json"),
            os.path.join(os.path.dirname(__file__), "ServiceForService.json"),
            os.path.join(os.path.dirname(__file__), "HourlyServicesShift.json"),
        ]
        cleared = []
        for path in files_to_clear:
            try:
                # overwrite with empty JSON object; create file if missing
                with open(path, "w", encoding="utf-8") as f:
                    json.dump({}, f, ensure_ascii=False, indent=2)
                cleared.append(os.path.basename(path))
            except Exception as e:
                # don't fail the whole operation if one file can't be written
                print(f"⚠️ failed clearing {path}: {e}")

        return jsonify({
            "message": "session history cleared",
            "cleared_files": cleared
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(port=5000, debug=True)