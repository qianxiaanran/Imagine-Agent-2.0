from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import ipaddress
import os
import re
import socket
from typing import Any
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse, urlunparse

SCRAPLING_IMPORT_ERROR: Optional[Exception] = None
try:
    from scrapling import Fetcher, StealthyFetcher

    SCRAPLING_AVAILABLE = True
except Exception as exc:  # pragma: no cover - import fallback
    Fetcher = None  # type: ignore
    StealthyFetcher = None  # type: ignore
    SCRAPLING_AVAILABLE = False
    SCRAPLING_IMPORT_ERROR = exc


MAX_URLS = max(1, int(os.getenv("SCRAPLING_MAX_URLS", "3")))
STATIC_FETCH_TIMEOUT_SECONDS = max(4, int(os.getenv("SCRAPLING_STATIC_TIMEOUT_SECONDS", "12")))
STATIC_FETCH_RETRIES = max(1, int(os.getenv("SCRAPLING_STATIC_RETRIES", "1")))
STEALTH_TIMEOUT_MS = max(
    5000,
    int(os.getenv("SCRAPLING_STEALTH_TIMEOUT_MS", "20000")),
)
STEALTH_WAIT_MS = max(0, int(os.getenv("SCRAPLING_STEALTH_WAIT_MS", "300")))
SCRAPE_FETCH_CONCURRENCY = max(1, int(os.getenv("SCRAPLING_FETCH_CONCURRENCY", "2")))
MAX_CHARS_PER_PAGE = max(1200, int(os.getenv("SCRAPLING_MAX_CHARS_PER_PAGE", "12000")))
MAX_TOTAL_CHARS = max(MAX_CHARS_PER_PAGE, int(os.getenv("SCRAPLING_MAX_TOTAL_CHARS", "18000")))
STEALTH_HEADLESS = os.getenv("SCRAPLING_HEADLESS", "true").lower() != "false"
STEALTH_SOLVE_CLOUDFLARE = os.getenv("SCRAPLING_SOLVE_CLOUDFLARE", "true").lower() != "false"

_URL_PATTERN = re.compile(r"https?://[^\s<>\"]+", re.IGNORECASE)
_TRAILING_PUNCTUATION = ".,;:!?)]}\"'，。；：！？）】》、"
_UNSAFE_HOST_SUFFIXES = (".local", ".internal", ".lan", ".home", ".localhost")
_UNSUPPORTED_EXTENSIONS = {
    ".pdf",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".ppt",
    ".pptx",
    ".zip",
    ".rar",
    ".7z",
    ".csv",
}
_CONTENT_ROOT_SELECTORS = (
    "article",
    "main",
    "[role='main']",
    "#content",
    "#main-content",
    ".article",
    ".article-content",
    ".post-content",
    ".entry-content",
    ".content",
    ".markdown-body",
)
_WEATHER_HOST_HINTS = (
    "weather.com.cn",
    "tianqi.com",
    "2345.com",
    "weather.cma.cn",
    "nmc.cn",
)
_EXCHANGE_RATE_HOST_HINTS = (
    "xe.com",
    "wise.com",
    "exchange-rates.org",
    "currencyrate.today",
    "shishihuilv.com",
    "money-converter.org",
    "finance.sina.com.cn",
)
_BLOCK_PAGE_PATTERNS = (
    "access denied",
    "forbidden",
    "captcha",
    "verify you are human",
    "security check",
    "attention required",
    "enable javascript",
    "robot check",
    "cloudflare",
)


class WebpageScrapeError(RuntimeError):
    """Raised when webpage scraping cannot continue safely."""


def extract_supported_urls(text: str, max_urls: int = MAX_URLS) -> List[str]:
    if not text:
        return []

    urls: List[str] = []
    seen = set()
    for raw in _URL_PATTERN.findall(str(text)):
        normalized = _normalize_url(raw)
        if not normalized:
            continue
        if _is_unsupported_extension(normalized):
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        urls.append(normalized)
        if len(urls) >= max(1, int(max_urls or MAX_URLS)):
            break
    return urls


