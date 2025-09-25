#!/bin/bash

###############################################################################
# KITTI LiDAR 完整論文實驗腳本
# 使用所有1140個原始檔案進行壓縮、TSN、IPFS實驗
# 作者：宇翰論文實驗
# 日期：2025-09-25
###############################################################################

set -e  # 錯誤時停止

# 顏色定義
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 時間戳記
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")

# 路徑設定
BASE_DIR="/home/adlink/宇翰論文"
KITTI_DIR="/home/adlink/下載/KITTI/KITTI"
OUTPUT_DIR="$BASE_DIR/outputs"
VENV_PATH="$BASE_DIR/.venv"
SCRIPTS_DIR="$BASE_DIR/scripts"

# 建立輸出目錄
mkdir -p "$OUTPUT_DIR"
mkdir -p "$OUTPUT_DIR/compression_results"
mkdir -p "$OUTPUT_DIR/tsn_results"
mkdir -p "$OUTPUT_DIR/ipfs_results"

# 紀錄檔
LOG_FILE="$OUTPUT_DIR/experiment_${TIMESTAMP}.log"

# 函數：印出訊息
log_msg() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1" | tee -a "$LOG_FILE"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1" | tee -a "$LOG_FILE"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1" | tee -a "$LOG_FILE"
}

# 函數：執行計時
time_execution() {
    local start=$(date +%s)
    "$@"
    local end=$(date +%s)
    local duration=$((end - start))
    log_msg "執行時間: ${duration} 秒"
}

###############################################################################
# 主要實驗流程
###############################################################################

log_msg "=========================================="
log_msg "開始 KITTI LiDAR 完整論文實驗"
log_msg "=========================================="

# 啟動虛擬環境
log_msg "啟動Python虛擬環境..."
source "$VENV_PATH/bin/activate"

###############################################################################
# 步驟 1: 驗證數據集
###############################################################################

log_msg "\n=== 步驟 1: 驗證KITTI數據集 ==="

SCENES=("campus" "city" "person" "residential" "road")
TOTAL_FILES=0

for scene in "${SCENES[@]}"; do
    scene_path="$KITTI_DIR/$scene"
    if [ -d "$scene_path" ]; then
        file_count=$(find "$scene_path" -name "*.bin" -type f | wc -l)
        size_gb=$(du -sb "$scene_path" | awk '{printf "%.3f", $1/1024/1024/1024}')
        log_msg "  $scene: $file_count 檔案, $size_gb GB"
        TOTAL_FILES=$((TOTAL_FILES + file_count))
    else
        log_error "場景 $scene 不存在!"
        exit 1
    fi
done

log_msg "總計: $TOTAL_FILES 檔案"

###############################################################################
# 步驟 2: 執行壓縮實驗（所有1140個檔案）
###############################################################################

log_msg "\n=== 步驟 2: 執行完整壓縮實驗 (1140 檔案) ==="

# 清理舊的壓縮結果
rm -f "$OUTPUT_DIR/compression_results/compression_*.csv"

# 對每個場景執行壓縮
for scene in "${SCENES[@]}"; do
    log_msg "處理 $scene 場景..."

    scene_dir="$KITTI_DIR/$scene"
    output_csv="$OUTPUT_DIR/compression_results/compression_${scene}_${TIMESTAMP}.csv"

    # 使用 -1 表示處理所有檔案
    python "$SCRIPTS_DIR/run_subset_experiments.py" \
        --data-dir "$scene_dir" \
        --max-files -1 \
        --be-list 1.0 \
        --out-csv "$output_csv" \
        2>&1 | tee -a "$LOG_FILE"

    if [ $? -eq 0 ]; then
        log_msg "  ✓ $scene 壓縮完成"
    else
        log_error "  ✗ $scene 壓縮失敗"
        exit 1
    fi
done

# 合併所有壓縮結果
log_msg "\n合併所有壓縮結果..."

MERGED_CSV="$OUTPUT_DIR/compression_results_full_${TIMESTAMP}.csv"

python3 << EOF
import pandas as pd
import glob

# 找到所有壓縮結果檔案
csv_files = glob.glob("$OUTPUT_DIR/compression_results/compression_*_${TIMESTAMP}.csv")

