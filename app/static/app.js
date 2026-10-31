const fileInput = document.getElementById("fileInput");
const dropzone = document.getElementById("dropzone");
const dropText = document.getElementById("dropText");
const generateBtn = document.getElementById("generateBtn");
const statusCard = document.getElementById("statusCard");
const resultCard = document.getElementById("resultCard");
const stageBadge = document.getElementById("stageBadge");
const statusMessage = document.getElementById("statusMessage");
const errorBox = document.getElementById("errorBox");
const warningsBox = document.getElementById("warnings");
const resultBody = document.getElementById("resultBody");

let selectedFile = null;
let pollTimer = null;

const STAGE_TEXT = {
  queued: "排队中",
  reading: "读取文件",
  extracting: "规范化结构",
  classifying: "商品分类",
  writing: "生成模板",
  done: "完成",
  error: "失败",
};

["dragenter", "dragover"].forEach((evt) =>
  dropzone.addEventListener(evt, (e) => {
    e.preventDefault();
    dropzone.classList.add("dragover");
  })
);
["dragleave", "drop"].forEach((evt) =>
  dropzone.addEventListener(evt, (e) => {
    e.preventDefault();
    dropzone.classList.remove("dragover");
  })
);
dropzone.addEventListener("drop", (e) => {
  if (e.dataTransfer.files.length) {
    pickFile(e.dataTransfer.files[0]);
  }
});
fileInput.addEventListener("change", () => {
  if (fileInput.files.length) pickFile(fileInput.files[0]);
});

function pickFile(file) {
  selectedFile = file;
  dropText.textContent = `已选择：${file.name}`;
  dropzone.classList.add("picked");
  generateBtn.disabled = false;
}

generateBtn.addEventListener("click", async () => {
  if (!selectedFile) return;
  generateBtn.disabled = true;
  resetResult();
  const form = new FormData();
  form.append("file", selectedFile);
  let data;
  try {
    const resp = await fetch("/api/jobs", { method: "POST", body: form });
    if (!resp.ok) throw new Error((await resp.json()).detail || resp.statusText);
    data = await resp.json();
  } catch (err) {
    showError(`上传失败：${err.message}`);
    generateBtn.disabled = false;
    return;
  }
  poll(data.job_id);
});

function resetResult() {
  statusCard.classList.remove("hidden");
  resultCard.classList.add("hidden");
  errorBox.classList.add("hidden");
  warningsBox.innerHTML = "";
  resultBody.innerHTML = "";
  stageBadge.className = "badge";
}

function poll(jobId) {
  if (pollTimer) clearTimeout(pollTimer);
  const tick = async () => {
    let job;
    try {
      const resp = await fetch(`/api/jobs/${jobId}`);
      job = await resp.json();
    } catch (err) {
      showError(`状态查询失败：${err.message}`);
      return;
    }
    render(job);
    if (job.stage === "done") {
      window.location.href = job.download_url;
      generateBtn.disabled = false;
      return;
    }
    if (job.stage === "error") {
      showError(job.error);
      generateBtn.disabled = false;
      return;
    }
    pollTimer = setTimeout(tick, 1500);
  };
  tick();
}

function render(job) {
  stageBadge.textContent = STAGE_TEXT[job.stage] || job.stage;
  stageBadge.className = "badge " + (job.stage === "done" ? "done" : job.stage === "error" ? "error" : "");
  statusMessage.textContent = job.message || "";
  document.getElementById("statTotal").textContent = job.total_items || "-";
  document.getElementById("statUnique").textContent = job.unique_names || "-";
  document.getElementById("statCache").textContent = `${job.cache_hits}/${job.unique_names || "-"}`;

  warningsBox.innerHTML = "";
  (job.warnings || []).forEach((w) => {
    const div = document.createElement("div");
    div.className = "warning-item";
    div.textContent = "⚠ " + w;
    warningsBox.appendChild(div);
  });

  if (job.rows && job.rows.length) {
    resultCard.classList.remove("hidden");
    resultBody.innerHTML = "";
    job.rows.forEach((r, i) => {
      const tr = document.createElement("tr");
      if (r.amount_warning) tr.className = "warn";
      tr.innerHTML =
        `<td>${i + 1}</td>` +
        `<td>${escapeHtml(r.name)}</td>` +
        `<td>${escapeHtml(r.category_name)}</td>` +
        `<td>${r.code}</td>` +
        `<td>${escapeHtml(r.unit)}</td>` +
        `<td class="num">${r.quantity}</td>` +
        `<td class="num">${r.unit_price}</td>` +
        `<td class="num">${r.amount}</td>` +
        `<td class="num">${r.tax_rate}</td>` +
        `<td class="${r.from_cache ? "tag-cache" : "tag-llm"}">${r.from_cache ? "缓存" : "Agent"}</td>`;
      resultBody.appendChild(tr);
    });
  }
}

function showError(msg) {
  statusCard.classList.remove("hidden");
  errorBox.classList.remove("hidden");
  errorBox.textContent = msg;
  stageBadge.textContent = "失败";
  stageBadge.className = "badge error";
}

function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
  );
}
