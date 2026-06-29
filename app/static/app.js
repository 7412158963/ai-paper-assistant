let currentPaperId = localStorage.getItem("paper_id") || "";
let currentPaper = null;
const MAX_QUESTION_LENGTH = 500;
const DEFAULT_TOP_K = 2;
const MAX_TOP_K = 3;

const uploadForm = document.querySelector("#upload-form");
const fileInput = document.querySelector("#paper-file");
const paperIdEl = document.querySelector("#paper-id");
const pageCountEl = document.querySelector("#page-count");
const charCountEl = document.querySelector("#char-count");
const statusUploadedEl = document.querySelector("#status-uploaded");
const statusChunkedEl = document.querySelector("#status-chunked");
const statusIndexedEl = document.querySelector("#status-indexed");
const indexButton = document.querySelector("#index-button");
const statusButton = document.querySelector("#status-button");
const indexOutput = document.querySelector("#index-output");
const refreshPapersButton = document.querySelector("#refresh-papers-button");
const paperListEl = document.querySelector("#paper-list");
const askForm = document.querySelector("#ask-form");
const questionInput = document.querySelector("#question");
const questionCounterEl = document.querySelector("#question-counter");
const topKInput = document.querySelector("#top-k");
const answerBox = document.querySelector("#answer-box");
const answerCitationsEl = document.querySelector("#answer-citations");
const refreshQaHistoryButton = document.querySelector("#refresh-qa-history-button");
const qaHistoryListEl = document.querySelector("#qa-history-list");
const sourcesList = document.querySelector("#sources-list");
const toast = document.querySelector("#toast");

setPaperId(currentPaperId);
renderPaperStatus(null);
updateQuestionCounter();
loadPaperList().catch((error) => showToast(error.message));

uploadForm.addEventListener("submit", async (event) => {
  event.preventDefault();

  const file = fileInput.files[0];
  if (!file) {
    showToast("先选择一个 PDF 文件");
    return;
  }

  const formData = new FormData();
  formData.append("file", file);

  setBusy(uploadForm, true);
  try {
    const data = await request("/papers/upload", {
      method: "POST",
      body: formData,
    });

    selectPaper(data);
    indexOutput.textContent = `上传成功：${data.original_filename}\n\n${data.preview}`;
    answerBox.textContent = "论文已上传，请先建立索引。";
    clearSources();
    await loadPaperList();
  } catch (error) {
    showToast(error.message);
  } finally {
    setBusy(uploadForm, false);
  }
});

indexButton.addEventListener("click", async () => {
  if (!requirePaperId()) return;

  setBusy(indexButton, true);
  try {
    const chunkData = await request(`/papers/${currentPaperId}/chunks`, {
      method: "POST",
    });
    const indexData = await request(`/papers/${currentPaperId}/index`, {
      method: "POST",
    });
    indexOutput.textContent = JSON.stringify(
      {
        chunk_count: chunkData.chunk_count,
        indexed_count: indexData.indexed_count,
        embedding_model: indexData.embedding_model,
      },
      null,
      2,
    );
    updateCurrentPaperStatus({
      has_pdf: true,
      has_text: true,
      has_chunks: true,
      indexed_count: indexData.indexed_count,
    });
    await loadPaperList();
  } catch (error) {
    showToast(error.message);
  } finally {
    setBusy(indexButton, false);
  }
});

statusButton.addEventListener("click", async () => {
  setBusy(statusButton, true);
  try {
    const data = await request("/vector-store/status");
    indexOutput.textContent = JSON.stringify(data, null, 2);
  } catch (error) {
    showToast(error.message);
  } finally {
    setBusy(statusButton, false);
  }
});

refreshPapersButton.addEventListener("click", async () => {
  setBusy(refreshPapersButton, true);
  try {
    await loadPaperList();
  } catch (error) {
    showToast(error.message);
  } finally {
    setBusy(refreshPapersButton, false);
  }
});

refreshQaHistoryButton.addEventListener("click", async () => {
  if (!requirePaperId()) return;

  setBusy(refreshQaHistoryButton, true);
  try {
    await loadQaHistory(currentPaperId);
  } catch (error) {
    showToast(error.message);
  } finally {
    setBusy(refreshQaHistoryButton, false);
  }
});

questionInput.addEventListener("input", updateQuestionCounter);

askForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!requirePaperId()) return;

  const question = questionInput.value.trim();
  if (!question) {
    showToast("请输入问题");
    return;
  }

  if (question.length > MAX_QUESTION_LENGTH) {
    showToast(`问题太长，最多 ${MAX_QUESTION_LENGTH} 个字符`);
    return;
  }

  const topK = normalizeTopK(topKInput.value);
  topKInput.value = topK;

  answerBox.textContent = "正在检索并生成回答...";
  clearSources();
  setBusy(askForm, true);

  try {
    const data = await request(`/papers/${currentPaperId}/ask`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        question,
        top_k: topK,
      }),
    });

    renderAnswer(data);
    await loadQaHistory(currentPaperId);
    await loadPaperList();
  } catch (error) {
    answerBox.textContent = "";
    showToast(error.message);
  } finally {
    setBusy(askForm, false);
  }
});

function setPaperId(paperId) {
  currentPaperId = paperId || "";
  if (currentPaperId) {
    localStorage.setItem("paper_id", currentPaperId);
    paperIdEl.textContent = currentPaperId;
  } else {
    localStorage.removeItem("paper_id");
    paperIdEl.textContent = "尚未上传";
  }
}

function selectPaper(paper) {
  currentPaper = paper || null;
  setPaperId(paper.paper_id);
  pageCountEl.textContent = formatValue(paper.page_count);
  charCountEl.textContent = formatValue(paper.char_count);
  renderPaperStatus(paper);
  loadQaHistory(paper.paper_id).catch((error) => showToast(error.message));
}

function requirePaperId() {
  if (currentPaperId) return true;
  showToast("请先上传 PDF");
  return false;
}

async function loadPaperList() {
  const data = await request("/papers");
  const papers = data.papers || [];
  const selectedPaper = papers.find((paper) => paper.paper_id === currentPaperId);

  if (selectedPaper) {
    selectPaper(selectedPaper);
  } else if (!currentPaperId) {
    renderPaperStatus(null);
  }

  renderPaperList(papers);
}

function renderPaperList(papers) {
  paperListEl.innerHTML = "";

  if (papers.length === 0) {
    const empty = document.createElement("p");
    empty.className = "empty-state";
    empty.textContent = "还没有上传过论文";
    paperListEl.append(empty);
    return;
  }

  for (const paper of papers) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "paper-item";
    button.classList.toggle("is-active", paper.paper_id === currentPaperId);

    const title = document.createElement("span");
    title.className = "paper-title";
    title.textContent = paper.original_filename || paper.paper_id;

    const meta = document.createElement("span");
    meta.className = "paper-meta";
    meta.textContent = [
      `页数 ${formatValue(paper.page_count)}`,
      `字符 ${formatValue(paper.char_count)}`,
      getPaperStatusText(paper),
      `问答 ${formatValue(paper.qa_count || 0)}`,
    ].join(" | ");

    const id = document.createElement("span");
    id.className = "paper-id-short";
    id.textContent = paper.paper_id;

    button.append(title, meta, id);
    button.addEventListener("click", () => {
      selectPaper(paper);
      answerBox.textContent = paper.indexed_count > 0
        ? "已选择历史论文，可以继续提问。"
        : "已选择历史论文，请先建立索引。";
      clearSources();
      renderQaHistory([]);
      renderPaperList(papers);
    });

    paperListEl.append(button);
  }
}

async function loadQaHistory(paperId) {
  if (!paperId) {
    renderQaHistory([]);
    return;
  }

  const data = await request(`/papers/${paperId}/qa-history`);
  if (paperId !== currentPaperId) return;
  renderQaHistory(data.items || []);
}

function renderQaHistory(items) {
  qaHistoryListEl.innerHTML = "";

  if (items.length === 0) {
    const empty = document.createElement("p");
    empty.className = "empty-state";
    empty.textContent = currentPaperId ? "这篇论文还没有问答记录" : "选择论文后显示历史问答";
    qaHistoryListEl.append(empty);
    return;
  }

  for (const item of items) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "qa-history-item";

    const question = document.createElement("span");
    question.className = "qa-history-question";
    question.textContent = item.question;

    const answer = document.createElement("span");
    answer.className = "qa-history-answer";
    answer.textContent = item.answer;

    const meta = document.createElement("span");
    meta.className = "qa-history-meta";
    meta.textContent = [
      formatDateTime(item.created_at),
      item.mode || "unknown",
      item.model || "no model",
      `sources ${(item.sources || []).length}`,
    ].join(" | ");

    button.append(question, answer, meta);
    button.addEventListener("click", () => {
      renderAnswer(item);
    });

    qaHistoryListEl.append(button);
  }
}

function updateCurrentPaperStatus(patch) {
  if (!currentPaperId) return;

  currentPaper = {
    ...(currentPaper || { paper_id: currentPaperId }),
    ...patch,
  };
  renderPaperStatus(currentPaper);
}

