#!/usr/bin/env python3
"""
PubMed Monitor - 监控指定领域的新文献，智能筛选后创建 Issue

Usage:
    # 获取文献并智能分析
    python scripts/monitor_pubmed.py \
        --token "ghp_xxx" \
        --repo "owner/repo" \
        --query "(speciation) OR (hybrid speciation) OR (introgression)"

    # 仅扫描获取文献列表
    python scripts/monitor_pubmed.py --scan-only --output /tmp/papers.json

Environment:
    LOG_LEVEL: 设置日志级别 (DEBUG, INFO, WARNING, ERROR)
    PUBMED_EMAIL: 必填，联系邮箱 (NCBI 要求)
"""

import argparse
import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import urllib.request
import urllib.parse

from github import Github

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class PubMedClient:
    """PubMed API 客户端"""

    BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

    def __init__(self, email: str):
        self.email = email
        self.last_request_time = 0

    def _rate_limit(self):
        """速率限制：NCBI 要求每秒最多 3 个请求"""
        elapsed = time.time() - self.last_request_time
        if elapsed < 0.34:
            time.sleep(0.34 - elapsed)
        self.last_request_time = time.time()

    def search(self, query: str, max_results: int = 20,
               mindate: str = None, maxdate: str = None,
               datetype: str = "pdat") -> list[str]:
        """搜索 PubMed，获取 PMID 列表

        Args:
            query: 检索词
            max_results: 最大返回数量
            mindate: 开始日期 (YYYY/MM/DD)
            maxdate: 结束日期
            datetype: 日期类型 (pdat=出版日期)

        Returns:
            PMID 列表
        """
        self._rate_limit()

        params = {
            "db": "pubmed",
            "term": query,
            "retmode": "json",
            "retmax": max_results,
            "datetype": datetype,
            "email": self.email
        }

        if mindate:
            params["mindate"] = mindate
        if maxdate:
            params["maxdate"] = maxdate

        url = f"{self.BASE_URL}/esearch.fcgi?{urllib.parse.urlencode(params)}"

        try:
            with urllib.request.urlopen(url) as response:
                data = json.loads(response.read().decode())
                ids = data.get("esearchresult", {}).get("idlist", [])
                return ids
        except Exception as e:
            logger.error(f"PubMed search failed: {e}")
            return []

    def summary(self, id_list: list[str]) -> dict:
        """获取文献详情

        Args:
            id_list: PMID 列表

        Returns:
            PMID -> 详情 的字典
        """
        if not id_list:
            return {}

        self._rate_limit()

        ids_str = ",".join(id_list)
        params = {
            "db": "pubmed",
            "id": ids_str,
            "retmode": "json",
            "email": self.email
        }

        url = f"{self.BASE_URL}/esummary.fcgi?{urllib.parse.urlencode(params)}"

        try:
            with urllib.request.urlopen(url) as response:
                data = json.loads(response.read().decode())
                return data.get("result", {})
        except Exception as e:
            logger.error(f"PubMed summary failed: {e}")
            return {}


def parse_pubmed_date(date_str: str) -> str:
    """解析 PubMed 日期格式"""
    if not date_str:
        return "Unknown"
    try:
        # PubMed 格式: "2024 Jan 15" 或 "2024/01/15"
        dt = datetime.strptime(date_str.strip(), "%Y %b %d")
        return dt.strftime("%Y-%m-%d")
    except ValueError:
        try:
            dt = datetime.strptime(date_str.strip(), "%Y/%m/%d")
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            return date_str[:10] if date_str else "Unknown"


def clean_text(text: str) -> str:
    """清理文本中的多余空白"""
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip().strip(".")


def truncate_text(text: str, max_length: int = 1500) -> str:
    """截断文本"""
    if not text:
        return ""
    if len(text) <= max_length:
        return text
    return text[:max_length].rsplit(".", 1)[0] + "..."


