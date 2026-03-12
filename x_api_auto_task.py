# -*- coding: utf-8 -*-
"""
x_api_auto_task.py  v5.6 (视觉大统一版：复刻截图圆角卡片排版)
Architecture: RapidAPI(TwtAPI) -> Recursive Parse -> Top3 Comments -> LLM Synthesis -> Distribution
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
# 🚨 模式切换开关
# False = 全量运行（扫 100 人，消耗 13 次 API 额度，推荐！）
# True  = 测试模式（只扫前 10 人，消耗 4 次 API 额度）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TEST_MODE = False

# ── 环境变量 ─────────────────────────────────────────────────────
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

# 🚨 接口配置
RAPIDAPI_HOST = "twitter241.p.rapidapi.com"
URL_TWTAPI    = "https://" + RAPIDAPI_HOST + "/search-v2"
URL_COMMENTS  = "https://" + RAPIDAPI_HOST + "/comments-v2"

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

# ── 工具函数 ─────────────────────────────────────────────────────
def get_feishu_webhooks():
    urls = []
    for suffix in ["", "_1", "_2", "_3"]:
        url = os.getenv(f"FEISHU_WEBHOOK_URL{suffix}", "")
        if url: urls.append(url)
    return urls

def get_dates():
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
    except: return 0

def clean_format(text: str) -> str:
    text = re.sub(r'(@\S[^\n]*)\n\n+(> )', r'\1\n\2', text)
    return text

# ==============================================================================
# 🚀 递归解析引擎 (V5.6：增加解析评论数)
# ==============================================================================
def parse_rapidapi_tweets(data) -> list:
    all_tweets = []
    def recurse(obj):
        if isinstance(obj, dict):
            if obj.get("__typename") == "Tweet" or ("legacy" in obj and "core" in obj):
                legacy = obj.get("legacy", {})
                user_legacy = obj.get("core", {}).get("user_results", {}).get("result", {}).get("legacy", {})
                text = legacy.get("full_text") or legacy.get("text")
                if text:
                    all_tweets.append({
                        "tweet_id": str(obj.get("rest_id") or legacy.get("id_str") or ""),
                        "screen_name": user_legacy.get("screen_name", "Unknown"),
                        "real_name": user_legacy.get("name", ""),
                        "text": text,
                        "favorites": safe_int(legacy.get("favorite_count", 0)),
                        "replies": safe_int(legacy.get("reply_count", 0)), # 🚨 新增
                        "created_at": legacy.get("created_at", ""),
                        "reply_to": legacy.get("in_reply_to_screen_name"),
                    })
                    return
            text = obj.get("full_text") or obj.get("text")
            if text and ("user" in obj or "author" in obj or "screen_name" in obj):
                u = obj.get("user") or obj.get("author") or {}
                sn = obj.get("screen_name") or u.get("screen_name") or u.get("userName")
                all_tweets.append({
                    "tweet_id": str(obj.get("id_str") or obj.get("id") or ""),
                    "screen_name": sn or "Unknown",
                    "real_name": u.get("name") or "",
                    "text": text,
                    "favorites": safe_int(obj.get("favorite_count") or obj.get("favorites") or 0),
                    "replies": safe_int(obj.get("reply_count") or 0), # 🚨 新增
                    "created_at": obj.get("created_at", ""),
                    "reply_to": obj.get("in_reply_to_screen_name"),
                })
                return
            for v in obj.values(): recurse(v)
        elif isinstance(obj, list):
            for item in obj: recurse(item)
    recurse(data)
    seen, unique = set(), []
    for t in all_tweets:
        tid = t["tweet_id"] or t["text"]
        if tid not in seen:
            seen.add(tid); unique.append(t)
    return unique

# ==============================================================================
# 🚀 抓取引擎
# ==============================================================================
def fetch_all_tweets_batched(accounts: list) -> list:
    if not TWTAPI_KEY: return []
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
    chunks = [accounts[i:i + 10] for i in range(0, len(accounts), 10)]
    all_tweets = []
    headers = {"x-rapidapi-key": TWTAPI_KEY, "x-rapidapi-host": RAPIDAPI_HOST}
    for i, chunk in enumerate(chunks, 1):
        print(f"⏳ [扫盘] 第 {i}/{len(chunks)} 批...", flush=True)
        query = " OR ".join([f"from:{acc}" for acc in chunk])
        params = {"query": f"({query}) since:{yesterday} -is:retweet", "type": "Latest", "count": 40}
        try:
            resp = requests.get(URL_TWTAPI, headers=headers, params=params, timeout=25)
            if resp.status_code == 200:
                ts = parse_rapidapi_tweets(resp.json())
                all_tweets.extend(ts)
                print(f"  ✅ 提取 {len(ts)} 条。")
            time.sleep(1.5)
        except: time.sleep(3)
    return all_tweets

def fetch_top_comments(tweet_id: str) -> list:
    if not tweet_id or not TWTAPI_KEY: return []
    headers = {"x-rapidapi-key": TWTAPI_KEY, "x-rapidapi-host": RAPIDAPI_HOST}
    try:
        resp = requests.get(URL_COMMENTS, headers=headers, params={"pid": tweet_id, "count": 15}, timeout=25)
        if resp.status_code == 200:
            raw = parse_rapidapi_tweets(resp.json())
            return [f"@{c['screen_name']}: {c['text'][:150]}" for c in raw if len(c['text']) > 10][:5]
    except: pass
    return []

# ==============================================================================
# LLM 提示词 (视觉大统一：严格规定引用块格式)
# ==============================================================================
def _build_llm_prompt(combined_jsonl: str, today_str: str) -> str:
    return f"""
