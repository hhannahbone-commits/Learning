from __future__ import annotations

from dataclasses import dataclass, asdict
import csv
import io
import json
import re
import socket
from typing import Any
from urllib.parse import urlparse

from bs4 import BeautifulSoup
import requests
from flask import Flask, Response, render_template, request

app = Flask(__name__)

DEFAULT_TIMEOUT = 20
MAX_RESULTS = 80
MAX_TEXT_LENGTH = 4000
SCRIPT_SCAN_LIMIT = 30000
MAX_DATA_SOURCES = 60

CHART_KEYWORDS = (
    "echarts",
    "highcharts",
    "chart.js",
    "chartjs",
    "d3",
    "plotly",
    "apexcharts",
    "recharts",
    "series",
    "dataset",
    "datasets",
    "xAxis",
    "yAxis",
    "values",
    "labels",
)

DATA_PATTERN = re.compile(
    r"(?P<key>series|dataset|datasets|xAxis|yAxis|values|labels|data)\s*:\s*(?P<value>[\[{])",
    re.IGNORECASE,
)

SCRIPT_JSON_TYPES = {"application/json", "application/ld+json"}


@dataclass
class DataSource:
    label: str
    value: str
    formatted: str | None
    source: str


def _strip_js_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    text = re.sub(r"//.*?$", "", text, flags=re.MULTILINE)
    return text


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
        parsed = json.loads(cleaned)
        return json.dumps(parsed, ensure_ascii=False, indent=2)
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


def _is_private_host(hostname: str) -> bool:
    if hostname in {"localhost", "127.0.0.1", "::1"}:
        return True
    private_prefixes = ("10.", "192.168.", "172.16.", "172.17.", "172.18.", "172.19.")
    if hostname.startswith(private_prefixes):
        return True
    try:
        ip = socket.gethostbyname(hostname)
    except socket.gaierror:
        return False
    return ip.startswith(private_prefixes) or ip.startswith("127.")


def _parse_cookie_string(cookie_str: str) -> dict[str, str]:
    cookies: dict[str, str] = {}
    for pair in cookie_str.split(";"):
        if "=" in pair:
            key, value = pair.split("=", 1)
            cookies[key.strip()] = value.strip()
    return cookies


def _parse_headers(headers_str: str) -> dict[str, str] | None:
    if not headers_str:
        return {}
    try:
        parsed = json.loads(headers_str)
    except json.JSONDecodeError:
        return None
    return {str(key): str(value) for key, value in parsed.items()}


def _extract_from_scripts(
    soup: BeautifulSoup, custom_regex: str | None
) -> tuple[list[DataSource], list[str]]:
    data_sources: list[DataSource] = []
    raw_snippets: list[str] = []

    for script in soup.find_all("script"):
        script_type = (script.get("type") or "").lower()
        content = script.string or script.get_text() or ""
        if not content:
            continue

        if script_type in SCRIPT_JSON_TYPES:
            try:
                parsed = json.loads(content)
                formatted = json.dumps(parsed, ensure_ascii=False, indent=2)
                data_sources.append(
                    DataSource(
                        label="脚本 JSON 数据",
                        value=formatted[:MAX_TEXT_LENGTH],
                        formatted=formatted,
                        source="script[type=application/json]",
                    )
                )
            except json.JSONDecodeError:
                pass

        lowered = content.lower()
        if any(keyword in lowered for keyword in CHART_KEYWORDS):
            snippet = " ".join(content.split())
            raw_snippets.append(snippet[:SCRIPT_SCAN_LIMIT])

            cleaned = _strip_js_comments(content)
            for match in DATA_PATTERN.finditer(cleaned):
                key = match.group("key")
                block = _find_balanced_block(cleaned, match.start("value"))
                if not block:
                    continue
                value = block[0].strip()
                formatted = _normalize_to_json(value)
                label = f"{key} 数据"
                data_sources.append(
                    DataSource(
                        label=label,
                        value=value[:MAX_TEXT_LENGTH],
                        formatted=formatted,
                        source="script",
                    )
                )
                if len(data_sources) >= MAX_DATA_SOURCES:
                    break

        if custom_regex:
            try:
                regex = re.compile(custom_regex, re.IGNORECASE | re.DOTALL)
                for idx, match in enumerate(regex.finditer(content), start=1):
                    value = match.group(0)
                    formatted = _normalize_to_json(value)
                    label = f"自定义匹配 #{idx}"
                    data_sources.append(
                        DataSource(
                            label=label,
                            value=value[:MAX_TEXT_LENGTH],
                            formatted=formatted,
                            source="custom regex",
                        )
                    )
            except re.error:
                pass

        if len(data_sources) >= MAX_DATA_SOURCES:
            break

    return data_sources[:MAX_DATA_SOURCES], raw_snippets[:MAX_RESULTS]


def _extract_tables(soup: BeautifulSoup) -> list[DataSource]:
    tables = soup.find_all("table")
    results: list[DataSource] = []
    for index, table in enumerate(tables, start=1):
        rows = table.find_all("tr")
        if not rows:
            continue
        header_cells = rows[0].find_all(["th", "td"])
        headers = [cell.get_text(strip=True) or f"列{idx+1}" for idx, cell in enumerate(header_cells)]
        data_rows = []
        for row in rows[1:]:
            cells = [cell.get_text(strip=True) for cell in row.find_all(["td", "th"])]
            if not any(cells):
                continue
            row_data = {headers[i]: cells[i] if i < len(cells) else "" for i in range(len(headers))}
            data_rows.append(row_data)
        if data_rows:
            formatted = json.dumps(data_rows, ensure_ascii=False, indent=2)
            results.append(
                DataSource(
                    label=f"表格数据 #{index}",
                    value=formatted[:MAX_TEXT_LENGTH],
                    formatted=formatted,
                    source="table",
                )
            )
    return results


