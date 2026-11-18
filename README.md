# kb-agent

> 从零手写的知识库问答 Agent，用于求职展示的端到端 RAG 工程。

**当前状态：W1 工程底座完成**（配置 / HTTP 客户端 / 语料扫描 / LLM 最小调用），W2 起接入检索与生成链路。

## 目标形态

上传文档 → 解析切分 → 混合检索（向量 + BM25）+ rerank → 带引用的问答 → 工具调用与人机确认 → 流式接口与鉴权 → 一条命令起服务。

> 以上是**路线图**，尚未全部实现。下面「已实现」一节只列当前真正跑得通的部分。

## 当前已实现

| 模块 | 文件 | 说明 |
|---|---|---|
| 配置 | app/config.py | pydantic-settings，SecretStr 保存密钥，缺 key 或越界值在启动时即报错 |
| HTTP | app/http_client.py | 两段超时、429/5xx 指数退避重试（含抖动）、4xx 快速失败、非 JSON 响应给出可读错误 |
| 语料 | app/manifest.py | 扫描 data/raw，输出文件名 / 大小 / 占比清单 |
| LLM | app/ask.py | DeepSeek API 最小调用，打印 token 用量 |
| 测试 | tests/ | 21 个单元测试，全部通过，约 0.4s |

## 快速开始

    git clone git@github.com:dongdong0v0/kb-agent.git
    cd kb-agent
    uv sync
    cp .env.example .env
    uv run pytest -q
    uv run python -m app.manifest
    uv run python -m app.ask "什么是 RAG"

填写 DEEPSEEK_API_KEY 后即可运行，其余配置项有默认值。

## 目录结构

    kb-agent/
    ├── app/
    │   ├── config.py        # 配置（唯一来源）
    │   ├── http_client.py   # 带重试的 HTTP 客户端
    │   ├── manifest.py      # 语料扫描
    │   ├── ask.py           # LLM 最小调用
    │   └── hello.py         # 环境自检
    ├── tests/               # 单元测试
    ├── data/raw/            # 原始语料（不入库）
    └── 配置模板文件

## 几个设计取舍

**配置用 pydantic-settings 而不是手写解析。** 手写版遇到「值里含等号」会截断、没有类型、缺字段要等到运行时才炸。换成声明式配置后，缺 key、类型错、超出范围都在启动阶段就报错。

**重试策略写成纯函数 should_retry(status)。** 集合写死也能跑，但「什么值得重试」是一条会变的规则：408 该不该重试、403 的某些情况要不要特判。做成函数后能单测、能扩展，规则只有一个真相来源。

**测试注入 session 与 policy，不真发网络请求。** get_json() 接受 session 参数，测试时传假对象，所以 21 个测试 0.4 秒跑完，且不依赖外部服务是否可用。

**统一用 python -m app.xxx 运行。** 直接跑文件路径时 sys.path 是脚本所在目录，包内导入会失败；-m 把项目根加入搜索路径，避免大量 ModuleNotFoundError。

## 路线图

| 周 | 内容 | 状态 |
|---|---|---|
| W1 | 工程底座：配置、HTTP、测试、提交规范 | 完成 |
| W2 | LLM 客户端：流式、重试、成本统计、结构化输出 | 进行中 |
| W3 | 文档解析与切分（PDF → 文本 → 块） | 计划 |
| W4 | 向量化与检索（向量 / BM25 / 混合 + rerank） | 计划 |
| W5 | 评测体系：50 题评测集、hit rate、faithfulness | 计划 |
| W6 | Agent 与工具调用、HITL | 计划 |
| W7 | FastAPI 服务化 + SSE 流式 | 计划 |
| W8 | 交付化：Docker、内网部署、权限 | 计划 |
| W9-W10 | 集成、打磨、评测报告、演示材料 | 计划 |
| W11 | 简历与投递 | 计划 |

## 环境要求

- Python 3.10+
- uv
- 一个 DeepSeek API key（platform.deepseek.com）

## 作者

李东平 · 2027 届 · 目标岗位：AI 应用开发 / FDE
