# kb-agent

> 从零手写的知识库问答 Agent，用于求职展示的端到端 RAG 工程。

**当前状态：W1 工程底座完成**（配置 / HTTP 客户端 / 语料扫描 / LLM 最小调用），W2 起接入检索与生成链路。

## 目标形态

上传文档 → 解析切分 → 混合检索（向量 + BM25）+ rerank → 带引用的问答 → 工具调用与人机确认 → 流式接口与鉴权 → 一条命令起服务。

> 以上是**路线图**，尚未全部实现。下面「已实现」一节只列当前真正跑得通的部分。

## 当前已实现

| 模块 | 文件 | 说明 |
|---|---|---|
| 配置 | `app/config.py` | pydantic-settings，`SecretStr` 保存密钥，缺 key 或越界值在启动时即报错 |
| HTTP | `app/http_client.py` | 两段超时、429/5xx 指数退避重试（含抖动）、4xx 快速失败、非 JSON 响应给出可读错误 |
| 语料 | `app/manifest.py` | 扫描 `data/raw`，输出文件名 / 大小 / 占比清单 |
| LLM | `app/ask.py` | DeepSeek API 最小调用，打印 token 用量 |
| 测试 | `tests/` | 21 个单元测试，全部通过，约 0.4s |

## 快速开始

```bash
git clone git@github.com:dongdong0v0/kb-agent.git
cd kb-agent
uv sync
cp .env.example .env DEEPSEEK_API_KEY=你的key
uv run pytest -q
uv run python -m app.manifest
uv run python -m app.ask "什么是 RAG"
