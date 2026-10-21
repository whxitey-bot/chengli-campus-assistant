"""界面：用 Streamlit 生成聊天页面。运行：streamlit run app.py"""
import datetime
import html
import os
import re

import streamlit as st

import config
import lost_found
from agent import chat_with_trace, get_client, extract_lostfound

PRESET_QUESTIONS = [
    "新生报到要带哪些材料？",
    "军训要准备什么？",
    "学校有哪些好吃的食堂？",
    "芙蓉餐厅都有哪些档口？",
    "帮我做一个保研学习计划",
    "帮我制定一个考研复习计划",
    "我丢了校园卡，怎么办？",
    "能带我逛逛校园吗？",
    "砚湖在哪里？",
    "最近学校有什么活动？",
    "今天成都天气怎么样？",
]

TOOL_LABELS = {
    "search_faq": "📖 检索知识库",
    "search_activity": "🎪 检索校园活动",
    "search_baoyan": "🎓 保研/考研规划",
    "search_canteen": "🍜 检索食堂档口",
    "canteen_overview": "🏪 食堂档口总览",
    "canteen_light": "🥗 轻食/健康推荐",
    "canteen_budget": "💰 按预算筛选",
    "campus_tour": "🗺️ 获取导览路线",
    "get_weather": "🌤️ 查询天气",
    "get_current_time": "🕐 获取时间",
    "search_lostfound": "📦 检索失物招领频道",
    "search_faculty": "👨‍🏫 检索教师库",
}


