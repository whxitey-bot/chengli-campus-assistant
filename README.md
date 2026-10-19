# 校园智能助手「成理小助手」

面向成都理工大学学生的校园智能体。基于大模型 + 知识库检索（RAG）+ 意图路由，随时解答报到、宿舍、食堂、选课、军训等校园问题，并提供校园活动查询、文化导览、学习规划、天气查询等服务。

> 参赛主题：AI 赋能校园，智创应用未来

## 项目结构

```
campus_agent/
├── app.py                 # Streamlit 网页聊天界面（莫兰迪配色 + 动效）
├── agent.py               # 智能体核心：意图识别 → 检索 → 大模型生成
├── config.py              # 配置：网关地址、API Key（从 Secrets 读取）、模型名
├── knowledge_base.py      # 知识库加载 + 关键词检索 + 导览路线
├── knowledge_base/
│   ├── faq.json           # 校园常见问题数据
│   └── activities.json    # 校园活动数据
├── skills/                # 分场景 SOP 说明文档（报到/军训/选课/导览）
├── .streamlit/secrets.toml.example  # 密钥示例（真实密钥放 secrets.toml，不入库）
├── requirements.txt       # 依赖
└── README.md
```

## 本地运行

### 1. 安装依赖（只需一次）

```bash
pip install -r requirements.txt
```

### 2. 配置 API Key

复制 `.streamlit/secrets.toml.example` 为 `.streamlit/secrets.toml`，把真实密钥填进去：

```toml
API_KEY = "sk-你的真实密钥"
```

### 3. 启动应用

```bash
streamlit run app.py
```

浏览器打开 `http://localhost:8501` 即可对话。

## 部署到 Streamlit Cloud（免费，永久 URL）

拿到别人（评委）能访问的永久链接，用 Streamlit Cloud 免费托管即可：

### 第 1 步：把代码推到 GitHub

1. 在 GitHub 新建一个 **Public** 仓库（不要勾选初始化 README）。
2. 本地执行：

```bash
git init
git add .
git commit -m "成理小助手：校园智能体"
git branch -M main
git remote add origin https://github.com/<你的用户名>/<仓库名>.git
git push -u origin main
```

### 第 2 步：在 Streamlit Cloud 部署

1. 打开 <https://share.streamlit.io>，用 GitHub 账号登录。
2. 点 **New app** → 选择刚才的仓库、分支 `main`、主文件填 `app.py`。
3. 点 **Deploy**，等待部署完成。

### 第 3 步：填入 API Key（Secret）

1. 进入应用的 **Settings → Secrets**。
2. 填一行（密钥不放仓库，防止公开泄漏）：

```toml
API_KEY = "sk-你的真实密钥"
```

3. 保存后应用会自动重启。

部署完成后，你会得到一个 `https://<仓库名>.streamlit.app` 的**永久 URL**，直接填到比赛作品的「可访问链接」即可。

## 能力说明

- **知识库检索**：`search_faq` 从真实校园数据中检索答案，严格基于检索结果回答、不编造
- **校园活动**：`search_activity` 查询校运会、音乐节、讲座等活动（时间 + 地点 + 亮点）
- **文化导览**：`campus_tour` 返回 8 站经典游览路线，带逛校园地标
- **学习规划**：按专业/年级/目标生成分阶段学习计划（阶段 + 周目标 + 每日任务 + 作息）
- **天气查询**：`get_weather` 查询成都/宜宾当前天气与 3 天预报（Open-Meteo 免费接口）
- **当前时间**：`get_current_time` 获取当前时间
- **多轮对话**：保留上下文，支持追问和澄清
- **分场景 SOP**：系统提示词内置报到/军训/选课/活动/导览/学习规划六个标准应答流程

> 架构说明：比赛网关的 `dsv4` 模型不支持 function calling，因此采用「规则意图识别 → 工具检索 → 大模型生成」的本地工作流，既可靠又不依赖模型的工具调用能力，同时从源头防止模型编造校园信息。

## 配置说明（config.py）

| 字段 | 含义 | 默认值 |
|------|------|--------|
| `BASE_URL` | 模型网关地址 | `http://sagalcc.cn:3002/v1` |
| `API_KEY` | 访问凭证（从 Secrets/环境变量读取） | 空，需自行填写 |
| `MODEL` | 模型名 | `dsv4` |
| `SCHOOL_NAME` | 学校名 | 成都理工大学 |

> 想改成别的学校？只需改 `SCHOOL_NAME`，并替换 `knowledge_base/faq.json` 和 `activities.json` 里的数据即可。
