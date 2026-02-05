# 网站图表数据爬取实现思路

下面给出通用的排查与实现流程，适用于大多数由前端图表库渲染的页面（如 ECharts、Highcharts、Chart.js、D3 等）。

## 1. 先确认数据来源

1. **网络请求优先**
   - 打开浏览器 DevTools → Network。
   - 刷新页面，筛选 `XHR/Fetch`，查看是否有返回 JSON 的接口。
   - 如果接口存在，优先使用请求接口的方式获取数据（稳定、效率高）。

2. **页面内嵌数据**
   - 查看页面源代码（View Source），搜索 `series`、`data`、`option`、`__DATA__`、`window.__INITIAL_STATE__` 等关键字。
   - 很多图表会把数据或配置对象内嵌在 script 中。

3. **前端运行时生成**
   - 有些页面会在浏览器端运行 JS 计算图表数据。
   - 需要通过无头浏览器执行 JS，再从全局变量或图表实例中读出数据。

## 2. 常见图表库的数据获取方式

- **ECharts**
  - 可能存在 `option` 对象：`myChart.setOption(option)`。
  - 无头浏览器里可通过 `chart.getOption()` 获取。

- **Highcharts**
  - 通常可访问 `Highcharts.charts` 数组，或通过 DOM 查找图表实例。

- **Chart.js**
  - 可通过 `Chart.instances` 或在页面脚本中找到 `new Chart(ctx, config)` 的 `config.data`。

## 3. 最稳妥的实现方案

### 方案 A：直接请求接口（推荐）

1. 用 DevTools 找到数据接口。
2. 复制请求头（如 `Authorization`、`Cookie`）。
3. 用 `requests` 发请求，解析 JSON。

### 方案 B：无头浏览器执行 JS

适用于无接口或前端动态计算数据的情况。

- 使用 Playwright/Puppeteer 加载页面。
- 等待图表渲染完成。
- 在页面上下文里执行 JS 读取数据。

## 4. 示例：Playwright 获取图表数据（Python）

下面示例展示了如何在页面内执行 JS，把 `window.chartData` 取出来。你需要根据实际页面调整 JS 逻辑。

```python
from playwright.sync_api import sync_playwright

url = "https://example.com/chart-page"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto(url, wait_until="networkidle")

    # 示例：从全局变量中取数据
    data = page.evaluate("""
        () => {
            if (window.chartData) {
                return window.chartData;
            }
            // 假设页面使用 ECharts 并把实例挂在 window.myChart 上
            if (window.myChart && window.myChart.getOption) {
                return window.myChart.getOption();
            }
            return null;
        }
    """)

    print(data)
    browser.close()
```

## 5. 示例：requests 直接获取接口数据

```python
import requests

url = "https://example.com/api/chart-data"
headers = {
    "User-Agent": "Mozilla/5.0",
}

resp = requests.get(url, headers=headers, timeout=30)
resp.raise_for_status()
print(resp.json())
```

## 6. 排查与调试技巧

- 使用 `page.on("response", ...)` 监听所有请求，定位图表数据接口。
- 如果数据被加密或签名，观察请求参数中是否有时间戳、签名字段。
- 如果接口需要登录，优先用 Playwright 登录后复用 cookie。

## 7. 合规注意事项

- 确认目标网站的 `robots.txt` 和用户协议允许抓取。
- 避免高频访问，设置合理的请求间隔和缓存。
- 对需要授权的数据，务必取得授权后再抓取。

## 8. 针对指定站点的操作示例（https://pm.gd.csg.cn/portal/#/home）

> 提示：该站点通常需要登录权限。以下流程以“已授权访问”为前提，重点是定位实际的数据接口与参数。

1. **先在浏览器手动登录并打开图表页面**
   - 用 Chrome 打开页面并登录，确保图表能正常显示。
   - 打开 DevTools → Network，勾选 Preserve log。

2. **定位图表数据接口**
   - 刷新页面，切换 Network 过滤为 `Fetch/XHR`。
   - 点击图表或切换筛选条件（如时间、地区），观察新增请求。
   - 找到返回 JSON（或可解析的响应）的请求，记录：
     - 请求 URL
     - 请求方法（GET/POST）
     - Query/Body 参数
     - 必要请求头（如 `Authorization`、`Cookie`、`X-Requested-With`）

3. **在复制的接口上先用 curl/requests 验证**
   - 把 DevTools 里请求“Copy as cURL”，在本地或脚本里复用。
   - 若需要登录态，优先使用浏览器里当前会话的 Cookie。

4. **如果接口参数含签名或时间戳**
   - 观察 JS 源码中是否有生成签名的逻辑（Search 关键词：`sign`、`timestamp`、`token`）。
   - 需要时通过无头浏览器执行 JS 来生成签名。

5. **示例：Playwright 复用登录态后抓取接口**

```python
from playwright.sync_api import sync_playwright

url = "https://pm.gd.csg.cn/portal/#/home"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()

    # 1) 打开页面并手动登录（首次运行时可改为 headless=False）
    page.goto(url, wait_until="networkidle")

    # 2) 在控制台打印接口响应，协助定位
    def handle_response(resp):
        if "api" in resp.url and resp.request.resource_type == "xhr":
            if resp.status == 200 and "application/json" in (resp.headers.get("content-type") or ""):
                print(resp.url, resp.status)

    page.on("response", handle_response)

    # 等待一段时间让图表数据请求完成
    page.wait_for_timeout(10000)

    browser.close()
```

> 实际抓取时建议：先在 DevTools 中明确接口与参数，再用 requests 或 Playwright 执行同样的请求。这样成功率最高。