# ============ 莫兰迪主题样式 ============
MORANDI_CSS = """
<style>
/* 莫兰迪色板 */
:root{
  --mbg1:#e8dfd5; --mbg2:#d7dee2; --mbg3:#e6dcd8;
  --card:#fbf8f3; --pink:#d3a7a2; --blue:#9fb6c0;
  --purple:#b9abc8; --green:#a8b79b; --text:#5c554c;
  --text-light:#8a8075; --border:#e8e0d5;
  /* 覆盖 Streamlit 默认红色主题，改成莫兰迪蓝，避免输入框/发送键出现红色 */
  --primary-color:#9fb6c0;
}

/* 隐藏 Streamlit 默认页眉与菜单 */
header[data-testid="stHeader"]{background:transparent !important;}
#MainMenu, footer{visibility:hidden;}
[data-testid="stToolbar"]{visibility:hidden;}

/* 整页莫兰迪渐变背景 + 缓慢流动动画 */
.stApp{
  background:linear-gradient(135deg,var(--mbg1),var(--mbg2),var(--mbg3)) !important;
  background-size:300% 300% !important;
  animation:gradientShift 18s ease infinite;
}
@keyframes gradientShift{
  0%{background-position:0% 50%;}
  50%{background-position:100% 50%;}
  100%{background-position:0% 50%;}
}

/* 漂浮光晕（固定在视口，不随滚动） */
.stApp::before,.stApp::after{
  content:"";position:fixed;border-radius:50%;filter:blur(60px);
  opacity:.5;z-index:0;pointer-events:none;
}
.stApp::before{width:260px;height:260px;background:var(--pink);top:-60px;left:-40px;animation:float 14s ease-in-out infinite;}
.stApp::after{width:300px;height:300px;background:var(--blue);bottom:-80px;right:-60px;animation:float 14s ease-in-out -5s infinite;}
@keyframes float{
  0%,100%{transform:translateY(0) scale(1);}
  50%{transform:translateY(-30px) scale(1.08);}
}

/* 主内容区置于光晕之上 */
.block-container{position:relative;z-index:1;max-width:760px;padding-top:2.2rem;}
[data-testid="stSidebar"]{position:relative;z-index:2;background:rgba(251,248,243,.92) !important;}

/* ===== 顶部信息卡 ===== */
.cdut-header{
  display:flex;align-items:center;gap:14px;padding:18px 22px;
  background:linear-gradient(120deg,var(--pink),var(--blue));
  color:#fff;border-radius:20px;box-shadow:0 10px 30px rgba(92,85,76,.18);
  margin-bottom:6px;animation:cardIn .8s cubic-bezier(.22,1,.36,1);
}
.cdut-avatar{
  width:48px;height:48px;display:flex;align-items:center;justify-content:center;
  font-size:26px;background:rgba(255,255,255,.25);border-radius:14px;
  animation:pulse 3s ease-in-out infinite;
}
@keyframes pulse{0%,100%{transform:scale(1);}50%{transform:scale(1.08);}}
.cdut-titlebox{flex:1;}
.cdut-title{font-size:20px;font-weight:700;letter-spacing:1px;}
.cdut-subtitle{font-size:12px;opacity:.9;margin-top:2px;}
.cdut-status{
  display:flex;align-items:center;gap:6px;font-size:12px;
  background:rgba(255,255,255,.2);padding:5px 12px;border-radius:20px;
}
.cdut-dot{width:8px;height:8px;background:#eaf2d8;border-radius:50%;animation:blink 1.6s ease-in-out infinite;}
@keyframes blink{0%,100%{opacity:1;}50%{opacity:.3;}}

/* ===== 聊天气泡 ===== */
.msg{display:flex;margin:6px 0;animation:msgIn .45s cubic-bezier(.22,1,.36,1);}
.msg.user{justify-content:flex-end;}
.msg.assistant{justify-content:flex-start;}
@keyframes msgIn{from{opacity:0;transform:translateY(12px);}to{opacity:1;transform:translateY(0);}}
.bubble{
  max-width:82%;padding:12px 16px;font-size:15px;line-height:1.7;
  border-radius:16px;color:var(--text);
  box-shadow:0 4px 14px rgba(92,85,76,.08);
}
.bubble.assistant{background:#fff;border:1px solid var(--border);border-top-left-radius:6px;}
.bubble.user{background:var(--purple);color:#fff;border-top-right-radius:6px;}
.bubble p{margin:0 0 6px;}
.bubble p:last-child{margin:0;}
.bubble ul,.bubble ol{margin:4px 0;padding-left:20px;}
.bubble li{margin:2px 0;}
.bubble code{background:rgba(92,85,76,.1);padding:1px 5px;border-radius:4px;font-size:.9em;}
.bubble.user code{background:rgba(255,255,255,.2);}
.bubble h3,.bubble h4,.bubble h5{margin:8px 0 4px;}

/* 工具调用过程（可折叠） */
.trace{margin-top:10px;font-size:12px;}
.trace summary{cursor:pointer;color:var(--text-light);opacity:.85;}
.trace ul{margin:6px 0 0;padding-left:18px;color:var(--text-light);}
.bubble.user .trace summary,.bubble.user .trace ul{color:rgba(255,255,255,.85);}

/* ===== 输入框 ===== */
[data-testid="stChatInput"]{
  background:#fff !important;border:1.5px solid var(--border) !important;
  border-radius:24px;padding:6px 8px;box-shadow:0 6px 20px rgba(92,85,76,.08);
}
[data-testid="stChatInput"]:focus-within{
  border-color:var(--blue) !important;box-shadow:0 0 0 4px rgba(159,182,192,.18);
}
/* 输入文字用深色，占位符用浅灰 */
[data-testid="stChatInput"] textarea{
  color:var(--text) !important;
  caret-color:var(--text) !important;
  background:transparent !important;
}
[data-testid="stChatInput"] textarea::placeholder{
  color:var(--text-light) !important;
  opacity:1 !important;
}
/* 发送键按钮改成莫兰迪蓝，去掉默认红色 */
[data-testid="stChatInputSubmitButton"],
[data-testid="stChatInputSubmitButton"] button{
  background:var(--blue) !important;
  color:#fff !important;
}

/* ===== 侧边栏按钮（莫兰迪胶囊） ===== */
[data-testid="stSidebar"] .stButton>button{
  border:1px solid var(--border);border-radius:20px;background:var(--mbg1);
  color:var(--text);font-size:13px;transition:all .25s ease;
}
[data-testid="stSidebar"] .stButton>button:hover{
  transform:translateY(-2px);background:var(--blue);color:#fff;
  border-color:var(--blue);box-shadow:0 6px 14px rgba(92,85,76,.16);
}
[data-testid="stSidebar"] h1,[data-testid="stSidebar"] h2,[data-testid="stSidebar"] h3{
  color:var(--text);
}
@keyframes cardIn{
  from{opacity:0;transform:translateY(30px) scale(.97);}
  to{opacity:1;transform:translateY(0) scale(1);}
}
</style>
"""


