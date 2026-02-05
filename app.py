from urllib.parse import urlparse

from bs4 import BeautifulSoup
import requests
from flask import Flask, render_template, request

app = Flask(__name__)

DEFAULT_TIMEOUT = 20
MAX_RESULTS = 50
MAX_TEXT_LENGTH = 2000


def normalize_url(raw_url: str) -> str:
    parsed = urlparse(raw_url)
    if not parsed.scheme:
        return f"https://{raw_url}"
    return raw_url


def scrape_content(url: str, selector: str) -> list[str]:
    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(url, headers=headers, timeout=DEFAULT_TIMEOUT)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    elements = soup.select(selector) if selector else []
    results: list[str] = []
    for element in elements[:MAX_RESULTS]:
        text = " ".join(element.get_text(strip=True).split())
        if text:
            results.append(text[:MAX_TEXT_LENGTH])
    return results


@app.route("/", methods=["GET", "POST"])
def index():
    data = {
        "url": "",
        "selector": "",
        "results": [],
        "error": "",
    }

    if request.method == "POST":
        data["url"] = request.form.get("url", "").strip()
        data["selector"] = request.form.get("selector", "").strip()

        if not data["url"]:
            data["error"] = "请输入网址。"
        elif not data["selector"]:
            data["error"] = "请输入 CSS 选择器。"
        else:
            try:
                target_url = normalize_url(data["url"])
                data["results"] = scrape_content(target_url, data["selector"])
                data["url"] = target_url
            except requests.RequestException as exc:
                data["error"] = f"请求失败：{exc}"
            except Exception as exc:  # noqa: BLE001
                data["error"] = f"解析失败：{exc}"

    return render_template("index.html", **data)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
