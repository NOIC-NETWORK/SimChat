import os
import re
import json
import time
import datetime
import ipaddress
import socket
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse, quote_plus
from simchat_mod import BaseSkill, ToolSpec, hook



try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False
    print("[WebSearch] requests 未安装，网络搜索功能不可用")

try:
    from bs4 import BeautifulSoup
    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False
    print("[WebSearch] beautifulsoup4 未安装，网页解析功能受限")

DEFAULT_TIMEOUT = 15
MAX_CONTENT_LENGTH = 50000
MAX_SEARCH_RESULTS = 10
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)

_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
}

_PRIVATE_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("0.0.0.0/8"),
]


def _is_private_ip(hostname: str) -> bool:
    try:
        addr_infos = socket.getaddrinfo(hostname, None)
        for info in addr_infos:
            ip = ipaddress.ip_address(info[4][0])
            for network in _PRIVATE_NETWORKS:
                if ip in network:
                    return True
    except Exception:
        return True
    return False


def _validate_url(url: str) -> Optional[str]:
    if not url or not isinstance(url, str):
        return "URL 不能为空"

    if not url.startswith(("http://", "https://")):
        return "仅支持 http:// 或 https:// 协议"

    try:
        parsed = urlparse(url)
        hostname = parsed.hostname
        if not hostname:
            return "URL 缺少主机名"

        if _is_private_ip(hostname):
            return "禁止访问内网地址（SSRF 防护）"

        return None
    except Exception as e:
        return f"URL 解析失败: {str(e)}"


def _clean_text(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'[ \t\r\n]+', ' ', text)
    text = re.sub(r' +', ' ', text)
    text = text.strip()
    return text


def _truncate_content(text: str, max_length: int = MAX_CONTENT_LENGTH) -> str:
    if len(text) <= max_length:
        return text
    half = max_length // 2
    return text[:half] + "\n... [内容已截断] ...\n" + text[-half:]


def _detect_language(text: str) -> str:
    if re.search(r'[\u4e00-\u9fff]', text):
        return "zh"
    return "en"


class BingSearch:

    @staticmethod
    def search(query: str, max_results: int = MAX_SEARCH_RESULTS,
               timeout: int = DEFAULT_TIMEOUT) -> Dict[str, Any]:
        if not REQUESTS_AVAILABLE:
            return {"success": False, "error": "requests 未安装"}

        try:
            url = "https://www.bing.com/search"
            params = {"q": query, "count": max_results, "setlang": "zh-CN"}
            resp = requests.get(url, params=params, headers=_HEADERS, timeout=timeout)
            resp.raise_for_status()

            if not BS4_AVAILABLE:
                return {
                    "success": True,
                    "source": "bing",
                    "results": [],
                    "raw_html": True,
                    "message": "beautifulsoup4 未安装，无法解析搜索结果"
                }

            soup = BeautifulSoup(resp.text, "html.parser")
            result_items = soup.select(".b_algo")
            results = []

            for item in result_items[:max_results]:
                link_tag = item.select_one("h2 a")
                caption_tag = item.select_one(".b_caption")
                snippet_tag = item.select_one(".b_snippet, p")

                title = link_tag.get_text(strip=True) if link_tag else ""
                href = link_tag.get("href", "") if link_tag else ""

                snippet = ""
                if caption_tag:
                    snippet = caption_tag.get_text(strip=True)
                elif snippet_tag:
                    snippet = snippet_tag.get_text(strip=True)

                results.append({
                    "title": _clean_text(title),
                    "url": href,
                    "snippet": _clean_text(snippet)
                })

            return {
                "success": True,
                "source": "bing",
                "query": query,
                "results": results,
                "count": len(results)
            }

        except requests.Timeout:
            return {"success": False, "error": f"Bing 请求超时 ({timeout}s)"}
        except requests.ConnectionError:
            return {"success": False, "error": "Bing 连接失败，请检查网络"}
        except Exception as e:
            return {"success": False, "error": f"Bing 搜索失败: {str(e)}"}