def scrape_urls_for_chat(urls: List[str]) -> Dict[str, List[Dict[str, str]]]:
    if not SCRAPLING_AVAILABLE or (Fetcher is None and StealthyFetcher is None):
        raise WebpageScrapeError(f"Scrapling unavailable: {SCRAPLING_IMPORT_ERROR}")

    safe_urls = extract_supported_urls("\n".join(urls), max_urls=MAX_URLS)
    pages: List[Dict[str, str]] = []
    errors: List[Dict[str, str]] = []
    total_chars = 0
    if not safe_urls:
        return {"pages": pages, "errors": errors}

    task_results: Dict[int, Dict[str, str]] = {}
    task_errors: Dict[int, Dict[str, str]] = {}

    max_workers = min(SCRAPE_FETCH_CONCURRENCY, len(safe_urls))
    if max_workers <= 1:
        for idx, url in enumerate(safe_urls):
            try:
                task_results[idx] = _fetch_one_page(url, remaining_chars=MAX_CHARS_PER_PAGE)
            except Exception as exc:
                task_errors[idx] = {"url": url, "error": str(exc)}
    else:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_map = {
                executor.submit(_fetch_one_page, url, remaining_chars=MAX_CHARS_PER_PAGE): (idx, url)
                for idx, url in enumerate(safe_urls)
            }
            for future in as_completed(future_map):
                idx, url = future_map[future]
                try:
                    task_results[idx] = future.result()
                except Exception as exc:
                    task_errors[idx] = {"url": url, "error": str(exc)}

    for idx, url in enumerate(safe_urls):
        remaining_chars = MAX_TOTAL_CHARS - total_chars
        if remaining_chars <= 0:
            break

        page = task_results.get(idx)
        if page:
            content = str(page.get("content") or "")
            if len(content) > remaining_chars:
                if remaining_chars < 400:
                    break
                page = dict(page)
                page["content"] = _truncate(content, remaining_chars)
                page["snippet"] = _make_snippet(page["content"])
            pages.append(page)
            total_chars += len(page.get("content") or "")
            continue

        err = task_errors.get(idx)
        if err:
            errors.append(err)

    return {"pages": pages, "errors": errors}


def _fetch_one_page(url: str, *, remaining_chars: int) -> Dict[str, str]:
    safe, reason = _is_safe_public_url(url)
    if not safe:
        raise WebpageScrapeError(reason)

    response = _fetch_response(url)
    final_url = _normalize_url(str(getattr(response, "url", "") or url)) or url
    final_safe, final_reason = _is_safe_public_url(final_url)
    if not final_safe:
        raise WebpageScrapeError(final_reason)

    status_code = int(getattr(response, "status", 0) or 0)
    if status_code and status_code >= 400:
        raise WebpageScrapeError(f"HTTP {status_code}")

    headers = getattr(response, "headers", {}) or {}
    content_type = str(headers.get("content-type") or "").lower()
    if content_type and not any(token in content_type for token in ("html", "xml", "text/")):
        raise WebpageScrapeError(f"Unsupported content-type: {content_type}")

    title = _extract_title(response)
    content = _extract_best_content(response, final_url=final_url)
    if not content:
        raise WebpageScrapeError("No readable webpage content extracted")

    page_limit = min(MAX_CHARS_PER_PAGE, max(500, int(remaining_chars)))
    trimmed_content = _truncate(content, page_limit)
    source_name = _source_name_from_url(final_url)

    return {
        "url": url,
        "final_url": final_url,
        "title": title or source_name or final_url,
        "source": source_name,
        "content": trimmed_content,
        "snippet": _make_snippet(trimmed_content),
    }


def _fetch_response(url: str):
    if Fetcher is None and StealthyFetcher is None:
        raise WebpageScrapeError("Scrapling fetchers unavailable")

    last_error: Optional[Exception] = None

    if Fetcher is not None:
        try:
            response = _fetch_response_static(url)
            if _is_response_usable(response, url):
                return response
        except Exception as exc:
            last_error = exc

    if StealthyFetcher is None:
        raise WebpageScrapeError(str(last_error or "Scrapling StealthyFetcher unavailable"))

    request_kwargs = {
        "headless": STEALTH_HEADLESS,
        "load_dom": True,
        "network_idle": True,
        "timeout": STEALTH_TIMEOUT_MS,
        "wait": STEALTH_WAIT_MS,
        "retries": 2,
        "retry_delay": 1,
    }
    response = StealthyFetcher.fetch(url, solve_cloudflare=False, **request_kwargs)
    status_code = int(getattr(response, "status", 0) or 0)
    if status_code in {401, 403, 429, 503} and STEALTH_SOLVE_CLOUDFLARE:
        return StealthyFetcher.fetch(url, solve_cloudflare=True, **request_kwargs)
    return response