def md_to_html(text: str) -> str:
    """极简 Markdown → HTML：覆盖加粗/斜体/行内代码/标题/列表/链接/换行。"""
    out = []
    in_list = None  # 'ul' | 'ol' | None
    for raw in text.split("\n"):
        line = raw.rstrip()
        s = html.escape(line)

        # 行内代码（先处理，避免被后续替换影响）
        s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
        # 加粗
        s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
        # 斜体
        s = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"<em>\1</em>", s)
        # 链接 [text](url) —— 仅允许 http/https
        s = re.sub(
            r"\[([^\]]+)\]\((https?://[^)\s]+)\)",
            r'<a href="\2" target="_blank">\1</a>',
            s,
        )
        # 标题
        m = re.match(r"^(#{1,4})\s+(.*)", s)
        if m:
            lvl = min(len(m.group(1)) + 2, 6)
            if in_list:
                out.append(f"</{in_list}>")
                in_list = None
            out.append(f"<h{lvl}>{m.group(2)}</h{lvl}>")
            continue
        # 无序列表
        m = re.match(r"^[-*•]\s+(.*)", s)
        if m:
            if in_list != "ul":
                if in_list:
                    out.append(f"</{in_list}>")
                out.append("<ul>")
                in_list = "ul"
            out.append(f"<li>{m.group(1)}</li>")
            continue
        # 有序列表
        m = re.match(r"^\d+[.)]\s+(.*)", s)
        if m:
            if in_list != "ol":
                if in_list:
                    out.append(f"</{in_list}>")
                out.append("<ol>")
                in_list = "ol"
            out.append(f"<li>{m.group(1)}</li>")
            continue
        # 非列表内容：先闭合列表
        if in_list:
            out.append(f"</{in_list}>")
            in_list = None
        if not line.strip():
            out.append("")
            continue
        out.append(f"<p>{s}</p>")
    if in_list:
        out.append(f"</{in_list}>")
    return "\n".join(out)


def new_session():
    sid = datetime.datetime.now().strftime("%Y%m%d%H%M%S%f")
    st.session_state.sessions[sid] = {
        "title": "新对话",
        "created_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "messages": [],
    }
    return sid


def format_tool_call(t):
    name = t["tool"]
    label = TOOL_LABELS.get(name, name)
    args = t.get("args") or {}
    if args:
        detail = "，".join(f"{k}={v}" for k, v in args.items())
        return f"{label}（{detail}）"
    return label


def format_conversation(messages):
    lines = []
    for m in messages:
        role = "我" if m["role"] == "user" else "成理小助手"
        lines.append(f"【{role}】")
        lines.append(m["content"])
        lines.append("")
    return "\n".join(lines)


def render_bubble(role: str, content: str, trace=None):
    """渲染一条消息为莫兰迪气泡。"""
    body = md_to_html(content)
    trace_html = ""
    if trace:
        items = "".join(
            f"<li>{html.escape(format_tool_call(t))}</li>" for t in trace
        )
        trace_html = (
            f'<details class="trace"><summary>🔧 查看工具调用过程</summary>'
            f"<ul>{items}</ul></details>"
        )
    st.markdown(
        f'<div class="msg {role}"><div class="bubble {role}">{body}{trace_html}</div></div>',
        unsafe_allow_html=True,
    )


def render_canteen_images(trace=None):
    """在回答下方展示命中的食堂档口配图（若有）。"""
    if not trace:
        return
    base_dir = os.path.dirname(os.path.abspath(__file__))
    for t in trace:
        tool = t.get("tool") or ""
        if tool != "search_canteen" and not tool.startswith("canteen"):
            continue
        imgs = t.get("images") or []
        if not imgs:
            continue
        cols = st.columns(len(imgs))
        for col, im in zip(cols, imgs):
            path = os.path.join(base_dir, im["image"])
            with col:
                st.image(path, caption=im["name"], width=220)