class SogouSearch:

    @staticmethod
    def search(query: str, max_results: int = MAX_SEARCH_RESULTS,
               timeout: int = DEFAULT_TIMEOUT) -> Dict[str, Any]:
        if not REQUESTS_AVAILABLE:
            return {"success": False, "error": "requests 未安装"}

        try:
            url = "https://www.sogou.com/web"
            params = {"query": query}
            resp = requests.get(url, params=params, headers=_HEADERS, timeout=timeout)
            resp.raise_for_status()

            if not BS4_AVAILABLE:
                return {
                    "success": True,
                    "source": "sogou",
                    "results": [],
                    "raw_html": True,
                    "message": "beautifulsoup4 未安装，无法解析搜索结果"
                }

            soup = BeautifulSoup(resp.text, "html.parser")
            result_items = soup.select(".vrwrap")
            results = []

            for item in result_items[:max_results]:
                link_tag = item.select_one("h3 a")
                snippet_tag = item.select_one(".ft, .str_info, p.str-text-info")

                title = link_tag.get_text(strip=True) if link_tag else ""
                href = link_tag.get("href", "") if link_tag else ""

                snippet = ""
                if snippet_tag:
                    snippet = snippet_tag.get_text(strip=True)
                elif item.select_one("p"):
                    snippet = item.select_one("p").get_text(strip=True)

                results.append({
                    "title": _clean_text(title),
                    "url": href,
                    "snippet": _clean_text(snippet)
                })

            return {
                "success": True,
                "source": "sogou",
                "query": query,
                "results": results,
                "count": len(results)
            }

        except requests.Timeout:
            return {"success": False, "error": f"搜狗请求超时 ({timeout}s)"}
        except requests.ConnectionError:
            return {"success": False, "error": "搜狗连接失败，请检查网络"}
        except Exception as e:
            return {"success": False, "error": f"搜狗搜索失败: {str(e)}"}


class WebPageFetcher:

    @staticmethod
    def fetch(url: str, timeout: int = DEFAULT_TIMEOUT,
              max_content: int = MAX_CONTENT_LENGTH) -> Dict[str, Any]:
        error = _validate_url(url)
        if error:
            return {"success": False, "error": error}

        if not REQUESTS_AVAILABLE:
            return {"success": False, "error": "requests 未安装"}

        try:
            resp = requests.get(url, headers=_HEADERS, timeout=timeout, allow_redirects=True)
            resp.raise_for_status()

            content_type = resp.headers.get("Content-Type", "")
            final_url = resp.url
            status_code = resp.status_code

            if "text/html" in content_type or "application/xhtml" in content_type:
                if BS4_AVAILABLE:
                    soup = BeautifulSoup(resp.text, "html.parser")
                    for tag in soup(["script", "style", "meta", "link", "noscript", "header", "footer", "nav"]):
                        tag.decompose()
                    text = soup.get_text(separator="\n", strip=True)
                else:
                    text = _clean_text(resp.text)
            elif "text/plain" in content_type or "application/json" in content_type:
                text = resp.text
            else:
                text = resp.text[:max_content]

            text = _truncate_content(text, max_content)
            lang = _detect_language(text)

            return {
                "success": True,
                "source": "web_fetch",
                "url": final_url,
                "status_code": status_code,
                "content_type": content_type,
                "content_length": len(text),
                "language": lang,
                "content": text
            }

        except requests.Timeout:
            return {"success": False, "error": f"请求超时 ({timeout}s)"}
        except requests.ConnectionError:
            return {"success": False, "error": "连接失败，请检查网络或 URL 是否正确"}
        except requests.TooManyRedirects:
            return {"success": False, "error": "重定向次数过多"}
        except requests.HTTPError as e:
            return {"success": False, "error": f"HTTP 错误: {e.response.status_code}"}
        except Exception as e:
            return {"success": False, "error": f"抓取失败: {str(e)}"}