def _fetch_response_static(url: str):
    if Fetcher is None:
        raise WebpageScrapeError("Scrapling Fetcher unavailable")

    request_kwargs = {
        "timeout": STATIC_FETCH_TIMEOUT_SECONDS,
        "follow_redirects": True,
        "retries": STATIC_FETCH_RETRIES,
        "retry_delay": 0.5,
    }
    try:
        return Fetcher.get(url, **request_kwargs)
    except Exception as exc:
        if not _is_ssl_error(exc):
            raise
    return Fetcher.get(url, verify=False, **request_kwargs)


def _extract_title(response) -> str:
    for selector in (
        "meta[property='og:title']",
        "meta[name='twitter:title']",
        "title",
        "h1",
    ):
        nodes = response.css(selector)
        if not nodes:
            continue
        node = nodes[0]
        value = ""
        if selector.startswith("meta"):
            value = str(node.attrib.get("content") or "").strip()
        else:
            value = str(getattr(node, "text", "") or "").strip()
        if value:
            return value
    return ""


def _extract_best_content(response, final_url: str = "") -> str:
    specialized = _extract_specialized_content(response, final_url=final_url)
    if specialized:
        return specialized

    best_text = ""
    best_score = -1

    for selector in _CONTENT_ROOT_SELECTORS:
        nodes = response.css(selector)
        if not nodes:
            continue
        for node in nodes[:3]:
            text = _clean_text(str(node.get_all_text(separator="\n", strip=True)))
            if len(text) < 120:
                continue
            score = len(text)
            if selector in {"article", "main", "[role='main']"}:
                score += 600
            elif selector.startswith("#"):
                score += 350
            elif selector.startswith("."):
                score += 200
            if score > best_score:
                best_score = score
                best_text = text

    body_nodes = response.css("body")
    body = body_nodes[0] if body_nodes else None
    if body is not None:
        body_text = _clean_text(str(body.get_all_text(separator="\n", strip=True)))
        if len(body_text) > len(best_text):
            if len(best_text) < 600 or len(body_text) <= len(best_text) * 2:
                best_text = body_text

    return best_text


def _extract_specialized_content(response, final_url: str = "") -> str:
    host = _source_name_from_url(final_url)
    if any(hint in host for hint in _WEATHER_HOST_HINTS):
        body_text = _extract_body_text(response)
        if not body_text:
            return ""
        for extractor in (_extract_weather_dot_com_cn, _extract_tianqi_dot_com, _extract_generic_weather_block):
            specialized = extractor(body_text)
            if specialized:
                return specialized
    if any(hint in host for hint in _EXCHANGE_RATE_HOST_HINTS):
        body_text = _extract_body_text(response)
        if not body_text:
            return ""
        specialized = _extract_exchange_rate_block(body_text)
        if specialized:
            return specialized
    return ""


def _is_weather_url(url: str) -> bool:
    host = _source_name_from_url(url)
    return any(hint in host for hint in _WEATHER_HOST_HINTS)


def _is_exchange_rate_url(url: str) -> bool:
    host = _source_name_from_url(url)
    return any(hint in host for hint in _EXCHANGE_RATE_HOST_HINTS)


def _extract_body_text(response) -> str:
    body_nodes = response.css("body")
    body = body_nodes[0] if body_nodes else None
    if body is None:
        return ""
    return _clean_text(str(body.get_all_text(separator="\n", strip=True)))


