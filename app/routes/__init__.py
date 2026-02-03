# -*- coding: utf-8 -*-
"""
app.routes 包初始化
包含所有蓝图的注册
"""

from app.routes.price import price_bp
from app.routes.funds import funds_bp
from app.routes.holdings import holdings_bp
from app.routes.settings import settings_bp
from app.routes.trading import trading_bp


def register_blueprints(app):
    """注册所有蓝图到 Flask 应用"""
    app.register_blueprint(price_bp)
    app.register_blueprint(funds_bp)
    app.register_blueprint(holdings_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(trading_bp)


__all__ = [
    'price_bp',
    'funds_bp',
    'holdings_bp',
    'settings_bp',
    'trading_bp',
    'register_blueprints'
]