class WebSearchSkill(BaseSkill):
    skill_name = "webSearch"
    skill_description = "网络搜索技能：支持关键词搜索（必应/搜狗）、网页内容抓取和信息提取"
    skill_version = "1.0.0"
    trigger_keywords = [
        "搜索", "搜一下", "查一下", "查资料", "搜索一下", "网络搜索",
        "search", "web search", "google", "bing",
        "查天气", "搜天气", "查新闻", "搜新闻", "最新消息", "最新进展",
        "今天新闻", "今天天气", "现在新闻",
        "查网页", "看网页", "网页内容", "网站内容",
        "必应", "搜狗", "sogou",
        "上网查", "帮我查", "帮我搜", "查一下最新", "搜一下最新"
    ]
    input_schema = {
        "action": str,
        "query": str,
        "url": str,
        "source": str,
        "max_results": int,
        "timeout": int,
        "max_content": int
    }

    def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        action = params.get("action", "")
        query = params.get("query", "")
        url = params.get("url", "")

        if not action:
            if url:
                action = "fetch"
            elif query:
                action = "search"
            else:
                return {"success": False, "error": "请提供 action (search/fetch) 或 query/url 参数"}

        if action == "search":
            if not query:
                return {"success": False, "error": "搜索需要提供 query 参数"}
            return self._handle_search(params)

        elif action == "fetch":
            if not url:
                return {"success": False, "error": "抓取需要提供 url 参数"}
            return self._handle_fetch(params)

        elif action == "search_and_summarize":
            if not query:
                return {"success": False, "error": "搜索需要提供 query 参数"}
            search_result = self._handle_search(params)
            if not search_result.get("success"):
                return search_result
            return self._summarize_results(search_result)

        else:
            return {
                "success": False,
                "error": f"未知操作: {action}",
                "supported_actions": ["search", "fetch", "search_and_summarize"]
            }

    def _handle_search(self, params: Dict[str, Any]) -> Dict[str, Any]:
        query = params.get("query", "")
        source = params.get("source", "auto")
        max_results = params.get("max_results", MAX_SEARCH_RESULTS)
        timeout = params.get("timeout", DEFAULT_TIMEOUT)

        if source == "auto":
            lang = _detect_language(query)
            if lang == "zh":
                source = "sogou"
            else:
                source = "bing"

        if source == "bing":
            result = BingSearch.search(query, max_results, timeout)
            if not result.get("success") or not result.get("results"):
                fallback = SogouSearch.search(query, max_results, timeout)
                if fallback.get("success") and fallback.get("results"):
                    fallback["fallback"] = True
                    fallback["primary_failed"] = result.get("error", "无结果")
                    return fallback
            return result

        elif source == "sogou":
            result = SogouSearch.search(query, max_results, timeout)
            if not result.get("success") or not result.get("results"):
                fallback = BingSearch.search(query, max_results, timeout)
                if fallback.get("success") and fallback.get("results"):
                    fallback["fallback"] = True
                    fallback["primary_failed"] = result.get("error", "无结果")
                    return fallback
            return result

        elif source == "both":
            bing_result = BingSearch.search(query, max_results // 2, timeout)
            sogou_result = SogouSearch.search(query, max_results // 2, timeout)

            combined_results = []
            if bing_result.get("success"):
                for r in bing_result.get("results", []):
                    r["source"] = "bing"
                combined_results.extend(bing_result.get("results", []))
            if sogou_result.get("success"):
                for r in sogou_result.get("results", []):
                    r["source"] = "sogou"
                combined_results.extend(sogou_result.get("results", []))

            return {
                "success": True,
                "source": "both",
                "query": query,
                "results": combined_results,
                "count": len(combined_results),
                "bing_status": bing_result.get("success", False),
                "sogou_status": sogou_result.get("success", False)
            }

        else:
            return {"success": False, "error": f"未知搜索源: {source}"}

    def _handle_fetch(self, params: Dict[str, Any]) -> Dict[str, Any]:
        url = params.get("url", "")
        timeout = params.get("timeout", DEFAULT_TIMEOUT)
        max_content = params.get("max_content", MAX_CONTENT_LENGTH)
        return WebPageFetcher.fetch(url, timeout, max_content)

    def _summarize_results(self, search_result: Dict[str, Any]) -> Dict[str, Any]:
        results = search_result.get("results", [])
        if not results:
            return {
                "success": True,
                "summary": "未找到相关结果",
                "source": search_result.get("source", ""),
                "results": []
            }

        summary_parts = []
        for i, r in enumerate(results[:5], 1):
            title = r.get("title", "")
            snippet = r.get("snippet", "")
            url = r.get("url", "")
            part = f"{i}. {title}\n   {snippet}"
            if url:
                part += f"\n   链接: {url}"
            summary_parts.append(part)

        summary = "\n".join(summary_parts)

        return {
            "success": True,
            "summary": summary,
            "source": search_result.get("source", ""),
            "query": search_result.get("query", ""),
            "results": results,
            "count": len(results)
        }

    def get_status(self) -> Dict[str, Any]:
        return {
            "success": True,
            "skill": self.skill_name,
            "requests_available": REQUESTS_AVAILABLE,
            "bs4_available": BS4_AVAILABLE,
            "timeout": DEFAULT_TIMEOUT,
            "max_content": MAX_CONTENT_LENGTH
        }


def init_webSearch_skill():
    manager = get_skill_manager()
    registry = manager.get_registry()

    existing = registry.get_skill("webSearch")
    if existing:
        print("[WebSearch] webSearch 技能已注册")
        return existing

    skill = WebSearchSkill()
    registry.register_skill(skill)
    print("[WebSearch] webSearch 技能初始化完成")
    return skill


if __name__ == "__main__":
    print("[WebSearch] 初始化网络搜索技能...")
    skill = init_webSearch_skill()

    print("\n[WebSearch] 功能列表:")
    print("  action=search              - 关键词搜索")
    print("  action=fetch               - 抓取网页内容")
    print("  action=search_and_summarize - 搜索并整理摘要")

    print("\n[WebSearch] 示例使用:")
    print('  manager = get_skill_manager()')
    print('  result = manager.execute_skill("webSearch", {"action": "search", "query": "Python 3.13"})')
    print('  result = manager.execute_skill("webSearch", {"action": "fetch", "url": "https://example.com"})')
    print('  result = manager.auto_execute("帮我搜索一下今天的新闻")')

# ----- 工具实例 -----
_instance = WebSearchSkill()


def execute(params):
    return _instance.execute(params)


@hook("agent.tool")
def register(api):
    api.register_tool(ToolSpec(
        name="webSearch",
        label="webSearch",
        description=_instance.skill_description,
        risk="read",
        usage="webSearch PARAMS: ...",
        input_schema=_instance.input_schema,
        triggers=_instance.trigger_keywords,
        backend="webSearch:execute",
    ))