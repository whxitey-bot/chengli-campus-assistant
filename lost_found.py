"""失物招领：基于 Supabase（PostgREST REST API）的共享频道 + 智能匹配。

不引入 supabase-py 依赖，直接用 httpx 调 REST（httpx 已在使用），少一个依赖、更可控。
Supabase 未配置时所有写操作抛 RuntimeError、读操作返回空列表，由界面提示用户去配置。
"""
import re
import secrets

import httpx

import config

TABLE = "lost_found"

# 物品类型集合（与 SQL 的 check 约束、agent 提取保持一致）
ITEM_TYPES = ["校园卡", "手机", "钱包", "书籍", "钥匙", "雨伞", "耳机", "U盘", "水杯", "其他"]

# 地点别名 → 规范化地点名（用于匹配时消除"图书馆/图书馆三楼"的差异）
_LOCATION_ALIAS = {
    "图书馆": "图书馆", "水上图书馆": "图书馆", "东区图书馆": "图书馆",
    "食堂": "食堂", "餐厅": "食堂", "芙蓉": "芙蓉餐厅", "香樟": "香樟餐厅", "银杏": "银杏餐厅",
    "操场": "操场", "运动场": "操场", "体育馆": "体育馆",
    "宿舍": "宿舍", "寝室": "宿舍", "公寓": "宿舍",
    "教学楼": "教学楼", "教室": "教学楼",
    "砚湖": "砚湖", "桐荫路": "桐荫路", "后街": "后街",
    "东区": "东区", "西区": "西区",
}

# 匹配时忽略的通用词（避免"一个/帮帮"这类词造成误匹配）
_MATCH_STOP = {"一个", "有没有", "捡到", "丢失", "遗失", "校园", "我的", "这个", "一下",
               "帮帮", "同学", "谢谢", "联系", "找到", "寻找", "本人", "失物"}


def generate_token() -> str:
    """生成 6 位数字口令，发布时下发给发布者，用于管理自己的帖子。"""
    return f"{secrets.randbelow(1000000):06d}"


def is_configured() -> bool:
    return bool(config.SUPABASE_URL and config.SUPABASE_ANON_KEY)


def _headers() -> dict:
    return {
        "apikey": config.SUPABASE_ANON_KEY,
        "Authorization": f"Bearer {config.SUPABASE_ANON_KEY}",
        "Content-Type": "application/json",
    }


def _client() -> httpx.Client:
    kwargs = {"base_url": config.SUPABASE_URL, "headers": _headers(), "timeout": 15.0}
    proxy = getattr(config, "SUPABASE_PROXY", "")
    if proxy:
        kwargs["proxy"] = proxy
    return httpx.Client(**kwargs)


def _norm_location(text) -> str:
    for alias, canonical in _LOCATION_ALIAS.items():
        if alias in (text or ""):
            return canonical
    return text or ""


# ============ 基础 CRUD ============

def list_posts(type_filter=None, status_filter="open", item_type=None, search=None, limit=100):
    """查询帖子，返回按创建时间倒序的列表。未配置时返回空列表。"""
    if not is_configured():
        return []
    params = {"select": "*", "order": "created_at.desc", "limit": str(limit)}
    if type_filter:
        params["type"] = f"eq.{type_filter}"
    if status_filter:
        params["status"] = f"eq.{status_filter}"
    if item_type:
        params["item_type"] = f"eq.{item_type}"
    if search:
        params["or"] = (
            f"(title.ilike.*{search}*,description.ilike.*{search}*,location.ilike.*{search}*)"
        )
    try:
        with _client() as c:
            r = c.get(f"/rest/v1/{TABLE}", params=params)
            r.raise_for_status()
            return r.json()
    except Exception:
        return []


def insert_post(data: dict):
    """插入一条帖子，返回插入后的完整记录（含 id）。"""
    if not is_configured():
        raise RuntimeError("Supabase 未配置，无法发布。")
    with _client() as c:
        r = c.post(f"/rest/v1/{TABLE}", json=data, headers={"Prefer": "return=representation"})
        r.raise_for_status()
        rows = r.json()
        return rows[0] if rows else None


def update_post(post_id, data: dict):
    """更新帖子（如状态、匹配对象），返回更新后的记录。"""
    with _client() as c:
        r = c.patch(
            f"/rest/v1/{TABLE}?id=eq.{post_id}", json=data,
            headers={"Prefer": "return=representation"},
        )
        r.raise_for_status()
        rows = r.json()
        return rows[0] if rows else None


def delete_post(post_id):
    with _client() as c:
        r = c.delete(f"/rest/v1/{TABLE}?id=eq.{post_id}")
        r.raise_for_status()


def get_post(post_id):
    """按 id 取单条帖子，不存在或未配置返回 None。"""
    if not is_configured():
        return None
    try:
        with _client() as c:
            r = c.get(f"/rest/v1/{TABLE}", params={"id": f"eq.{post_id}", "select": "*"})
            r.raise_for_status()
            rows = r.json()
            return rows[0] if rows else None
    except Exception:
        return None


def confirm_and_resolve(post_id):
    """一方确认交接：把自己置为已确认；若配对双方都已确认，则双方一并标记 resolved。

    返回 (提示文本, 是否双方已确认)。
    """
    post = get_post(post_id)
    if not post:
        return "帖子不存在", False
    update_post(post_id, {"confirmed": True})
    mate_id = post.get("matched_with")
    if not mate_id:
        return "已确认", False
    mate = get_post(mate_id)
    if mate and mate.get("confirmed"):
        update_post(post_id, {"status": "resolved"})
        update_post(mate_id, {"status": "resolved"})
        return "双方均已确认，物品已找回 🎉", True
    return "本方已确认，等待对方确认", False


