# information_paper

本專案提供論文實驗的可執行環境與腳本，整合了：
- LiDAR 誤差界限壓縮（EB-HC、EB-3D/Octree、EB-HC-3D）
- 壓縮效能與幾何誤差指標（含 Chamfer Distance、Occupancy IoU）
-（可選）將壓縮檔上傳 IPFS 並把 CID 上鏈
-（可選）以 TSN 工具評估不同壓縮率對時槽排程延遲的影響

目錄結構：
- `data/`：放置測試用 LiDAR 檔（已放入一個小樣本 `sample_0000000000.bin`）
- `outputs/`：壓縮結果（CSV 與檔案）輸出位置
- `scripts/EBpapercopy2.py`：EB-HC、EB-3D(EB-Octree)、EB-HC-3D 演算法完整實作（已自包含）
- `scripts/run_subset_experiments.py`：最小可重現壓縮實驗（使用 3 個方法族共 6 個方法，少量 BE 值）
- `scripts/ipfs_batch.py`：（可選）批次將壓縮檔上傳至 IPFS 並寫入鏈上（Ganache）
- `scripts/tsn_generate_flows.py`：（可選）將壓縮結果 CSV 轉成 TSN 流量規格（供 tsnkit 使用）

本專案已自包含演算法檔：`scripts/EBpapercopy2.py`。若要改回使用原始位置的檔案，可自行調整 `run_subset_experiments.py` 的載入邏輯。

## 1. 先決條件
- Python 3.8+，且建議安裝：numpy、scipy、bitarray、matplotlib、pandas、ipfshttpclient、web3、py-solc-x（若使用 IPFS/鏈）。
- 本機已存在：`下載/KITTI/EBpapercopy2.py`（或把該檔複製到本專案 `scripts/` 內）。
- 測試 LiDAR 檔位於 `data/`（已提供 `sample_0000000000.bin`）。
-（可選）若要 IPFS/鏈：本機 IPFS 守護行程（5001）與 Ganache（7545）。

## 2. 建議安裝與環境
```bash
# 進入專案根目錄
cd 宇翰論文

# 建議使用虛擬環境
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip

# 基礎套件
pip install numpy scipy bitarray pandas matplotlib

# 若要跑 IPFS + 區塊鏈
pip install ipfshttpclient web3 py-solc-x
```

## 3. 跑最小子集壓縮實驗
本腳本會：
- 讀取 `data/` 底下 `.bin`（預設取 1~2 個檔案）；
- 對每個檔案跑以下方法與少量 BE 值（預設 0.5、1.0、2.0 cm）：
  - EB-HC(Axis)、EB-HC(L2)
  - EB-3D = EB-Octree(Axis/L2)
  - EB-HC-3D(Axis/L2)
- 輸出 CSV 至 `outputs/compression_results_subset.csv`

```bash
python scripts/run_subset_experiments.py \
  --data-dir data \
  --max-files 1 \
  --be-list 0.5 1.0 2.0
```

已內建 `scripts/EBpapercopy2.py`，`run_subset_experiments.py` 會優先載入本地版本。

## 4.（可選）上傳 IPFS 並寫入鏈上
會針對 `outputs/` 內的壓縮檔逐一：
- 上傳 IPFS，取得 CID；
- 在 Ganache 部署簡單合約後，把 CID 寫入鏈上；
- 進行 CID 驗證。

```bash
python scripts/ipfs_batch.py \
  --inputs outputs \
  --ganache-url http://127.0.0.1:7545 \
  --ipfs-address /ip4/127.0.0.1/tcp/5001/http
```

## 5. TSN 評估（說明）
建議使用您已有的 `下載/KITTI/tsnkit-1/` 套件：
- 將 `outputs/compression_results_subset.csv` 取出每檔案的 `Num Packets` 與平均封包大小（或位元率）作為高優先級流量；
- 在 tsnkit 內設定 802.1Qbv 的 GCL 週期與時槽，預留高優先級窗，其餘為低優先級；
- 観察端到端延遲與抖動，並比較不同 BE（壓縮率）下的可排程性。

也可使用本專案提供的轉換器，直接生成 TSN 流量規格 CSV：
```bash
python scripts/tsn_generate_flows.py \
  --results-csv outputs/compression_results_subset.csv \
  --data-dir data \
  --frame-rate 10 \
  --packet-size-bits 1000 \
  --out outputs/tsn_flows.csv
```
欄位包含 `Bitrate_bps / PacketsPerFrame / PacketSize_bits / Priority` 等，可作為 tsnkit 的輸入來源。

## 6. 完整實驗腳本

### 6.1 快速測試腳本
用於驗證環境設定與流程是否正常：

