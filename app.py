"""界面：用 Streamlit 生成聊天页面。运行：streamlit run app.py"""
import datetime
import html
import re

import streamlit as st

import config
from agent import chat_with_trace, get_client

PRESET_QUESTIONS = [
    "新生报到要带哪些材料？",
    "砚湖在哪里？有什么好玩的？",
    "学校有哪些好吃的食堂？",
    "最近学校有什么活动？",
    "能带我逛逛校园吗？",
    "帮我做一个保研学习计划",
    "今天成都天气怎么样？",
]

TOOL_LABELS = {
    "search_faq": "📖 检索知识库",
    "search_activity": "🎪 检索校园活动",
    "campus_tour": "🗺️ 获取导览路线",
    "get_weather": "🌤️ 查询天气",
    "get_current_time": "🕐 获取时间",
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


st.set_page_config(page_title="成理小助手", page_icon="🎓", layout="centered")
st.markdown(MORANDI_CSS, unsafe_allow_html=True)

# ============ 状态初始化（每个访问者独立，仅内存，不写共享文件） ============
if "sessions" not in st.session_state:
    st.session_state.sessions = {}
    st.session_state.current_id = new_session()

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
        st.rerun()

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
                st.rerun()
            if col2.button("🗑", key=f"del_{sid}", help="删除该会话"):
                del st.session_state.sessions[sid]
                if st.session_state.current_id == sid:
                    st.session_state.current_id = None
                st.rerun()

    st.divider()

    st.subheader("⚡ 快捷提问")
    for q in PRESET_QUESTIONS:
        if st.button(q, key=f"preset_{q}", use_container_width=True):
            st.session_state.pending_question = q
            st.rerun()

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

cur_sess = st.session_state.sessions[st.session_state.current_id]
messages = cur_sess["messages"]

# 显示历史消息
for msg in messages:
    render_bubble(msg["role"], msg["content"], msg.get("trace"))

# 处理输入：优先聊天框，其次预设问题
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
            content = f"出错了：{e}\n\n请检查 config.py 里的接口地址、API Key 和模型名称是否正确。"
            trace = []

    render_bubble("assistant", content, trace)
    messages.append({"role": "assistant", "content": content, "trace": trace})

    # 首次问答后，用第一个问题作为会话标题
    if cur_sess["title"] == "新对话":
        first_user = next((m["content"] for m in messages if m["role"] == "user"), "")
        if first_user:
            cur_sess["title"] = first_user[:16]

    st.rerun()
