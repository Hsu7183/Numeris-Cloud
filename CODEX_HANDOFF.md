# Numeris 工程交接

## 系統架構

FastAPI提供JSON API與Jinja2單頁介面；SQLAlchemy 2使用SQLite；Alembic管理schema。所有路徑從`app/core/paths.py`的專案根目錄衍生，不寫死使用者家目錄。業務邏輯位於`app/services`，HTTP路由位於`app/api`。

## 重要檔案

- `app/main.py`：應用生命週期、錯誤格式、路由、首頁。
- `app/models/database_models.py`：21張資料表。
- `config/games/*.yaml`：8種啟用商品ruleset；BINGO設定保留但為inactive（內容為JSON相容YAML）。
- `app/services/analytics/core.py`：頻率、遺漏、冷熱、結構、AC。
- `app/services/generation/generators.py`：四類候選生成器與差異化。
- `app/services/generation/service.py`：資料截止、生成run持久化與鎖定。
- `app/services/importers/draw_importer.py`：檔案解析、規則驗證與冪等匯入。
- `app/services/replay/service.py`：歷史逐期模擬與基準。
- `app/services/data_sources/official.py`：官方來源探索及原始檔保存。
- `app/services/simple_dashboard.py`：簡易首頁、包牌、同期別核對及每週歷史指標。
- `app/api/simple.py`：簡易首頁資料與下期組合API。
- `tests`：單元、整合與Playwright E2E。

## 資料庫schema

核心表：`games`、`rulesets`、`source_artifacts`、`draws`、`draw_numbers`、`analysis_runs`、`number_metrics`、`generation_presets`、`generation_runs`、`generated_tickets`、`generated_ticket_numbers`、`evaluation_runs`、`ticket_results`、`replay_runs`、`replay_draw_results`、`jobs`、`audit_logs`與`app_settings`。完整欄位見模型與`migrations/versions/0001_initial_schema.py`。

## 資料更新流程

`POST /api/data/update`建立job；背景工作依`config/sources.yaml`連線官方網域、
保存原始回應及metadata。台灣來源呼叫`ResultDownload`官方API取得2007年至今的
年度CDN ZIP，再以當月查詢API補齊啟用中的傳統彩券；年度CSV以「遊戲名稱」欄辨識
遊戲，不依可能亂碼的舊ZIP檔名。香港來源使用賽馬會結果頁實際呼叫的官方GraphQL，
以季度區間下載1993年至今六合彩結果。所有資料通過白名單schema後才由批次匯入器
寫入。39／49樂合彩共用母遊戲事件，大樂透加開獎項不作一般開獎匯入。

## 分析流程

使用遊戲或衍生遊戲的底層draws，依日期及期別排序，截取截止期之前最近N期。各pool獨立呼叫`analyze_numbers`；有位置的彩種應按位置擴充儲存`position_index`。組合結構由`calculate_structure`集中計算。

## 選號流程

API驗證輸入 → 取得截止期 → 建立各pool metrics → PCG64產生候選 → 硬條件篩選 → 偏好分數 → ticket hash去重 → greedy max-min/MMR差異化 → 保存generation run與tickets。條件不足拋出`GEN_CANDIDATE_SHORTAGE`，不更改使用者條件。

## 防止未來資料洩漏

一般生成使用資料庫最新可用期別作截止點，並只載入所需lookback與AC歷史視窗。
新推薦鎖定時會以目標期、截止期、鎖定時間、完整設定與全部ticket建立SHA-256
`recommendation_anchor`。實戰核對必須同時通過定錨、目標期一致，以及
`draw.created_at > generation_run.locked_at`；同一目標期只計最早鎖定的一份。
舊有未定錨推薦與歷史回放不得混入首頁實戰達標率。
歷史逐期模擬以目標期前的查詢條件載入資料，不包含目標期及未來期。每期保存
`target_draw_id`、`cutoff_draw_id`、預測／實際號碼、命中位置與
`future_data_used=false`；`tests/unit/test_replay_guard.py`持續驗證切片守門。

## 新增彩種

1. 在`config/games`新增JSON相容YAML，指定game type、pool、範圍、draw/pick count、unique、ordered、大小分界與zones。
2. 執行`python -m scripts.init_data`建立game與ruleset。
3. 依資料格式新增parser及驗證fixture。
4. 為生成、核對及API增加測試；若是新結構，新增`CandidateGenerator`實作。

## 新增preset

在`config/presets`新增設定檔，包含唯一`preset_code`、名稱與版本，執行初始化。若新增參數，先擴充Pydantic request與generator硬條件，並更新config hash與UI。

## 修正官方來源解析器

只使用官方網域。先保存原始回應及SHA-256，再建立針對內容類型與schema的parser；不可以使用畫面文字推測缺值。加入固定官方樣本fixture、schema變更測試、冪等測試與衝突測試後，才把`parse_status`改為completed。

## 執行所有測試

```bat
test.bat
```

或：

```bat
.venv\Scripts\python.exe -m ruff check app tests scripts
.venv\Scripts\python.exe -m mypy
.venv\Scripts\python.exe -m pytest
```

端對端測試會啟動隨機本機連接埠並以Playwright Chromium完成五步選號、10組生成、鎖定及推薦紀錄流程。
