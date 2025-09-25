# LiDAR × TSN × IPFS 實驗完整流程

本文檔彙整專案目前基於實測資料的端到端流程，說明所需環境、重要腳本與輸出成果，提供後續重現與延伸實驗的依據。

---

## 1. 實驗總覽
- **目標**：驗證 EB 系列 LiDAR 壓縮演算法在 TSN 車內網路中的頻寬需求、延遲表現與 IPFS 儲存成本效益。
- **資料來源**：KITTI raw Velodyne HDL-64E 點雲（`.bin` 檔）；原始資料保留於使用者機器上，本 repo 只存放子集或分析結果。
- **核心流程**：
  1. 準備環境與資料路徑。
  2. 以 `run_subset_experiments.py` 對指定場景進行真實壓縮測試。
  3. 應用 `tsn_generate_flows.py` 將壓縮結果轉換為 TSN 流量描述並呼叫 tsnkit 模擬。
  4. 經由實驗腳本分析 TSN 延遲、頻寬、儲存節省與 IPFS 上傳時間。
  5. 利用 `run_real_comprehensive_experiments.py` 串接壓縮 → TSN → IPFS 的全流程並產出總結報告。
  6. 使用驗證腳本交叉檢查統計結果與關鍵指標。

---

## 2. 前置需求
1. **Python 環境**：專案預期在 Python 3.8+ 上執行，建議建立虛擬環境 `.venv/` 並安裝 `numpy`, `scipy`, `bitarray`, `pandas`, `matplotlib`。
2. **LiDAR 演算法**：`scripts/EBpapercopy2.py` 內含論文使用的 EB 系列壓縮演算法。若未放置於 `scripts/`，會回退搜尋 `~/下載/KITTI/EBpapercopy2.py`。
3. **KITTI 資料**：原始 `.bin` 檔需存在於 下載資料夾或使用者指定路徑；repo 內 `data/` 只保存截取樣本以供快速測試。
4. **tsnkit**：在 `third_party/tsnkit/` 內提供模擬工具，不需額外安裝。
5. **IPFS/鏈服務（選用）**：若欲真正上傳 IPFS 或鏈上，需要本機守護行程與節點；目前腳本預設為模擬/佔位。

---

## 3. 目錄與關鍵腳本
| 位置 | 功能重點 |
| --- | --- |
| `scripts/run_subset_experiments.py` | 掃描指定資料夾中的 `.bin`，逐一套用 Huffman/EB-HC/EB-Octree/EB-HC-3D，計算壓縮比、誤差與封包數。 |
| `scripts/tsn_generate_flows.py` | 讀取壓縮 CSV ，根據 BE、封包數等資訊產生 TSN 流量描述 (`task.csv`, `network.csv` 等)。 |
| `run_real_comprehensive_experiments.py` | 串接壓縮 → TSN → IPFS 模擬，並輸出 `outputs/comprehensive_real_experiment_report.json`。 |
| `real_experiments_verification.py` | 針對最新壓縮結果計算頻寬節省、儲存節省、延遲改善等真實指標。 |
| `validate_real_experiments.py` | 驗證三個核心實驗（TSN、IPFS、延遲）是否全部基於實測資料。 |
| `outputs/` | 存放所有結果 CSV、JSON 及圖表。子資料夾如 `paper/`、`tsnkit/`、`single_vehicle/` 等各自有 README 說明。 |

---

## 4. 詳細流程

### 4.1 環境與資料確認
1. **檢查 KITTI**：可執行 `setup_real_experiment.py` 或手動確認 `~/下載/KITTI/KITTI/<scene>/.../*.bin` 是否存在。
2. **確認 EB 演算法**：若尚未複製 `EBpapercopy2.py` 至 `scripts/`，請從原始位置複製。
3. **虛擬環境**：
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt  # 若有自訂需求檔
   ```

### 4.2 執行壓縮實驗
`run_subset_experiments.py` 支援以下參數：
```bash
python scripts/run_subset_experiments.py \
  --data-dir /path/to/KITTI/scene \
  --max-files 5 \
  --be-list 0.5 1.0 2.0 \
  --out-csv outputs/compression_results_subset.csv
```
- 逐一讀取 `.bin` 檔，量化並執行多種壓縮演算法。
- 輸出欄位包含 `Compression Ratio`, `Mean Error`, `Num Packets`, `Chamfer Distance`, `Occupancy IoU` 等。

### 4.3 產生 TSN 流量描述
```bash
python scripts/tsn_generate_flows.py \
  --results-csv outputs/compression_results_subset.csv \
  --out outputs/tsn_flows.csv
