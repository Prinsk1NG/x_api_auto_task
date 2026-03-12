# -*- coding: utf-8 -*-
"""
x_api_auto_task.py  v6.0 (双擎搜索防漏 + @unknown终结 + 视觉原声对位)
Architecture: Expert & Global Track -> Deep Parse -> Strict LLM Synthesis -> UI Rendering
"""

import os
import re
import json
import time
import base64
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests
from requests.exceptions import ConnectionError, Timeout
from openai import OpenAI

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🚨 模式切换开关 🚨
# False = 全量运行（扫 100 人 + 2次全球热点搜索，推荐！）
# True  = 测试模式（只扫前 10 人 + 2次全球热点搜索，省配额）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TEST_MODE = True

# ── 环境变量 (严格对齐 Secrets 规范) ──────────────────────────────
JIJYUN_WEBHOOK_URL  = os.getenv("JIJYUN_WEBHOOK_URL", "")
SF_API_KEY          = os.getenv("SF_API_KEY", "")
KIMI_API_KEY        = os.getenv("KIMI_API_KEY", "")
OPENROUTER_API_KEY  = os.getenv("OPENROUTER_API_KEY", "")
TWTAPI_KEY          = os.getenv("TWTAPI_KEY", "")
IMGBB_API_KEY       = os.getenv("IMGBB_API_KEY", "") 

OPENROUTER_MODEL    = os.getenv("OPENROUTER_MODEL", "anthropic/claude-3.7-sonnet")
try:
    KIMI_TEMPERATURE  = float(os.getenv("KIMI_TEMPERATURE", "0.3"))
except:
    KIMI_TEMPERATURE  = 0.3

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🚨 专属你的 RapidAPI (Twttr API) 接口配置 🚨
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RAPIDAPI_HOST = "twitter241.p.rapidapi.com"
SEARCH_PATH   = "/search-v2" 
URL_TWTAPI    = "https://" + RAPIDAPI_HOST + SEARCH_PATH
COMMENTS_PATH = "/comments-v2"
URL_COMMENTS  = "https://" + RAPIDAPI_HOST + COMMENTS_PATH

# ── Base64 URL 隐身术 ─────────
def D(b64_str):
    return base64.b64decode(b64_str).decode("utf-8")

URL_OPENROUTER = D("aHR0cHM6Ly9vcGVucm91dGVyLmFpL2FwaS92MS9jaGF0L2NvbXBsZXRpb25z")
URL_MOONSHOT   = D("aHR0cHM6Ly9hcGkubW9vbnNob3QuY24vdjE=")
URL_SF_IMAGE   = D("aHR0cHM6Ly9hcGkuc2lsaWNvbmZsb3cuY24vdjEvaW1hZ2VzL2dlbmVyYXRpb25z")
URL_IMGBB      = D("aHR0cHM6Ly9hcGkuaW1nYmIuY29tLzEvdXBsb2Fk")

# ── 100 核心账号名单 ──────────────────────────────────────────────
ALL_ACCOUNTS = [
    "elonmusk", "sama", "karpathy", "demishassabis", "darioamodei",
    "OpenAI", "AnthropicAI", "GoogleDeepMind", "xAI", "AIatMeta",
    "GoogleAI", "MSFTResearch", "IlyaSutskever", "gregbrockman",
    "GaryMarcus", "rowancheung", "clmcleod", "bindureddy",
    "dotey", "oran_ge", "vista8", "imxiaohu", "Sxsyer",
    "K_O_D_A_D_A", "tualatrix", "linyunqiu", "garywong", "web3buidl",
    "AI_Era", "AIGC_News", "jiangjiang", "hw_star", "mranti", "nishuang",
    "a16z", "ycombinator", "lightspeedvp", "sequoia", "foundersfund",
    "eladgil", "pmarca", "bchesky", "chamath", "paulg",
    "TheInformation", "TechCrunch", "verge", "WIRED", "Scobleizer", "bentossell",
    "HuggingFace", "MistralAI", "Perplexity_AI", "GroqInc", "Cohere",
    "TogetherCompute", "runwayml", "Midjourney", "StabilityAI", "Scale_AI",
    "CerebrasSystems", "tenstorrent", "weights_biases", "langchainai", "llama_index",
    "supabase", "vllm_project", "huggingface_hub",
    "nvidia", "AMD", "Intel", "SKhynix", "tsmc",
    "magicleap", "NathieVR", "PalmerLuckey", "ID_AA_Carmack", "boz",
    "rabovitz", "htcvive", "XREAL_Global", "RayBan", "MetaQuestVR", "PatrickMoorhead",
    "jeffdean", "chrmanning", "hardmaru", "goodfellow_ian", "feifeili",
    "_akhaliq", "promptengineer", "AI_News_Tech", "siliconvalley", "aithread",
    "aibreakdown", "aiexplained", "aipubcast", "lexfridman", "hubermanlab", "swyx",
]

