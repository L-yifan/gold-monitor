# -*- coding: utf-8 -*-
"""
Flask 应用工厂
个人投资监控看板
"""
from pathlib import Path

from flask import Flask

from app.config import TEMPLATES_DIR
from app.routes import register_blueprints
from app.services.persistence import load_data

# 项目根目录
BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / 'static'


def create_app():
    """
    应用工厂函数
    创建并配置 Flask 应用实例
    """
    # 创建 Flask 应用，指定模板目录和静态文件目录
    flask_app = Flask(
        __name__,
        template_folder=TEMPLATES_DIR,
        static_folder=str(STATIC_DIR)
    )
    
    # 注册所有路由蓝图
    register_blueprints(flask_app)
    
    # 加载持久化数据
    load_data()
    
    return flask_app