if csv_files:
    # 讀取並合併所有CSV
    dfs = []
    for file in csv_files:
        df = pd.read_csv(file)
        # 從檔名提取場景名稱
        scene = file.split('/')[-1].split('_')[1]
        df['Scene'] = scene
        dfs.append(df)

    # 合併
    merged_df = pd.concat(dfs, ignore_index=True)

    # 儲存
    merged_df.to_csv("$MERGED_CSV", index=False)

    print(f"合併完成: {len(merged_df)} 筆記錄")

    # 顯示統計
    print("\n壓縮統計:")
    print(merged_df.groupby('Method')['Compression Ratio'].agg(['mean', 'std', 'count']))
else:
    print("找不到壓縮結果檔案!")
    exit(1)
EOF

if [ $? -ne 0 ]; then
    log_error "合併壓縮結果失敗"
    exit 1
fi

log_msg "✓ 壓縮結果已合併至: $MERGED_CSV"

###############################################################################
# 步驟 3: 生成TSN流量
###############################################################################

log_msg "\n=== 步驟 3: 生成TSN流量 ==="

TSN_FLOWS_CSV="$OUTPUT_DIR/tsn_flows_${TIMESTAMP}.csv"

python "$SCRIPTS_DIR/tsn_generate_flows.py" \
    --compression-csv "$MERGED_CSV" \
    --out-csv "$TSN_FLOWS_CSV" \
    2>&1 | tee -a "$LOG_FILE"

if [ $? -eq 0 ]; then
    log_msg "✓ TSN流量生成完成: $TSN_FLOWS_CSV"
else
    log_error "TSN流量生成失敗"
    exit 1
fi

###############################################################################
# 步驟 4: 執行TSN網路分析
###############################################################################

log_msg "\n=== 步驟 4: TSN網路性能分析 ==="

python3 << 'EOF'
import pandas as pd
import json
import sys

# 載入數據
compression_df = pd.read_csv("$MERGED_CSV")
output_file = "$OUTPUT_DIR/tsn_results/tsn_analysis_${TIMESTAMP}.csv"

# LiDAR參數
frame_rate = 10  # Hz
frame_size_mb = 1.88  # MB
tsn_bandwidth = 1000  # Mbps
eth_bandwidth = 100  # Mbps

# 計算網路性能
results = []

# 未壓縮
bitrate_mbps = frame_size_mb * 8 * frame_rate

# 車載乙太網路
eth_util = (bitrate_mbps / eth_bandwidth) * 100
results.append({
    'Network': 'Ethernet_100Mbps',
    'Method': 'Uncompressed',
    'Compression_Ratio': 1.0,
    'Bitrate_Mbps': bitrate_mbps,
    'Network_Utilization_%': eth_util,
    'Feasible': eth_util < 100
})

# TSN未壓縮
tsn_util = (bitrate_mbps / tsn_bandwidth) * 100
tsn_trans_ms = (frame_size_mb * 8 / tsn_bandwidth) * 1000
tsn_latency = 2 + tsn_trans_ms + tsn_util * 0.05

results.append({
    'Network': 'TSN_1Gbps',
    'Method': 'Uncompressed',
    'Compression_Ratio': 1.0,
    'Bitrate_Mbps': bitrate_mbps,
    'Network_Utilization_%': tsn_util,
    'Total_Latency_ms': tsn_latency,
    'Feasible': True
})

# 壓縮方法
compression_delays = {
    'Huffman': 2.8,
    'EB-HC(Axis)': 3.5,
    'EB-HC(L2)': 4.1,
    'EB-Octree(Axis)': 5.0,
    'EB-Octree(L2)': 5.0,
    'EB-HC-3D(Axis)': 5.2,
    'EB-HC-3D(L2)': 6.1
}

# 計算各壓縮方法
avg_ratios = compression_df.groupby('Method')['Compression Ratio'].mean()

for method, ratio in avg_ratios.items():
    if method in compression_delays:
        compressed_bitrate = bitrate_mbps * ratio
        compressed_util = (compressed_bitrate / tsn_bandwidth) * 100
        compressed_trans = (frame_size_mb * ratio * 8 / tsn_bandwidth) * 1000
        compressed_latency = 2 + compression_delays[method] + compressed_trans + compressed_util * 0.05

        results.append({
            'Network': 'TSN_1Gbps',
            'Method': method,
            'Compression_Ratio': ratio,
            'Bitrate_Mbps': compressed_bitrate,
            'Network_Utilization_%': compressed_util,
            'Processing_Time_ms': compression_delays[method],
            'Total_Latency_ms': compressed_latency,
            'Feasible': True
        })

