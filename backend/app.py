import os

from flask import Flask, jsonify, request, send_from_directory

from stock_price import get_stock_price

# Populated by deployment: the built React app (npm run build's dist/) gets
# copied here on the server. Doesn't exist in local dev -- Vite serves the
# frontend and proxies /api to this Flask server instead (see vite.config.js).
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

app = Flask(__name__, static_folder=None)


@app.route("/api/stock-price")
def stock_price():
    symbol = request.args.get("symbol", "")
    return jsonify(get_stock_price(symbol))


@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve_frontend(path):
    full_path = os.path.join(STATIC_DIR, path)
    if path and os.path.isfile(full_path):
        return send_from_directory(STATIC_DIR, path)
    return send_from_directory(STATIC_DIR, "index.html")


if __name__ == "__main__":
    app.run(debug=True, port=5001)
