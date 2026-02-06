# 图表数据智能爬取工具

这是一个基于 Flask 的 Web 应用，帮助你从网页中自动提取图表数据。支持常见图表库（ECharts/Highcharts/Chart.js/D3/Plotly 等）、表格数据、`script[type=application/json]` 数据，并提供 JSON/CSV 导出。

## 功能亮点

- 自动识别常见图表配置数据（`series`/`datasets`/`xAxis`/`data` 等）。
- 支持 Cookie / Headers / 代理，适用于需要登录或授权的站点。
- 可自定义正则表达式增强匹配能力。
- 支持 JSON/CSV/Excel/Word 导出，内置复制数据按钮与基础 CSRF 保护。
- 支持“一键动态爬取”模式（需要 Playwright），适用于 SPA/实时页面。
- 现代化 UI + 响应式布局。

## 快速开始

1. 安装依赖：

```bash
pip install -r requirements.txt
```

2. 启动服务：

```bash
python app.py
```

3. 浏览器访问：

```
http://localhost:5000
```

> 启动后会自动打开浏览器页面。

> 默认会在启动时自动检测依赖并尝试安装（可通过环境变量 `AUTO_INSTALL_DEPS=0` 关闭）。

## 使用建议

- 对于需要登录的网站，请先在浏览器中登录，并把 Cookie 粘贴到高级设置中。
- 如果数据来自 API 接口，建议先通过 DevTools Network 确认接口是否可直接访问。
- 如果页面脚本被混淆，可尝试添加自定义正则提升识别效果。
- 如果数据由 JavaScript 动态渲染，启用“动态爬取”并安装 Playwright 依赖。

## 注意事项

- 本工具会阻止访问本地与内网地址，以降低 SSRF 风险。
- 如果需要部署到公网，建议设置环境变量 `SECRET_KEY` 以增强会话安全。
- 请遵守目标网站的使用条款与 robots 协议。

## 导出说明

- JSON 导出包含所有数据块的结构化内容。
- CSV 导出会将每个数据块作为一行，适合快速查看与二次处理。
- Excel 导出会为每个数据块创建一个工作表，并尝试结构化表格数据。
- Word 导出会为每个数据块创建表格，保持列对齐。
