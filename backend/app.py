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
    response = jsonify(get_stock_price(symbol))
    response.headers["Cache-Control"] = "no-store"
    return response


@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve_frontend(path):
    full_path = os.path.join(STATIC_DIR, path)
    if path and os.path.isfile(full_path):
        response = send_from_directory(STATIC_DIR, path)
        # Hashed filenames (assets/index-<hash>.js etc.) are safe to cache
        # forever -- a new build always gets a new filename. Anything else
        # (favicon, etc.) isn't hashed, so don't let it get stuck stale.
        if path.startswith("assets/"):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        else:
            response.headers["Cache-Control"] = "no-store"
        return response

    # index.html itself references the hashed asset filenames, so it must
    # never be cached -- otherwise a new deploy's assets would never load.
    response = send_from_directory(STATIC_DIR, "index.html")
    response.headers["Cache-Control"] = "no-store"
    return response


if __name__ == "__main__":
    app.run(debug=True, port=5001)