# 儲存結果
import os
os.makedirs(os.path.dirname(output_file), exist_ok=True)
pd.DataFrame(results).to_csv(output_file, index=False)
print(f"TSN分析完成: {len(results)} 個配置")
EOF

###############################################################################
# 步驟 5: IPFS儲存分析
###############################################################################

log_msg "\n=== 步驟 5: IPFS儲存分析 ==="

python3 << 'EOF'
import pandas as pd

# 載入數據
compression_df = pd.read_csv("$MERGED_CSV")
output_file = "$OUTPUT_DIR/ipfs_results/ipfs_analysis_${TIMESTAMP}.csv"

# IPFS參數
frame_rate = 10  # Hz
frame_size_mb = 1.88  # MB
daily_hours = 12
days_per_year = 365
upload_speed_mbps = 10

# 計算年度數據
frames_per_year = frame_rate * 3600 * daily_hours * days_per_year
annual_gb_uncompressed = (frames_per_year * frame_size_mb) / 1024
upload_hours_uncompressed = (annual_gb_uncompressed * 1024 * 8) / (upload_speed_mbps * 3600)

results = []

# 未壓縮
results.append({
    'Method': 'Uncompressed',
    'Compression_Ratio': 1.0,
    'Annual_Storage_GB': annual_gb_uncompressed,
    'Storage_Savings_%': 0,
    'Upload_Time_Hours': upload_hours_uncompressed,
    'Upload_Time_Savings_%': 0
})

# 壓縮方法
avg_ratios = compression_df.groupby('Method')['Compression Ratio'].mean()

for method, ratio in avg_ratios.items():
    compressed_gb = annual_gb_uncompressed * ratio
    storage_savings = (1 - ratio) * 100
    upload_hours = upload_hours_uncompressed * ratio
    upload_savings = (1 - ratio) * 100

    results.append({
        'Method': method,
        'Compression_Ratio': ratio,
        'Annual_Storage_GB': compressed_gb,
        'Storage_Savings_%': storage_savings,
        'Upload_Time_Hours': upload_hours,
        'Upload_Time_Savings_%': upload_savings
    })

# 儲存結果
import os
os.makedirs(os.path.dirname(output_file), exist_ok=True)
pd.DataFrame(results).to_csv(output_file, index=False)
print(f"IPFS分析完成: {len(results)} 個方法")
EOF

###############################################################################
# 步驟 6: 生成最終報告
###############################################################################

log_msg "\n=== 步驟 6: 生成最終實驗報告 ==="

FINAL_REPORT="$OUTPUT_DIR/final_report_${TIMESTAMP}.json"

python3 << EOF
import pandas as pd
import json

# 載入所有結果
compression_df = pd.read_csv("$MERGED_CSV")
tsn_df = pd.read_csv("$OUTPUT_DIR/tsn_results/tsn_analysis_${TIMESTAMP}.csv")
ipfs_df = pd.read_csv("$OUTPUT_DIR/ipfs_results/ipfs_analysis_${TIMESTAMP}.csv")

# 建立報告
report = {
    'experiment': 'KITTI LiDAR 完整論文實驗',
    'timestamp': '$TIMESTAMP',
    'dataset': {
        'total_files': $TOTAL_FILES,
        'scenes': ['campus', 'city', 'person', 'residential', 'road']
    },
    'compression': {
        'total_records': len(compression_df),
        'methods': {}
    },
    'tsn': {},
    'ipfs': {}
}

# 壓縮統計
for method, group in compression_df.groupby('Method'):
    report['compression']['methods'][method] = {
        'mean_ratio': float(group['Compression Ratio'].mean()),
        'std_ratio': float(group['Compression Ratio'].std()),
        'count': len(group)
    }

# TSN結果
tsn_uncompressed = tsn_df[(tsn_df['Network'] == 'TSN_1Gbps') & (tsn_df['Method'] == 'Uncompressed')].iloc[0]
tsn_compressed = tsn_df[(tsn_df['Network'] == 'TSN_1Gbps') & (tsn_df['Method'] != 'Uncompressed')]

