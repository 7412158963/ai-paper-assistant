# GitHub Release Checklist

发布到 GitHub 前按这个清单检查。

## 必须确认

- `.env` 没有被提交。
- `.venv/` 没有被提交。
- `app/storage/` 里的 PDF、文本、chunks、向量库、问答历史没有被提交。
- 截图里没有 API Key。
- README 里的 API Key 只是示例，不是真实密钥。

## 建议提交的文件

```text
.env.example
.gitignore
README.md
requirements.txt
app/
  __init__.py
  config.py
  main.py
  services/
  static/
  storage/.gitkeep
```

## 不建议提交的文件

```text
.env
.venv/
.vscode/
__pycache__/
*.pyc
app/storage/uploads/
app/storage/extracted/
app/storage/chunks/
app/storage/vector_db/
app/storage/qa_history/
app/storage/vector_db_diag/
app/storage/vector_db_diag2/
app/storage/vector_db_test/
```

## 初始化 Git 仓库

如果本地还不是 Git 仓库，在 `D:\ai-paper-assistant` 运行：

```powershell
git init
git add .
git status
```

确认没有 `.env`、`.venv/`、PDF、提取文本、向量库文件后，再提交：

```powershell
git commit -m "Initial AI paper assistant prototype"
```

## 推送到 GitHub

在 GitHub 创建空仓库，例如：

```text
ai-paper-assistant
```

然后运行：

```powershell
git branch -M main
git remote add origin https://github.com/你的用户名/ai-paper-assistant.git
git push -u origin main
```

## 简历项目名

```text
AI 论文阅读与问答助手 | Python / FastAPI / RAG / DeepSeek API / 向量检索
```
