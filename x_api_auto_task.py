# -*- coding: utf-8 -*-
"""
x_api_auto_task.py  v4.2 (排版进阶版：支持实名身份标签 + 飞书/微信原生横线分割 + 视觉优化)
Architecture: RapidAPI(TwtAPI) -> Classification -> Claude/Kimi-k2.5 Synthesis -> AI Cover -> Feishu/WeChat
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

# ── 环境变量 (严格对齐 Secrets 规范) ──────────────────────────────
JIJYUN_WEBHOOK_URL  = os.getenv("JIJYUN_WEBHOOK_URL", "")
SF_API_KEY          = os.getenv("SF_API_KEY", "")
KIMI_API_KEY        = os.getenv("KIMI_API_KEY", "")
OPENROUTER_API_KEY  = os.getenv("OPENROUTER_API_KEY", "")
TWTAPI_KEY          = os.getenv("TWTAPI_KEY", "")

OPENROUTER_MODEL    = os.getenv("OPENROUTER_MODEL", "anthropic/claude-3.7-sonnet")
try:
    KIMI_TEMPERATURE  = float(os.getenv("KIMI_TEMPERATURE", "0.3"))
except:
    KIMI_TEMPERATURE  = 0.3

# ── Base64 URL 隐身术 (防止编辑器强制转码) ─────────────────────────
def D(b64_str):
    return base64.b64decode(b64_str).decode("utf-8")

URL_OPENROUTER = D("aHR0cHM6Ly9vcGVucm91dGVyLmFpL2FwaS92MS9jaGF0L2NvbXBsZXRpb25z")
URL_MOONSHOT   = D("aHR0cHM6Ly9hcGkubW9vbnNob3QuY24vdjE=")
URL_SF_IMAGE   = D("aHR0cHM6Ly9hcGkuc2lsaWNvbmZsb3cuY24vdjEvaW1hZ2VzL2dlbmVyYXRpb25z")
URL_IMGBB      = D("aHR0cHM6Ly9hcGkuaW1nYmIuY29tLzEvdXBsb2Fk")
URL_TWTAPI     = D("aHR0cHM6Ly90d2l0dGVyLWFwaTQ1LnAucmFwaWRhcGkuY29tL3NlYXJjaC5waHA=")

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

# ==============================================================================
# 基础工具函数
# ==============================================================================
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
        elif "T" in date_str:
            return date_str[5:7] + date_str[8:10]
    except: pass
    return datetime.now(timezone.utc).strftime("%m%d")

def clean_format(text: str) -> str:
    text = re.sub(r'(@\S[^\n]*)\n\n+(> )', r'\1\n\2', text)
    text = re.sub(r'(> "[^\n]*"[^\n]*)\n\n+(\*\*)', r'\1\n\2', text)
    text = re.sub(r'(- [^\n]+)\n\n+(- )', r'\1\n\2', text)
    return text

# ==============================================================================
# 🚀 核心解析引擎 (兼容深层 GraphQL 嵌套)
# ==============================================================================
def parse_rapidapi_tweets(data: dict) -> list:
    """提取深度嵌套的 Twttr API 数据 (基于官方提示路径)"""
    all_tweets = []
    try:
        instructions = data.get("result", {}).get("timeline", {}).get("instructions", [])
        for instr in instructions:
            for entry in instr.get("entries", []):
                try:
                    item_content = entry.get("content", {}).get("itemContent", {})
                    if item_content.get("itemType") == "TimelineTweet":
                        tweet_res = item_content.get("tweet_results", {}).get("result", {})
                        
                        if tweet_res.get("__typename") == "TweetWithVisibilityResults":
                            tweet_res = tweet_res.get("tweet", tweet_res)
                        
                        legacy = tweet_res.get("legacy", {})
                        user_legacy = tweet_res.get("core", {}).get("user_results", {}).get("result", {}).get("legacy", {})
                        
                        if legacy and user_legacy:
                            all_tweets.append({
                                "screen_name": user_legacy.get("screen_name", ""),
                                "text": legacy.get("full_text", legacy.get("text", "")),
                                "favorites": legacy.get("favorite_count", 0),
                                "created_at": legacy.get("created_at", ""),
                                "reply_to": legacy.get("in_reply_to_user_id_str"),
                                "quote_text": tweet_res.get("quoted_status_result", {}).get("result", {}).get("legacy", {}).get("full_text", "")
                            })
                except Exception:
                    pass
    except Exception as e:
        print(f"  ⚠️ 深层解析异常: {e}")

    if not all_tweets:
        flat_list = data.get("timeline") or data.get("tweets") or []
        for t in flat_list:
            all_tweets.append({
                "screen_name": t.get("screen_name") or t.get("author", {}).get("userName") or t.get("user_info", {}).get("screen_name") or "",
                "text": t.get("text") or t.get("full_text") or "",
                "favorites": t.get("favorites") or t.get("favorite_count") or t.get("likes") or 0,
                "created_at": t.get("created_at", ""),
                "reply_to": t.get("reply_to") or t.get("in_reply_to_user_id") or t.get("is_reply"),
                "quote_text": t.get("quote_text", "")
            })
            
    return all_tweets

# ==============================================================================
# 🚀 核心抓取引擎
# ==============================================================================
def fetch_all_tweets_batched(accounts: list) -> list:
    if not TWTAPI_KEY:
        print("🚨 Fatal Error: TWTAPI_KEY not configured!", flush=True)
        return []
    
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
    chunk_size = 10
    chunks = [accounts[i:i + chunk_size] for i in range(0, len(accounts), chunk_size)]
    
    all_tweets = []
    headers = {
        "X-RapidAPI-Key": TWTAPI_KEY,
        "X-RapidAPI-Host": "twitter-api45.p.rapidapi.com"
    }

    for i, chunk in enumerate(chunks, 1):
        print(f"\n⏳ 正在抓取第 {i}/{len(chunks)} 批账号 (包含 {len(chunk)} 人)...", flush=True)
        query = " OR ".join([f"from:{acc}" for acc in chunk])
        full_query = f"({query}) since:{yesterday} -is:retweet"
        params = {"query": full_query, "search_type": "Latest", "count": 20}
        
        for attempt in range(3):
            try:
                resp = requests.get(URL_TWTAPI, headers=headers, params=params, timeout=25)
                if resp.status_code == 200:
                    tweets = parse_rapidapi_tweets(resp.json())
                    all_tweets.extend(tweets)
                    print(f"  ✅ 第 {i} 批成功，提取到 {len(tweets)} 条纯净原创帖。")
                    break
                elif resp.status_code == 429:
                    print("  ⚠️ API 限流，紧急避险 3 秒...")
                    time.sleep(3)
                else:
                    print(f"  ⚠️ HTTP {resp.status_code}，重试中...")
                    time.sleep(2)
            except Exception as e:
                print(f"  ❌ 第 {i} 批网络错误: {e}")
                time.sleep(2)
                
        time.sleep(1.5)
        
    return all_tweets

def classify_accounts(meta_results: dict) -> dict:
    tz = timezone(timedelta(hours=8))
    today = datetime.now(tz)
    classification = {}

    for account, meta in meta_results.items():
        total  = meta.get("total", 0)
        max_l  = meta.get("max_l", 0)
        latest = meta.get("latest", "NA")

        if total == 0 or latest == "NA":
            classification[account] = "inactive"
            continue
        try:
            mm = int(latest[:2])
            dd = int(latest[2:])
            latest_date = today.replace(month=mm, day=dd)
            if latest_date > today:
                latest_date = latest_date.replace(year=today.year - 1)
            days_since = (today - latest_date).days
        except:
            days_since = 999

        if days_since > 30: classification[account] = "inactive"
        elif max_l > 3000 and days_since <= 7: classification[account] = "S"
        elif max_l > 800 and days_since <= 14: classification[account] = "A"
        else: classification[account] = "B"

    return classification

# ==============================================================================
# LLM 提示词与引擎调用 (增强实名与分割线)
# ==============================================================================
def _build_llm_prompt(combined_jsonl: str, today_str: str) -> str:
    return f"""