def _extract_weather_dot_com_cn(text: str) -> str:
    compact = str(text or "")
    update_match = re.search(r"(\d{1,2}:\d{2})更新", compact)
    day_matches = re.findall(
        r"\d{1,2}日（(今天|明天|后天)）\s+([^\n]+?)\s+(\d{1,2})\s*/\s*(\d{1,2})℃\s+([^\n]+?)(?=\s+\d{1,2}日（(?:今天|明天|后天|周.)）|\s+分时段预报|$)",
        compact,
    )
    if not day_matches:
        return ""

    lines = []
    if update_match:
        lines.append(f"更新时间: {update_match.group(1)}")
    for day_label, condition, high, low, wind in day_matches[:3]:
        lines.append(f"{str(day_label).strip()}天气: {str(condition).strip()}")
        lines.append(f"{str(day_label).strip()}最高/最低气温: {str(high).strip()}/{str(low).strip()}℃")
        if str(wind or "").strip():
            lines.append(f"{str(day_label).strip()}风力: {str(wind).strip()}")
    return "\n".join(lines).strip()


def _extract_tianqi_dot_com(text: str) -> str:
    compact = str(text or "")
    direct_match = re.search(
        r"今日天气[:：]\s*([^，,\n]+)[，,]([^，,\n]+)[，,](\d{1,2})℃~(\d{1,2})℃[，,]([^，,\n]+)(?:[，,]当前温度(\d{1,2})℃)?",
        compact,
    )
    if direct_match:
        city, condition, low, high, wind, current = [str(group or "").strip() for group in direct_match.groups()]
        lines = [f"城市: {city}", f"今日天气: {condition}", f"最高/最低气温: {high}/{low}℃", f"风力: {wind}"]
        if current:
            lines.append(f"当前温度: {current}℃")
        return "\n".join(lines).strip()

    forecast_match = re.search(
        r"(\d{4}年\d{2}月\d{2}日)\s+星期.\s+[^\n]*\s+今日天气[:：]\s*([^，,\n]+)[，,]([^，,\n]+)[，,](\d{1,2})℃~(\d{1,2})℃",
        compact,
    )
    if forecast_match:
        date_text, city, condition, low, high = [str(group or "").strip() for group in forecast_match.groups()]
        return "\n".join(
            [
                f"日期: {date_text}",
                f"城市: {city}",
                f"今日天气: {condition}",
                f"最高/最低气温: {high}/{low}℃",
            ]
        ).strip()

    return ""


def _extract_generic_weather_block(text: str) -> str:
    lines = [line for line in str(text or "").splitlines() if line.strip()]
    if not lines:
        return ""

    start_idx = -1
    weather_keywords = ("今日天气", "今天", "天气预报", "当前温度", "最高/最低", "℃")
    for idx, line in enumerate(lines):
        if any(keyword in line for keyword in weather_keywords):
            start_idx = idx
            break
    if start_idx < 0:
        return ""

    end_idx = min(len(lines), start_idx + 24)
    selected = []
    for line in lines[start_idx:end_idx]:
        stripped = line.strip()
        if len(stripped) > 60 and "http" not in stripped:
            selected.append(stripped[:60])
        else:
            selected.append(stripped)
    return "\n".join(selected).strip()


def _extract_exchange_rate_block(text: str) -> str:
    compact = str(text or "")
    update_match = re.search(
        r"(\d{4}[年/-]\d{1,2}[月/-]\d{1,2}(?:日)?(?:\s+UTC)?\s+\d{1,2}:\d{2}(?::\d{2})?(?:\s*UTC)?)",
        compact,
    )
    pair_lines: List[str] = []
    seen = set()
    for pattern in (
        r"(?<![\d,])1(?:\.0+)?(?![\d,])\s*([A-Z]{3})\s*=\s*([0-9][0-9\s.,]{0,24})\s*([A-Z]{3})",
        r"(?<![\d,])1(?![\d,])\s*([A-Z]{3})\s*([0-9][0-9\s.,]{0,24})\s*([A-Z]{3})",
    ):
        for match in re.finditer(pattern, compact):
            base_code = str(match.group(1) or "").upper().strip()
            rate_text = re.sub(r"\s+", "", str(match.group(2) or "")).replace(",", "")
            quote_code = str(match.group(3) or "").upper().strip()
            if not base_code or not quote_code or not rate_text:
                continue
            if not re.fullmatch(r"\d+(?:\.\d+)?", rate_text):
                continue
            key = (base_code, quote_code)
            if key in seen:
                continue
            seen.add(key)
            pair_lines.append(f"1 {base_code}: {rate_text} {quote_code}")
            if len(pair_lines) >= 4:
                break
        if len(pair_lines) >= 4:
            break

    if not pair_lines:
        return ""

    lines = []
    if update_match:
        updated_at = re.sub(r"\s+", " ", update_match.group(1)).strip()
        lines.append(f"更新时间: {updated_at}")
    lines.extend(pair_lines)
    return "\n".join(lines).strip()


