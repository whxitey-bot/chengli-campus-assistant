"""智能体核心：本地工作流（意图识别 → 工具检索 → 大模型生成）。

dsv4 网关不支持 function calling（tool_choice="auto" 会 400），
因此这里不依赖模型自己调用工具，而是用「规则路由 + RAG」的方式：
先按关键词判断意图、执行对应工具拿到真实数据，再把检索结果注入提示词，
交给大模型做口语化、严格基于检索内容的回答。
"""
import json
import datetime
import urllib.request
import urllib.parse
import re

from openai import OpenAI
import httpx

import config
from knowledge_base import search_faq, search_activity, campus_tour

# 系统提示词：定义这个智能体的「人设」和职责
SYSTEM_PROMPT = f"""你是「{config.SCHOOL_NAME}」的校园助手「成理小助手」，一个热情、耐心、靠谱的智能体，像熟悉学校每个角落的学长学姐，专门帮同学解决入学和校园生活问题。

【学校背景】
成都理工大学是国家"双一流"建设高校，教育部与四川省共建，前身是1956年创办的成都地质勘探学院，2001年更名。学校以地质、能源、资源、核技术、环境为优势学科，"地质资源与地质工程"入选国家"双一流"建设学科。现有成都（成华区二仙桥东三路1号）和宜宾两个校区。

【核心规则】
1. 涉及校园事实，必须严格依据本轮提供的【检索结果】回答，绝不编造检索结果里没有的地标、菜品、设施、数据等任何细节。检索结果不足时，诚实说明"知识库暂无相关信息"，并建议咨询辅导员或对应部门。
2. 纯问候、闲聊、感谢等非事实类问题，友好回应即可，无需引用检索结果。
3. 问题模糊时礼貌追问澄清，不瞎猜。

【分场景 SOP】
- 报到引导：先问清"报到前"还是"当天"→ 给对应清单（迎新网 yx.cdut.edu.cn 线上报到、带录取通知书/身份证/档案）→ 提醒报到地址与招生办电话 028-84078927。
- 军训准备：约14天、不剪头发 → 给准备清单（防晒霜/水杯/舒适运动鞋/换洗衣物）→ 提醒防晒补水。
- 选课指导：分预选、正选两阶段 → 提醒热门课要抢、关注教务处通知。
- 校园活动：按「活动名 + 时间 + 地点 + 亮点」介绍，查不到就建议关注团委、教务处通知。
- 校园导览：按游览顺序讲解，讲清"在哪里 + 有什么看点/小故事"（如砚湖是师生徒手挖成、桐荫路是 TFboys《heart》MV 拍摄地）。
- 学习规划：先问清专业、年级、目标（考研/保研/期末/就业）和可用时间 → 再给出分阶段计划，结构固定包含：① 阶段划分（基础/强化/冲刺）② 每周目标 ③ 每日任务（早/中/晚）④ 各科重点 ⑤ 作息表 ⑥ 实用建议。

【回答风格】
- 中文，语气亲切像学长学姐。
- 先给结论，再补充必要说明。
- 可少量 emoji 让语气更友好。
"""


# 绕过系统代理（本机系统代理 127.0.0.1 会拒绝连接，直连才能访问外网）
_NO_PROXY_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _fetch_json(url: str):
    with _NO_PROXY_OPENER.open(url, timeout=10) as r:
        return json.loads(r.read().decode("utf-8"))


def _weather_desc(code):
    mapping = {
        0: "晴", 1: "基本晴朗", 2: "多云", 3: "阴",
        45: "雾", 48: "雾凇",
        51: "小毛毛雨", 53: "毛毛雨", 55: "大毛毛雨",
        61: "小雨", 63: "中雨", 65: "大雨",
        66: "冻雨", 67: "冻雨",
        71: "小雪", 73: "中雪", 75: "大雪", 77: "雪粒",
        80: "小阵雨", 81: "阵雨", 82: "强阵雨",
        85: "阵雪", 86: "阵雪",
        95: "雷暴", 96: "雷暴伴冰雹", 99: "强雷暴伴冰雹",
    }
    return mapping.get(code, "未知")


def get_weather(city: str = "成都") -> str:
    """通过 Open-Meteo 查询天气（免 key）。"""
    city = (city or "").strip() or "成都"
    try:
        geo_url = "https://geocoding-api.open-meteo.com/v1/search?" + urllib.parse.urlencode(
            {"name": city, "count": 1, "language": "zh", "format": "json"}
        )
        geo = _fetch_json(geo_url)
        results = geo.get("results") or []
        if not results:
            return f"没有找到「{city}」的天气信息。"
        lat = results[0]["latitude"]
        lon = results[0]["longitude"]
        name = results[0].get("name", city)

        w_url = "https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode(
            {
                "latitude": lat,
                "longitude": lon,
                "current": "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m",
                "daily": "temperature_2m_max,temperature_2m_min,weather_code",
                "timezone": "auto",
                "forecast_days": 3,
            }
        )
        w = _fetch_json(w_url)
        cur = w.get("current") or {}
        daily = w.get("daily") or {}

        lines = [f"{name} 天气："]
        lines.append(
            f"当前：{_weather_desc(cur.get('weather_code', 0))}，气温 {cur.get('temperature_2m')}°C，"
            f"湿度 {cur.get('relative_humidity_2m')}%，风速 {cur.get('wind_speed_10m')} km/h"
        )
        for i, date in enumerate(daily.get("time", [])):
            tmax = daily["temperature_2m_max"][i]
            tmin = daily["temperature_2m_min"][i]
            code = daily["weather_code"][i]
            lines.append(f"{date}：{_weather_desc(code)}，{tmin}~{tmax}°C")
        return "\n".join(lines)
    except Exception as e:
        return f"天气查询失败：{e}"