# Role
You are a top-tier AI industry primary market investment analyst with 10 years of experience. You write a "daily briefing" for senior partners, and simultaneously produce a public WeChat account version with the same facts but a wittier, more internet-savvy tone.

Reply entirely in Chinese.

# Task
Analyze tweets from 60+ tech leaders, investors, and hardware experts on X over the past 24 hours (data in JSONL at the end).
Filter out trivial technical parameters and social noise; distill insights with "investment reference value" and output the public account version.

# Output Structure (strictly follow Markdown format)

## ⚡️ 今日看板 (The Pulse)
> 用一句话总结今日最核心的 1-2 个行业定调信号。

---

## 🧠 深度叙事追踪 (Thematic Narratives)
将零散的推文按「主题/赛道」进行聚合（如：模型军备竞赛、具身智能、Agent 商业化、算力基础设施等）。
每个主题输出格式严格如下（3-5个主题）：

**🔁 主题标题：副标题**

> 💡 叙事转向：[一句话核心判断，说清楚"什么在变化、为什么重要"]

- **@账号名 | 真实姓名 | 真实身份标签** 具体行为 + 投资视角解读（不超过 60 字）
- **@账号名 | 真实姓名 | 真实身份标签** 具体行为 + 投资视角解读（不超过 60 字）
- **@账号名 | 真实姓名 | 真实身份标签** 具体行为 + 投资视角解读（不超过 60 字）