def render_chat(client):
    """智能问答视图：现有聊天流程。"""
    cur_sess = st.session_state.sessions[st.session_state.current_id]
    messages = cur_sess["messages"]

    for msg in messages:
        render_bubble(msg["role"], msg["content"], msg.get("trace"))
        if msg["role"] == "assistant":
            render_canteen_images(msg.get("trace"))

    prompt = st.chat_input("请输入你的问题，例如：宿舍怎么分配？") or st.session_state.pop(
        "pending_question", None
    )

    if prompt:
        messages.append({"role": "user", "content": prompt})
        render_bubble("user", prompt)

        with st.spinner("思考中..."):
            clean_msgs = [{"role": m["role"], "content": m["content"]} for m in messages]
            try:
                content, trace = chat_with_trace(clean_msgs, client)
            except Exception as e:
                name = type(e).__name__
                if "Timeout" in name or "timeout" in str(e).lower():
                    content = "回答超时了，可能是服务暂时繁忙。请稍等几秒再点一次发送重试～"
                else:
                    content = f"出错了：{e}\n\n请检查 config.py 里的接口地址、API Key 和模型名称是否正确。"
                trace = []

        render_bubble("assistant", content, trace)
        render_canteen_images(trace)
        messages.append({"role": "assistant", "content": content, "trace": trace})

        if cur_sess["title"] == "新对话":
            first_user = next((m["content"] for m in messages if m["role"] == "user"), "")
            if first_user:
                cur_sess["title"] = first_user[:16]

        st.rerun()


# ============ 失物招领 ============

STATUS_LABEL = {"open": "🟡 待处理", "matched": "🟢 已匹配", "resolved": "✅ 已找回"}


def _do_insert(data: dict):
    token = lost_found.generate_token()
    data["secret_token"] = token
    try:
        row = lost_found.insert_post(data)
        return True, None, row
    except Exception as e:
        return False, str(e), None


def _render_voice_publish(client):
    st.markdown("**💬 用一句话描述**：智能体自动提取并帮你发布。")
    draft_text = st.text_input("例如：我在图书馆三楼丢了校园卡，蓝色卡套", key="lf_voice")
    if st.button("🔍 智能提取", key="lf_extract"):
        if not draft_text.strip():
            st.warning("先输入一句话描述。")
        else:
            with st.spinner("提取中..."):
                data = extract_lostfound(draft_text, client)
            if data and data.get("type") in ("lost", "found"):
                st.session_state.lf_draft = data
                st.rerun()
            else:
                st.error("没提取成功，请换用下方表单。")

    draft = st.session_state.get("lf_draft")
    if draft:
        with st.container(border=True):
            kind = "🔍 寻物" if draft.get("type") == "lost" else "📌 拾到"
            st.markdown(f"**{kind}（提取结果，确认后发布）**")
            st.markdown(f"- 物品：{draft.get('item_type') or '未识别'}")
            st.markdown(f"- 标题：{draft.get('title') or '（未命名）'}")
            st.markdown(f"- 地点：{draft.get('location') or '未注明'}")
            st.markdown(f"- 时间：{draft.get('lost_time') or '未注明'}")
            st.markdown(f"- 联系方式：{draft.get('contact') or '未注明'}")
            if draft.get("description"):
                st.markdown(f"- 描述：{draft['description']}")
            c_ok, c_cancel = st.columns([1, 1])
            if c_ok.button("✅ 确认发布", key="lf_confirm"):
                payload = {
                    "type": draft.get("type"),
                    "item_type": draft.get("item_type") or "其他",
                    "title": draft.get("title") or "未命名物品",
                    "description": draft.get("description") or "",
                    "location": draft.get("location") or "",
                    "lost_time": draft.get("lost_time") or "",
                    "contact": draft.get("contact") or "",
                    "secret_question": "",
                    "secret_answer": "",
                    "status": "open",
                }
                ok, err, row = _do_insert(payload)
                if ok:
                    st.session_state.pop("lf_draft", None)
                    st.session_state.setdefault("lf_tokens", {})[row["id"]] = payload["secret_token"]
                    st.session_state.lf_last_token = payload["secret_token"]
                    st.rerun()
                else:
                    st.error(f"发布失败：{err}")
            if c_cancel.button("取消", key="lf_cancel"):
                st.session_state.pop("lf_draft", None)
                st.rerun()