# Role
AI圈顶级吃瓜主编。你需要分析 X 上的推文数据，产出一份具备“专业卡片化排版”的日报。

# Output Format (严格遵守，涉及原文引用必须按截图格式)

## ⚡️ 今日看板 (The Pulse)
> 一句话总结今日。

---

## 🧠 深度叙事追踪 (Thematic Narratives)

---

### 🔁 主题标题：副标题

> 💡 叙事转向：[一句话核心判断]

🗣️ 极客原声态 | 一手信源
> **@账号名 | 真实姓名** (❤️ [赞数]赞 | 💬 [评论数]评)
> "[中文译文，保留原文语气]"

📝 捕手深度解码：
- **🔥 核心共识**：...
- **⚔️ 最大分歧**：...
- 📌 增量事实：...

---
(⚠️ 每一个子话题结束后，必须插入 `---` 分割线)

# Constraints
- **引用块规范（核心要求）：** 所有的原文翻译必须放在 `🗣️ 极客原声态 | 一手信源` 下方的引用块中，格式必须包含 `@账号 | 姓名 (❤️ [数]赞 | 💬 [数]评)`。
- **排版：** 严格遵循 `###` 与 `---` 的层级关系。

# Input Data
{combined_jsonl}

# Date: {today_str}

TITLE: (公众号标题)
PROMPT: (封面提示词)
INSIGHT: (深度洞察)
"""

# ==============================================================================
# LLM 引擎调用
# ==============================================================================
def _parse_llm_result(result: str):
    report_text = result.strip()
    title_m   = re.search(r"TITLE[:：]\s*(.+)", result)
    prompt_m  = re.search(r"PROMPT[:：]\s*([\s\S]+?)(?=INSIGHT[:：]|$)", result)
    insight_m = re.search(r"INSIGHT[:：]\s*([\s\S]+)", result)
    return report_text, (title_m.group(1).strip() if title_m else ""), (prompt_m.group(1).strip() if prompt_m else ""), (insight_m.group(1).strip() if insight_m else "")

def llm_call_claude(combined_jsonl: str, today_str: str):
    if not OPENROUTER_API_KEY: return "", "", "", ""
    prompt = _build_llm_prompt(combined_jsonl, today_str)
    try:
        r = requests.post(URL_OPENROUTER, headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}"}, json={"model": OPENROUTER_MODEL, "messages": [{"role": "user", "content": prompt}]}, timeout=300)
        return _parse_llm_result(r.json()["choices"][0]["message"]["content"])
    except: return "", "", "", ""

# ==============================================================================
# 飞书/微信 视觉排版引擎 (核心修复点：复刻卡片外观)
# ==============================================================================
def _split_to_elements(content_md: str) -> list:
    """飞书卡片排版逻辑：识别引用块，将其转换为带背景色的 note 容器"""
    elements = []
    # 物理分块：按模块标题和分割线切分
    parts = re.split(r'(\n---\n|\n###\s+|🗣️\s+极客原声态\s+\|)', content_md)
    
    current_text = ""
    for p in parts:
        p = p.strip()
        if not p: continue
        
        if p == "---":
            if current_text: elements.append({"tag": "markdown", "content": current_text.strip()}); current_text = ""
            elements.append({"tag": "hr"})
        elif p.startswith("极客原声态"):
            # 🚨 识别到引用头部，开始组装 Note 卡片
            pass 
        elif p.startswith("**@"):
            # 🚨 识别到推特原文引用内容，将其包装进 Note
            elements.append({
                "tag": "note",
                "elements": [{"tag": "lark_md", "content": f"**🗣️ 极客原声态 | 一手信源**\n{p}"}],
                "background_color": "grey" # 对应截图中的灰蓝色背景效果
            })
        else:
            if p.startswith("🧠") or p.startswith("⚡️") or p.startswith("💰"):
                if current_text: elements.append({"tag": "markdown", "content": current_text.strip()})
                current_text = f"\n**▌ {p}**\n"
            else:
                current_text += "\n" + p

    if current_text.strip(): elements.append({"tag": "markdown", "content": current_text.strip()})
    return elements

def _md_to_html(text):
    """微信端排版逻辑：将原文引用部分渲染为圆角卡片样式"""
    lines = text.split("\n")
    html_lines = []
    in_quote_box = False
    
    for line in lines:
        line = line.strip()
        if not line: continue
        
        if "🗣️ 极客原声态" in line:
            # 开启卡片容器
            html_lines.append('<div style="background:#f8f9fa; border-radius:12px; border-left:4px solid #3498db; padding:15px; margin:15px 0;">')
            html_lines.append(f'<p style="font-size:13px; color:#3498db; font-weight:bold; margin-bottom:10px;">{line}</p>')
            in_quote_box = True
            continue
            
        if in_quote_box and line.startswith(">"):
            content = line.replace(">", "").strip()
            # 账户行加粗蓝色
            content = re.sub(r'\*\*(.+?)\*\*', r'<strong style="color:#2980b9;">\1</strong>', content)
            html_lines.append(f'<p style="font-size:15px; line-height:1.6; color:#555; margin:5px 0;">{content}</p>')
            if not any(next_line.startswith(">") for next_line in lines[lines.index(line)+1:lines.index(line)+2]):
                html_lines.append('</div>')
                in_quote_box = False
            continue

        # 正常模块标题渲染
        if line.startswith("## "):
            html_lines.append(f'<h2 style="margin:25px 0 10px 0; font-size:18px; border-left:5px solid #2980b9; padding-left:10px;">{line[3:]}</h2>')
        elif line.startswith("### "):
            html_lines.append(f'<h3 style="margin:20px 0 10px 0; font-size:16px; color:#e74c3c;">{line[4:]}</h3>')
        elif line.startswith("---") or line == "<HR>":
            html_lines.append('<hr style="border:none; border-top:1px dashed #ddd; margin:20px 0;"/>')
        else:
            line = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', line)
            html_lines.append(f'<p style="margin:8px 0; font-size:15px; line-height:1.7;">{line}</p>')
            
    return "".join(html_lines)

# ==============================================================================
# 其它逻辑 (生图、分发、Main) - 保持 V5.5 结构
# ==============================================================================
def generate_cover_image(prompt):
    if not SF_API_KEY: return ""
    try:
        r = requests.post(URL_SF_IMAGE, headers={"Authorization": f"Bearer {SF_API_KEY}"}, json={"model": "black-forest-labs/FLUX.1-schnell", "prompt": prompt, "image_size": "1024x576"}, timeout=60)
        return r.json().get("images", [{}])[0].get("url") or r.json().get("data", [{}])[0].get("url")
    except: return ""

def upload_to_imgbb(url):
    if not IMGBB_API_KEY or not url: return url
    try:
        img = requests.get(url).content
        r = requests.post(URL_IMGBB, data={"key": IMGBB_API_KEY, "image": base64.b64encode(img)}, timeout=45)
        return r.json()["data"]["url"]
    except: return url

def send_to_feishu_card(md, date, model):
    hooks = get_feishu_webhooks()
    if not hooks: return
    payload = {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True},
            "header": {"title": {"content": f"昨晚硅谷在聊啥 | {date}", "tag": "plain_text"}, "template": "blue"},
            "elements": _split_to_elements(md) + [{"tag": "note", "elements": [{"tag": "plain_text", "content": f"Powered by TwtAPI + {model}"}]}]
        }
    }
    for h in hooks: requests.post(h, json=payload)

def main():
    print("=" * 60); print(f"昨晚硅谷在聊啥 v5.6 (视觉大统一版)"); print("=" * 60)
    today_str, _ = get_dates()
    raw_tweets = fetch_all_tweets_batched(ALL_ACCOUNTS)
    
    feed = []
    for t in raw_tweets:
        feed.append({
            "a": t["screen_name"], "n": t["real_name"], "l": t["favorites"], "r": t["replies"],
            "t": parse_twitter_date(t["created_at"]), "s": t["text"][:600], "tid": t["tweet_id"]
        })
    
    feed.sort(key=lambda x: x["l"], reverse=True)
    top_3 = [t for t in feed if t["tid"]][:3]
    for t in top_3:
        comments = fetch_top_comments(t["tid"])
        if comments: t["hot_comments"] = comments

    final_jsonl = "\n".join(json.dumps(obj, ensure_ascii=False) for obj in feed[:35])
    
    report, title, prompt, insight = llm_call_claude(final_jsonl, today_str)
    if not report: 
        print("❌ LLM 生成失败"); return

    cover_url = generate_cover_image(prompt)
    final_cover = upload_to_imgbb(cover_url) if cover_url else ""

    send_to_feishu_card(report, today_str, "Claude-3.7")
    if JIJYUN_WEBHOOK_URL:
        html = f'<p style="text-align:center;"><img src="{final_cover}" style="max-width:100%; border-radius:10px;" /></p>'
        if insight: html += f'<div style="background:#fff7e6; padding:15px; border-radius:8px; margin-bottom:20px;"><strong>Insight:</strong> {insight}</div>'
        html += _md_to_html(report)
        requests.post(JIJYUN_WEBHOOK_URL, json={"title": title or "AI吃瓜日报", "author": "Prinski", "html_content": html, "cover_jpg": final_cover})
    
    print("🎉 任务圆满完成！")

if __name__ == "__main__": main()
