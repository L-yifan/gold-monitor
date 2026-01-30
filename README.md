# 国内金价实时监控系统 (Au99.99)

一个用于监控 **上海黄金交易所 (SGE) Au99.99** 实时价格的本地看板系统。支持自动计算盈亏、多级止盈目标提示以及实时数据可视化。

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.8%2B-blue)
![Vue](https://img.shields.io/badge/vue-3.x-green)

## ✨ 核心功能

*   **实时监控**: 每 5 秒从可靠数据源（东方财富/新浪财经）自动拉取 Au99.99 最新成交价。
*   **高可用数据源**: 独创的多源自动切换机制（东方财富 -> 新浪财经 -> 备用），确保数据流不中断。
*   **智能盈亏计算**:
    *   设置您的 **买入成本**，系统自动计算实时盈亏金额及百分比。
    *   自动推算 5%, 10%, 20% 等多个档位的**止盈卖出价格**（已自动扣除 0.5% 手续费）。
*   **可视化交互**:
    *   **红涨绿跌**: 符合国内投资者习惯的视觉配色。
    *   **动态心跳**: 价格更新时不仅有数值变化，更有舒适的呼吸与弹跳动画。
    *   **实时图表**: 基于 Chart.js 绘制的分钟级价格走势图。
*   **价格记录**: 支持手动“快照”记录当前价格，并添加备注，方便复盘。

## 🚀 快速开始

### 环境要求

*   Python 3.8+
*   Pip

### 安装步骤

1.  克隆仓库:
    ```bash
    git clone https://github.com/yourusername/gold-price-monitor.git
    cd gold-price-monitor
    ```

2.  安装依赖:
    ```bash
    pip install -r requirements.txt
    ```

### 启动运行

1.  **启动服务**:
    *   **Windows 用户**: 双击 `start.bat` (如已配置好环境) 或在命令行运行:
        ```bash
        python app.py
        ```
    *   **Linux/Mac 用户**:
        ```bash
        python3 app.py
        ```

2.  **访问看板**:
    打开浏览器访问: `http://localhost:5000`

## 🛠 技术栈

*   **后端**: Flask (Python)
*   **前端**: Vue 3, Tailwind CSS, Chart.js
*   **数据源**: 东方财富 API, 新浪财经 API

## 📝 配置说明

您可以在 `app.py` 中调整以下配置:

*   `DATA_SOURCES`: 添加或修改数据源及优先级。
*   `MAX_HISTORY_SIZE`: 修改内存中保留的历史价格数据量（默认约 1 小时）。

## 🤝 贡献指南

欢迎提交 Pull Requests。如果您有重大的功能修改建议，请先提交 Issue 进行讨论。

## 📄 开源协议

[MIT](LICENSE)