if TEST_MODE:
    ALL_ACCOUNTS = ALL_ACCOUNTS[:10]

def get_feishu_webhooks() -> list:
    urls = []
    for suffix in ["", "_1", "_2", "_3"]:
        url = os.getenv(f"FEISHU_WEBHOOK_URL{suffix}", "")
        if url: urls.append(url)
    return urls

def get_dates() -> tuple:
    tz = timezone(timedelta(hours=8))
    today = datetime.now(tz)
    yesterday = today - timedelta(days=1)
    return today.strftime("%Y-%m-%d"), yesterday.strftime("%Y-%m-%d")

def parse_twitter_date(date_str):
    try:
        if " " in date_str:
            parts = date_str.split()
            if len(parts) >= 3:
                m_map = {"Jan":"01", "Feb":"02", "Mar":"03", "Apr":"04", "May":"05", "Jun":"06", 
                         "Jul":"07", "Aug":"08", "Sep":"09", "Oct":"10", "Nov":"11", "Dec":"12"}
                mm = m_map.get(parts[1], "01")
                dd = parts[2].zfill(2)
                return f"{mm}{dd}"
    except: pass
    return datetime.now(timezone.utc).strftime("%m%d")

def safe_int(val):
    try:
        if isinstance(val, (int, float)): return int(val)
        v = str(val).lower().replace(',', '')
        if 'k' in v: return int(float(re.search(r'[\d\.]+', v).group()) * 1000)
        if 'm' in v: return int(float(re.search(r'[\d\.]+', v).group()) * 1000000)
        num = re.search(r'\d+', v)
        return int(num.group()) if num else 0
    except:
        return 0

def clean_format(text: str) -> str:
    text = re.sub(r'(@\S[^\n]*)\n\n+(> )', r'\1\n\2', text)
    text = re.sub(r'(> "[^\n]*"[^\n]*)\n\n+(\*\*)', r'\1\n\2', text)
    return text

# ==============================================================================
# 🚀 降维解析引擎 (完全终结 @unknown，并抓取评论数)
# ==============================================================================
def parse_rapidapi_tweets(data) -> list:
    all_tweets = []
    
    def recurse(obj):
        if isinstance(obj, dict):
            text = obj.get("full_text") or obj.get("text")
            if not text and obj.get("legacy"):
                text = obj["legacy"].get("full_text") or obj["legacy"].get("text")
                
            if text and isinstance(text, str):
                sn = None
                try: sn = obj.get("core", {}).get("user_results", {}).get("result", {}).get("legacy", {}).get("screen_name")
                except: pass
                if not sn: sn = obj.get("screen_name")
                if not sn:
                    u = obj.get("user") or obj.get("author") or obj.get("user_info") or {}
                    sn = u.get("screen_name") or u.get("userName") or u.get("username")
                if not sn and obj.get("legacy"): sn = obj["legacy"].get("screen_name")

                if sn:
                    t_id = obj.get("rest_id") or obj.get("id_str") or obj.get("id") or obj.get("tweet_id")
                    if not t_id and obj.get("legacy"): t_id = obj["legacy"].get("id_str")
                    
                    fav = obj.get("favorite_count") or obj.get("favorites") or obj.get("likes") or 0
                    if not fav and obj.get("legacy"): fav = obj["legacy"].get("favorite_count", 0)

                    rep = obj.get("reply_count") or obj.get("replies") or 0
                    if not rep and obj.get("legacy"): rep = obj["legacy"].get("reply_count", 0)
                    
                    created_at = obj.get("created_at")
                    if not created_at and obj.get("legacy"): created_at = obj["legacy"].get("created_at", "")
                    
                    reply_to = obj.get("in_reply_to_screen_name") or obj.get("reply_to") or obj.get("is_reply")
                    if not reply_to and obj.get("legacy"): reply_to = obj["legacy"].get("in_reply_to_screen_name")

                    if str(t_id):
                        all_tweets.append({
                            "tweet_id": str(t_id),
                            "screen_name": sn,
                            "text": text,
                            "favorites": safe_int(fav),
                            "replies": safe_int(rep), 
                            "created_at": created_at,
                            "reply_to": reply_to,
                        })
                        return 
            
            for v in obj.values(): recurse(v)
        elif isinstance(obj, list):
            for item in obj: recurse(item)

    recurse(data)
    
    seen, unique = set(), []
    for t in all_tweets:
        tid = t["tweet_id"]
        if tid not in seen:
            seen.add(tid)
            unique.append(t)
            
    return unique

