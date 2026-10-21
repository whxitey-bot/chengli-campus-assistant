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
from knowledge_base import (
    search_faq, search_activity, search_baoyan, campus_tour,
    search_canteen, canteen_images, match_canteen,
    canteen_overview, canteen_light, canteen_by_budget, search_faculty,
)
import lost_found

# 系统提示词：定义这个智能体的「人设」和职责
SYSTEM_PROMPT = f"""你是「{config.SCHOOL_NAME}」的校园助手「成理小助手」，像熟悉学校每个角落的学长学姐，热情、耐心、靠谱，专门帮同学解决入学和校园生活问题。

【核心规则】
1. 优先依据本轮【检索结果】回答，检索结果里明确有的细节（地标、菜品、价格、数据）必须照实、不得编造。若检索结果显示"暂无相关内容"或与问题无关，说明本地知识库未覆盖，可基于你对「成都理工大学」的通用了解回答（这是真实高校），但涉及具体人名、电话、排名数字、最新政策等细节时，没把握就说明"建议以学校官网/教务处最新通知为准"，不要编造不存在的人名、学院、专业。
2. 纯问候、闲聊、感谢等非事实问题友好回应即可，无需引用检索结果。
3. 问题模糊时礼貌追问，不瞎猜。
4. 学校名必须写「成都理工大学」或简称「成理」，绝不可写成别的校名（如"德州理工""成都理工大"等错误写法）。

【分场景 SOP】
- 报到：问清"报到前/当天"，给材料清单（迎新网 yx.cdut.edu.cn、录取通知书/身份证/档案），招生办 028-84078927。
- 军训：约14天不剪头发，备防晒霜/水杯/运动鞋/换洗衣物，注意防晒补水。
- 选课：分预选正选两阶段，热门课要抢，关注教务处通知。
- 活动：按「名称+时间+地点+亮点」介绍，查不到建议关注团委/教务处通知。
- 导览：按游览顺序讲"在哪里+看点"（砚湖师生徒手挖成、桐荫路是TFboys MV拍摄地）。
- 食堂：严格依据【食堂档口检索】推荐，档口名称/菜品/价格/供应时间只说检索结果里明确有的；本知识库只收录芙蓉餐厅档口，其他餐厅（香樟/银杏/珙桐等）的具体档口信息暂无，不要自行补写；价格筛选、轻食推荐均以检索结果为准。
- 失物招领：严格依据【失物招领频道】检索结果回答"有没有人捡到/丢了XX"；查不到就说频道暂无相关记录，并建议去「失物招领」页发布或登记；绝不编造帖子。若用户想发布寻物/拾到信息，引导其到「失物招领」页填写。
- 学习规划：先问专业/年级/目标/时间，给分阶段计划（阶段划分+周目标+每日任务+各科重点+作息+建议）。
- 保研：严格基于【检索结果】的分阶段规划（大一绩点→大二科研竞赛→大三夏令营→大四推免）、院校推荐和官方链接回答，结构为「时间线+院校推荐+官方链接」。注意：「X级」指 20XX 年入学（如 24级=2024年入学），要按当前年份换算成年级，不要望文生义把「24级」当成大一。若【检索结果】给出用户当前年级，就从该年级讲起、重点规划该年级及之后的阶段，不要从大一重复讲。不编造具体院校排名数字，招生政策以研招网和官网为准。
- 考研：按「择校→公共课（政治/英语/数学）→专业课→报名（9-10月）→初试（12月底）→复试（次年3-4月）」分阶段规划，结合用户年级、专业、目标院校、是否跨考、每日可学习时长定制；公共课和专业课分科给重点与节奏；政治不宜过早开始、英语坚持每日单词+真题、专业课以目标院校参考书目为准；跨考要额外补专业课基础。
- 教师查询：严格依据【教师检索】回答老师的姓名、职称、学院、研究方向、邮箱等；若检索显示"教师库中暂时没有收录"，诚实说明没收录，建议到学校教师个人主页平台 faculty.cdut.edu.cn 查询，绝不编造老师姓名、职称、研究方向。

【自我介绍】
当用户问「你能做什么 / 你有什么功能 / 介绍一下你自己 / 你是谁」时，先一句话定位，再用下面几点分点介绍自己（可少量 emoji）：
- 🏫 校园生活：新生报到、军训、选课、宿舍等校园 FAQ。
- 🍜 食堂攻略：芙蓉餐厅档口、轻食健康餐、按预算推荐。
- 🎓 保研/考研规划：分阶段规划、院校推荐、个性化定制计划。
- 📦 失物招领：共享频道发布、浏览、智能匹配。
- 👨‍🏫 教师查询：查老师的职称、学院、研究方向。
- 🗺️ 校园导览、🌤️ 天气、🕐 时间、🎪 校园活动。

【回答风格】
中文、亲切像学长学姐，先结论后说明，可少量 emoji。
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
BAOYAN_KW = ["保研", "推免", "夏令营", "预推免", "九推", "考研", "读研", "研究生",
             "深造", "目标院校", "导师", "绩点排名", "优秀营员"]
CANTEEN_KW = ["食堂", "餐厅", "吃饭", "吃什么", "吃啥", "好吃的", "美食", "档口",
              "菜单", "菜品", "夜宵", "外卖", "早餐", "午餐", "晚餐", "芙蓉",
              "全家", "瑞幸", "咖啡", "蜜雪冰城", "麦当劳", "汉堡", "名创优品",
              "螺蛳粉", "冒菜", "麻辣烫", "鸡公煲", "饺子", "云吞", "馄饨", "抄手",
              "牛肉面", "拉面", "小面", "煎饼", "水果捞", "奶茶", "冰淇淋",
              "手撕鸡", "捞饭", "铁锅炖", "鸭脖", "卤味", "醉鸡", "豌杂面", "渔粉",
              "擂椒饭", "三明治", "轻食", "沙拉",
              "减肥", "减脂", "低卡", "低脂", "清淡", "瘦身", "预算", "多少钱", "价格"]

# 轻食/减肥场景关键词（在食堂意图内细分）
LIGHT_KW = ["减肥", "减脂", "轻食", "低卡", "低脂", "清淡", "瘦身", "控制体重", "热量", "健康"]

# 餐厅总览场景关键词（问「一共几个档口 / 有哪些店」）
OVERVIEW_KW = ["几个档口", "多少档口", "多少个档口", "哪些档口", "有什么档口", "有哪些档口",
               "都有什么", "有些什么", "都有啥", "有些啥", "有哪些店", "有什么店",
               "介绍一下", "总览", "全部", "都有哪些", "档口吗"]

# 失物招领关键词（丢了/捡到 → 检索频道或引导发布）
LOSTFOUND_KW = ["丢了", "遗失", "丢失", "掉了", "找不到", "不见了", "忘在", "落下",
                "捡到", "拾到", "捡了", "招领", "寻物", "失物", "丢东西"]
CITY_NAMES = ["成都", "宜宾", "北京", "上海", "广州", "深圳", "重庆", "杭州", "武汉",
              "西安", "南京", "天津", "苏州", "长沙", "郑州"]

# 教师查询关键词（问老师/教授/校长/书记/是谁 → 检索教师库）
FACULTY_KW = ["老师", "教授", "副教授", "讲师", "导师", "院长", "副院长", "书记",
              "辅导员", "班主任", "院士", "教师", "是谁", "哪位"]

# 纯问候/闲聊：不继承历史里的食堂等意图，避免「问过食堂后再发你好」又弹出档口配图
GREETING_KW = ["你好", "您好", "哈喽", "哈啰", "嗨", "hello", "hi", "hey",
               "在吗", "谢谢", "多谢", "再见", "拜拜", "晚安", "早安", "你是谁"]


def is_greeting(text: str) -> bool:
    t = (text or "").strip().lower()
    return any(k in t for k in GREETING_KW)


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
    if any(k in q for k in BAOYAN_KW):
        intents.append("baoyan")
    if any(k in q for k in CANTEEN_KW):
        intents.append("canteen")
    if any(k in q for k in LOSTFOUND_KW):
        intents.append("lostfound")
    if any(k in q for k in FACULTY_KW):
        intents.append("faculty")
    return intents


# 追问式意图：需要继承最近几轮历史消息来保持意图（如「保研→可是我是大三」）。
# 其余一次性查询（食堂/天气/时间/导览/活动）只从当前问题判断，避免历史里的食堂关键词
# 污染无关提问（比如先问过食堂再问「帮我做保研计划」，却弹出食堂配图）。
STICKY_INTENTS = ("baoyan", "faculty", "lostfound")


def extract_city(query: str) -> str:
    for c in CITY_NAMES:
        if c in query:
            return c
    return "成都"


def extract_budget(query: str):
    """提取预算金额（元）。只在出现明确预算信号时返回，避免把「手撕鸡饭12元」误判成预算。

    支持：「预算10元」「10元以内/以下」「10块钱以内」「不超过15元」等。
    """
    text = query or ""
    m = re.search(r"预算(?:是|为|在|大概|大约|约)?\s*(\d+(?:\.\d+)?)", text)
    if m:
        return float(m.group(1))
    m = re.search(r"(\d+(?:\.\d+)?)\s*元\s*(?:以内|以下|左右|之内|上下)", text)
    if m:
        return float(m.group(1))
    m = re.search(r"(\d+(?:\.\d+)?)\s*块(?:钱)?\s*(?:以内|以下|左右|之内)", text)
    if m:
        return float(m.group(1))
    m = re.search(r"(?:不超过|控制在|最多|上限)\s*(\d+(?:\.\d+)?)\s*元", text)
    if m:
        return float(m.group(1))
    return None


GRADE_CN = {1: "大一", 2: "大二", 3: "大三", 4: "大四"}
_GRADE_DIGIT = {"一": 1, "二": 2, "三": 3, "四": 4, "1": 1, "2": 2, "3": 3, "4": 4}


def infer_grade(text: str):
    """从文本推断用户当前年级，返回中文年级（如"大三"）或 None。

    支持两种写法：
    - 直接写"大三"/"大3"
    - 写"24级"/"2024级"（入学年份），按当前年月推算年级
    """
    text = text or ""
    m = re.search(r"大([一二三四1-4])", text)
    if m:
        return GRADE_CN[_GRADE_DIGIT[m.group(1)]]

    m = re.search(r"(20\d{2}|\d{2})级", text)
    if m:
        year = int(m.group(1))
        if year < 100:
            year += 2000
        now = datetime.datetime.now()
        grade = now.year - year + (1 if now.month >= 9 else 0)
        if 1 <= grade <= 4:
            return GRADE_CN[grade]
    return None


LOSTFOUND_EXTRACT_PROMPT = """你是失物招领信息提取助手。从用户口语描述里提取结构化信息，只返回一个 JSON 对象（不要任何多余文字、不要代码块标记）：
{"type":"lost或found","item_type":"校园卡/手机/钱包/书籍/钥匙/雨伞/耳机/U盘/水杯/其他","title":"简短标题","location":"地点","lost_time":"时间","contact":"联系方式，可为空","description":"一段规范友好的描述"}
判定规则：用户说"丢了/遗失/不见了/忘在"则 type=lost；说"捡到/拾到"则 type=found。item_type 从给定集合选最接近的；提取不到的字段填空字符串。"""


def extract_lostfound(query: str, client):
    """从口语描述提取失物招领结构化信息，返回 dict；失败或 client 为空时返回 {}。"""
    if client is None or not query:
        return {}
    try:
        resp = client.chat.completions.create(
            model=config.MODEL,
            messages=[
                {"role": "system", "content": LOSTFOUND_EXTRACT_PROMPT},
                {"role": "user", "content": query},
            ],
        )
        text = resp.choices[0].message.content or ""
        m = re.search(r"\{.*\}", text, re.S)
        if not m:
            return {}
        data = json.loads(m.group(0))
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {}


def _route_canteen(query: str):
    """食堂子场景路由，返回 (检索文本, 配图列表, 工具名)。

    优先级：预算 → 轻食 → 具体档口 → 总览 → 招牌推荐兜底。
    """
    budget = extract_budget(query)
    if budget is not None:
        text, imgs = canteen_by_budget(budget)
        return text, imgs, "canteen_budget"
    if any(k in query for k in LIGHT_KW):
        text, imgs = canteen_light()
        return text, imgs, "canteen_light"
    if match_canteen(query):
        return search_canteen(query), canteen_images(query), "search_canteen"
    if any(k in query for k in OVERVIEW_KW):
        return canteen_overview(), [], "canteen_overview"
    return search_canteen(query), canteen_images(query), "search_canteen"


def build_context(query: str, recent: str = ""):
    """执行工作流：检索知识库 + 按意图调用工具，返回 (上下文文本, trace)。

    recent：最近几轮历史用户消息，用于多轮追问时保持意图识别不丢。
    """
    parts = []
    trace = []
    # 当前这轮从「当前问题」判意图；只有追问式意图才继承历史消息，
    # 食堂/天气/时间/导览/活动这类一次性查询不继承，避免历史关键词污染无关提问。
    intents = list(detect_intents(query))
    recent_intents = detect_intents(recent) if recent else []
    for s in STICKY_INTENTS:
        if s in recent_intents and s not in intents:
            intents.append(s)

    # 保研/考研有专门的 search_baoyan，此时跳过通用 faq 检索，避免无关结果混入、拉长上下文
    if "baoyan" not in intents:
        faq_res = search_faq(query)
        trace.append({"tool": "search_faq", "args": {"question": query}})
        parts.append("【校园知识库检索】\n" + faq_res)

    if "activity" in intents:
        act_res = search_activity(query)
        trace.append({"tool": "search_activity", "args": {"query": query}})
        parts.append("【校园活动检索】\n" + act_res)

    if "baoyan" in intents:
        by_res = search_baoyan(f"{query} {recent}")
        trace.append({"tool": "search_baoyan", "args": {"query": query}})
        # 推断用户当前年级并前置，让模型聚焦该年级之后的阶段
        grade = infer_grade(f"{query} {recent}")
        if grade:
            by_res = f"【用户当前年级】{grade}（从该年级讲起，重点规划之后阶段，不要从大一重复讲）\n" + by_res
        parts.append("【保研/考研规划】\n" + by_res)

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

    if "canteen" in intents:
        c_res, imgs, tool = _route_canteen(query)
        trace.append({"tool": tool, "args": {"query": query}, "images": imgs})
        parts.append("【食堂档口检索】\n" + c_res)

    if "lostfound" in intents:
        posts = lost_found.list_posts(status_filter="open", limit=20)
        lf_res = lost_found.format_posts_for_llm(posts)
        trace.append({"tool": "search_lostfound", "args": {"query": query}})
        parts.append("【失物招领频道】\n" + lf_res)

    if "faculty" in intents:
        fc_res = search_faculty(f"{query} {recent}")
        trace.append({"tool": "search_faculty", "args": {"query": query}})
        parts.append("【教师检索】\n" + fc_res)

    return "\n\n".join(parts), trace


def get_client():
    """创建 OpenAI 兼容客户端。API Key 没填时返回 None，由上层提示用户。"""
    if not config.API_KEY:
        return None
    # trust_env=False：绕过系统代理（本机曾因走 127.0.0.1 代理导致 405/连接失败）
    # timeout=120：考研/保研这类分阶段规划会生成较长回答，网关又偶发慢，放宽到 120 秒避免误报超时
    http_client = httpx.Client(trust_env=False, timeout=120.0)
    return OpenAI(
        base_url=config.BASE_URL,
        api_key=config.API_KEY,
        http_client=http_client,
        max_retries=1,
    )


def chat_with_trace(messages: list, client: OpenAI):
    """一轮对话：本地工作流（意图识别→检索→大模型生成），返回 (回复, trace)。"""
    query = messages[-1]["content"] if messages else ""
    history = messages[:-1]

    recent = ""
    if not is_greeting(query):
        recent = " ".join(m["content"] for m in history[-3:] if m["role"] == "user")
    context, trace = build_context(query, recent)

    grade = infer_grade(f"{query} {recent}")
    grade_line = ""
    if grade:
        grade_line = f"\n（注意：用户当前就读 {grade}，这是已换算好的年级，请直接按 {grade} 及之后的阶段规划，不要从大一开始。）"

    tools = [t.get("tool") for t in trace]
    if "canteen_overview" in tools:
        # 总览直接返回本地完整列表，避免大模型逐条复制 34 个档口导致生成慢、甚至超时
        return "这是芙蓉餐厅的全部档口，按类别给你列好啦～\n\n" + canteen_overview(), trace
    length_rule = "回答简洁精炼，控制在 300 字以内，重点突出，不要啰嗦（除非用户明确要求详细展开）。"
    if any(t in ("search_canteen", "canteen_light", "canteen_budget") for t in tools):
        length_rule = "请按检索结果给出的档口顺序逐一介绍，不要打乱顺序、不要遗漏；每个档口说清名称和关键菜品/价格即可，确保与下方配图一一对应。"

    user_prompt = f"""请严格根据下方【检索结果】回答用户的问题，务必遵守：
1. 优先使用检索结果中明确出现的信息，检索结果里有的（地标、菜品、设施、价格、数据）必须照实、不得编造。
2. 若检索结果显示"暂无相关内容"或与问题无关（本地知识库未覆盖），可基于你对「成都理工大学」的通用了解回答；涉及具体人名、电话、排名数字、最新政策等，没把握就说明"建议以学校官网/教务处最新通知为准"，不要编造不存在的人名、学院、专业。
3. 如果是纯问候、闲聊（如"你好""谢谢""再见"），友好回应即可，无需引用检索结果。
4. 回答用中文，亲切自然，先给结论。
5. {length_rule}

【检索结果】
{context}

【用户问题】
{query}{grade_line}
"""

    full_messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history
    full_messages.append({"role": "user", "content": user_prompt})

    response = client.chat.completions.create(
        model=config.MODEL,
        messages=full_messages,
        max_tokens=2000,
    )
    message = response.choices[0].message
    return message.content or "", trace


def chat(messages: list, client: OpenAI) -> str:
    """一轮对话，返回最终回复文本（向后兼容）。"""
    content, _ = chat_with_trace(messages, client)
    return content