---
（⚠️ 严厉警告：每个主题板块结束之后，必须插入 `---` 形成物理分割线，然后再开启下一个主题！emoji 可根据主题选择：🔁🤖⚔️🏭🦾💡🔥📊）

## 💰 资本与估值雷达 (Investment Radar)
1. **投融资快讯：** 扫描数据中提到的具体融资额、估值以及领投机构。
2. **VC 偏好：** 提炼顶级机构（如 a16z, Sequoia, Benchmark）合伙人透露出的投资风向或对估值泡沫的警示。

---

## 📊 风险与中国视角 (Risk & China View)
1. **中国 AI 评价：** 汇总海外大佬/专家对中国大模型（如 DeepSeek, Zhipu, Kimi）的技术评价、成本优势或竞争压力。
2. **地缘与监管：** 提示关于芯片出口、合规审计或版权诉讼的潜在风险。

---

## 📣 今日精选推文 (Top 5 Picks)

从今日数据中精选 5 条最具代表性的原始推文，格式严格如下（不得偏离）：

- **@账号名 | 真实姓名 | 身份标签**
  > 「中文译文，限 60 字内，保留原文语气」

# Constraints
- **账号身份补全（必须执行）：** 只要出现 @账号名，后面必须跟上 ` | 真实姓名 | 身份`，例如 `@karpathy | Andrej Karpathy | OpenAI前科学家` 或 `@sama | Sam Altman | OpenAI CEO`。
- **格式纪律（严格遵守）：**
  - 只允许使用 ## 二级标题，禁止出现 ### 三级标题
  - 深度叙事追踪内，必须使用 `---` 作为每个子话题的间隔！
  - 每个要点用 `- ` 开头的短 bullet，单条不超过 80 个汉字（约两行）
- **禁止技术堆砌：** 不要解释算法原理，只需说该技术如何影响商业竞争或降低成本。
- **投资视角：** 重点关注「钱的流向」和「估值逻辑的变化」。
- **语言风格：** 专业、干脆、利落，适合在飞书移动端快速扫读。

# Input Data (JSONL)
{combined_jsonl}

# Date
{today_str}

---
**输出完正文后，必须在最后附上以下三行（不可省略，紧跟正文末尾）：**
TITLE: （5-10字中文标题，适合微信公众号，如"GPT震荡日，谁在偷偷布局"）
PROMPT: （英文封面图生成提示词，100字以内，描述科技感画面，如"futuristic AI neural network glowing blue circuits silicon valley night"）
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
            print(f"[LLM/Claude] OK Response received ({len(result)} chars)", flush=True)
            return _parse_llm_result(result)
        except Exception as e:
            print(f"[LLM/Claude] attempt {attempt} failed: {e}", flush=True)
            time.sleep(2)
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
            print(f"[LLM/Kimi] OK Response received ({len(result)} chars)", flush=True)
            return _parse_llm_result(result)
        except Exception as e:
            print(f"[LLM/Kimi] attempt {attempt} failed: {e}", flush=True)
            time.sleep(2)
    return "", "", "", ""

# ==============================================================================
# LLM Result Parser
# ==============================================================================
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

# ==============================================================================
# AI Cover & ImgBB
# ==============================================================================
def generate_cover_image(prompt):
    if not SF_API_KEY or not prompt: return ""
    print(f"\n[Image] Generating cover via SiliconFlow FLUX...", flush=True)
    try:
        resp = requests.post(
            URL_SF_IMAGE,
            headers={"Authorization": f"Bearer {SF_API_KEY}", "Content-Type": "application/json"},
            json={"model": "black-forest-labs/FLUX.1-schnell", "prompt": prompt, "n": 1, "image_size": "1024x576"},
            timeout=60
        )
        if resp.status_code == 200:
            url = resp.json().get("images", [{}])[0].get("url") or resp.json().get("data", [{}])[0].get("url")
            return url
    except Exception as e: print(f"  ❌ Generation failed: {e}")
    return ""

