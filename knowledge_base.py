"""校园知识库：从 faq.json 加载数据，做关键词检索。

以后要新增或修改校园信息，直接编辑 knowledge_base/faq.json 即可，代码不用改。
"""
import json
import os

DATA_FILE = os.path.join(os.path.dirname(__file__), "knowledge_base", "faq.json")
ACTIVITIES_FILE = os.path.join(os.path.dirname(__file__), "knowledge_base", "activities.json")


def load_faq():
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def load_activities():
    with open(ACTIVITIES_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


FAQ = load_faq()
ACTIVITIES = load_activities()


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