# ============ 智能匹配 ============

def _score_pair(a: dict, b: dict):
    """给一对「寻物 + 拾到」帖子打分，返回 (score, reasons)。a/b 顺序无所谓。"""
    reasons = []
    score = 0
    if a.get("item_type") == b.get("item_type"):
        score += 3
        reasons.append(f"物品类型一致：{a['item_type']}")
    la = _norm_location(a.get("location"))
    lb = _norm_location(b.get("location"))
    if la and lb and (la in lb or lb in la):
        score += 2
        reasons.append(f"地点接近：{a.get('location')} / {b.get('location')}")
    # 标题/描述里的关键词重叠（连续中文片段）
    ta = f"{a.get('title') or ''} {a.get('description') or ''}"
    tb = f"{b.get('title') or ''} {b.get('description') or ''}"
    shared = set(re.findall(r"[一-龥]{2,}", ta)) & set(re.findall(r"[一-龥]{2,}", tb))
    shared -= _MATCH_STOP
    if shared:
        score += min(len(shared), 3)
        reasons.append("特征吻合：" + "、".join(sorted(shared)[:3]))
    return score, reasons


def find_matches(post: dict):
    """为一条帖子找对面类型的候选，返回按置信度降序的列表。

    只把「物品类型一致」作为必要门槛，避免无关帖子被当成匹配。
    """
    other = "found" if post.get("type") == "lost" else "lost"
    candidates = list_posts(type_filter=other, status_filter="open")
    out = []
    for c in candidates:
        if c.get("id") == post.get("id"):
            continue
        score, reasons = _score_pair(post, c)
        if score < 3:
            continue
        confidence = min(95, 60 + score * 8)
        out.append({"post": c, "score": score, "confidence": confidence, "reasons": reasons})
    out.sort(key=lambda x: -x["confidence"])
    return out


def hot_locations():
    """失物高发点统计：统计所有 open 帖子出现的地点频次。"""
    posts = list_posts(status_filter="open", limit=200)
    counts = {}
    for p in posts:
        loc = _norm_location(p.get("location")) or "未注明地点"
        counts[loc] = counts.get(loc, 0) + 1
    return sorted(counts.items(), key=lambda x: -x[1])


# ============ 供智能体引用 ============

def format_posts_for_llm(posts, max_n=8) -> str:
    """把帖子列表压缩成给大模型的文本。"""
    if not posts:
        return "当前失物招领频道里暂无相关记录。"
    lines = []
    for p in posts[:max_n]:
        kind = "寻物" if p.get("type") == "lost" else "拾到"
        status = {"open": "待处理", "matched": "已匹配", "resolved": "已找回"}.get(p.get("status"), p.get("status"))
        line = f"【{kind}·{status}】{p.get('title')}（{p.get('item_type')}）"
        if p.get("location"):
            line += f" 地点：{p['location']}"
        if p.get("lost_time"):
            line += f" 时间：{p['lost_time']}"
        if p.get("description"):
            line += f" 描述：{p['description']}"
        lines.append(line)
    return "\n".join(lines)


# ============ 演示种子数据 ============

def seed_demo():
    """演示模式：清空表并灌入一组真实感帖子（含一组可命中的「校园卡」对）。"""
    if not is_configured():
        raise RuntimeError("Supabase 未配置，无法灌入种子数据。")
    for p in list_posts(status_filter=None, limit=1000):
        try:
            delete_post(p["id"])
        except Exception:
            pass
    seed = [
        {"type": "found", "item_type": "校园卡", "title": "图书馆捡到一张校园卡",
         "description": "蓝色卡套，卡面有贴纸，卡号尾号 4216", "location": "图书馆三楼自习区",
         "lost_time": "今天下午", "contact": "加微信 chengli_helper",
         "secret_question": "卡背面贴了什么图案？", "secret_answer": "小恐龙贴纸", "status": "open"},
        {"type": "lost", "item_type": "校园卡", "title": "图书馆丢了校园卡",
         "description": "蓝色卡套，卡号尾号 4216，有谁捡到请联系我", "location": "图书馆",
         "lost_time": "昨天下午", "contact": "电话 13512345678",
         "secret_question": "", "secret_answer": "", "status": "open"},
        {"type": "found", "item_type": "雨伞", "title": "食堂捡到一把黑色长柄伞",
         "description": "黑色长柄雨伞，伞柄有磨损", "location": "芙蓉餐厅",
         "lost_time": "今天中午", "contact": "放到了餐厅服务台",
         "secret_question": "", "secret_answer": "", "status": "open"},
        {"type": "lost", "item_type": "耳机", "title": "操场丢了白色蓝牙耳机",
         "description": "AirPods 单只，白色，带透明保护壳", "location": "操场",
         "lost_time": "前天晚上", "contact": "电话 13987654321",
         "secret_question": "", "secret_answer": "", "status": "open"},
        {"type": "found", "item_type": "U盘", "title": "教学楼捡到银色U盘",
         "description": "银色金属U盘，16G，里面有很多课件", "location": "教学楼",
         "lost_time": "昨天", "contact": "交给教学楼值班室",
         "secret_question": "", "secret_answer": "", "status": "open"},
        {"type": "lost", "item_type": "钱包", "title": "砚湖附近丢了棕色钱包",
         "description": "棕色短款钱包，里面有校园卡和少量现金", "location": "砚湖",
         "lost_time": "今天早上", "contact": "电话 13812344321",
         "secret_question": "", "secret_answer": "", "status": "open"},
    ]
    for data in seed:
        data["secret_token"] = "123456"
        insert_post(data)
    return len(seed)