def extract_chart_data(
    html: str, custom_regex: str | None
) -> tuple[list[DataSource], list[str]]:
    soup = BeautifulSoup(html, "html.parser")
    data_sources, raw_snippets = _extract_from_scripts(soup, custom_regex)
    data_sources.extend(_extract_tables(soup))
    return data_sources[:MAX_DATA_SOURCES], raw_snippets


def _build_requests_options(form: dict[str, str]) -> tuple[dict[str, str], dict[str, str], dict[str, str], int, str | None]:
    headers = {"User-Agent": "Mozilla/5.0"}
    cookies: dict[str, str] = {}
    proxies: dict[str, str] = {}
    proxy = form.get("proxy", "").strip()
    timeout_raw = form.get("timeout", "").strip()
    custom_regex = form.get("custom_regex", "").strip() or None

    headers_input = form.get("headers", "").strip()
    parsed_headers = _parse_headers(headers_input)
    if parsed_headers is None:
        raise ValueError("Headers 必须是 JSON 格式，例如 {\"Authorization\": \"Bearer ...\"}。")
    headers.update(parsed_headers)

    cookie_input = form.get("cookies", "").strip()
    if cookie_input:
        cookies.update(_parse_cookie_string(cookie_input))

    if proxy:
        proxies = {"http": proxy, "https": proxy}

    timeout = DEFAULT_TIMEOUT
    if timeout_raw:
        try:
            timeout = max(5, min(60, int(timeout_raw)))
        except ValueError:
            raise ValueError("超时时间必须是数字（5-60）。")

    return headers, cookies, proxies, timeout, custom_regex


def scrape_content(
    url: str,
    headers: dict[str, str],
    cookies: dict[str, str],
    proxies: dict[str, str],
    timeout: int,
    custom_regex: str | None,
) -> tuple[list[DataSource], list[str]]:
    response = requests.get(url, headers=headers, cookies=cookies, proxies=proxies, timeout=timeout)
    response.raise_for_status()
    return extract_chart_data(response.text, custom_regex)


def _serialize_data_sources(data_sources: list[DataSource]) -> str:
    return json.dumps([asdict(source) for source in data_sources], ensure_ascii=False)


def _csv_rows_from_sources(data_sources: list[DataSource]) -> list[list[str]]:
    rows = [["label", "source", "data"]]
    for source in data_sources:
        data_value = source.formatted or source.value
        rows.append([source.label, source.source, data_value])
    return rows


def _deserialize_sources(raw: str) -> list[DataSource]:
    try:
        items = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return [DataSource(**item) for item in items if isinstance(item, dict)]


def _prepare_form_data() -> dict[str, Any]:
    return {
        "url": "",
        "cookies": "",
        "headers": "",
        "proxy": "",
        "timeout": str(DEFAULT_TIMEOUT),
        "custom_regex": "",
        "data_sources": [],
        "raw_snippets": [],
        "data_sources_json": "",
        "error": "",
        "searched": False,
    }


@app.route("/", methods=["GET", "POST"])
def index():
    data = _prepare_form_data()

    if request.method == "POST":
        data.update({key: request.form.get(key, "").strip() for key in data if isinstance(data[key], str)})
        data["searched"] = True

        if not data["url"]:
            data["error"] = "请输入网址。"
            return render_template("index.html", **data)

        target_url = normalize_url(data["url"])
        parsed = urlparse(target_url)
        if not parsed.hostname or _is_private_host(parsed.hostname):
            data["error"] = "出于安全考虑，暂不支持访问内网或本地主机地址。"
            return render_template("index.html", **data)

        try:
            headers, cookies, proxies, timeout, custom_regex = _build_requests_options(data)
            data_sources, raw_snippets = scrape_content(
                target_url,
                headers=headers,
                cookies=cookies,
                proxies=proxies,
                timeout=timeout,
                custom_regex=custom_regex,
            )
            data["url"] = target_url
            data["data_sources"] = data_sources
            data["raw_snippets"] = raw_snippets
            data["data_sources_json"] = _serialize_data_sources(data_sources)
        except ValueError as exc:
            data["error"] = str(exc)
        except requests.RequestException as exc:
            data["error"] = f"请求失败：{exc}"
        except Exception as exc:  # noqa: BLE001
            data["error"] = f"解析失败：{exc}"

    return render_template("index.html", **data)


@app.route("/export/json", methods=["POST"])
def export_json() -> Response:
    raw = request.form.get("data_sources_json", "")
    sources = _deserialize_sources(raw)
    payload = json.dumps([asdict(source) for source in sources], ensure_ascii=False, indent=2)
    return Response(
        payload,
        mimetype="application/json",
        headers={"Content-Disposition": "attachment; filename=chart-data.json"},
    )


@app.route("/export/csv", methods=["POST"])
def export_csv() -> Response:
    raw = request.form.get("data_sources_json", "")
    sources = _deserialize_sources(raw)
    output = io.StringIO()
    writer = csv.writer(output)
    for row in _csv_rows_from_sources(sources):
        writer.writerow(row)
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=chart-data.csv"},
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
