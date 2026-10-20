import os

# 比赛方提供的接口地址
BASE_URL = os.getenv("BASE_URL", "http://sagalcc.cn:3002/v1")

# 模型名称
MODEL = os.getenv("MODEL", "dsv4")

# 学校名称：智能体会以这个身份回答问题
SCHOOL_NAME = os.getenv("SCHOOL_NAME", "成都理工大学")


def _get_secret(name: str) -> str:
    """优先从 Streamlit Secrets 读取（云端部署 / 本地 .streamlit/secrets.toml），其次读环境变量。

    密钥不写死在代码里，避免提交到公开仓库时泄漏。
    """
    try:
        import streamlit as st
        v = st.secrets.get(name)
        if v:
            return str(v)
    except Exception:
        pass
    return os.getenv(name, "")


# API Key：本地运行时填到 .streamlit/secrets.toml；部署时填到 Streamlit Cloud 的 Secrets。
API_KEY = _get_secret("API_KEY")

# Supabase（失物招领共享频道后端）：在 Supabase 项目里复制 URL 和 anon public key 填入。
SUPABASE_URL = _get_secret("SUPABASE_URL")
SUPABASE_ANON_KEY = _get_secret("SUPABASE_ANON_KEY")

# Supabase 代理：本地直连 Supabase 被墙时，填本机代理（如 http://127.0.0.1:7890）；
# 部署到 Streamlit Cloud 时留空即可，云端能直连 Supabase。
SUPABASE_PROXY = _get_secret("SUPABASE_PROXY")
