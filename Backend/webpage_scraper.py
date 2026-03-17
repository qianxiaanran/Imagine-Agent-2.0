from __future__ import annotations

import ipaddress
import os
import re
import socket
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse, urlunparse

SCRAPLING_IMPORT_ERROR: Optional[Exception] = None
try:
    from scrapling import StealthyFetcher

    SCRAPLING_AVAILABLE = True
except Exception as exc:  # pragma: no cover - import fallback
    StealthyFetcher = None  # type: ignore
    SCRAPLING_AVAILABLE = False
    SCRAPLING_IMPORT_ERROR = exc


MAX_URLS = max(1, int(os.getenv("SCRAPLING_MAX_URLS", "3")))
FETCH_TIMEOUT_SECONDS = max(5, int(os.getenv("SCRAPLING_FETCH_TIMEOUT_SECONDS", "45")))
STEALTH_TIMEOUT_MS = max(
    5000,
    int(os.getenv("SCRAPLING_STEALTH_TIMEOUT_MS", str(FETCH_TIMEOUT_SECONDS * 1000))),
)
STEALTH_WAIT_MS = max(0, int(os.getenv("SCRAPLING_STEALTH_WAIT_MS", "300")))
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
    if not SCRAPLING_AVAILABLE or StealthyFetcher is None:
        raise WebpageScrapeError(f"Scrapling unavailable: {SCRAPLING_IMPORT_ERROR}")

    safe_urls = extract_supported_urls("\n".join(urls), max_urls=MAX_URLS)
    pages: List[Dict[str, str]] = []
    errors: List[Dict[str, str]] = []
    total_chars = 0

    for url in safe_urls:
        remaining_chars = MAX_TOTAL_CHARS - total_chars
        if remaining_chars <= 0:
            break

        try:
            page = _fetch_one_page(url, remaining_chars=remaining_chars)
            pages.append(page)
            total_chars += len(page.get("content") or "")
        except Exception as exc:
            errors.append({"url": url, "error": str(exc)})

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
    content = _extract_best_content(response)
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
    if StealthyFetcher is None:
        raise WebpageScrapeError("Scrapling StealthyFetcher unavailable")

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


def _extract_best_content(response) -> str:
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