def fetch_papers(query: str, email: str, days: int = 7,
                 max_papers: int = 20) -> list[dict[str, Any]]:
    """获取 PubMed 新文献

    Args:
        query: 检索词
        email: 联系邮箱
        days: 追溯天数
        max_papers: 最大文献数

    Returns:
        文献列表
    """
    # 计算日期范围
    end_date = datetime.now().strftime("%Y/%m/%d")
    start_date = (datetime.now() - datetime.timedelta(days=days)).strftime("%Y/%m/%d")

    logger.info(f"检索词: {query}")
    logger.info(f"时间范围: {start_date} - {end_date}")

    client = PubMedClient(email)

    # Step 1: esearch 获取 PMID
    pmids = client.search(
        query=query,
        max_results=max_papers * 2,  # 多取一些供筛选
        mindate=start_date,
        maxdate=end_date,
        datetype="pdat"
    )

    if not pmids:
        logger.info("未找到新文献")
        return []

    logger.info(f"发现 {len(pmids)} 篇候选文献")

    # Step 2: esummary 获取详情
    details = client.summary(pmids)

    # 解析文献
    papers = []
    for uid in pmids:
        if uid not in details or uid == "uids":
            continue

        doc = details[uid]

        authors = ", ".join(
            a.get("name", "")
            for a in doc.get("authors", [])[:5]
        )
        if len(doc.get("authors", [])) > 5:
            authors += f" 等 {len(doc['authors'])} 位作者"

        # 获取摘要 (efetch 需要另外调用，这里先用 keywords)
        keywords = doc.get("keywords", [])

        papers.append({
            "pmid": uid,
            "title": clean_text(doc.get("title", "")),
            "journal": doc.get("source", ""),
            "pubdate": parse_pubmed_date(doc.get("pubdate", "")),
            "authors": authors,
            "doi": doc.get("doi", ""),
            "url": f"https://pubmed.ncbi.nlm.nih.gov/{uid}/",
            "keywords": keywords if isinstance(keywords, list) else [],
            "has_abstract": doc.get("hasabstract", 0),
        })

    # 按日期排序（最新的在前）
    papers.sort(key=lambda x: x.get("pubdate", ""), reverse=True)

    return papers[:max_papers]


def build_papers_for_observer(papers: list[dict], query: str) -> str:
    """构建供 Observer 分析的文献上下文"""
    lines = [
        f"## PubMed 文献候选\n",
        f"**检索词**: {query}\n",
        f"**候选数量**: {len(papers)} 篇\n",
        f"---\n",
    ]

    for i, paper in enumerate(papers):
        lines.append(f"### 文献 {i}")
        lines.append(f"**PMID**: [{paper['pmid']}]({paper['url']})")
        lines.append(f"**标题**: {paper['title']}")
        lines.append(f"**期刊**: {paper['journal']}")
        lines.append(f"**发表日期**: {paper['pubdate']}")
        lines.append(f"**作者**: {paper['authors']}")
        if paper.get('keywords'):
            lines.append(f"**关键词**: {', '.join(paper['keywords'][:5])}")
        lines.append("")

    return "\n".join(lines)


def filter_existing_papers(papers: list[dict], repo_name: str, token: str) -> list[dict]:
    """过滤掉已创建 Issue 的文献（通过 GitHub Issues 标题匹配）

    Args:
        papers: 文献列表
        repo_name: 仓库名
        token: GitHub Token

    Returns:
        过滤后的文献列表
    """
    if not papers:
        return []

    g = Github(token)
    repo = g.get_repo(repo_name)

    # 获取近 30 天内已存在的 Issue 标题
    thirty_days_ago = datetime.now() - timedelta(days=30)
    existing_titles = set()

    for issue in repo.get_issues(state='all', since=thirty_days_ago):
        # 只检查我们自己创建的文献 Issue
        if issue.title.startswith("[文献]"):
            existing_titles.add(issue.title.lower())

    # 过滤
    filtered = []
    for paper in papers:
        title_prefix = f"[文献] {paper['title'][:40]}".lower()

        if any(title_prefix in existing for existing in existing_titles):
            logger.debug(f"跳过已存在: {title_prefix[:30]}...")
            continue

        filtered.append(paper)

    logger.info(f"过滤后剩余 {len(filtered)} 篇新文献（已排除 {len(papers) - len(filtered)} 篇）")
    return filtered


