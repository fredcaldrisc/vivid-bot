from flask import Flask, request
import os
import requests
app = Flask(__name__)
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "vivid_verify_token")
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")

def send_whatsapp(to, text):
    if not WHATSAPP_TOKEN or not PHONE_NUMBER_ID:
        print("Missing WHATSAPP_TOKEN or PHONE_NUMBER_ID")
        return
    url = f"https://graph.facebook.com/v20.0/{PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }
    data = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text}
    }
    r = requests.post(url, headers=headers, json=data)
    print(f"Send status {r.status_code}: {r.text}")

@app.route("/webhook", methods=["GET", "POST"])
@app.route("/webhook/whatsapp", methods=["GET", "POST"])
@app.route("/", methods=["GET"])
def webhook():
    if request.method == "GET":
        mode = request.args.get("hub.mode")
        token = request.args.get("hub.verify_token")
        challenge = request.args.get("hub.challenge")
        print(f"VERIFY CHECK: got token={token} expected={VERIFY_TOKEN}")
        if mode == "subscribe" and token == VERIFY_TOKEN:
            return challenge, 200
        return "Verification failed", 403

    data = request.get_json()
    print(data)

    try:
        entry = data['entry'][0]
        changes = entry['changes'][0]
        value = changes['value']
        if 'messages' in value:
            msg = value['messages'][0]
            from_number = msg['from']
            text = msg.get('text', {}).get('body', '').lower()

            print(f"Message from {from_number}: {text}")

            if "hi" in text or "hello" in text:
                reply = "Hi! Welcome to VIVID \nWe make shirts, boxers, hoodies and more.\n\nWhat would you like to order today?"
            elif "shirt" in text:
                reply = "We have VIVID Shirts for GHS 150.\nWhat size? S, M, L, XL?"
            elif "boxer" in text:
                reply = "Boxers are GHS 60 for 1, GHS 110 for 2.\nHow many do you want?"
            else:
                reply = f"You said: {text}\n\nI'm VIVID bot. Tell me what you want to order: shirt, boxer, hoodie?"

            send_whatsapp(from_number, reply)
    except Exception as e:
        print(f"Error: {e}")

    return "ok", 200

if __name__ == "_main_":
    app.run(host="0.0.0.0", port=10000)