def _render_form_publish():
    with st.form("lf_form"):
        type_label = st.radio("类型", ["寻物启事（我丢了）", "拾到物品（我捡到了）"], horizontal=True)
        item_type = st.selectbox("物品类型", lost_found.ITEM_TYPES)
        title = st.text_input("物品名称/标题", placeholder="如：校园卡")
        location = st.text_input("地点", placeholder="如：图书馆三楼")
        lost_time = st.text_input("时间", placeholder="如：今天下午")
        contact = st.text_input("联系方式", placeholder="手机/微信，认领时用")
        description = st.text_area("描述", placeholder="颜色、特征等，越具体越容易匹配")
        is_found = type_label.startswith("拾到")
        secret_q, secret_a = "", ""
        if is_found:
            st.markdown("**防冒领（可选）**：设一个只有失主答得上来的问题")
            secret_q = st.text_input("验证问题", placeholder="如：卡背面贴了什么图案？")
            secret_a = st.text_input("答案", placeholder="如：小恐龙贴纸")
        submitted = st.form_submit_button("发布", use_container_width=True)

    if submitted:
        if not title.strip():
            st.warning("至少填一个物品名称。")
        else:
            payload = {
                "type": "found" if is_found else "lost",
                "item_type": item_type,
                "title": title.strip(),
                "description": description.strip(),
                "location": location.strip(),
                "lost_time": lost_time.strip(),
                "contact": contact.strip(),
                "secret_question": secret_q.strip(),
                "secret_answer": secret_a.strip(),
                "status": "open",
            }
            ok, err, row = _do_insert(payload)
            if ok:
                st.session_state.setdefault("lf_tokens", {})[row["id"]] = payload["secret_token"]
                st.session_state.lf_last_token = payload["secret_token"]
                st.rerun()
            else:
                st.error(f"发布失败：{err}")


def _render_post_card(p):
    kind = "🔍 寻物" if p.get("type") == "lost" else "📌 拾到"
    status = STATUS_LABEL.get(p.get("status"), p.get("status"))
    with st.container(border=True):
        st.markdown(f"{kind}　**{p.get('title')}**　`{p.get('item_type')}`　{status}")
        meta = []
        if p.get("location"):
            meta.append(f"📍 {p['location']}")
        if p.get("lost_time"):
            meta.append(f"🕐 {p['lost_time']}")
        if meta:
            st.caption("　".join(meta))
        if p.get("description"):
            st.markdown(p["description"])

        if p.get("type") == "found" and p.get("secret_question"):
            with st.expander("🔐 认领（回答验证问题解锁联系方式）"):
                ans = st.text_input("你的答案", key=f"claim_{p['id']}")
                if ans:
                    if ans.strip() == (p.get("secret_answer") or "").strip():
                        st.success(f"验证通过！联系方式：{p.get('contact') or '（未留）'}")
                        st.caption("双方确认后可点下方「标记已找回」。")
                    else:
                        st.warning("答案不对，再想想～")
        elif p.get("contact"):
            st.caption(f"📞 联系方式：{p['contact']}")

        if p.get("status") != "resolved":
            _render_manage_area(p)


