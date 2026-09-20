# Numeris Cloud 部署說明

這份設定將 Numeris 放在 Linux VPS，以 Docker 常駐執行。GitHub 只保存程式碼；資料庫、原始資料、報告與日誌留在 VPS 的 Docker volumes，不會被推回 GitHub。

## 1. 在 VPS 初次安裝

以 SSH 登入 Ubuntu 24.04 或相容 Linux 主機後，安裝 Docker 與 Git，然後複製私有 repository：

```bash
git clone https://github.com/Hsu7183/Numeris-Cloud.git ~/numeris-cloud
cd ~/numeris-cloud
docker compose up -d --build numeris
```

網站服務會只綁定 VPS 本機的 `127.0.0.1:8767`。接著以 Caddy 或 Nginx 設定 HTTPS 與網域反向代理至此連接埠；不要直接把 8767 暴露到網際網路。

## 2. 設定 GitHub 的手動更新按鈕

在 repository 的 `Settings` → `Secrets and variables` → `Actions` 新增以下內容：

| 類型 | 名稱 | 內容 |
| --- | --- | --- |
| Secret | `VPS_HOST` | VPS IP 或網域 |
| Secret | `VPS_USER` | VPS 的 SSH 使用者名稱 |
| Secret | `VPS_SSH_PRIVATE_KEY` | 專供 GitHub Actions 使用的 SSH 私鑰全文 |
| Variable | `VPS_APP_DIR` | VPS 上專案絕對路徑，例如 `/home/ubuntu/numeris-cloud` |

完成後，開啟 GitHub 的 `Actions` → `手動更新雲端開獎資料` → `Run workflow`。工作流程會在 VPS 執行官方資料更新與本週統計；平常不會自行更新。

## 3. 更新網站程式

登入 VPS 後執行：

```bash
cd ~/numeris-cloud
git pull --ff-only
docker compose up -d --build numeris
```

首次部署完成後，請確認 `/api/health` 可經由 HTTPS 網域讀取，再從手機以行動網路開啟網站驗證。
