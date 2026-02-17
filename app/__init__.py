# -*- coding: utf-8 -*-
"""
Flask 应用工厂
个人投资监控看板
"""

from flask import Flask

from app.config import TEMPLATES_DIR
from app.routes import register_blueprints
from app.services.persistence import load_data


def create_app():
    """
    应用工厂函数
    创建并配置 Flask 应用实例
    """
    # 创建 Flask 应用，指定模板目录
    flask_app = Flask(__name__, template_folder=TEMPLATES_DIR)
    
    # 注册所有路由蓝图
    register_blueprints(flask_app)
    
    # 加载持久化数据
    load_data()
    
    return flask_app