def analyze_with_observer(papers: list[dict], query: str, token: str) -> list[dict]:
    """使用 Observer agent 分析文献，返回推荐的文献"""

    import asyncio
    from issuelab.agents.observer import run_observer_for_papers

    logger.info(f"\n{'='*60}")
    logger.info(f"[Observer Agent] 开始智能分析 {len(papers)} 篇文献")
    logger.info(f"{'='*60}")

    # 如果文献不足 2 篇，无法推荐
    if len(papers) < 2:
        logger.warning(f"文献数量不足 2 篇，无法进行智能推荐")
        return []

    # 构建上下文（适配 arxiv_observer 的格式）
    papers_context = build_papers_for_observer(papers, query)

    # 转换格式以适配现有 observer
    adapted_papers = []
    for i, paper in enumerate(papers):
        adapted_papers.append({
            "id": paper['pmid'],
            "title": paper['title'],
            "summary": paper.get('keywords', [])[:3],  # 用关键词替代摘要
            "url": paper['url'],
            "pdf_url": paper['doi'],  # 用 DOI 替代 PDF
            "authors": paper['authors'],
            "published": paper['pubdate'],
            "category": paper['journal'],
        })

    # 调用 Observer
    try:
        # 这里需要创建 pubmed_observer，暂时使用启发式规则
        recommended = heuristic_selection(papers, query)
        return recommended
    except Exception as e:
        logger.error(f"[Observer] 分析失败: {e}")
        logger.info("[回退] 使用启发式规则...")
        return heuristic_selection(papers, query)


def heuristic_selection(papers: list[dict], query: str) -> list[dict]:
    """启发式规则选择高质量文献"""

    recommended = []
    selected_journals = set()

    for i, paper in enumerate(papers):
        # 期刊权重（简化版）
        journal = paper.get('journal', '').lower()

        # 高影响因子期刊列表（简化判断）
        high_impact_keywords = ['nature', 'science', 'cell', 'pnas', 'national']
        med_impact_keywords = ['evolutionary', 'molecular', 'genetics', 'ecology']

        if any(kw in journal for kw in high_impact_keywords):
            priority = 3
        elif any(kw in journal for kw in med_impact_keywords):
            priority = 2
        else:
            priority = 1

        # 计算得分
        score = priority

        # 发表日期加分（越新越高）
        pubdate = paper.get('pubdate', '')
        if pubdate and "2025" in str(pubdate):
            score += 1
        if pubdate and "2026" in str(pubdate):
            score += 2

        # 关键词匹配加分
        title_lower = paper.get('title', '').lower()
        query_terms = ['speciation', 'hybrid', 'introgression']
        match_count = sum(1 for term in query_terms if term in title_lower)
        score += match_count * 0.5

        reason = f"期刊优先级: {priority}级, 关键词匹配: {match_count}个"

        recommended.append({
            "index": i,
            "pmid": paper['pmid'],
            "title": paper['title'],
            "reason": reason,
            "journal": paper['journal'],
            "pubdate": paper['pubdate'],
            "authors": paper['authors'],
            "doi": paper['doi'],
            "url": paper['url'],
            "keywords": paper.get('keywords', []),
            "score": score,
        })

    # 按分数排序，取 Top 2
    recommended.sort(key=lambda x: x['score'], reverse=True)
    top2 = recommended[:2]

    logger.info(f"启发式筛选完成，推荐 {len(top2)} 篇文献")

    return top2