# ==============================================================================
# 🚀 抓取引擎：Grok 双轨制搜索策略
# ==============================================================================
def fetch_all_tweets_batched(accounts: list) -> list:
    if not TWTAPI_KEY: return []
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
    chunk_size = 10
    chunks = [accounts[i:i + chunk_size] for i in range(0, len(accounts), chunk_size)]
    
    all_tweets = []
    headers = {"x-rapidapi-key": TWTAPI_KEY, "x-rapidapi-host": RAPIDAPI_HOST}
    consecutive_errors = 0  

    # 🟢 引擎一：专家雷达 (保证垂直深度)
    for i, chunk in enumerate(chunks, 1):
        if consecutive_errors >= 2: break
        print(f"\n⏳ [专家扫盘] 第 {i}/{len(chunks)} 批账号...", flush=True)
        query = " OR ".join([f"from:{acc}" for acc in chunk])
        params = {"query": f"({query}) since:{yesterday} -is:retweet", "type": "Latest", "count": "40"}
        
        success = False
        for attempt in range(3):
            try:
                resp = requests.get(URL_TWTAPI, headers=headers, params=params, timeout=25)
                if resp.status_code == 200:
                    tweets = parse_rapidapi_tweets(resp.json())
                    all_tweets.extend(tweets)
                    print(f"  ✅ 提取 {len(tweets)} 条。")
                    consecutive_errors = 0 
                    success = True
                    break
                elif resp.status_code in [403, 404]:
                    consecutive_errors += 1
                    time.sleep(2)
                    if consecutive_errors >= 2: break 
                else: time.sleep(2)
            except Exception: time.sleep(2)
                
        if success: time.sleep(1.5)
        else: time.sleep(3)

    # 🟢 引擎二：Grok 全网双重探测模式 (打破信息茧房)
    print(f"\n📡 [全网探测] 启动 Grok 策略，扫描全球突发热点...", flush=True)
    grok_queries = [
        f'(AI OR "artificial intelligence" OR LLM OR OpenAI OR xAI OR Grok OR Anthropic OR DeepMind OR Claude) since:{yesterday} min_faves:50 -is:retweet',
        f'(AI OR LLM) (release OR launch OR breakthrough OR update) since:{yesterday} min_faves:30 (filter:links OR filter:media) -is:retweet'
    ]

    for idx, q in enumerate(grok_queries, 1):
        print(f"  🔍 执行 Grok 策略 {idx}/2...", flush=True)
        params_discovery = {"query": q, "type": "Top", "count": "20"}
        for attempt in range(3):
            try:
                resp = requests.get(URL_TWTAPI, headers=headers, params=params_discovery, timeout=25)
                if resp.status_code == 200:
                    tweets = parse_rapidapi_tweets(resp.json())
                    all_tweets.extend(tweets)
                    print(f"    ✅ 策略 {idx} 成功，全网捕获 {len(tweets)} 条高赞情报。")
                    break
                elif resp.status_code in [403, 404]: break 
                else: time.sleep(2)
            except Exception: time.sleep(2)
        time.sleep(1.5)
        
    return all_tweets

def fetch_top_comments(tweet_id: str) -> list:
    if not tweet_id or not TWTAPI_KEY: return []
    print(f"  🎯 [爆破] 正在深挖神评 (Tweet ID: {tweet_id})...", flush=True)
    headers = {"x-rapidapi-key": TWTAPI_KEY, "x-rapidapi-host": RAPIDAPI_HOST}
    try:
        resp = requests.get(URL_COMMENTS, headers=headers, params={"pid": tweet_id, "rankingMode": "Relevance", "count": "20"}, timeout=25)
        if resp.status_code == 200:
            raw_comments = parse_rapidapi_tweets(resp.json())
            return [f"@{c['screen_name']}: {c['text'][:150]}" for c in raw_comments if len(c.get("text", "")) > 10][:5]
    except Exception: pass
    return []

