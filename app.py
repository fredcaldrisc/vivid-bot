from flask import Flask, request
import json, os
app = Flask("vivid")
TOKEN = "vivid123"
FILE = "memory.json"
if not os.path.exists(FILE):
    open(FILE,'w').write('[]')

@app.route("/")
def home():
    mem = json.loads(open(FILE).read())
    html = "<h1>VIVID is LIVE! Memory: " + str(len(mem)) + "</h1>"
    html += "<p><a href='/memory'>View Memory JSON</a></p><hr>"
    html += "<h3>Last 20 memories:</h3>"
    for m in mem[::-1][:20]:
        html += "<p>" + str(m)[:300] + "</p>"
    return html

@app.route("/webhook", methods=["GET"])
def verify():
    t = request.args.get("hub.verify_token")
    c = request.args.get("hub.challenge")
    if t == TOKEN:
        return c
    return "Failed", 403

@app.route("/webhook", methods=["POST"])
def incoming():
    data = request.get_json()
    print(data)
    mem = json.loads(open(FILE).read())
    mem.append({"text": str(data)[:500]})
    open(FILE,'w').write(json.dumps(mem, indent=2))
    return "OK", 200

@app.route("/memory")
def memory():
    return open(FILE).read()

if _name_ == "_main_":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)