def _render_manage_area(p):
    """发布者口令门控：只有知道口令的人能管理这条帖子（标记匹配/找回/确认）。"""
    pid = p["id"]
    tokens = st.session_state.setdefault("lf_tokens", {})
    authed = tokens.get(pid) == (p.get("secret_token") or "")

    if not authed:
        with st.expander("🔑 我是发布者，管理这条帖子"):
            st.caption("发布时下发的 6 位数字口令。演示示例数据统一为 123456。")
            entered = st.text_input("发布口令", key=f"token_{pid}", placeholder="6 位数字口令")
            if st.button("验证", key=f"tokengate_{pid}"):
                if entered.strip() == (p.get("secret_token") or "").strip():
                    tokens[pid] = entered.strip()
                    st.success("口令正确，现在可以管理这条帖子了。")
                    st.rerun()
                else:
                    st.error("口令不对。")
        return

    if p.get("status") == "open":
        with st.expander("🔍 智能匹配"):
            matches = lost_found.find_matches(p)
            if not matches:
                st.caption("暂未找到疑似匹配，可稍后刷新。")
            for m in matches:
                mp = m["post"]
                with st.container(border=True):
                    st.markdown(
                        f"**{mp.get('title')}**（{mp.get('item_type')}）　置信度 `{m['confidence']}%`"
                    )
                    for r in m["reasons"]:
                        st.caption(f"· {r}")
                    if mp.get("location"):
                        st.caption(f"📍 {mp['location']}")
                    if mp.get("contact"):
                        st.caption(f"📞 {mp['contact']}")
                    if st.button("✅ 标记双方已匹配", key=f"match_{pid}_{mp['id']}"):
                        try:
                            lost_found.update_post(pid, {"status": "matched", "matched_with": mp["id"]})
                            lost_found.update_post(mp["id"], {"status": "matched", "matched_with": pid})
                            st.session_state.lf_announcement = (
                                f"🔔 成理小助手已为「{p.get('title')}」和「{mp.get('title')}」牵线成功，"
                                f"双方可互看联系方式联系认领～"
                            )
                            st.rerun()
                        except Exception as e:
                            st.error(f"失败：{e}")

        if st.button("✅ 标记已找回", key=f"resolve_{pid}"):
            try:
                lost_found.update_post(pid, {"status": "resolved"})
                st.rerun()
            except Exception as e:
                st.error(f"失败：{e}")

    elif p.get("status") == "matched":
        if p.get("confirmed"):
            st.caption("本方已确认 ✅，等待对方确认")
        else:
            confirm_label = "✅ 失主确认：已拿回" if p.get("type") == "lost" else "✅ 拾到者确认：已交还"
            if st.button(confirm_label, key=f"confirm_{pid}"):
                try:
                    msg, both = lost_found.confirm_and_resolve(pid)
                    if both:
                        st.session_state.lf_announcement = "🎉 双方确认完成，物品已找回！"
                    st.rerun()
                except Exception as e:
                    st.error(f"失败：{e}")


def _render_feed():
    f_type = st.radio("筛选", ["全部", "寻物", "拾到"], horizontal=True, key="lf_filter")
    type_map = {"全部": None, "寻物": "lost", "拾到": "found"}
    posts = lost_found.list_posts(type_filter=type_map[f_type], status_filter=None, limit=100)
    if not posts:
        st.info("频道还没有帖子，去发布一条吧，或用「演示模式」灌入示例数据。")
        return
    st.caption(f"共 {len(posts)} 条")
    for p in posts:
        _render_post_card(p)


