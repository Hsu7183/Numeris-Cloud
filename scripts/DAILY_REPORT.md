# 今彩539 每日 A4 總表

首頁 `docs/index.html` 顯示預覽與下載入口；完整頁面為 `docs/daily539-report.html`。

執行環境：Python 3.12+、Node.js 22+、`scripts/daily-report-requirements.txt`。
Linux 安裝 `fonts-wqy-zenhei`；Windows 自動使用微軟正黑體，亦可用
`NUMERIS_REPORT_FONT` 指定支援繁中的 TrueType 字型（TTC 使用第一個字型）。

```sh
python -m scripts.build_539_daily_report
python -m unittest discover -s tests/unit -p test_daily539_report_data.py
```

日期採 Asia/Taipei，預設報表日期為今天。日期選號目標沿用使用者指定的預覽日，
換日後至少推至當日；目標日開獎資料公布後，再移至下一日。因此11/20預覽11/21，
到了11/21開獎前仍是11/21名單，不會提早跳到11/22。
可使用 `--date YYYY-MM-DD --target-date YYYY-MM-DD` 明確指定。
程式不抓取或猜測未來獎號；資料來源不得晚於報表日，且必須早於選號目標日。

相鄰排名直接執行 `docs/daily539_output.js` 的計算區塊；八組號碼直接執行
`docs/workbench/539-sliding-window.html` 的算法，固定 W=18、模擬600期、種子20261025。
若來源算法的擷取界線改變，程式會失敗而保留先前報表，不使用硬編碼快照。
兩份官方來源最近200期必須一致，格式、日期排序及球號必須通過檢查。

星號對應排名欄位：4、5、7、11、17、19、24、26、28、35，再依對應球號升序。
日期選號取目標日前4、2、10、11個日曆日，剔除來源日之後至資料截止日已再開出的球號。
來源日未開獎時明列沒有資料，不改用相鄰期。截止日未達目標日前一天時標記暫算。
每日日報更新的是藍字；底圖灰色圈記僅為原照片的固定參考標記，不作每日推算。

輸出至 `docs/reports/daily539/`：`latest.pdf`、`latest.png`、`latest.json`、
`archive.json` 及 `archive/YYYY-MM-DD.pdf`。確認單頁PDF可正常渲染後才更新輸出。
首頁以 metadata 日期標示最近成功版本，使用內容版本參數避免PDF及預覽舊快取。

既有資料工作流程每天台灣22:00、23:00更新官方資料後重建報表。
`update-539-daily-report.yml` 於每天00:10依已公布資料換日重建並發布，無需本機開機。
GitHub排程可能延後；頁面顯示實際報表日期與資料截止日。
