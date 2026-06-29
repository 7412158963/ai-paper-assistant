# AI Paper Assistant

一个本地运行的 AI 论文阅读与问答助手。项目支持上传 PDF、提取论文文本、切分 chunk、建立本地向量索引，并基于检索结果调用大模型 API 进行论文问答。

## 功能

- PDF 上传：通过网页或 Swagger 上传论文 PDF。
- 文本提取：使用 PyMuPDF 提取 PDF 文本并保存到本地。
- RAG 检索：将论文文本切分为 chunks，并建立本地 JSON 向量索引。
- 论文问答：先检索相关 chunk，再调用 OpenAI-compatible 大模型 API 生成回答。
- 历史论文：页面显示上传过的论文，可以重新选择继续提问。
- 索引状态：显示当前论文是否已上传、已分块、已建索引。
- 问答历史：每篇论文单独保存提问和回答记录。
- 来源引用：回答下方展示来源 chunk，来源片段显示 chunk 编号和相似度。
- 成本保护：限制问题长度、限制 top_k、限制模型输出长度，减少 API 消耗。

## 技术栈

- Python
- FastAPI
- Uvicorn
- PyMuPDF
- httpx
- RAG
- 本地 JSON 向量数据库
- OpenAI-compatible LLM API，例如 DeepSeek
- HTML / CSS / JavaScript

## 项目结构

```text
ai-paper-assistant/
  app/
    main.py
    config.py
    services/
      embedding_service.py
      llm_service.py
      pdf_parser.py
      text_cleaner.py
      text_splitter.py
      vector_store.py
    static/
      index.html
      style.css
      app.js
    storage/
      uploads/
      extracted/
      chunks/
      vector_db/
      qa_history/
  .env.example
  .gitignore
  requirements.txt
  README.md
```

## 运行方式

进入项目目录：

```powershell
cd D:\ai-paper-assistant
```

创建虚拟环境：

```powershell
python -m venv .venv
```

激活虚拟环境：

```powershell
.\.venv\Scripts\activate
```

安装依赖：

```powershell
pip install -r requirements.txt
```

复制环境变量文件：

```powershell
copy .env.example .env
```

编辑 `.env`：

```text
LLM_API_KEY=你的大模型 API Key
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-v4-flash
LLM_MAX_TOKENS=800
```

启动服务：

```powershell
uvicorn app.main:app --reload
```

打开网页：

```text
http://127.0.0.1:8000/app
```

打开 Swagger API 文档：

```text
http://127.0.0.1:8000/docs
```

## 使用流程

1. 打开 `http://127.0.0.1:8000/app`
2. 上传论文 PDF
3. 点击“生成 chunks 并建立索引”
4. 在提问框输入问题
5. 查看回答、来源 chunk 和问答历史
6. 下次打开页面时，可以在“历史论文”里重新选择论文继续提问

## 主要接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/` | 健康检查 |
| `GET` | `/app` | 打开网页应用 |
| `GET` | `/papers` | 查看历史论文 |
| `POST` | `/papers/upload` | 上传 PDF 并提取文本 |
| `GET` | `/papers/{paper_id}/text` | 查看提取后的文本 |
| `POST` | `/papers/{paper_id}/chunks` | 生成 chunks |
| `GET` | `/papers/{paper_id}/chunks` | 查看 chunks |
| `POST` | `/papers/{paper_id}/index` | 建立向量索引 |
| `POST` | `/papers/{paper_id}/search` | 检索相关 chunks |
| `POST` | `/papers/{paper_id}/ask` | 基于论文内容提问 |
| `GET` | `/papers/{paper_id}/qa-history` | 查看问答历史 |
| `GET` | `/vector-store/status` | 查看向量库状态 |

## 成本保护

为了避免误消耗大模型余额，项目内置了几项限制：

- 单个问题最多 500 个字符。
- `top_k` 默认值为 2。
- `top_k` 最大值为 3。
- LLM 输出默认限制为 800 tokens。
- 页面会显示问题字符计数。
- 如果没有配置 `LLM_API_KEY`，系统只返回检索结果，不调用大模型。

## 数据存储

项目使用本地文件保存数据：

| 目录 | 内容 |
| --- | --- |
| `app/storage/uploads/` | 上传的 PDF |
| `app/storage/extracted/` | 提取后的文本 |
| `app/storage/chunks/` | 文本 chunks |
| `app/storage/vector_db/` | 本地 JSON 向量索引 |
| `app/storage/qa_history/` | 每篇论文的问答历史 |


## 截图

主界面支持论文上传、索引状态查看、历史论文管理、基于 RAG 的论文问答、来源 chunk 引用和问答历史记录。

<img width="1592" height="770" alt="AI Paper Assistant UI" src="https://github.com/user-attachments/assets/a2aad578-f8ce-44df-bdbc-c3f5b8fc1317" />

## 当前版本说明

当前版本使用本地 JSON 向量库，适合课程项目、小样展示和本地原型验证。后续如果需要处理更多论文，可以替换为 FAISS、Milvus、Qdrant 或稳定配置后的 ChromaDB。
