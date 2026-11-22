# kb-agent

> 从零手写的知识库问答 Agent，用于求职展示的端到端 RAG 工程。

**当前状态：W2 LLM 调用层完成**（LLM 客户端 / 流式输出 / 成本统计 / 结构化输出 / 成功率评测），W3 起接入文档解析与切分。

## 目标形态

上传文档 → 解析切分 → 混合检索（向量 + BM25）+ rerank → 带引用的问答 → 工具调用与人机确认 → 流式接口与鉴权 → 一条命令起服务。

> 以上是**路线图**，尚未全部实现。下面「已实现」一节只列当前真正跑得通的部分。

## 当前已实现

| 模块 | 文件 | 说明 |
|---|---|---|
| 配置 | app/config.py | pydantic-settings，SecretStr 保存密钥，缺 key 或越界值在启动时即报错 |
| HTTP | app/http_client.py | 两段超时、429/5xx 指数退避重试（含抖动）、4xx 快速失败、非 JSON 响应给出可读错误 |
| 语料 | app/manifest.py | 扫描 data/raw，输出文件名 / 大小 / 占比清单 |
| LLM | app/llm.py | 多轮对话、SSE 流式输出、token 与成本统计、会话重置 |
| 结构化输出 | app/structured.py | response_format + pydantic 校验；截断与格式错两类失败分别重试 |
| 评测 | scripts/eval_json.py | 20 题抽样评测结构化输出成功率，报告落盘、退出码表达达标与否 |
| 测试 | tests/ | 34 个单元测试，全部通过，约 0.5s |

## 评测证据

结构化输出（schema 含枚举与列表嵌套）20 题抽样，每题独立会话：

| 场景 | 成功率 | 平均尝试 | 平均耗时 | tokens | 花费 |
|---|---|---|---|---|---|
| 常规 | 20/20 = 100% | 1.0 | 1469ms | 6365 | ¥0.0259 |
| 强制截断（max_tokens=20，压测重试路径） | 20/20 = 100% | 2.0 | 1785ms | 11057 | ¥0.0317 |

复现：

    uv run python scripts/eval_json.py
    uv run python scripts/eval_json.py --force-truncation

原始报告在 `data/eval/json_success_<时间戳>.json`，含每题 attempts / 耗时 / token / 错误文本。

## 快速开始

    git clone git@github.com:dongdong0v0/kb-agent.git
    cd kb-agent
    uv sync
    cp .env.example .env
    uv run pytest -q
    uv run python -m app.manifest
    uv run python -m app.llm          # 多轮流式对话
    uv run python scripts/eval_json.py

填写 DEEPSEEK_API_KEY 后即可运行，其余配置项有默认值。

## 目录结构

    kb-agent/
    ├── app/
    │   ├── config.py        # 配置（唯一来源）
    │   ├── http_client.py   # 带重试的 HTTP 客户端
    │   ├── llm.py           # LLM 客户端：流式 / 成本
    │   ├── structured.py    # 结构化输出与重试
    │   ├── manifest.py      # 语料扫描
    │   └── hello.py         # 环境自检
    ├── scripts/
    │   └── eval_json.py     # 结构化输出成功率评测
    ├── tests/               # 单元测试
    ├── data/raw/            # 原始语料（不入库）
    ├── data/eval/           # 评测报告（入库，作证据）
    └── 配置模板文件

## 几个设计取舍

**配置用 pydantic-settings 而不是手写解析。** 手写版遇到「值里含等号」会截断、没有类型、缺字段要等到运行时才炸。换成声明式配置后，缺 key、类型错、超出范围都在启动阶段就报错。

**重试策略写成纯函数 should_retry(status)。** 集合写死也能跑，但「什么值得重试」是一条会变的规则：408 该不该重试、403 的某些情况要不要特判。做成函数后能单测、能扩展，规则只有一个真相来源。

**测试注入 session 与 policy，不真发网络请求。** get_json() 接受 session 参数，测试时传假对象，所以 34 个测试 0.5 秒跑完，且不依赖外部服务是否可用。

**截断类失败要放大预算，不是原样重试。** 模型被 max_tokens 掐断时，重发同样的预算必然再次截断——这是空转。所以 chat_json 用 finish_reason == "length" 区分两类失败：截断就放大预算（下限 256），格式/schema 错才把校验错误原文回灌让它自纠。

**评测每题新建客户端。** 复用同一个 ChatClient 会让历史不断累积，prompt_tokens 逐题上涨，评测数据就不可比了。独立样本是评测的前提。

**统一用 python -m app.xxx 运行。** 直接跑文件路径时 sys.path 是脚本所在目录，包内导入会失败；-m 把项目根加入搜索路径，避免大量 ModuleNotFoundError。scripts/ 下的脚本则显式把项目根插进 sys.path。

## 路线图

| 周 | 内容 | 状态 |
|---|---|---|
| W1 | 工程底座：配置、HTTP、测试、提交规范 | 完成 |
| W2 | LLM 客户端：流式、重试、成本统计、结构化输出 | 完成 |
| W3 | 文档解析与切分（PDF → 文本 → 块） | 进行中 |
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