```
- 會建立 `outputs/tsnkit/` 下的 `task.csv`, `network.csv`, `scenario.yaml` 等檔案。
- 這些檔案可直接給 tsnkit 模擬，也會被其他腳本重複使用。

### 4.4 TSN 模擬與指標統計
- `run_real_comprehensive_experiments.py` 會呼叫 tsnkit，以 `outputs/tsnkit/` 的檔案進行網路模擬並輸出：
  - `outputs/real_tsn_simulation.csv`
  - `outputs/real_tsn_latency_results.csv`
- 各種分析腳本（如 `real_tsn_latency_experiment.py`, `analyze_tsn_latency_comparison.py`）可將模擬結果與車內乙太網路基準做比較。

### 4.5 儲存與 IPFS 模擬
- `real_experiments_verification.py`、`validate_real_experiments.py` 會依壓縮比估算年度儲存量、上傳時間節省。
- `run_real_comprehensive_experiments.py` 的 `run_real_ipfs_experiment()` 會走訪 `outputs/` ，對所有結果檔進行模擬上傳，產生：
  - `outputs/real_ipfs_upload.csv`
  - `outputs/comprehensive_real_experiment_report.json`

### 4.6 全流程一鍵執行
```bash
python run_real_comprehensive_experiments.py
```
按順序執行：
1. **真實壓縮**：呼叫 `scripts/run_subset_experiments.py`，輸出 `outputs/compression_results_subset.csv`。
2. **TSN 流與模擬**：利用 `scripts/tsn_generate_flows.py` 生成流量，再以內建模擬函式計算延遲與抖動。
3. **IPFS 模擬**：針對 `outputs/` 中的 CSV/JSON 估算上傳時間與生成假想 CID/交易紀錄。
4. **整合報告**：輸出 `outputs/comprehensive_real_experiment_report.json` 總結壓縮、TSN、IPFS 指標。

---

## 5. 驗證與再現性
- `real_experiments_verification.py`：建立基於「剛跑出的壓縮結果」的 TSN/儲存/延遲分析，結果寫入 `outputs/real_*` 系列檔案。
- `validate_real_experiments.py`：交叉檢查 `outputs/compression_results_full.csv` 是否被所有實驗所引用，並重新計算關鍵指標。
- `EXPERIMENT_VERIFICATION_REPORT.md`：長篇文字報告，記錄一次完整實驗的輸出與統計。
- 圖表與表格（`outputs/paper/*.png`, `table_*.csv`）皆可直接引用於論文。

---

## 6. 重要輸出總表
| 檔案 | 說明 |
| --- | --- |
| `outputs/compression_results_subset.csv` | 最新壓縮實驗原始資料。 |
| `outputs/tsn_flows.csv` | TSN 流量摘要，含封包率與優先權。 |
| `outputs/real_tsn_simulation.csv` | tsnkit 模擬的延遲與抖動統計。 |
| `outputs/real_ipfs_upload.csv` | IPFS 模擬上傳時間與 CID/交易記錄。 |
| `outputs/comprehensive_real_experiment_report.json` | 全流程關鍵指標（頻寬節省、延遲、儲存節省等）。 |
| `outputs/paper/*.png`、`*.csv` | 論文專用圖表。 |

---

## 7. 常見問題與排錯
1. **找不到 EBpapercopy2**：請確認檔案存在於 `scripts/` 或 `~/下載/KITTI/`。
2. **沒有 `.bin`**：repo `.gitignore` 已忽略 `.bin`，需自行下載 KITTI 點雲至指定路徑。
3. **tsnkit 模擬失敗**：檢查 `outputs/tsnkit/` 是否存在 `task.csv` 及 `network.csv`，必要時重新執行 `tsn_generate_flows.py`。
4. **IPFS 寫入錯誤**：若要從模擬改成實際上傳，請調整 `run_real_ipfs_experiment()`，提供有效的 IPFS/API 端點與鏈節點。

---

## 8. 推薦的重現步驟彙總
```bash
# 1. 建立環境
python3 -m venv .venv
source .venv/bin/activate
pip install numpy scipy bitarray pandas matplotlib

# 2. 下載或確認 KITTI 資料仍在原位置
# 3. 進行限制樣本的真實壓縮
python scripts/run_subset_experiments.py --data-dir /path/to/KITTI/city --max-files 5 --be-list 1.0 2.0 --out-csv outputs/compression_results_subset.csv

# 4. 生成 TSN 流量描述
python scripts/tsn_generate_flows.py --results-csv outputs/compression_results_subset.csv --out outputs/tsn_flows.csv

# 5. 串接整體流程並製作報告
python run_real_comprehensive_experiments.py

# 6. (選用) 進行詳盡驗證
python real_experiments_verification.py
python validate_real_experiments.py
```

完成後，即可在 `outputs/` 中找到所有統計、報表與圖表，並可將本檔案與相關成果推送或引用於論文中。