def create_issues(recommended: list[dict], repo_name: str, token: str,
                  query: str) -> int:
    """根据 Observer 推荐创建 GitHub Issues"""

    if not recommended:
        print("[INFO] 无推荐文献，不创建 Issue")
        return 0

    g = Github(token)
    repo = g.get_repo(repo_name)

    created = 0

    # 构建 Issue 主体
    papers_list = "\n\n---\n\n".join([
        f"""### {i+1}. {paper['title']}

- **PMID**: [{paper['pmid']}]({paper['url']})
- **DOI**: [{paper['doi']}](https://doi.org/{paper['doi']}) if paper['doi'] else 'N/A'
- **期刊**: {paper['journal']}
- **发表日期**: {paper['pubdate']}
- **作者**: {paper['authors']}
- **推荐理由**: {paper['reason']}"""
        for i, paper in enumerate(recommended)
    ])

    body = f"""## PubMed 文献速递

**检索词**: `{query}`
**分析时间**: {datetime.now().strftime("%Y-%m-%d")}
**推荐文献**: {len(recommended)} 篇

---

{papers_list}

---

_由 PubMed Monitor 自动创建_
"""

    title = f"[文献] 物种形成与杂交领域新文献 - {datetime.now().strftime('%Y-%m-%d')}"

    try:
        issue = repo.create_issue(title=title, body=body)
        print(f"[OK] 创建 Issue: {title}")

        # 触发 Moderator
        trigger_comment = "@Moderator 请审核"
        issue.create_comment(trigger_comment)
        print(f"[INFO] 触发评论: {trigger_comment}")

        created = 1

    except Exception as e:
        logger.error(f"创建 Issue 失败: {e}")

    return created


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="PubMed Monitor - 智能获取并分析文献"
    )
    parser.add_argument("--token", type=str, help="GitHub Token")
    parser.add_argument("--repo", type=str, help="Repository (owner/repo)")
    parser.add_argument("--query", type=str,
                        default="(speciation) OR (hybrid speciation) OR (introgression)",
                        help="PubMed 检索词")
    parser.add_argument("--days", type=int, default=1,
                        help="追溯天数（默认: 1，即最近 1 天）")
    parser.add_argument("--max-papers", type=int, default=10,
                        help="获取文献数量（分析前，默认: 10）")
    parser.add_argument("--output", type=str,
                        help="Output JSON file (optional)")
    parser.add_argument("--email", type=str,
                        help="PubMed 联系邮箱（必填）")
    parser.add_argument("--scan-only", action="store_true",
                        help="Only scan, don't analyze")

    args = parser.parse_args(argv)

    # 环境变量覆盖
    email = args.email or os.environ.get("PUBMED_EMAIL")
    if not email:
        logger.error("请提供 --email 参数或设置 PUBMED_EMAIL 环境变量")
        return 1

    # 日志级别
    log_level = getattr(logging,
                        os.environ.get("LOG_LEVEL", "INFO").upper(),
                        logging.INFO)
    logging.getLogger().setLevel(log_level)
    logger.setLevel(log_level)

    logger.info(f"{'='*60}")
    logger.info("[PubMed Monitor] 开始扫描新文献")
    logger.info(f"{'='*60}")
    logger.info(f"检索词: {args.query}")
    logger.info(f"追溯天数: {args.days}")

    # 获取文献
    papers = fetch_papers(
        query=args.query,
        email=email,
        days=args.days,
        max_papers=args.max_papers
    )
    logger.info(f"发现 {len(papers)} 篇候选文献")

    if not papers:
        logger.info("未发现新文献")
        return 0

    # 保存 JSON
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(papers, f, ensure_ascii=False, indent=2)
        logger.info(f"保存到: {args.output}")

    # 仅扫描模式
    if args.scan_only:
        for i, p in enumerate(papers, 1):
            logger.info(f"   {i}. [{p.get('journal', 'N/A')}] {p['title'][:60]}...")
        return 0

    # 分析并创建 Issues
    if args.token and args.repo:
        # 过滤已存在的
        new_papers = filter_existing_papers(papers, args.repo, args.token)

        # Observer 分析
        recommended = analyze_with_observer(new_papers, args.query, args.token)

        if len(recommended) == 0:
            if len(new_papers) == 0:
                logger.info("所有文献已存在，无需推荐")
            elif len(new_papers) < 2:
                logger.info(f"新文献数量不足 2 篇，无法智能推荐")
            else:
                logger.info("智能分析未返回有效结果")
            return 0

        # 创建 Issues
        logger.info("开始创建 Issues...")
        created = create_issues(recommended, args.repo, args.token, args.query)
        logger.info(f"{'='*60}")
        logger.info(f"[完成] 创建 {created} 个 Issues")
        logger.info(f"{'='*60}")
    else:
        logger.info("提供 --token 和 --repo 参数可自动分析并创建 Issues")
        for i, p in enumerate(papers, 1):
            logger.info(f"   {i}. [{p.get('journal', 'N/A')}] {p['title'][:60]}...")

    return 0


if __name__ == "__main__":
    sys.exit(main())
