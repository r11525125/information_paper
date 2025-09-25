# 實驗腳本完整說明文件

## 概述
本文件詳細說明論文實驗腳本的使用方式、參數設定與預期結果。

## 腳本清單

### 1. 核心實驗腳本

#### `run_full_paper_experiment.sh`
**用途**: 執行完整論文實驗，使用全部 1140 個 KITTI LiDAR 檔案

**執行方式**:
```bash
./run_full_paper_experiment.sh
```

**主要步驟**:
1. 驗證 KITTI 數據集（1140 個檔案，2.09 GB）
2. 執行壓縮實驗（7 種方法 × 1140 檔案 = 7980 筆測試）
3. 合併壓縮結果
4. 生成 TSN 流量配置
5. 分析 TSN 網路性能
6. 計算 IPFS 儲存效益
7. 生成最終報告

**預期執行時間**: 30-60 分鐘

**輸出檔案**:
- `outputs/compression_results_full_TIMESTAMP.csv` - 合併的壓縮結果
- `outputs/tsn_flows_TIMESTAMP.csv` - TSN 流量配置
- `outputs/tsn_results/tsn_analysis_TIMESTAMP.csv` - TSN 性能分析
- `outputs/ipfs_results/ipfs_analysis_TIMESTAMP.csv` - IPFS 儲存分析
- `outputs/final_report_TIMESTAMP.json` - JSON 格式完整報告
- `outputs/experiment_TIMESTAMP.log` - 實驗執行紀錄

#### `quick_test_experiment.sh`
**用途**: 快速測試環境與流程是否正常

**執行方式**:
```bash
./quick_test_experiment.sh
```

**測試範圍**:
- 2 個場景（campus、city）
- 每個場景 3 個檔案
- 總計 42 筆壓縮測試

**預期執行時間**: 1-2 分鐘

**用於驗證**:
- Python 環境設定
- 壓縮演算法功能
- 數據路徑正確性
- 輸出格式

### 2. Python 實驗腳本

#### `complete_corrected_experiment.py`
**用途**: 完整實驗的 Python 實作版本

**執行方式**:
```bash
python complete_corrected_experiment.py
```

**類別結構**:
```python
class CompleteKITTIExperiment:
    def verify_kitti_dataset()    # 驗證數據集
    def run_real_compression()     # 執行壓縮
    def analyze_tsn_performance()  # TSN 分析
    def analyze_ipfs_storage()     # IPFS 分析
    def generate_final_report()    # 生成報告
```

**可調整參數**:
```python
lidar_specs = {
    'frame_rate': 10,           # Hz
    'frame_period_ms': 100,     # ms
    'avg_frame_size_mb': 1.88   # MB
}

compression_delays = {
    'Huffman': 2.8,             # ms
    'EB-HC(Axis)': 3.5,
    'EB-HC(L2)': 4.1,
    # ...
}
```

### 3. 分析腳本

#### `analyze_compression_latency_tradeoff.py`
**用途**: 分析壓縮造成的延遲權衡

**關鍵分析**:
- 為何 TSN 中壓縮反而降低總延遲
- 不同網路速度下的壓縮效益
- 多車輛場景的頻寬需求

#### `explain_network_utilization.py`
**用途**: 詳細解釋網路利用率計算方式

**計算公式**:
```
網路利用率 = (幀率 × 幀大小 × 8) / 網路頻寬 × 100%
```

## 參數調整指南

### 壓縮實驗參數

編輯 `run_full_paper_experiment.sh`:

```bash
# 場景列表
SCENES=("campus" "city" "person" "residential" "road")

# 每個場景的檔案數
MAX_FILES=-1  # -1 表示全部，可改為具體數字如 10

# 誤差界限值（cm）
BE_LIST="1.0"  # 可改為 "0.5 1.0 2.0" 測試多個值
```

### TSN 網路參數

```bash
# 網路頻寬設定
TSN_BANDWIDTH=1000    # Mbps
ETH_BANDWIDTH=100     # Mbps

# LiDAR 參數
FRAME_RATE=10         # Hz
FRAME_SIZE_MB=1.88    # MB
```

