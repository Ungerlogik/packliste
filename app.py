import json
import os
import socket
from flask import Flask, Response, jsonify, request, send_from_directory

app = Flask(__name__, static_folder="static")

DATA_DIR = "/app/data"
STATE_FILE = os.path.join(DATA_DIR, "packliste_state.json")

PRINTER_IP = os.environ.get("PRINTER_IP", "")
PRINTER_PORT = int(os.environ.get("PRINTER_PORT", "9100"))

os.makedirs(DATA_DIR, exist_ok=True)


@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/manifest.json")
def manifest():
    manifest_data = {
        "name": "Packliste Familie Unger",
        "short_name": "Packliste",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#1e293b",
        "theme_color": "#1e293b",
        "icons": [
            {
                "src": "/icon.svg",
                "sizes": "any",
                "type": "image/svg+xml",
                "purpose": "any maskable"
            }
        ]
    }
    return jsonify(manifest_data)


@app.route("/icon.svg")
def icon():
    svg = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120">
      <rect width="120" height="120" rx="26" fill="#1e293b"/>
      <text x="60" y="78" font-size="64" text-anchor="middle">🎒</text>
    </svg>"""
    return Response(svg, mimetype="image/svg+xml")


@app.route("/sw.js")
def service_worker():
    sw_code = """
    var CACHE_NAME = 'packliste-unger-v1';
    var URLS_TO_CACHE = ['/', '/manifest.json', '/icon.svg'];

    self.addEventListener('install', function(event) {
      self.skipWaiting();
      event.waitUntil(
        caches.open(CACHE_NAME).then(function(cache) {
          return cache.addAll(URLS_TO_CACHE);
        })
      );
    });

    self.addEventListener('fetch', function(event) {
      if (event.request.url.indexOf('/api/') !== -1) {
        return; // API-Aufrufe immer direkt ans Netzwerk/Fallback leiten
      }
      event.respondWith(
        fetch(event.request).then(function(response) {
          var resClone = response.clone();
          caches.open(CACHE_NAME).then(function(cache) {
            cache.put(event.request, resClone);
          });
          return response;
        }).catch(function() {
          return caches.match(event.request);
        })
      );
    });
    """
    return Response(sw_code, mimetype="application/javascript")


@app.route("/api/state", methods=["GET"])
def get_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return jsonify(json.load(f))
    return jsonify({}), 404


@app.route("/api/state", methods=["POST"])
def save_state():
    data = request.get_json(force=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return jsonify({"status": "ok"})


@app.route("/api/print", methods=["POST"])
def print_packing_list():
    payload = request.get_json(force=True)
    title = payload.get("title", "Packliste")
    sections = payload.get("sections", [])

    lines = [title, "=" * len(title), ""]
    for sec in sections:
        lines.append(f"--- {sec.get('title', '')} ---")
        for item in sec.get("items", []):
            mark = "[x]" if item.get("packed") else "[ ]"
            lines.append(f"  {mark} {item.get('name', '')}")
        lines.append("")

    print_text = "\r\n".join(lines) + "\r\n\f"

    if not PRINTER_IP:
        return jsonify({
            "status": "prepared",
            "message": "Druckauftrag wurde erfolgreich generiert! (PRINTER_IP ist noch leer – sobald eingetragen, druckt der Netzwerkdrucker sofort los.)"
        }), 200

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(5)
            s.connect((PRINTER_IP, PRINTER_PORT))
            s.sendall(print_text.encode("utf-8"))
        return jsonify({
            "status": "printed",
            "message": f"Packliste wurde an den Netzwerkdrucker ({PRINTER_IP}) gesendet."
        }), 200
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"Drucker ({PRINTER_IP}) nicht erreichbar: {str(e)}"
        }), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
