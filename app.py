from flask import Flask, request, jsonify
import requests
import os
from threading import Thread
from dotenv import load_dotenv  
import google.auth.transport.requests
import google.oauth2.service_account as sa
from db import save_message, get_last_messages  
import json


load_dotenv()

app = Flask(__name__)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")


def get_access_token():
    """
    Get OAuth2 token using service account stored in environment variable
    """
    SCOPES = ["https://www.googleapis.com/auth/chat.bot"]

    # Load JSON from environment variable
    creds_json = os.getenv("GOOGLE_CREDENTIALS")
    if not creds_json:
        raise ValueError("GOOGLE_CREDENTIALS env variable is not set")

    creds_info = json.loads(creds_json)

    credentials = sa.Credentials.from_service_account_info(creds_info, scopes=SCOPES)
    auth_req = google.auth.transport.requests.Request()
    credentials.refresh(auth_req)
    return credentials.token



def send_to_gchat(thread_name, ai_text):
    """
    Sends a message back to GChat asynchronously
    """
    # Ensure ai_text is a string (fix for 'str' object has no attribute keys)
    if not isinstance(ai_text, str):
        ai_text = str(ai_text)

    space_id = thread_name.split("/")[1]
    url = f"https://chat.googleapis.com/v1/spaces/{space_id}/messages"

    response_payload = {
        "text": ai_text,
        "thread": {"name": thread_name}
    }

    # Log payload
    print("Async GChat payload:", response_payload, flush=True)

    try:
        token = get_access_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        # requests.post expects a dict for json=...
        resp = requests.post(url, json=response_payload, headers=headers)
        print("Async GChat response status:", resp.status_code, resp.text, flush=True)
    except Exception as e:
        print("Error sending to GChat:", e, flush=True)



def get_ai_response(context_key, user_text):
    """
    Calls OpenAI API with last 5 messages context
    """
    # Fetch last 5 messages for context (ensure chronological order in db.py)
    history = get_last_messages(context_key)

    # Add current user message (not yet in DB)
    context = history + [{"role": "user", "text": user_text}]

    # Prepare payload for OpenAI
    payload_input = "\n".join([f"{m['role']}: {m['text']}" for m in context])

    url = "https://api.openai.com/v1/responses"
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "gpt-4.1-mini",
        "input": payload_input
    }

    print("Sending user text with context to OpenAI API...", flush=True)
    print("OpenAI payload:", payload_input, flush=True)

    try:
        resp = requests.post(url, headers=headers, json=payload)
        data = resp.json()
        text = data["output"][0]["content"][0]["text"].strip()

        # Save both user and AI messages
        save_message(context_key, "user", user_text)
        save_message(context_key, "ai", text)

        return text
    except Exception as e:
        print("OpenAI error:", e, flush=True)
        return "Sorry, I couldn't get a response from AI."


@app.route("/", methods=["POST"])
def chat_event():
    event = request.get_json(force=True, silent=True)
    print(" Incoming event:", event, flush=True)

    user_text = None
    thread_name = None

    # Handle GChat message event
    if "chat" in event and "messagePayload" in event["chat"]:
        msg = event["chat"]["messagePayload"].get("message", {})
        user_text = msg.get("text", "")
        thread_name = msg.get("thread", {}).get("name")

        print(f"Detected GCHAT message: {user_text}, thread: {thread_name}", flush=True)

        if user_text and thread_name:
            space = event["chat"]["messagePayload"].get("space", {})
            space_id = space.get("name")
            space_type = space.get("type")

            # Decide key for history
            if space_type == "DM":
                context_key = space_id   # use space for DMs
            else:
                context_key = thread_name  # use thread for group chats

            # Start async processing without acknowledgment message
            Thread(
                target=lambda: send_to_gchat(
                    thread_name,
                    get_ai_response(context_key, user_text)
                )
            ).start()
        return jsonify({})  #

    # Handle ADDED_TO_SPACE
    if event.get("type") == "ADDED_TO_SPACE":
        return jsonify({"text": "Hello! I’m your AI assistant. Ask me anything!"})

    return jsonify({})


if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 8080))  # Use Cloud Run port
    print(f"Starting Flask server on port {port}...", flush=True)
    app.run(host="0.0.0.0", port=port)
