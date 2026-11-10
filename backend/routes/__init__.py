from flask import Flask

from routes.analytics import bp as analytics_bp
from routes.products import bp as products_bp
from routes.sales import bp as sales_bp
from routes.stock import bp as stock_bp
from routes.intent import bp as intent_bp
from routes.planner import bp as planner_bp
from routes.memory import bp as memory_bp
from routes.tts import bp as tts_bp
from routes.voice import bp as voice_bp
from routes.exports import bp as exports_bp


def register_blueprints(app: Flask) -> None:
    app.register_blueprint(products_bp)
    app.register_blueprint(stock_bp)
    app.register_blueprint(sales_bp)
    app.register_blueprint(analytics_bp)
    app.register_blueprint(voice_bp)
    app.register_blueprint(tts_bp)
    app.register_blueprint(intent_bp)
    app.register_blueprint(planner_bp)
    app.register_blueprint(memory_bp)
    app.register_blueprint(exports_bp)