# ==============================================================================
# LLM 提示词 (严格修正排版、防乱码、翻译约束)
# ==============================================================================
def _build_llm_prompt(combined_jsonl: str, today_str: str) -> str:
    return f"""
# Role
You are a top-tier AI industry primary market investment analyst with 10 years of experience. You write a "daily briefing" for senior partners.
Reply entirely in Chinese, EXCEPT for English names, titles, and short original texts.

# Task
Analyze tweets from tech leaders and global breaking trends (data in JSONL at the end).
Pay special attention to posts that include a "comments" array—this represents industry consensus or controversy. 

# Output Structure (strictly follow Markdown format)

## ⚡️ 今日看板 (The Pulse)
一句话总结今日最核心的 1-2 个行业定调信号。（绝对禁止以 > 开头，直接写正文）

---

## 🧠 深度叙事追踪 (Thematic Narratives)
将推文按主题聚合。每个主题严格如下（3-5个主题）：

---

### 🔁 主题标题：副标题

💡 叙事转向：[一句话核心判断，什么在变化]（绝对禁止以 > 开头，直接写正文）

🗣️ @账号名 | Title
"「中文译文或英文原文」"❤️ [赞数]赞 | 💬 [评论数]评
🔥 核心共识：评论区或行业普遍认同的观点
⚔️ 最大分歧：激烈的反驳意见或截然不同的视角

---

## 💰 资本与估值雷达 (Investment Radar)
1. **投融资快讯：** 具体的融资额与领投机构。
2. **VC观点：** 顶级机构投资风向警示。

---

## 📣 今日精选推文 (Top 5 Picks)
🗣️ @账号名 | Title
> 「中文译文或英文原文」(❤️ [赞数]赞 | 💬 [评论数]评)

# Constraints (Must Obey)
1. **账号展示格式：** 统一使用 `🗣️ @账号名|Title` 的格式。
2. **英文不翻译：** 名字和 Title 绝对不要翻译，保留纯英文！例如：`🗣️ @elonmusk | CEO of Tesla/SpaceX/X`。
3. **短句不翻译：** 如果推文原文少于 10 个单词，绝对不要翻译！直接在引用块 `` 中保留原滋原味的英文。
4. **禁止无用乱码：** 在「核心共识」和「最大分歧」前面，不要使用 `-` 或 `*` 列表符，直接以 🔥 和 ⚔️ 作为段落开头，防止出现排版乱码和蓝色圆点。
5. **排版纪律：** 每个子话题 (###) 之前必须有一条 `---` 分割线。

# Input Data (JSONL)
{combined_jsonl}

# Date
{today_str}

---
**输出完正文后，必须在最后附上以下三行（不可省略，紧跟正文末尾）：**
TITLE: （5-10字中文爆款标题，适合微信公众号）
PROMPT: （英文封面图生成提示词，100字以内，赛博朋克风，纯英文）
INSIGHT: （一句话核心洞察，中文，30字以内）
"""

