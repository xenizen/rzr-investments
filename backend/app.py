from flask import Flask, jsonify, request

from stock_price import get_stock_price

app = Flask(__name__)


@app.route("/api/stock-price")
def stock_price():
    symbol = request.args.get("symbol", "")
    return jsonify(get_stock_price(symbol))


if __name__ == "__main__":
    app.run(debug=True)