def render_lost_found(client):
    st.markdown("#### 📦 失物招领 · 共享频道")

    if not lost_found.is_configured():
        st.warning("Supabase 还没配置，失物招领暂时不可用。")
        st.markdown(
            "**三步配置**\n"
            "1. 到 [supabase.com](https://supabase.com) 建一个免费项目。\n"
            "2. 打开项目 **SQL Editor**，把 `supabase_schema.sql` 的内容粘进去执行一次。\n"
            "3. 在 **Settings → API** 复制 `Project URL` 和 `anon public` key，填到 "
            "`.streamlit/secrets.toml`（本地）或 Streamlit Cloud 的 Secrets（云端）："
        )
        st.code(
            'SUPABASE_URL = "https://xxxx.supabase.co"\n'
            'SUPABASE_ANON_KEY = "eyJ..."',
            language="toml",
        )
        return

    if st.session_state.get("lf_last_token"):
        st.markdown(
            '<div style="padding:14px 16px;border-radius:12px;background:#fff7e0;'
            'border:1px solid #f0d9a0;color:#5c554c;font-size:15px;">'
            "✅ 发布成功！你的<strong>发布口令</strong>是 "
            f'<code style="font-size:20px;font-weight:700;letter-spacing:2px;">{html.escape(st.session_state.lf_last_token)}</code>'
            "<br><span style='font-size:13px;color:#8a8075;'>记下它——之后「标记找回 / 双方确认」管理这条帖子要用，"
            "不知道口令的人点不了管理按钮。换新帖子发布时会自动更新。</span></div>",
            unsafe_allow_html=True,
        )
        if st.button("我已记下", key="lf_dismiss_token"):
            st.session_state.pop("lf_last_token", None)
            st.rerun()
        st.write("")

    if st.session_state.get("lf_announcement"):
        st.markdown(
            '<div style="padding:12px 16px;border-radius:12px;background:#eaf2d8;'
            'border:1px solid #c8d9b0;color:#5c554c;font-size:14px;">'
            + html.escape(st.session_state.lf_announcement)
            + "</div>",
            unsafe_allow_html=True,
        )
        if st.button("清除公告", key="lf_clear_announce"):
            st.session_state.pop("lf_announcement", None)
            st.rerun()
        st.write("")

    if st.session_state.get("lf_tokens"):
        with st.expander("🔑 我的发布口令（本机会话内记住）"):
            for pid, tok in st.session_state.lf_tokens.items():
                st.write(f"口令 `{tok}`（帖子 id 尾号 …{str(pid)[-4:]}）")

    c1, c2 = st.columns([1, 1])
    if c1.button("🔄 演示模式：重置示例数据", use_container_width=True):
        with st.spinner("重置中..."):
            try:
                n = lost_found.seed_demo()
                st.success(f"已重置并灌入 {n} 条示例数据")
            except Exception as e:
                st.error(f"失败：{e}")
        st.rerun()
    with c2.expander("📍 失物高发点"):
        hot = lost_found.hot_locations()
        if hot:
            for loc, cnt in hot[:6]:
                st.write(f"**{loc}** · {cnt} 条")
        else:
            st.caption("暂无数据")

    st.divider()

    st.markdown("#### ✍️ 发布信息")
    pub_chat, pub_form = st.tabs(["💬 口语发布", "📋 表单发布"])
    with pub_chat:
        _render_voice_publish(client)
    with pub_form:
        _render_form_publish()

    st.divider()

    st.markdown("#### 📋 频道")
    _render_feed()


def _render_kaoyan_customizer():
    """考研个性化定制：收集几个信息，生成专属考研复习计划。"""
    with st.expander("🎓 考研个性化定制", expanded=False):
        st.caption("填几个信息，帮你生成专属考研复习计划")
        grade = st.selectbox("年级", ["大一", "大二", "大三", "大四"], key="ky_grade")
        major = st.text_input("专业", placeholder="如：计算机科学与技术", key="ky_major")
        target = st.text_input("目标院校 / 方向", placeholder="如：电子科技大学 · 计算机", key="ky_target")
        cross = st.radio("是否跨考", ["本专业", "跨考"], horizontal=True, key="ky_cross")
        hours = st.selectbox(
            "每天可学习时长", ["2 小时以内", "3-4 小时", "5-6 小时", "6 小时以上"], key="ky_hours"
        )
        if st.button("生成定制计划", use_container_width=True, key="ky_submit"):
            if not target.strip():
                st.warning("至少填一下目标院校/方向。")
            else:
                q = (
                    f"我想考研，请帮我做一份个性化考研定制计划。我的情况：{grade}，"
                    f"{major.strip() or '未填'}专业，{cross}，目标院校/方向是{target.strip()}，"
                    f"每天大约能学{hours}。请按择校、公共课、专业课、报名、初试、复试分阶段定制，"
                    f"公共课和专业课分科给重点，并给作息建议。"
                )
                st.session_state.pending_question = q
                st.session_state.view = "chat"
                st.rerun()


def _render_about():
    """侧边栏：智能体能力介绍。"""
    with st.expander("📖 关于成理小助手"):
        st.markdown(
            "**成理小助手**是面向成都理工大学同学的校园智能体，专注几件事：\n\n"
            "- 🏫 **校园生活**：报到、军训、选课、宿舍等 FAQ\n"
            "- 🍜 **食堂攻略**：芙蓉餐厅档口、轻食、按预算推荐\n"
            "- 🎓 **保研/考研规划**：分阶段规划、个性化定制\n"
            "- 📦 **失物招领**：共享频道发布、浏览、智能匹配\n"
            "- 🗺️ **校园导览** · 🌤️ **天气** · 🎪 **活动**"
        )


