"""校园知识库：从 faq.json 加载数据，做关键词检索。

以后要新增或修改校园信息，直接编辑 knowledge_base/faq.json 即可，代码不用改。
"""
import json
import os

DATA_FILE = os.path.join(os.path.dirname(__file__), "knowledge_base", "faq.json")
ACTIVITIES_FILE = os.path.join(os.path.dirname(__file__), "knowledge_base", "activities.json")
BAOYAN_FILE = os.path.join(os.path.dirname(__file__), "knowledge_base", "baoyan.json")
CANTEEN_FILE = os.path.join(os.path.dirname(__file__), "knowledge_base", "canteen.json")


def load_faq():
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def load_activities():
    with open(ACTIVITIES_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def load_baoyan():
    with open(BAOYAN_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def load_canteen():
    with open(CANTEEN_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


FAQ = load_faq()
ACTIVITIES = load_activities()
BAOYAN = load_baoyan()
CANTEEN = load_canteen()


def search_faq(query: str, top_k: int = 3) -> str:
    """检索知识库：按关键词命中数打分，返回最相关的几条。"""
    scored = []
    for item in FAQ:
        score = 0
        for kw in item.get("keywords", []):
            if kw in query:
                score += 3
        # 问题标题里的字也有少量权重，帮助匹配同义表达
        for ch in set(query):
            if ch in item["question"]:
                score += 1
        if score > 0:
            scored.append((score, item))

    scored.sort(key=lambda x: x[0], reverse=True)
    if not scored:
        return "知识库中暂时没有找到相关内容。"

    lines = []
    for _, item in scored[:top_k]:
        lines.append(f"【{item['category']}】{item['answer']}")
    return "\n\n".join(lines)


def search_activity(query: str, top_k: int = 3) -> str:
    """检索校园活动：按关键词命中数打分，返回最相关的活动。"""
    scored = []
    for item in ACTIVITIES:
        score = 0
        for kw in item.get("keywords", []):
            if kw in query:
                score += 3
        for ch in set(query):
            if ch in item["name"]:
                score += 1
        if score > 0:
            scored.append((score, item))

    scored.sort(key=lambda x: x[0], reverse=True)
    if not scored:
        return "暂时没有找到相关的校园活动，建议关注教务处、团委或学院的通知。"

    lines = []
    for _, item in scored[:top_k]:
        lines.append(
            f"【{item['type']}】{item['name']}\n"
            f"时间：{item['time']}\n地点：{item['location']}\n简介：{item['desc']}"
        )
    return "\n\n".join(lines)


def search_baoyan(query: str) -> str:
    """保研/考研规划：返回分阶段规划、学科方向推荐与官方资料链接（紧凑格式，减少换行）。"""
    data = BAOYAN
    timeline = "；".join(f"{t['stage']}：{t['todo']}" for t in data["timeline"])

    q = query or ""
    matched = [d for d in data["directions"] if any(k in q for k in d.get("keywords", []))]
    if not matched:
        matched = data["directions"]
    schools = "；".join(f"{d['field']}：{d['schools']}" for d in matched)

    links = "；".join(f"{r['title']} {r['url']}（{r['desc']}）" for r in data["resources"])

    return "【保研时间线】" + timeline + "\n【院校推荐】" + schools + "\n【官方链接】" + links


def _match_canteen(query: str, top_k: int = 3):
    """按档口标签与名称打分，返回最相关的档口列表。

    只把「标签命中」或「名称直接命中」当作具体匹配，避免「食堂有什么好吃的」
    这种泛泛提问被单字重叠误判成具体档口（应走招牌推荐兜底）。
    """
    q = query or ""
    scored = []
    for item in CANTEEN["items"]:
        score = 0
        name = item["name"]
        for kw in item.get("tags", []):
            if kw and kw in q:
                score += 3
        if name and (name in q or q in name):
            score += 6
        if score >= 3:
            scored.append((score, item))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [item for _, item in scored[:top_k]]


def match_canteen(query: str, top_k: int = 3):
    """公开接口：返回命中的档口列表；无具体命中返回空列表，用于判断是否为具体档口提问。"""
    return _match_canteen(query, top_k)


def _featured(top_k: int = 3):
    return [i for i in CANTEEN["items"] if i.get("featured")][:top_k]


def _fmt_canteen(items) -> str:
    """把档口列表格式化为检索文本（含供应时间，仅 docx 明确写了的才有）。"""
    out = []
    for it in items:
        s = f"【{it['name']}】{it['intro']}"
        if it.get("service_hours"):
            s += f" 供应时间：{it['service_hours']}"
        s += f" 菜品/价格：{it['menu']}"
        out.append(s)
    return "\n".join(out)


def _imgs_canteen(items) -> list:
    return [{"name": it["name"], "image": it["image"], "menu": it["menu"]} for it in items]


def search_canteen(query: str, top_k: int = 3) -> str:
    """食堂档口检索：返回档口简介与菜品价格，供智能体推荐。"""
    items = _match_canteen(query, top_k) or _featured(top_k)
    return f"以下是{CANTEEN['restaurant']}的档口信息：\n" + _fmt_canteen(items)


def canteen_images(query: str, top_k: int = 3) -> list:
    """返回匹配档口的图片信息（名称 + 图片路径），供界面展示配图。"""
    items = _match_canteen(query, top_k) or _featured(top_k)
    return _imgs_canteen(items)


def canteen_overview() -> str:
    """食堂总览：按分类统计档口数量并列出，供「餐厅有几个档口/有哪些店」类问题。"""
    groups = {}
    for it in CANTEEN["items"]:
        groups.setdefault(it["group"], []).append(it["name"])
    order = ["正餐", "面食", "快餐西式", "轻食", "早餐", "自选餐", "保障餐",
             "小吃", "甜品水果", "茶饮咖啡", "烘焙甜品", "便利店", "零食", "文创百货", "服务设施"]
    total = len(CANTEEN["items"])
    lines = [f"{CANTEEN['restaurant']}共有 {total} 个档口，按类别如下："]
    for g in order:
        if g in groups:
            lines.append(f"【{g}】{len(groups[g])} 家：{'、'.join(groups[g])}")
    return "\n".join(lines)


def canteen_light():
    """轻食/减肥：返回轻食类档口，返回 (文本, 图片列表)。"""
    items = [i for i in CANTEEN["items"] if i.get("light")]
    return f"以下是{CANTEEN['restaurant']}的轻食/健康类档口：\n" + _fmt_canteen(items), _imgs_canteen(items)


def canteen_by_budget(budget: float):
    """预算筛选：返回「最便宜一份 ≤ 预算」的档口，按价格从低到高，返回 (文本, 图片列表)。

    文本与配图严格同源（都取最便宜的前 3 个），保证文字介绍和图片一一对应。
    """
    items = [i for i in CANTEEN["items"] if i.get("price_min") and i["price_min"] <= budget]
    items.sort(key=lambda i: i["price_min"])
    if not items:
        return f"{CANTEEN['restaurant']}内暂时没有「最便宜一份 ≤ {budget} 元」的档口，建议适当提高预算。", []
    shown = items[:3]
    header = f"{CANTEEN['restaurant']}内「最便宜一份 ≤ {budget} 元」的档口共 {len(items)} 个，按价格从低到高，先推荐最便宜的 3 个："
    return header + "\n" + _fmt_canteen(shown), _imgs_canteen(shown)


# 经典校园游览路线：按游览顺序排列，每个点讲清「在哪里 + 看点/小故事」
CAMPUS_TOUR = [
    ("校门三角草坪", "进校第一站，9米高的「青春」雕塑矗立，基座刻着校训「穷究于理，成就于工」"),
    ("砚湖", "建校初期师生徒手挖成的人工湖，形似砚台，校歌里唱「砚湖泱泱」，湖边有回廊和锦鲤"),
    ("水上图书馆", "坐落在砚湖旁，1990年落成，被称为中国高校「第一水上图书馆」，五层独特建筑"),
    ("桐荫路", "TFboys《heart》MV 的拍摄地，秋季银杏梧桐一片金黄，是成理最美的路"),
    ("东风渠", "横贯校园的景观水渠，渠旁就是美食一条街「后街」"),
    ("成都自然博物馆", "藏有亚洲最大的完整恐龙化石「合川马门溪龙」，成理因此被叫「恐龙大学」"),
    ("东区图书馆", "现代大气的图书馆，有星空顶，阅览座位近8000个"),
    ("求真广场·岭岚阁·艺术大楼", "校园标志性建筑群，适合拍照打卡"),
]


def campus_tour() -> str:
    """返回经典校园游览路线，供智能体按顺序讲解。"""
    lines = ["以下是成都理工大学经典游览路线（按顺序）："]
    for i, (spot, intro) in enumerate(CAMPUS_TOUR, 1):
        lines.append(f"{i}. {spot}：{intro}")
    return "\n".join(lines)