def upload_to_imgbb_via_url(sf_url):
    if not IMGBB_API_KEY or not sf_url: return sf_url 
    print(f"  [Image] Uploading to ImgBB for WeChat compatibility...", flush=True)
    try:
        img_resp = requests.get(sf_url, timeout=30)
        img_b64 = base64.b64encode(img_resp.content).decode("utf-8")
        upload_resp = requests.post(URL_IMGBB, data={"key": IMGBB_API_KEY, "image": img_b64}, timeout=45)
        if upload_resp.status_code == 200:
            return upload_resp.json()["data"]["url"]
    except Exception as e: print(f"  ⚠️ ImgBB Upload failed: {e}")
    return sf_url

# ==============================================================================
# Feishu / WeChat formatting & Push (排版大升级版)
# ==============================================================================
def _preprocess_md(content_md: str) -> str:
    content_md = re.sub(r'^###\s+(.+)$', r'**\1**', content_md, flags=re.MULTILINE)
    content_md = re.sub(r'^##\s+(.+)$', r'\n**▌ \1**', content_md, flags=re.MULTILINE)
    
    # 🚨 将 markdown 的横线标记转译为占位符 <HR>
    content_md = re.sub(r'^\s*---\s*$', '\n<HR>\n', content_md, flags=re.MULTILINE)
    content_md = re.sub(r'\n(\*\*[🔁🤖⚔️🏭🦾💡🔥📊🧠💰🌐])', r'\n\n\n\1', content_md)
    content_md = re.sub(r'\n{3,}', '\n\n', content_md)
    return content_md.strip()

def _split_to_elements(content_md: str) -> list:
    """将预处理后的文本拆分成飞书卡片可接受的 block 数组，原生支持 hr 标签"""
    elements = []
    paragraphs = content_md.split('\n\n')
    chunk = ""
    
    for para in paragraphs:
        para = para.strip()
        if not para: continue
        
        # 拦截到 <HR> 占位符时，切断当前 chunk 并单独插入一条飞书分隔线
        if para == '<HR>':
            if chunk:
                elements.append({"tag": "markdown", "content": chunk.strip()})
                chunk = ""
            elements.append({"tag": "hr"})
            continue
            
        # 拦截到模块标题，自成一段
        if para.startswith('**▌ '):
            if chunk:
                elements.append({"tag": "markdown", "content": chunk.strip()})
                chunk = ""
            chunk = para
        else:
            # 防超过 4000 字符限制
            if len(chunk) + len(para) + 2 > 3800 and chunk:
                elements.append({"tag": "markdown", "content": chunk.strip()})
                chunk = para
            else:
                chunk = chunk + "\n\n" + para if chunk else para
                
    if chunk.strip(): 
        elements.append({"tag": "markdown", "content": chunk.strip()})
    return elements

def send_to_feishu_card(content_md: str, today_str: str, model_label: str = "Claude"):
    webhooks = get_feishu_webhooks()
    if not webhooks: return

    formatted_content = _preprocess_md(content_md)
    content_elements  = _split_to_elements(formatted_content)

    card_payload = {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True, "enable_forward": True},
            "header": {
                "title": {"content": f"昨晚硅谷在聊啥 | {today_str}", "tag": "plain_text"},
                "template": "blue",
            },
            "elements": content_elements + [
                {"tag": "hr"},
                {"tag": "note", "elements": [{"tag": "plain_text", "content": f"Powered by RapidAPI + {model_label}"}]},
            ],
        },
    }

    for url in webhooks:
        try:
            requests.post(url, json=card_payload, timeout=20)
            print(f"[Push] OK Feishu pushed: {url.split('/')[-1][:8]}...", flush=True)
        except Exception as e: print(f"[Push] ERROR Feishu failed: {e}", flush=True)