def llm_call_claude(combined_jsonl: str, today_str: str):
    if not OPENROUTER_API_KEY: return "", "", "", ""
    data = combined_jsonl[:200000] if len(combined_jsonl) > 200000 else combined_jsonl
    prompt = _build_llm_prompt(data, today_str)

    for attempt in range(1, 4):
        try:
            print(f"[LLM/Claude] POST (attempt {attempt}/3)", flush=True)
            payload = {"model": OPENROUTER_MODEL, "messages": [{"role": "user", "content": prompt}], "temperature": 0.7, "max_tokens": 8000}
            resp = requests.post(URL_OPENROUTER, headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"}, json=payload, timeout=300)
            resp.raise_for_status()
            result = resp.json()["choices"][0]["message"]["content"].strip()
            return _parse_llm_result(result)
        except Exception: time.sleep(2)
    return "", "", "", ""

def llm_call_kimi(combined_jsonl: str, today_str: str):
    if not KIMI_API_KEY: return "", "", "", ""
    data = combined_jsonl[:200000] if len(combined_jsonl) > 200000 else combined_jsonl
    prompt = _build_llm_prompt(data, today_str)

    for attempt in range(1, 4):
        try:
            print(f"[LLM/Kimi] Calling kimi-k2.5 (attempt {attempt}/3)", flush=True)
            client = OpenAI(api_key=KIMI_API_KEY, base_url=URL_MOONSHOT)
            resp = client.chat.completions.create(model="kimi-k2.5", messages=[{"role": "user", "content": prompt}], temperature=KIMI_TEMPERATURE)
            result = resp.choices[0].message.content.strip()
            return _parse_llm_result(result)
        except Exception: time.sleep(2)
    return "", "", "", ""

def _parse_llm_result(result: str):
    start, end = result.find("@@@START@@@"), result.find("@@@END@@@")
    report_text = result[start + 11:end].strip() if (start != -1 and end > start) else result

    search_text = result[result.find("@@@END@@@") + 9:] if "@@@END@@@" in result else result
    title_m   = re.search(r"TITLE[:：]\s*(.+)", search_text)
    prompt_m  = re.search(r"PROMPT[:：]\s*([\s\S]+?)(?=INSIGHT[:：]|$)", search_text)
    insight_m = re.search(r"INSIGHT[:：]\s*([\s\S]+)", search_text)

    cover_title   = title_m.group(1).strip()   if title_m   else ""
    cover_prompt  = prompt_m.group(1).strip()  if prompt_m  else ""
    cover_insight = insight_m.group(1).strip() if insight_m else ""

    clean_report = re.sub(r"\n?TITLE[:：][\s\S]*$", "", report_text).strip()
    return clean_report, cover_title, cover_prompt, cover_insight

def generate_cover_image(prompt):
    if not SF_API_KEY or not prompt: return ""
    try:
        resp = requests.post(URL_SF_IMAGE, headers={"Authorization": f"Bearer {SF_API_KEY}", "Content-Type": "application/json"}, json={"model": "black-forest-labs/FLUX.1-schnell", "prompt": prompt, "n": 1, "image_size": "1024x576"}, timeout=60)
        if resp.status_code == 200: return resp.json().get("images", [{}])[0].get("url") or resp.json().get("data", [{}])[0].get("url")
    except Exception: pass
    return ""

def upload_to_imgbb_via_url(sf_url):
    if not IMGBB_API_KEY or not sf_url: return sf_url 
    try:
        img_resp = requests.get(sf_url, timeout=30)
        img_b64 = base64.b64encode(img_resp.content).decode("utf-8")
        upload_resp = requests.post(URL_IMGBB, data={"key": IMGBB_API_KEY, "image": img_b64}, timeout=45)
        if upload_resp.status_code == 200: return upload_resp.json()["data"]["url"]
    except Exception: pass
    return sf_url

# ==============================================================================
# 视觉对位引擎 (严格还原引用竖线 + 剔除乱码和蓝点)
# ==============================================================================
def _preprocess_md(content_md: str) -> str:
    content_md = re.sub(r'^###\s+(.+)$', r'**\1**', content_md, flags=re.MULTILINE)
    content_md = re.sub(r'^##\s+(.+)$', r'\n**▌ \1**', content_md, flags=re.MULTILINE)
    content_md = re.sub(r'^\s*---\s*$', '\n<HR>\n', content_md, flags=re.MULTILINE)
    content_md = re.sub(r'\n{3,}', '\n\n', content_md)
    return content_md.strip()

def _split_to_elements(content_md: str) -> list:
    elements = []
    paragraphs = content_md.split('\n\n')
    chunk = ""
    for para in paragraphs:
        para = para.strip()
        if not para: continue
        if para == '<HR>':
            if chunk: elements.append({"tag": "markdown", "content": chunk.strip()}); chunk = ""
            elements.append({"tag": "hr"})
            continue
        
        if para.startswith('**▌ '):
            if chunk: elements.append({"tag": "markdown", "content": chunk.strip()}); chunk = ""
            chunk = para
        else:
            if len(chunk) + len(para) + 2 > 3800 and chunk:
                elements.append({"tag": "markdown", "content": chunk.strip()}); chunk = para
            else: chunk = chunk + "\n\n" + para if chunk else para
            
    # 让飞书原生的 markdown 解析器去处理 "> "，飞书原生会渲染出完美的灰色引用竖线框
    if chunk.strip(): elements.append({"tag": "markdown", "content": chunk.strip()})
    return elements

def send_to_feishu_card(content_md: str, today_str: str, model_label: str = "Claude"):
    webhooks = get_feishu_webhooks()
    if not webhooks: return
    card_payload = {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True, "enable_forward": True},
            "header": {"title": {"content": f"昨晚硅谷在聊啥 | {today_str}", "tag": "plain_text"}, "template": "blue"},
            "elements": _split_to_elements(_preprocess_md(content_md)) + [{"tag": "hr"}, {"tag": "note", "elements": [{"tag": "plain_text", "content": f"Powered by TwtAPI + {model_label}"}]}],
        },
    }
    for url in webhooks:
        try: requests.post(url, json=card_payload, timeout=20)
        except Exception: pass

