# GitHub Pages 使用方式

這是 Numeris Cloud 的免主機版本。網站顯示的是已產生的今彩539統計資料；使用者在網頁上不會直接抓取或改寫資料。

## 初次啟用

1. 開啟 GitHub repository 的 `Settings` → `Pages`。
2. 在 `Build and deployment` 的 `Source` 選擇 **GitHub Actions**。
3. 開啟 `Actions`，執行 **更新今彩539 GitHub Pages 資料**，點選 `Run workflow`。
4. 更新成功後，該流程會提交 `docs/data/daily539.json`；接著 **發布 Numeris Cloud** 會自動執行。
5. 到 `Actions` 的發布工作查看網址，或開啟：

   `https://hsu7183.github.io/Numeris-Cloud/`

## 日後手動更新

每次想取得最新資料時，執行：

`Actions` → `更新今彩539 GitHub Pages 資料` → `Run workflow`

系統只在這個流程執行時抓取台灣彩券官方資料。平常不會自動更新，也不需要你的電腦保持開機。

## 注意事項

- GitHub Actions 第一次執行可能要幾分鐘，用來安裝 Python 套件、抓取官方資料並計算統計。
- 如果 Actions 顯示沒有寫入權限，到 repository 的 `Settings` → `Actions` → `General`，將 `Workflow permissions` 設為 **Read and write permissions**。
- 網站入口為彩種選擇首頁：`daily539.html` 保留今彩539；`lotto649/index.html` 提供大樂透。
- 大樂透統計使用 1–49 號、每期 6 個主號，特別號獨立顯示且不計入主號統計。資料存於 `docs/data/lotto649.json`，與539分開。
- 大樂透由「更新大樂透 GitHub Pages 資料」工作流程每晚台灣時間22:15更新，也可手動執行。
- 修改539共用版型後，執行 `python -m scripts.build_lotto649_pages` 重建對應的大樂透版型。
- 本機預覽：`python -m http.server 8765 --directory docs`，開啟 `http://localhost:8765/`。
- 本機 FastAPI 版的 CSV 匯入與其他動態功能仍保留在本機程式。GitHub Pages 原本沒有帳號登入，此次新增的是網站入口首頁。