```bash
./quick_test_experiment.sh
```

- 僅測試 2 個場景（campus、city）
- 每個場景測試 3 個檔案
- 執行時間約 1 分鐘
- 用於驗證壓縮、TSN、IPFS 流程

### 6.2 完整論文實驗腳本
使用全部 1140 個 KITTI LiDAR 檔案進行完整實驗：

```bash
./run_full_paper_experiment.sh
```

#### 實驗流程：
1. **數據集驗證**：掃描並驗證 KITTI 數據集完整性
2. **壓縮實驗**：對所有 1140 個檔案執行 7 種壓縮方法
3. **TSN 分析**：計算網路利用率與延遲
4. **IPFS 分析**：評估儲存空間與上傳時間節省
5. **生成報告**：產生完整 JSON 格式實驗報告

#### 輸出檔案：
- `outputs/compression_results_full_*.csv` - 所有壓縮測試結果
- `outputs/tsn_flows_*.csv` - TSN 流量配置
- `outputs/tsn_results/tsn_analysis_*.csv` - TSN 性能分析
- `outputs/ipfs_results/ipfs_analysis_*.csv` - IPFS 儲存分析
- `outputs/final_report_*.json` - 完整實驗報告

#### 執行時間：
- 完整實驗預計需要 30-60 分鐘（取決於硬體性能）
- 實驗結束後會詢問是否刪除壓縮產生的暫存檔案

### 6.3 自訂實驗參數
若要調整實驗參數，可編輯腳本中的變數：

```bash
# 編輯腳本
vim run_full_paper_experiment.sh

# 可調整參數：
MAX_FILES=-1        # 每個場景的檔案數（-1 表示全部）
BE_LIST="1.0"       # 誤差界限值（cm）
DAILY_HOURS=12      # 每日運行時數（用於 IPFS 計算）
UPLOAD_SPEED=10     # 上傳速度（Mbps，用於 IPFS 計算）
```

### 6.4 實驗結果驗證
執行以下命令檢查實驗結果：

```bash
# 查看壓縮統計
python3 -c "
import pandas as pd
df = pd.read_csv('outputs/compression_results_full_*.csv')
print(df.groupby('Method')['Compression Ratio'].agg(['mean', 'std', 'count']))
"

# 查看最終報告
python3 -c "
import json
with open('outputs/final_report_*.json', 'r') as f:
    report = json.load(f)
    print(json.dumps(report, indent=2))
"
```

## 7. 實驗數據說明

### 7.1 KITTI 數據集結構
```
/home/adlink/下載/KITTI/KITTI/
├── campus/      (186 檔案, 0.34 GB)
├── city/        (108 檔案, 0.20 GB)
├── person/      (68 檔案, 0.13 GB)
├── residential/ (481 檔案, 0.89 GB)
└── road/        (297 檔案, 0.53 GB)
總計: 1140 檔案, 2.09 GB
```

### 7.2 LiDAR 規格（Velodyne HDL-64E）
- **更新頻率**: 10 Hz（每秒 10 個 frame）
- **Frame 定義**: 1 個 frame = 360° 完整掃描 = 1 個 .bin 檔案
- **平均 Frame 大小**: 1.88 MB
- **數據率**: 150.4 Mbps

### 7.3 壓縮方法比較
| 方法 | 平均壓縮比 | 處理延遲(ms) |
|------|-----------|-------------|
| EB-HC-3D(Axis) | 0.2605 | 5.2 |
| EB-HC-3D(L2) | 0.2605 | 6.1 |
| EB-HC(Axis) | 0.3415 | 3.5 |
| EB-HC(L2) | 0.3481 | 4.1 |
| EB-Octree(Axis) | 0.5509 | 5.0 |
| EB-Octree(L2) | 0.5437 | 5.0 |
| Huffman | 0.6515 | 2.8 |

## 8. Git 初始化與推送
本專案已在本機初始化 Git。若要推送至 GitHub：

```bash
cd 宇翰論文
git init
git add .
git commit -m "first commit"
git branch -M main
git remote add origin https://github.com/r11525125/information_paper.git
# 推送需要 GitHub 權杖（PAT）。若未設定憑證，會提示輸入。
git push -u origin main
```

> 若環境無法直接連網或缺少權杖，請在本機終端自行執行上述命令並輸入 GitHub 個人存取權杖（PAT）。

## 9. 常見問題
- 找不到 `EBpapercopy2.py`：請確認它存在於 `下載/KITTI/`，或直接複製到 `scripts/`。
- 缺套件：依步驟 2 安裝相依套件。
- IPFS/鏈連線失敗：請確認本機 IPFS daemon 與 Ganache 正在執行，連線位址與埠正確。
