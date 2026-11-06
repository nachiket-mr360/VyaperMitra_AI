from flask import Flask

from routes.analytics import bp as analytics_bp
from routes.products import bp as products_bp
from routes.sales import bp as sales_bp
from routes.stock import bp as stock_bp


def register_blueprints(app: Flask) -> None:
    app.register_blueprint(products_bp)
    app.register_blueprint(stock_bp)
    app.register_blueprint(sales_bp)
    app.register_blueprint(analytics_bp)