### IPFS 儲存參數

```bash
# 年度運行參數
DAILY_HOURS=12        # 每日運行小時數
DAYS_PER_YEAR=365     # 年度天數

# 網路參數
UPLOAD_SPEED_MBPS=10  # 上傳速度
```

## 實驗結果驗證

### 驗證壓縮結果

```python
import pandas as pd

# 載入壓縮結果
df = pd.read_csv('outputs/compression_results_full_*.csv')

# 檢查數據完整性
print(f"總記錄數: {len(df)}")
print(f"場景數: {df['Scene'].nunique()}")
print(f"方法數: {df['Method'].nunique()}")

# 統計壓縮比
stats = df.groupby('Method')['Compression Ratio'].agg(['mean', 'std', 'count'])
print(stats)
```

### 驗證 TSN 分析

```python
# 載入 TSN 結果
tsn_df = pd.read_csv('outputs/tsn_results/tsn_analysis_*.csv')

# 檢查網路利用率
for _, row in tsn_df.iterrows():
    print(f"{row['Method']:20s}: {row['Network_Utilization_%']:.1f}%")

# 驗證延遲計算
uncompressed = tsn_df[tsn_df['Method'] == 'Uncompressed']
print(f"未壓縮延遲: {uncompressed['Total_Latency_ms'].iloc[0]:.2f} ms")
```

### 驗證最終報告

```python
import json

# 載入報告
with open('outputs/final_report_*.json', 'r') as f:
    report = json.load(f)

# 關鍵指標
print(f"壓縮測試數: {report['compression']['total_records']}")
print(f"最佳壓縮法: {report['compression']['methods']}")
print(f"TSN延遲改善: {report['tsn']['best_latency_ms']:.2f} ms")
print(f"IPFS儲存節省: {report['ipfs']['best_savings_%']:.1f}%")
```

## 故障排除

### 常見錯誤

1. **找不到 KITTI 數據**
```
錯誤: 場景 campus 不存在!
解決: 確認路徑 /home/adlink/下載/KITTI/KITTI/ 存在
```

2. **Python 套件缺失**
```
錯誤: ModuleNotFoundError: No module named 'pandas'
解決: source .venv/bin/activate && pip install pandas
```

3. **權限錯誤**
```
錯誤: Permission denied
解決: chmod +x *.sh
```

4. **記憶體不足**
```
錯誤: MemoryError
解決: 減少 MAX_FILES 參數或分批執行
```

### 偵錯模式

啟用詳細輸出：
```bash
# 編輯腳本，加入
set -x  # 顯示執行的每個命令

# 或執行時
bash -x ./run_full_paper_experiment.sh
```

## 性能優化建議

### 加速壓縮實驗

1. **平行處理**（需修改腳本）:
```bash
# 同時處理多個場景
for scene in "${SCENES[@]}"; do
    process_scene "$scene" &
done
wait
```

2. **減少檔案數**:
```bash
MAX_FILES=100  # 每個場景只測試 100 個檔案
```

3. **使用 SSD**:
確保 KITTI 數據集存放在 SSD 而非 HDD

### 記憶體管理

對於大量檔案，可分批處理：
```python
# 分批載入 CSV
chunk_size = 1000
for chunk in pd.read_csv(file, chunksize=chunk_size):
    process(chunk)
```

## 實驗數據備份

建議定期備份實驗結果：
```bash
# 備份腳本
tar -czf experiment_backup_$(date +%Y%m%d).tar.gz \
    outputs/*.csv \
    outputs/*.json \
    outputs/*.log

# 同步到遠端
rsync -av outputs/ backup_server:/path/to/backup/
```

## 引用格式

若使用本實驗腳本，請引用：
```bibtex
@misc{kitti_lidar_compression,
  title={KITTI LiDAR Compression Experiments},
  author={Yu-Han},
  year={2025},
  howpublished={\url{https://github.com/r11525125/information_paper}}
}
```

## 聯絡資訊

如有問題或建議，請透過以下方式聯絡：
- GitHub Issues: https://github.com/r11525125/information_paper/issues
- Email: [您的電子郵件]

---

*最後更新: 2025-09-25*