def _md_to_html(text):
    lines = text.split("\n")
    html_lines = []
    for line in lines:
        line = line.strip()
        if not line: continue
        
        m = re.match(r'^##\s+(.+)$', line)
        if m:
            html_lines.append(f'<h3 style="margin:24px 0 10px 0;font-size:17px;border-left:4px solid #4A90E2;padding-left:10px;">{m.group(1)}</h3>')
            continue
            
        m3 = re.match(r'^###\s+(.+)$', line)
        if m3:
            html_lines.append(f'<p><strong style="color:#2c3e50;">{m3.group(1)}</strong></p>')
            continue
            
        # 🚨 渲染微信原生的优雅分割线
        if re.match(r'^\s*---\s*$', line) or line == '<HR>':
            html_lines.append('<hr style="border:none;border-top:1px dashed #dcdde1;margin:20px 0;"/>')
            continue
            
        # 🚨 优化 "💡 叙事转向" 拥有灰蓝色高级感背景框
        if line.startswith('> 💡'):
            html_lines.append(f'<div style="background:#f4f8fb; padding:12px; border-radius:6px; margin:12px 0; font-size:14px; color:#2c3e50;">{line.replace("> ", "")}</div>')
            continue
        elif line.startswith('>'):
            html_lines.append(f'<blockquote style="border-left:3px solid #bdc3c7; margin:8px 0; padding-left:10px; color:#7f8c8d; font-size:14px;">{line.replace("> ", "")}</blockquote>')
            continue
            
        # 加粗文字颜色微调，更适合护眼阅读
        converted = re.sub(r'\*\*([^*]+?)\*\*', r'<strong style="color:#2c3e50;">\1</strong>', line)
        html_lines.append(f'<p style="margin:6px 0; font-size:15px; line-height:1.6;">{converted}</p>')
        
    return "".join(html_lines)

def build_wechat_html(text, cover_url="", insight=""):
    cover_block = f'<p style="text-align:center;margin:0 0 16px 0;"><img src="{cover_url}" style="max-width:100%;border-radius:8px;" /></p>' if cover_url else ""
    insight_block = f'<div style="border-radius:8px;background:#FFF7E6;padding:12px 14px;margin:0 0 16px 0;"><div style="font-weight:bold;margin-bottom:6px;">Insight</div><div>{insight.replace(chr(10), "<br/>")}</div></div>' if insight else ""
    text = clean_format(text)
    return cover_block + insight_block + _md_to_html(text)

def push_to_jijyun(html_content, title, cover_url=""):
    if not JIJYUN_WEBHOOK_URL: return
    try:
        requests.post(JIJYUN_WEBHOOK_URL, json={"title": title, "author": "Prinski", "html_content": html_content, "cover_jpg": cover_url}, timeout=30)
        print(f"[Push] WeChat push OK", flush=True)
    except Exception as e: print(f"[Push] WeChat push error: {e}", flush=True)

def save_daily_data(today_str: str, post_objects: list, meta_results: dict, report_text: str, classification: dict):
    data_dir = Path(f"data/{today_str}")
    data_dir.mkdir(parents=True, exist_ok=True)
    combined_txt = "\n".join(json.dumps(obj, ensure_ascii=False) for obj in post_objects if obj.get("type") != "meta")
    (data_dir / "combined.txt").write_text(combined_txt, encoding="utf-8")
    (data_dir / "meta.json").write_text(json.dumps(meta_results, ensure_ascii=False, indent=2), encoding="utf-8")
    if report_text: (data_dir / "daily_report.txt").write_text(report_text, encoding="utf-8")

