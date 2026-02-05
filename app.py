from urllib.parse import urlparse

from bs4 import BeautifulSoup
import requests
from flask import Flask, render_template, request

app = Flask(__name__)

DEFAULT_TIMEOUT = 20
MAX_RESULTS = 50
MAX_TEXT_LENGTH = 2000
SCRIPT_SCAN_LIMIT = 20000


CHART_KEYWORDS = (
    "echarts",
    "highcharts",
    "chart.js",
    "chartjs",
    "series",
    "xAxis",
    "yAxis",
    "dataset",
)


def normalize_url(raw_url: str) -> str:
    parsed = urlparse(raw_url)
    if not parsed.scheme:
        return f"https://{raw_url}"
    return raw_url


def extract_chart_data(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    results: list[str] = []

    for script in soup.find_all("script"):
        content = script.string or ""
        if not content:
            continue
        lowered = content.lower()
        if any(keyword in lowered for keyword in CHART_KEYWORDS):
            snippet = " ".join(content.split())
            results.append(snippet[:SCRIPT_SCAN_LIMIT])

    return results[:MAX_RESULTS]


def scrape_content(url: str) -> list[str]:
    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(url, headers=headers, timeout=DEFAULT_TIMEOUT)
    response.raise_for_status()
    return extract_chart_data(response.text)


@app.route("/", methods=["GET", "POST"])
def index():
    data = {
        "url": "",
        "results": [],
        "error": "",
    }

    if request.method == "POST":
        data["url"] = request.form.get("url", "").strip()
        if not data["url"]:
            data["error"] = "请输入网址。"
        else:
            try:
                target_url = normalize_url(data["url"])
                data["results"] = scrape_content(target_url)
                data["url"] = target_url
            except requests.RequestException as exc:
                data["error"] = f"请求失败：{exc}"
            except Exception as exc:  # noqa: BLE001
                data["error"] = f"解析失败：{exc}"

    return render_template("index.html", **data)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