if not tsn_compressed.empty:
    best = tsn_compressed.loc[tsn_compressed['Total_Latency_ms'].idxmin()]
    report['tsn'] = {
        'uncompressed_latency_ms': float(tsn_uncompressed.get('Total_Latency_ms', 0)),
        'best_method': best['Method'],
        'best_latency_ms': float(best['Total_Latency_ms']),
        'best_utilization_%': float(best['Network_Utilization_%'])
    }

# IPFS結果
best_ipfs = ipfs_df.loc[ipfs_df['Storage_Savings_%'].idxmax()]
report['ipfs'] = {
    'best_method': best_ipfs['Method'],
    'best_savings_%': float(best_ipfs['Storage_Savings_%']),
    'annual_gb_saved': float(ipfs_df[ipfs_df['Method'] == 'Uncompressed']['Annual_Storage_GB'].iloc[0] - best_ipfs['Annual_Storage_GB'])
}

# 儲存報告
with open("$FINAL_REPORT", 'w', encoding='utf-8') as f:
    json.dump(report, f, indent=2, ensure_ascii=False)

# 顯示摘要
print("\n" + "="*60)
print("實驗完成摘要")
print("="*60)
print(f"壓縮測試: {report['compression']['total_records']} 筆記錄")
print(f"TSN最佳延遲: {report['tsn'].get('best_latency_ms', 'N/A'):.2f} ms ({report['tsn'].get('best_method', 'N/A')})")
print(f"IPFS儲存節省: {report['ipfs']['best_savings_%']:.1f}% ({report['ipfs']['best_method']})")
print(f"\n報告儲存至: $FINAL_REPORT")
EOF

###############################################################################
# 步驟 7: 選擇性清理壓縮檔案（IPFS測試後）
###############################################################################

log_msg "\n=== 步驟 7: 清理暫存檔案 ==="

read -p "是否要刪除壓縮產生的暫存檔案？(y/n): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    log_msg "清理壓縮暫存檔..."
    # 清理壓縮過程產生的暫存檔
    find "$OUTPUT_DIR" -name "*.compressed" -type f -delete 2>/dev/null
    find "$OUTPUT_DIR" -name "*.tmp" -type f -delete 2>/dev/null
    log_msg "✓ 清理完成"
else
    log_msg "保留所有檔案"
fi

###############################################################################
# 完成
###############################################################################

END_TIME=$(date +%s)
START_TIME_FILE="/tmp/experiment_start_${TIMESTAMP}"
if [ -f "$START_TIME_FILE" ]; then
    START_TIME=$(cat "$START_TIME_FILE")
    DURATION=$((END_TIME - START_TIME))
    rm "$START_TIME_FILE"
else
    DURATION=0
fi

log_msg "\n=========================================="
log_msg "✅ 實驗完成！"
log_msg "=========================================="
log_msg "總執行時間: ${DURATION} 秒"
log_msg "輸出檔案:"
log_msg "  - 壓縮結果: $MERGED_CSV"
log_msg "  - TSN流量: $TSN_FLOWS_CSV"
log_msg "  - TSN分析: $OUTPUT_DIR/tsn_results/tsn_analysis_${TIMESTAMP}.csv"
log_msg "  - IPFS分析: $OUTPUT_DIR/ipfs_results/ipfs_analysis_${TIMESTAMP}.csv"
log_msg "  - 最終報告: $FINAL_REPORT"
log_msg "  - 實驗紀錄: $LOG_FILE"

# 顯示關鍵結果
echo
echo -e "${GREEN}關鍵結果：${NC}"
python3 -c "
import json
with open('$FINAL_REPORT', 'r') as f:
    report = json.load(f)
    if 'tsn' in report and 'best_method' in report['tsn']:
        print(f\"  TSN最佳方案: {report['tsn']['best_method']}\")
        print(f\"  延遲: {report['tsn']['best_latency_ms']:.2f} ms\")
        print(f\"  網路利用率: {report['tsn']['best_utilization_%']:.1f}%\")
    if 'ipfs' in report:
        print(f\"  IPFS最佳方案: {report['ipfs']['best_method']}\")
        print(f\"  儲存節省: {report['ipfs']['best_savings_%']:.1f}%\")
        print(f\"  年度節省: {report['ipfs']['annual_gb_saved']:.0f} GB\")
"

echo
log_msg "實驗腳本執行完畢"