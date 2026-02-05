# 图表数据智能爬取工具

这是一个基于 Flask 的 Web 应用，帮助你从网页中自动提取图表数据。支持常见图表库（ECharts/Highcharts/Chart.js/D3/Plotly 等）、表格数据、`script[type=application/json]` 数据，并提供 JSON/CSV 导出。

## 功能亮点

- 自动识别常见图表配置数据（`series`/`datasets`/`xAxis`/`data` 等）。
- 支持 Cookie / Headers / 代理，适用于需要登录或授权的站点。
- 可自定义正则表达式增强匹配能力。
- 支持 JSON/CSV 导出，内置复制数据按钮。
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

## 使用建议

- 对于需要登录的网站，请先在浏览器中登录，并把 Cookie 粘贴到高级设置中。
- 如果数据来自 API 接口，建议先通过 DevTools Network 确认接口是否可直接访问。
- 如果页面脚本被混淆，可尝试添加自定义正则提升识别效果。

## 注意事项

- 本工具会阻止访问本地与内网地址，以降低 SSRF 风险。
- 请遵守目标网站的使用条款与 robots 协议。

## 导出说明

- JSON 导出包含所有数据块的结构化内容。
- CSV 导出会将每个数据块作为一行，适合快速查看与二次处理。