# ==============================================================================
# Main Execution
# ==============================================================================
def main():
    print("=" * 60, flush=True)
    print("昨晚硅谷在聊啥 v4.2 (实名身份追踪 + 视觉优化版)", flush=True)
    print("=" * 60, flush=True)

    today_str, _ = get_dates()
    Path("data").mkdir(exist_ok=True)
    
    # 1. 使用极速批处理抓取 100 人的 Twitter 数据
    all_raw_tweets = fetch_all_tweets_batched(ALL_ACCOUNTS)
    
    # 2. 本地过滤与账号分桶
    bucketed_tweets = {acc.lower(): [] for acc in ALL_ACCOUNTS}
    for t in all_raw_tweets:
        author = t.get("screen_name") or t.get("author", {}).get("userName") or t.get("user_info", {}).get("screen_name") or ""
        author_lower = author.lower()
        if author_lower in bucketed_tweets:
            bucketed_tweets[author_lower].append(t)

    meta_results = {}
    for acc in ALL_ACCOUNTS:
        acc_lower = acc.lower()
        tweets = bucketed_tweets[acc_lower]
        
        # 核心清洗逻辑：剔除他人回复、点赞数太低(<10)的内容
        filtered = []
        for t in tweets:
            likes = t.get("favorites") or t.get("favorite_count") or t.get("likes") or 0
            is_reply = t.get("reply_to") or t.get("in_reply_to_user_id") or t.get("is_reply")
            if not is_reply and likes >= 10:
                filtered.append(t)
                
        # 补充元数据用于分类
        total = len(filtered)
        max_l = max([t.get("favorites", t.get("favorite_count", t.get("likes", 0))) for t in filtered], default=0)
        latest = "NA"
        if total > 0:
            latest = parse_twitter_date(filtered[0].get("created_at", ""))
        
        meta_results[acc] = {"total": total, "max_l": max_l, "latest": latest}
        bucketed_tweets[acc_lower] = filtered 

    classification = classify_accounts(meta_results)
    
    # 3. 动态拼接输出结构 (复刻原版的 S/A/B 分级)
    phase1_posts, phase2_posts = {}, {}
    all_posts_flat = []

    for acc in ALL_ACCOUNTS:
        tier = classification.get(acc, "B")
        tweets = bucketed_tweets[acc.lower()]
        parsed_list = []
        
        for t in tweets:
            likes = t.get("favorites") or t.get("favorite_count") or t.get("likes") or 0
            date_str = parse_twitter_date(t.get("created_at", ""))
            text = t.get("text", t.get("full_text", ""))
            qt_text = t.get("quote_text", "")
            
            text = re.sub(r'https?://\S+', '', text).strip()
            obj = {"a": acc, "l": likes, "t": date_str, "s": text[:600], "tag": "raw"}
            if qt_text: obj["qt"] = qt_text[:200]
            parsed_list.append(obj)
            
        if tier == "S": phase2_posts[acc] = parsed_list[:10]
        elif tier == "A": phase2_posts[acc] = parsed_list[:5]
        else: phase1_posts[acc] = parsed_list[:3]

    for acc in [a for a, t in classification.items() if t in ["S", "A"]]:
        if phase2_posts.get(acc): all_posts_flat.extend(phase2_posts[acc])
        elif phase1_posts.get(acc): all_posts_flat.extend(phase1_posts[acc])

    for acc in [a for a, t in classification.items() if t == "B"]:
        if phase1_posts.get(acc): all_posts_flat.extend(phase1_posts[acc])

    combined_jsonl = "\n".join(json.dumps(obj, ensure_ascii=False) for obj in all_posts_flat)
    print(f"\n[Data] Combined JSONL: {len(all_posts_flat)} posts ready for LLM.")

    # ==========================================================================
    # 4. LLM 总结与生图 (与原版保持 100% 一致)
    # ==========================================================================
    report_text, cover_title, cover_prompt, cover_insight = "", "", "", ""
    model_label = ""

    if combined_jsonl.strip():
        print("\n[LLM] Calling Claude (primary)...", flush=True)
        report_text, cover_title, cover_prompt, cover_insight = llm_call_claude(combined_jsonl, today_str)
        if report_text:
            model_label = "Claude"
        else:
            print("[LLM] Claude failed, falling back to Kimi-k2.5...", flush=True)
            report_text, cover_title, cover_prompt, cover_insight = llm_call_kimi(combined_jsonl, today_str)
            if report_text: model_label = "Kimi-k2.5"
    
    cover_url = ""
    if cover_prompt:
        sf_url = generate_cover_image(cover_prompt)
        if sf_url:
            imgbb_url = upload_to_imgbb_via_url(sf_url)
            cover_url = imgbb_url if imgbb_url else sf_url

    # ==========================================================================
    # 5. 分发
    # ==========================================================================
    if report_text:
        send_to_feishu_card(report_text, today_str, model_label=model_label or "AI")
        if JIJYUN_WEBHOOK_URL:
            html_content = build_wechat_html(report_text, cover_url=cover_url, insight=cover_insight)
            wechat_title = cover_title or f"AI吃瓜日报 | {today_str}"
            push_to_jijyun(html_content, title=wechat_title, cover_url=cover_url)

    save_daily_data(today_str, all_posts_flat, meta_results, report_text, classification)
    print("\n" + "=" * 60, flush=True)
    print(f"DONE | today={today_str} | posts={len(all_posts_flat)} | model={model_label or 'none'} | feishu_hooks={len(get_feishu_webhooks())}")

if __name__ == "__main__":
    main()
