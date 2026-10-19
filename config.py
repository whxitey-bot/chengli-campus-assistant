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
