from flask import Flask, request
import os

app = Flask(_name_)

VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "vivid_verify_token")

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
        else:
            return "Verification failed", 403
    
    # POST - handle messages
    data = request.get_json()
    print(data)
    return "ok", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