st.set_page_config(page_title="成理小助手", page_icon="🎓", layout="centered")
st.markdown(MORANDI_CSS, unsafe_allow_html=True)

# ============ 状态初始化（每个访问者独立，仅内存，不写共享文件） ============
if "sessions" not in st.session_state:
    st.session_state.sessions = {}
    st.session_state.current_id = new_session()
if "view" not in st.session_state:
    st.session_state.view = "chat"

client = get_client()

# ============ 侧边栏 ============
with st.sidebar:
    st.markdown(
        '<div class="cdut-header" style="border-radius:14px;padding:14px 16px;">'
        '<div class="cdut-avatar" style="width:40px;height:40px;font-size:22px;">🎓</div>'
        '<div class="cdut-titlebox"><div class="cdut-title" style="font-size:17px;">成理小助手</div>'
        '<div class="cdut-subtitle">校园智能服务 · Agent</div></div></div>',
        unsafe_allow_html=True,
    )
    st.write("")

    if st.button("➕ 新建对话", use_container_width=True):
        st.session_state.current_id = new_session()
        st.session_state.view = "chat"
        st.rerun()

    st.divider()

    _render_kaoyan_customizer()

    st.divider()

    st.subheader("📚 历史会话")
    if not st.session_state.sessions:
        st.caption("暂无历史会话")
    else:
        sids = sorted(
            st.session_state.sessions.keys(),
            key=lambda k: st.session_state.sessions[k].get("created_at", ""),
            reverse=True,
        )
        for sid in sids:
            sess = st.session_state.sessions[sid]
            title = sess.get("title", "新对话")
            mark = "● " if sid == st.session_state.current_id else "○ "
            col1, col2 = st.columns([5, 1])
            if col1.button(mark + title[:14], key=f"switch_{sid}", use_container_width=True):
                st.session_state.current_id = sid
                st.session_state.view = "chat"
                st.rerun()
            if col2.button("🗑", key=f"del_{sid}", help="删除该会话"):
                del st.session_state.sessions[sid]
                if st.session_state.current_id == sid:
                    remaining = sorted(
                        st.session_state.sessions.keys(),
                        key=lambda k: st.session_state.sessions[k].get("created_at", ""),
                        reverse=True,
                    )
                    st.session_state.current_id = remaining[0] if remaining else new_session()
                st.rerun()

    st.divider()

    st.subheader("⚡ 快捷提问")
    for q in PRESET_QUESTIONS:
        if st.button(q, key=f"preset_{q}", use_container_width=True):
            st.session_state.pending_question = q
            st.session_state.view = "chat"
            st.rerun()

    st.divider()

    _render_about()

    st.divider()

    st.subheader("💾 导出对话")
    cur_sess = st.session_state.sessions[st.session_state.current_id]
    if cur_sess["messages"]:
        st.download_button(
            "下载当前对话",
            data=format_conversation(cur_sess["messages"]),
            file_name=f"对话记录_{cur_sess['title'][:10]}.txt",
            mime="text/plain",
            use_container_width=True,
        )
    else:
        st.caption("当前对话为空")

# ============ 主区 ============
st.markdown(
    '<div class="cdut-header">'
    '<div class="cdut-avatar">🎓</div>'
    '<div class="cdut-titlebox"><div class="cdut-title">成理校园助手</div>'
    '<div class="cdut-subtitle">成都理工大学 · 校园智能体</div></div>'
    '<span class="cdut-status"><span class="cdut-dot"></span>在线</span></div>',
    unsafe_allow_html=True,
)

if client is None:
    st.warning("还没有配置 API Key。请打开 `config.py`，把密钥填进 `API_KEY`，再重新运行。")
    st.stop()

view = st.segmented_control(
    "功能", ["💬 智能问答", "📦 失物招领"], default="💬 智能问答", label_visibility="collapsed"
)
view = view or "💬 智能问答"

if view == "💬 智能问答":
    render_chat(client)
else:
    render_lost_found(client)