def _is_response_usable(response, url: str) -> bool:
    status_code = int(getattr(response, "status", 0) or 0)
    if status_code in {401, 403, 429, 503}:
        return False

    headers = getattr(response, "headers", {}) or {}
    content_type = str(headers.get("content-type") or "").lower()
    if content_type and not any(token in content_type for token in ("html", "xml", "text/")):
        return False

    final_url = _normalize_url(str(getattr(response, "url", "") or url)) or url
    content = _extract_best_content(response, final_url=final_url)
    min_len = 40 if (_is_weather_url(final_url) or _is_exchange_rate_url(final_url)) else 120
    if len(content) < min_len:
        return False
    return not _is_probable_block_page(response, content)


def _is_probable_block_page(response, content: str) -> bool:
    title = _extract_title(response).lower()
    preview = re.sub(r"\s+", " ", str(content or "")).strip().lower()[:600]
    hay = f"{title} {preview}"
    return any(pattern in hay for pattern in _BLOCK_PAGE_PATTERNS)


def _clean_text(text: str) -> str:
    if not text:
        return ""
    cleaned_lines: List[str] = []
    for raw_line in str(text).splitlines():
        line = re.sub(r"\s+", " ", raw_line).strip()
        if not line:
            continue
        if cleaned_lines and cleaned_lines[-1] == line:
            continue
        cleaned_lines.append(line)
    return "\n".join(cleaned_lines).strip()


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    truncated = text[: max(0, limit - 1)].rsplit("\n", 1)[0].strip()
    if not truncated:
        truncated = text[: max(0, limit - 1)].strip()
    return f"{truncated}…"


def _make_snippet(text: str, limit: int = 220) -> str:
    compact = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(compact) <= limit:
        return compact
    return f"{compact[: max(0, limit - 1)].rstrip()}…"


def _is_ssl_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return "ssl" in message or "certificate" in message or "issuer certificate" in message


def _normalize_url(raw: str) -> Optional[str]:
    if not raw:
        return None
    candidate = str(raw).strip().rstrip(_TRAILING_PUNCTUATION)
    parsed = urlparse(candidate)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    normalized = parsed._replace(fragment="")
    return urlunparse(normalized)


def _is_unsupported_extension(url: str) -> bool:
    path = (urlparse(url).path or "").lower()
    return any(path.endswith(ext) for ext in _UNSUPPORTED_EXTENSIONS)


def _source_name_from_url(url: str) -> str:
    host = (urlparse(url).netloc or "").strip().lower()
    return host[4:] if host.startswith("www.") else host


def _is_safe_public_url(url: str) -> Tuple[bool, str]:
    parsed = urlparse(url)
    host = (parsed.hostname or "").strip().lower()
    if not host:
        return False, "Invalid URL host"
    if host == "localhost" or host.endswith(_UNSAFE_HOST_SUFFIXES):
        return False, f"Blocked local hostname: {host}"
    if "." not in host and not _looks_like_ip(host):
        return False, f"Blocked non-public hostname: {host}"

    if _looks_like_ip(host):
        ip = ipaddress.ip_address(host)
        if not ip.is_global:
            return False, f"Blocked non-public IP: {host}"
        return True, ""

    try:
        resolved_hosts = {
            info[4][0]
            for info in socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
            if info and info[4]
        }
    except OSError as exc:
        return False, f"Host resolution failed: {exc}"

    if not resolved_hosts:
        return False, f"Host resolution failed: {host}"

    for resolved in resolved_hosts:
        ip = ipaddress.ip_address(resolved)
        if not ip.is_global:
            return False, f"Blocked non-public resolved IP: {resolved}"
    return True, ""


def _looks_like_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False
