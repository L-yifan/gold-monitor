# -*- coding: utf-8 -*-
"""
个人投资监控看板 - 应用入口
数据来源：上海黄金交易所 Au99.99 / 公募基金实时估值
"""

import threading
from app import create_app
from app.services.background import background_fetch_loop

# 创建 Flask 应用实例
application = create_app()


if __name__ == '__main__':
    print("=" * 50)
    print(" 个人投资监控看板")
    print(" 数据来源: 上海黄金交易所 Au99.99")
    print(" 访问地址: http://localhost:5000")
    print("=" * 50)

    # 启动后台抓取线程
    t = threading.Thread(target=background_fetch_loop, daemon=True)
    t.start()

    # 启动 Flask 应用
    application.run(host='0.0.0.0', port=5000, debug=True, threaded=True, use_reloader=False)
