"""Flask web app: giao diện cấu hình + điều khiển bot."""
from flask import Flask, jsonify, request, render_template
from flask_cors import CORS

from bot_manager import get_bot

app = Flask(__name__)
CORS(app)
bot = get_bot()


@app.route("/")
def index():
    return render_template("index.html")


# ---------- Config ----------
@app.route("/api/config", methods=["GET"])
def api_get_config():
    return jsonify(bot.get_config())


@app.route("/api/config", methods=["POST"])
def api_set_config():
    data = request.get_json(force=True)
    cfg = bot.update_config(data)
    return jsonify({"success": True, "config": cfg})


# ---------- Bot control ----------
@app.route("/api/start", methods=["POST"])
def api_start():
    return jsonify(bot.start())


@app.route("/api/stop", methods=["POST"])
def api_stop():
    return jsonify(bot.stop())


@app.route("/api/status", methods=["GET"])
def api_status():
    return jsonify(bot.get_status())


@app.route("/api/logs", methods=["GET"])
def api_logs():
    return jsonify(bot.get_logs())


@app.route("/api/signals", methods=["GET"])
def api_signals():
    return jsonify(bot.get_signals())


@app.route("/api/reset_processed", methods=["POST"])
def api_reset():
    bot.reset_processed()
    return jsonify({"success": True})


# ---------- MEXC ----------
@app.route("/api/mexc/test", methods=["POST"])
def api_mexc_test():
    return jsonify(bot.test_mexc())


@app.route("/api/mexc/refresh", methods=["POST"])
def api_mexc_refresh():
    n = bot.refresh_mexc_contracts()
    return jsonify({"success": True, "contracts": n})


# ---------- Telegram Auth ----------
@app.route("/api/telegram/status", methods=["GET"])
def api_tg_status():
    return jsonify(bot.telegram_status())


@app.route("/api/telegram/connect", methods=["POST"])
def api_tg_connect():
    return jsonify(bot.telegram_connect())


@app.route("/api/telegram/verify", methods=["POST"])
def api_tg_verify():
    data = request.get_json(force=True) or {}
    return jsonify(bot.telegram_verify(data.get("code", ""), data.get("password")))


# ---------- Positions ----------
@app.route("/api/positions", methods=["GET"])
def api_positions():
    return jsonify(bot.get_positions_combined())


@app.route("/api/positions/close", methods=["POST"])
def api_positions_close():
    data = request.get_json(force=True) or {}
    symbol = data.get("symbol", "").strip()
    if not symbol:
        return jsonify({"success": False, "message": "Missing symbol"})
    return jsonify(bot.close_position(symbol))


if __name__ == "__main__":
    print("=" * 60)
    print(" BotTradeList — http://127.0.0.1:5000")
    print("=" * 60)
    app.run(host="127.0.0.1", port=5000, debug=False, use_reloader=False)