def _md_to_html(text):
    lines = text.split("\n")
    html_lines = []
    in_quote = False

    for line in lines:
        line = line.strip()
        if not line: continue

        # 🚨 原声态引用体：渲染为左侧深色竖线 + 灰底块，极致复刻截图效果
        if line.startswith('>'):
            content = line[1:].strip()
            content = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', content)
            if not in_quote:
                html_lines.append('<blockquote style="margin: 12px 0; padding: 10px 16px; color: #555; background-color: #f4f7f9; border-left: 4px solid #8c98a4; border-radius: 4px; font-size: 15px; line-height: 1.6;">')
                in_quote = True
            html_lines.append(f'<p style="margin: 4px 0;">{content}</p>')
            continue
        else:
            if in_quote:
                html_lines.append('</blockquote>')
                in_quote = False

        # 🚨 剔除可能带有列表符的乱码，防止产生蓝色点点
        if re.match(r'^-?\s*\**[🔥⚔️📌]', line):
            line = re.sub(r'^-?\s*', '', line) 
            converted = re.sub(r'\*\*(.+?)\*\*', r'<strong style="color:#d35400;">\1</strong>', line)
            html_lines.append(f'<p style="margin:8px 0; font-size:15px; line-height:1.6;">{converted}</p>')
            continue

        # 🗣️ 账号行
        if line.startswith('🗣️'):
            converted = re.sub(r'\*\*(.+?)\*\*', r'<strong style="color:#2980b9;">\1</strong>', line)
            html_lines.append(f'<p style="margin:16px 0 4px 0; font-size:14px; font-weight:bold;">{converted}</p>')
            continue

        # Headers
        m = re.match(r'^##\s+(.+)$', line)
        if m:
            html_lines.append(f'<h3 style="margin:24px 0 10px 0;font-size:17px;border-left:4px solid #4A90E2;padding-left:10px;color:#2c3e50;">{m.group(1)}</h3>')
            continue
            
        m3 = re.match(r'^###\s+(.+)$', line)
        if m3:
            html_lines.append(f'<h4 style="margin:20px 0 12px 0; font-size:16px; color:#e74c3c; font-weight:bold;">{m3.group(1)}</h4>')
            continue
            
        if re.match(r'^\s*---\s*$', line) or line == '<HR>':
            html_lines.append('<hr style="border:none;border-top:1px dashed #dcdde1;margin:24px 0 20px 0;"/>')
            continue
            
        if line.startswith('💡'):
            html_lines.append(f'<div style="background:#f4f8fb; padding:12px; border-radius:6px; margin:12px 0; font-size:14px; color:#2c3e50;">{line}</div>')
            continue
            
        converted = re.sub(r'\*\*(.+?)\*\*', r'<strong style="color:#2c3e50;">\1</strong>', line)
        html_lines.append(f'<p style="margin:6px 0; font-size:15px; line-height:1.6; color:#333;">{converted}</p>')

    if in_quote:
        html_lines.append('</blockquote>')

    return "".join(html_lines)

def build_wechat_html(text, cover_url="", insight=""):
    cover_block = f'<p style="text-align:center;margin:0 0 16px 0;"><img src="{cover_url}" style="max-width:100%;border-radius:8px;" /></p>' if cover_url else ""
    insight_block = f'<div style="border-radius:8px;background:#FFF7E6;padding:12px 14px;margin:0 0 16px 0;"><div style="font-weight:bold;margin-bottom:6px;">Insight</div><div>{insight.replace(chr(10), "<br/>")}</div></div>' if insight else ""
    return cover_block + insight_block + _md_to_html(text)

