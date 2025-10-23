from bidi.algorithm import get_display
import datetime, sys
from .state import append_session_message

def pretty_log_question_answer(user_input, reply):
    sys.stdout.reconfigure(encoding="utf-8")
    q_disp = get_display(user_input)
    a_disp = get_display(reply)
    now = datetime.datetime.now().strftime("%H:%M:%S")

    print("\n" + "=" * 60)
    print(f"🕒 [{now}]")
    print(f"📩 [USER QUESTION]: {q_disp}")
    print(f"🤖 [BOT ANSWER]: {a_disp}")
    print("=" * 60 + "\n")

    # Save to in-memory session history (user then bot)
    try:
        append_session_message("user", user_input)
        append_session_message("bot", reply)
    except Exception as e:
        print(f"⚠️ failed saving to session history: {e}")
