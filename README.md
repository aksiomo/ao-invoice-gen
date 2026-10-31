# ao-invoice-gen

> 本项目由 AI Agent 生成。作者（模型）：**ark-code-latest**（模型 ID：`coding-plan/ark-code-latest`）。

根据上传的采购/入库 Excel，自动生成可导入**全国统一规范电子税务局**的《发票开具项目信息导入模板.xlsx》。

## 核心逻辑

```
采购入库单（格式不固定：xlsx / OLE xls / WPS 导出的 HTML 伪 xls）
  │ ① 本地确定性解析为二维文本矩阵（app/io_excel.py）
  ▼
Agent A 结构化（app/agents/extractor.py）
  │ 矩阵 + JSON Schema → 规范明细 JSON；程序侧二次校验：
  │ 商品名必须在原表单元格中逐字符存在（防篡改），失败带错误信息重试一次
  ▼
分类（app/agents/classifier.py + app/taxonomy.py + app/cache.py）
  │ · 4205 条税收编码预构建为 SQLite（FTS5 bigram + 单字/同义词召回 + 规则重排）
  │ · 商品名精确匹配本地缓存（data/cache.sqlite），命中直接取，不请求模型
  │ · 未命中商品本地召回 Top-20 叶子候选，Agent B 批量精选，后端校验编码
  │   必须真实存在且为叶子节点，随后写回缓存
  ▼
写出（app/excel_writer.py）
    openpyxl 基于官方模板写入 sheet「1-明细模板」第 4 行起，
    其余 sheet 与说明/表头原样保留；结果留存 storage/generated/ 并经页面自动下载
```

### 字段对应（重要）

| 输出模板列 | 取值 |
|---|---|
| 项目名称 | 分类名称（编码库中的“货物和劳务名称”，由后端按编码反查，**不是商品名**） |
| 商品和服务税收分类编码 | Agent B 选出的 19 位叶子编码 |
| 规格型号 | **输入文件中的商品/存货名称原文，逐字符完全一致** |
| 单位 / 商品数量 / 商品单价 / 金额 | 主计量单位 / 数量 / 本币单价 / 本币金额（金额保留两位小数） |
| 税率 | 固定 `0.01` |

> 商品名永不篡改：Agent A 返回的名称必须逐字符出现在原始单元格中；最终写出后还有
> “输出规格型号集合 == 输入商品名集合”的不变量测试（90 行样例全量核对）。

## 目录结构

```
app/
  main.py            FastAPI 路由（页面 / 创建任务 / 轮询 / 下载）
  pipeline.py        处理流程编排（后台任务）
  jobs.py            内存任务表与阶段进度
  config.py          环境变量配置
  io_excel.py        xlsx / xls / HTML 三种格式 → 二维矩阵
  taxonomy.py        SQLite 候选检索与编码反查
  cache.py           商品分类持久化缓存（精确匹配）
  excel_writer.py    官方模板填充
  schemas.py         pydantic 模型
  agents/
    llm.py           OpenAI 兼容 Chat Completions（JSON）
    extractor.py     Agent A：表格规范化
    classifier.py    Agent B：候选编码精选
    prompts.py
  assets/            官方导入模板（生成基准）
  templates/ static/ 单页前端
scripts/build_taxonomy.py   编码表 xls → data/taxonomy.sqlite
data/taxonomy.sqlite        预构建编码库（FTS5），随仓库提供
storage/uploads|generated/  上传原件与生成结果（调试留存）
tests/
```

## 开发启动

```bash
# 1. 创建虚拟环境并安装依赖
python3 -m venv .python
.python/bin/pip install -r requirements.txt

# 2. 配置环境变量
cp .env.example .env
#   填入 OPENAI_BASE_URL / OPENAI_API_KEY / LLM_MODEL（任何 OpenAI 兼容服务均可）

# 3.（可选）重建税收编码库；data/taxonomy.sqlite 已随仓库提供
.python/bin/python scripts/build_taxonomy.py

# 4. 启动
.python/bin/uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

浏览器打开 <http://127.0.0.1:8000>，上传 `example_files/采购入库单.XLS`，点击“生成”，
页面轮询进度并展示“商品名 ↔ 分类名称 ↔ 编码”核对表，完成后自动下载结果文件。

## 测试

```bash
.python/bin/python -m pytest -q
```

包含：三种格式解析、候选召回、Agent A 名称防篡改与重试、缓存命中不调用 LLM、
编码合法性校验、模板完整性、以及 90 行样例的商品名不变量端到端测试。

## 部署

单进程 ASGI 部署（任务状态存内存，适配单实例）：

```bash
.python/bin/pip install -r requirements.txt
.python/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
```

生产建议前置 Nginx 反向代理与 HTTPS；`storage/` 为本地留存目录，注意磁盘清理。
若需多实例水平扩展，可将 `app/jobs.py` 的内存任务表替换为 Redis（当前未引入）。

## 环境变量

见 `.env.example`：`OPENAI_BASE_URL`、`OPENAI_API_KEY`、`LLM_MODEL`，
可选 `EXTRACTOR_MODEL` / `CLASSIFIER_MODEL`，以及 `TOP_K`、`CLASSIFY_BATCH_SIZE`、
`FIXED_TAX_RATE=0.01`、`AMOUNT_TOLERANCE`、`MAX_UPLOAD_MB` 等。