function renderPaperStatus(paper) {
  const hasUploaded = Boolean(paper?.has_pdf || paper?.has_text || currentPaperId);
  const hasChunks = Boolean(paper?.has_chunks);
  const hasIndex = Number(paper?.indexed_count || 0) > 0;

  updateStatusStep(statusUploadedEl, hasUploaded, hasUploaded ? "已上传" : "未上传");
  updateStatusStep(statusChunkedEl, hasChunks, hasChunks ? "已分块" : "未分块");
  updateStatusStep(statusIndexedEl, hasIndex, hasIndex ? `已建索引 ${paper.indexed_count}` : "未建索引");
}

function updateStatusStep(element, isDone, text) {
  element.textContent = text;
  element.classList.toggle("is-done", isDone);
}

function getPaperStatusText(paper) {
  if (Number(paper.indexed_count || 0) > 0) {
    return `已建索引 ${paper.indexed_count}`;
  }

  if (paper.has_chunks) {
    return "已分块，未建索引";
  }

  if (paper.has_text || paper.has_pdf) {
    return "已上传，未分块";
  }

  return "未处理";
}

async function request(url, options = {}) {
  const response = await fetch(url, options);
  const contentType = response.headers.get("content-type") || "";
  const isJson = contentType.includes("application/json");
  const data = isJson ? await response.json() : await response.text();

  if (!response.ok) {
    const detail = isJson ? data.detail || JSON.stringify(data) : data;
    throw new Error(detail || `请求失败：${response.status}`);
  }

  return data;
}

function formatValue(value) {
  return value === null || value === undefined ? "-" : value;
}

function normalizeTopK(value) {
  const parsed = Number(value || DEFAULT_TOP_K);
  if (!Number.isFinite(parsed)) return DEFAULT_TOP_K;
  return Math.min(Math.max(Math.trunc(parsed), 1), MAX_TOP_K);
}

function updateQuestionCounter() {
  const length = questionInput.value.length;
  questionCounterEl.textContent = `${length} / ${MAX_QUESTION_LENGTH}`;
  questionCounterEl.classList.toggle("is-warn", length > MAX_QUESTION_LENGTH * 0.9);
}

function formatDateTime(value) {
  if (!value) return "-";

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;

  return date.toLocaleString("zh-CN", {
    hour12: false,
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function renderAnswer(data) {
  const statusLine = `mode: ${data.mode}${data.model ? ` | model: ${data.model}` : ""}`;
  answerBox.textContent = `${statusLine}\n\n${data.answer}`;
  answerBox.classList.toggle("is-warn", data.mode !== "llm");

  renderAnswerCitations(data.sources || []);

  sourcesList.innerHTML = "";
  (data.sources || []).forEach((source, index) => {
    const item = document.createElement("article");
    item.className = "source-item";

    const title = document.createElement("div");
    title.className = "source-title";
    title.textContent = `来源 ${index + 1}：Chunk #${source.chunk_index}`;

    const meta = document.createElement("div");
    meta.className = "source-meta";
    meta.textContent = [
      `chunk_id: ${source.chunk_id}`,
      `相似度: ${formatScore(source.score)}`,
    ].join(" | ");

    const text = document.createElement("p");
    text.className = "source-text";
    text.textContent = source.text;

    item.append(title, meta, text);
    sourcesList.append(item);
  });
}

function renderAnswerCitations(sources) {
  answerCitationsEl.innerHTML = "";

  if (!sources.length) {
    answerCitationsEl.hidden = true;
    return;
  }

  const label = document.createElement("span");
  label.className = "citation-label";
  label.textContent = "引用自";
  answerCitationsEl.append(label);

  sources.forEach((source, index) => {
    const chip = document.createElement("span");
    chip.className = "citation-chip";
    chip.textContent = `来源 ${index + 1} / Chunk #${source.chunk_index}`;
    answerCitationsEl.append(chip);
  });

  answerCitationsEl.hidden = false;
}

function clearSources() {
  sourcesList.innerHTML = "";
  answerCitationsEl.innerHTML = "";
  answerCitationsEl.hidden = true;
}

function formatScore(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number.toFixed(4) : "-";
}

function setBusy(target, busy) {
  const buttons = target instanceof HTMLButtonElement ? [target] : target.querySelectorAll("button");
  buttons.forEach((button) => {
    button.disabled = busy;
  });
}

function showToast(message) {
  toast.textContent = message;
  toast.hidden = false;
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => {
    toast.hidden = true;
  }, 3600);
}