def get_current_time() -> str:
    now = datetime.datetime.now()
    week = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][now.weekday()]
    return f"{now.strftime('%Y-%m-%d %H:%M:%S')}（{week}）"


# ============ 意图识别（规则路由，替代 function calling） ============

WEATHER_KW = ["天气", "气温", "温度", "下雨", "降雨", "下雪", "多云", "阴天",
              "几度", "降温", "升温", "冷吗", "热吗", "穿什么", "晴"]
TIME_KW = ["几点", "日期", "今天几号", "星期几", "现在时间", "几月几号", "时间"]
TOUR_KW = ["逛校园", "导览", "游览", "路线", "校园景点", "地标", "带我逛", "转转",
           "参观", "逛一逛", "游校园"]
ACTIVITY_KW = ["活动", "比赛", "讲座", "社团", "招新", "晚会", "校运会", "音乐节",
               "运动会", "竞赛", "展览", "宣讲", "答辩"]
CITY_NAMES = ["成都", "宜宾", "北京", "上海", "广州", "深圳", "重庆", "杭州", "武汉",
              "西安", "南京", "天津", "苏州", "长沙", "郑州"]


def detect_intents(query: str):
    """按关键词判断需要调用的工具。"""
    q = query or ""
    intents = []
    if any(k in q for k in WEATHER_KW):
        intents.append("weather")
    if any(k in q for k in TIME_KW):
        intents.append("time")
    if any(k in q for k in TOUR_KW):
        intents.append("tour")
    if any(k in q for k in ACTIVITY_KW):
        intents.append("activity")
    return intents


def extract_city(query: str) -> str:
    for c in CITY_NAMES:
        if c in query:
            return c
    return "成都"


def build_context(query: str):
    """执行工作流：检索知识库 + 按意图调用工具，返回 (上下文文本, trace)。"""
    parts = []
    trace = []
    intents = detect_intents(query)

    faq_res = search_faq(query)
    trace.append({"tool": "search_faq", "args": {"question": query}})
    parts.append("【校园知识库检索】\n" + faq_res)

    if "activity" in intents:
        act_res = search_activity(query)
        trace.append({"tool": "search_activity", "args": {"query": query}})
        parts.append("【校园活动检索】\n" + act_res)

    if "tour" in intents:
        tour_res = campus_tour()
        trace.append({"tool": "campus_tour", "args": {}})
        parts.append("【校园导览】\n" + tour_res)

    if "weather" in intents:
        city = extract_city(query)
        w_res = get_weather(city)
        trace.append({"tool": "get_weather", "args": {"city": city}})
        parts.append("【天气】\n" + w_res)

    if "time" in intents:
        t_res = get_current_time()
        trace.append({"tool": "get_current_time", "args": {}})
        parts.append("【当前时间】\n" + t_res)

    return "\n\n".join(parts), trace


def get_client():
    """创建 OpenAI 兼容客户端。API Key 没填时返回 None，由上层提示用户。"""
    if not config.API_KEY:
        return None
    # trust_env=False：绕过系统代理（本机曾因走 127.0.0.1 代理导致 405/连接失败）
    http_client = httpx.Client(trust_env=False, timeout=60.0)
    return OpenAI(base_url=config.BASE_URL, api_key=config.API_KEY, http_client=http_client)


def chat_with_trace(messages: list, client: OpenAI):
    """一轮对话：本地工作流（意图识别→检索→大模型生成），返回 (回复, trace)。"""
    query = messages[-1]["content"] if messages else ""
    history = messages[:-1]

    context, trace = build_context(query)

    user_prompt = f"""请严格根据下方【检索结果】回答用户的问题，务必遵守：
1. 只能使用检索结果中明确出现的信息，绝不编造检索结果里没有的地标、菜品、设施、数据等任何细节。
2. 如果检索结果不足以回答用户的问题，就诚实说明"知识库暂无相关信息"，并建议咨询辅导员或对应部门。
3. 如果是纯问候、闲聊（如"你好""谢谢""再见"），友好回应即可，无需引用检索结果。
4. 回答用中文，亲切自然，先给结论。

【检索结果】
{context}

【用户问题】
{query}
"""

    full_messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history
    full_messages.append({"role": "user", "content": user_prompt})

    response = client.chat.completions.create(
        model=config.MODEL,
        messages=full_messages,
    )
    message = response.choices[0].message
    return message.content or "", trace


def chat(messages: list, client: OpenAI) -> str:
    """一轮对话，返回最终回复文本（向后兼容）。"""
    content, _ = chat_with_trace(messages, client)
    return content
