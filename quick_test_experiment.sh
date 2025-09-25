#!/bin/bash

###############################################################################
# KITTI LiDAR 快速測試腳本
# 用少量檔案測試流程是否正常
###############################################################################

set -e

# 顏色定義
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}=== 快速測試模式 ===${NC}"
echo "每個場景只測試3個檔案"

# 路徑設定
BASE_DIR="/home/adlink/宇翰論文"
KITTI_DIR="/home/adlink/下載/KITTI/KITTI"
OUTPUT_DIR="$BASE_DIR/outputs/quick_test"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")

mkdir -p "$OUTPUT_DIR"

# 啟動虛擬環境
source "$BASE_DIR/.venv/bin/activate"

# 1. 快速壓縮測試
echo -e "\n${GREEN}步驟1: 壓縮測試${NC}"

SCENES=("campus" "city")  # 只測試2個場景
MAX_FILES=3  # 每個場景3個檔案

for scene in "${SCENES[@]}"; do
    echo "處理 $scene..."
    python "$BASE_DIR/scripts/run_subset_experiments.py" \
        --data-dir "$KITTI_DIR/$scene" \
        --max-files $MAX_FILES \
        --be-list 1.0 \
        --out-csv "$OUTPUT_DIR/compression_${scene}_test.csv"
done

# 2. 合併結果
echo -e "\n${GREEN}步驟2: 合併結果${NC}"

python3 << EOF
import pandas as pd
import glob

csvs = glob.glob("$OUTPUT_DIR/compression_*_test.csv")
if csvs:
    dfs = [pd.read_csv(f) for f in csvs]
    merged = pd.concat(dfs, ignore_index=True)
    merged.to_csv("$OUTPUT_DIR/merged_test.csv", index=False)
    print(f"合併 {len(merged)} 筆記錄")
    print("\n壓縮比統計:")
    print(merged.groupby('Method')['Compression Ratio'].mean())
EOF

# 3. TSN分析
echo -e "\n${GREEN}步驟3: TSN分析${NC}"

python3 << EOF
import pandas as pd

df = pd.read_csv("$OUTPUT_DIR/merged_test.csv")
avg_ratios = df.groupby('Method')['Compression Ratio'].mean()

print("TSN網路利用率:")
frame_size = 1.88  # MB
frame_rate = 10  # Hz
bitrate = frame_size * 8 * frame_rate

print(f"未壓縮: {bitrate:.1f} Mbps → {bitrate/1000*100:.1f}% (TSN)")

for method, ratio in avg_ratios.items():
    compressed_bitrate = bitrate * ratio
    util = compressed_bitrate / 1000 * 100
    print(f"{method}: {compressed_bitrate:.1f} Mbps → {util:.1f}% (TSN)")
EOF

echo -e "\n${GREEN}✅ 快速測試完成！${NC}"
echo "如果測試正常，請執行："
echo "  ./run_full_paper_experiment.sh"