def push_to_jijyun(html_content, title, cover_url=""):
    if not JIJYUN_WEBHOOK_URL: return
    try: requests.post(JIJYUN_WEBHOOK_URL, json={"title": title, "author": "Prinski", "html_content": html_content, "cover_jpg": cover_url}, timeout=30)
    except Exception: pass

def save_daily_data(today_str: str, post_objects: list, report_text: str):
    data_dir = Path(f"data/{today_str}")
    data_dir.mkdir(parents=True, exist_ok=True)
    combined_txt = "\n".join(json.dumps(obj, ensure_ascii=False) for obj in post_objects)
    (data_dir / "combined.txt").write_text(combined_txt, encoding="utf-8")
    if report_text: (data_dir / "daily_report.txt").write_text(report_text, encoding="utf-8")

# ==============================================================================
# Main Execution 🚀
# ==============================================================================
def main():
    print("=" * 60, flush=True)
    mode_str = "测试模式(10人)" if TEST_MODE else "全量模式(100人)"
    print(f"昨晚硅谷在聊啥 v6.0 (双擎搜索防漏 + 原声还原版 - {mode_str})", flush=True)
    print("=" * 60, flush=True)

    today_str, _ = get_dates()
    all_raw_tweets = fetch_all_tweets_batched(ALL_ACCOUNTS)
    
    if not all_raw_tweets:
        print("⚠️ 未能抓取推文，链路测试...", flush=True)
        all_raw_tweets = [{"screen_name": "elonmusk", "text": "Fallback mode", "favorites": 100, "created_at": "0101"}]
        
    all_posts_flat = []
    
    for t in all_raw_tweets:
        likes = t.get("favorites", 0)
        is_reply = bool(t.get("reply_to"))
        
        if not is_reply or likes >= 0:
            tweet_id = t.get("tweet_id", "")
            text = t.get("text", "")
            replies = t.get("replies", 0)
            
            all_posts_flat.append({
                "a": t.get("screen_name", "Unknown"), 
                "tweet_id": tweet_id,
                "l": likes, 
                "r": replies,
                "t": parse_twitter_date(t.get("created_at", "")), 
                "s": re.sub(r'https?://\S+', '', text).strip()[:600], 
                "qt": t.get("quote_text", "")[:200]
            })

    all_posts_flat.sort(key=lambda x: x["l"], reverse=True)
    
    final_feed = all_posts_flat[:30]
    top_3_tweets = [t for t in final_feed if t.get("tweet_id")][:3]
    
    print(f"\n[深挖] 锁定今日最具争议的 {len(top_3_tweets)} 大话题，开始抓取评论区...")
    for t in top_3_tweets:
        comments = fetch_top_comments(t["tweet_id"])
        if comments:
            t["hot_comments"] = comments 

    combined_jsonl = "\n".join(json.dumps(obj, ensure_ascii=False) for obj in final_feed)
    
    print(f"\n[Data] 组装完成：{len(final_feed)} 条推文 (含共识提纯数据) ready for LLM.")

    report_text, cover_title, cover_prompt, cover_insight = "", "", "", ""
    model_label = ""

    if combined_jsonl.strip():
        print("\n[LLM] Calling Claude...", flush=True)
        report_text, cover_title, cover_prompt, cover_insight = llm_call_claude(combined_jsonl, today_str)
        if report_text: model_label = "Claude"
        else:
            report_text, cover_title, cover_prompt, cover_insight = llm_call_kimi(combined_jsonl, today_str)
            if report_text: model_label = "Kimi-k2.5"
    
    cover_url = ""
    if cover_prompt:
        sf_url = generate_cover_image(cover_prompt)
        cover_url = upload_to_imgbb_via_url(sf_url) if sf_url else ""

    if report_text:
        send_to_feishu_card(report_text, today_str, model_label=model_label)
        if JIJYUN_WEBHOOK_URL:
            html_content = build_wechat_html(report_text, cover_url=cover_url, insight=cover_insight)
            wechat_title = cover_title or f"AI吃瓜日报 | {today_str}"
            push_to_jijyun(html_content, title=wechat_title, cover_url=cover_url)

    save_daily_data(today_str, final_feed, report_text)
    print("\n🎉 V6.0 运行完毕！", flush=True)

if __name__ == "__main__":
    main()
