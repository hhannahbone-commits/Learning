from dataclasses import dataclass
import json
import re
from urllib.parse import urlparse

from bs4 import BeautifulSoup
import requests
from flask import Flask, render_template, request

app = Flask(__name__)

DEFAULT_TIMEOUT = 20
MAX_RESULTS = 50
MAX_TEXT_LENGTH = 2000
SCRIPT_SCAN_LIMIT = 20000
MAX_DATA_SOURCES = 30


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

DATA_PATTERN = re.compile(
    r"(?P<key>series|dataset|datasets|xAxis|yAxis|values|labels)\s*:\s*(?P<value>[\[{])",
    re.IGNORECASE,
)


@dataclass
class DataSource:
    label: str
    value: str
    formatted: str | None


def _find_balanced_block(text: str, start_index: int) -> tuple[str, int] | None:
    stack = []
    in_string = False
    string_char = ""
    escape = False

    for index in range(start_index, len(text)):
        char = text[index]
        if escape:
            escape = False
            continue
        if char == "\\":
            escape = True
            continue
        if in_string:
            if char == string_char:
                in_string = False
            continue
        if char in ("'", '"'):
            in_string = True
            string_char = char
            continue
        if char in "[{":
            stack.append(char)
        elif char in "]}":
            if not stack:
                break
            opener = stack.pop()
            if (opener == "[" and char != "]") or (opener == "{" and char != "}"):
                break
            if not stack:
                return text[start_index : index + 1], index + 1
    return None


def _normalize_to_json(raw: str) -> str | None:
    cleaned = raw.strip()
    try:
        json.loads(cleaned)
        return json.dumps(json.loads(cleaned), ensure_ascii=False, indent=2)
    except json.JSONDecodeError:
        pass

    normalized = cleaned.replace("'", '"')
    normalized = normalized.replace("undefined", "null").replace("NaN", "null")
    normalized = normalized.replace("true", "true").replace("false", "false")
    try:
        parsed = json.loads(normalized)
        return json.dumps(parsed, ensure_ascii=False, indent=2)
    except json.JSONDecodeError:
        return None


def normalize_url(raw_url: str) -> str:
    parsed = urlparse(raw_url)
    if not parsed.scheme:
        return f"https://{raw_url}"
    return raw_url


def extract_chart_data(html: str) -> tuple[list[DataSource], list[str]]:
    soup = BeautifulSoup(html, "html.parser")
    data_sources: list[DataSource] = []
    raw_snippets: list[str] = []

    for script in soup.find_all("script"):
        content = script.string or ""
        if not content:
            continue
        lowered = content.lower()
        if any(keyword in lowered for keyword in CHART_KEYWORDS):
            snippet = " ".join(content.split())
            raw_snippets.append(snippet[:SCRIPT_SCAN_LIMIT])

            for match in DATA_PATTERN.finditer(content):
                key = match.group("key")
                block = _find_balanced_block(content, match.start("value"))
                if not block:
                    continue
                value = block[0].strip()
                formatted = _normalize_to_json(value)
                label = f"{key} 数据"
                data_sources.append(
                    DataSource(label=label, value=value[:MAX_TEXT_LENGTH], formatted=formatted)
                )
                if len(data_sources) >= MAX_DATA_SOURCES:
                    break
        if len(data_sources) >= MAX_DATA_SOURCES:
            break

    return data_sources, raw_snippets[:MAX_RESULTS]


def scrape_content(url: str) -> tuple[list[DataSource], list[str]]:
    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(url, headers=headers, timeout=DEFAULT_TIMEOUT)
    response.raise_for_status()
    return extract_chart_data(response.text)


@app.route("/", methods=["GET", "POST"])
def index():
    data = {
        "url": "",
        "data_sources": [],
        "raw_snippets": [],
        "error": "",
        "searched": False,
    }

    if request.method == "POST":
        data["searched"] = True
        data["url"] = request.form.get("url", "").strip()
        if not data["url"]:
            data["error"] = "请输入网址。"
        else:
            try:
                target_url = normalize_url(data["url"])
                data["data_sources"], data["raw_snippets"] = scrape_content(target_url)
                data["url"] = target_url
            except requests.RequestException as exc:
                data["error"] = f"请求失败：{exc}"
            except Exception as exc:  # noqa: BLE001
                data["error"] = f"解析失败：{exc}"

    return render_template("index.html", **data)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
