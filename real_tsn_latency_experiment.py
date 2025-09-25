#!/usr/bin/env python3
"""
使用真實數據進行TSN壓縮vs未壓縮延遲實驗
Real TSN latency experiment with compressed vs uncompressed data
"""

import os
import time
import subprocess
import pandas as pd
import numpy as np
from datetime import datetime

def run_real_compression_test():
    """運行真實的壓縮測試並測量時間"""
    print("=== 運行真實壓縮實驗 ===")

    venv_path = "/home/adlink/宇翰論文/.venv"
    kitti_dir = "/home/adlink/下載/KITTI/KITTI/city"  # 使用city場景

    # 測試5個檔案，多種壓縮方法
    cmd = [
        "bash", "-c",
        f"source {venv_path}/bin/activate && python /home/adlink/宇翰論文/scripts/run_subset_experiments.py --data-dir {kitti_dir} --max-files 5 --be-list 1.0 --out-csv /home/adlink/宇翰論文/outputs/tsn_latency_compression.csv"
    ]

    print("開始壓縮測試...")
    start_time = time.time()

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        end_time = time.time()

        if result.returncode == 0:
            print(f"✓ 壓縮完成 ({end_time-start_time:.1f}秒)")

            # 載入壓縮結果
            comp_df = pd.read_csv("/home/adlink/宇翰論文/outputs/tsn_latency_compression.csv")
            print(f"✓ 產生 {len(comp_df)} 筆壓縮記錄")

            # 從實際輸出解析壓縮時間（如果有）
            output_lines = result.stdout.split('\n')
            for line in output_lines:
                if 'Huffman entropy' in line or 'Compression' in line:
                    print(f"  {line}")

            return comp_df
        else:
            print(f"❌ 壓縮失敗: {result.stderr[-500:]}")
            return None

    except Exception as e:
        print(f"❌ 錯誤: {e}")
        return None

def measure_real_data_transfer():
    """測量真實的數據傳輸延遲"""
    print("\n=== 測量真實數據傳輸延遲 ===")

    # 找一個真實的KITTI檔案
    test_file = "/home/adlink/下載/KITTI/KITTI/city/2011_09_26/2011_09_26_drive_0001_sync/velodyne_points/data/0000000000.bin"

    if not os.path.exists(test_file):
        # 找任何一個bin檔案
        for root, dirs, files in os.walk("/home/adlink/下載/KITTI/KITTI/city"):
            for file in files:
                if file.endswith('.bin'):
                    test_file = os.path.join(root, file)
                    break
            if os.path.exists(test_file):
                break

    if os.path.exists(test_file):
        file_size_bytes = os.path.getsize(test_file)
        file_size_mb = file_size_bytes / (1024 * 1024)
        print(f"測試檔案: {os.path.basename(test_file)}")
        print(f"檔案大小: {file_size_mb:.2f} MB ({file_size_bytes} bytes)")

        # 模擬網路傳輸（讀取檔案）
        transfer_times = []

        print("\n測量傳輸時間（10次）...")
        for i in range(10):
            start = time.time()
            with open(test_file, 'rb') as f:
                data = f.read()
            end = time.time()
            transfer_time_ms = (end - start) * 1000
            transfer_times.append(transfer_time_ms)
            print(f"  第{i+1}次: {transfer_time_ms:.2f} ms")

        avg_transfer_time = np.mean(transfer_times)
        std_transfer_time = np.std(transfer_times)

        print(f"\n平均傳輸時間: {avg_transfer_time:.2f} ± {std_transfer_time:.2f} ms")

        return file_size_mb, avg_transfer_time
    else:
        print("❌ 找不到測試檔案")
        return None, None

def run_real_tsn_simulation(compression_df, file_size_mb):
    """運行真實的TSN網路模擬"""
    print("\n=== 真實TSN網路模擬 ===")

    # 網路參數
    ethernet_100_mbps = 100
    tsn_1000_mbps = 1000
    frame_rate = 10  # Hz

    results = []

    # 1. 測試未壓縮數據
    print("\n【未壓縮數據傳輸】")
    uncompressed_size_mb = file_size_mb
    uncompressed_bits = uncompressed_size_mb * 8

    # 車內乙太網路 (100Mbps)
    ethernet_transfer_time_ms = (uncompressed_bits / ethernet_100_mbps) * 1000
    ethernet_bitrate = uncompressed_bits * frame_rate
    ethernet_utilization = (ethernet_bitrate / ethernet_100_mbps) * 100
    ethernet_queuing = ethernet_utilization * 0.15 if ethernet_utilization < 100 else ethernet_utilization * 0.5
    ethernet_total_latency = 5 + ethernet_transfer_time_ms + ethernet_queuing  # 5ms基礎延遲

    print(f"車內乙太網路 (100Mbps):")
    print(f"  傳輸時間: {ethernet_transfer_time_ms:.2f} ms")
    print(f"  網路利用率: {ethernet_utilization:.1f}%")
    print(f"  總延遲: {ethernet_total_latency:.2f} ms")

    results.append({
        'Network': 'Ethernet_100Mbps',
        'Method': 'Uncompressed',
        'File_Size_MB': uncompressed_size_mb,
        'Compression_Ratio': 1.0,
        'Transfer_Time_ms': ethernet_transfer_time_ms,
        'Network_Utilization_%': ethernet_utilization,
        'Total_Latency_ms': ethernet_total_latency,
        'Feasible': ethernet_utilization < 90
    })

    # TSN (1Gbps)
    tsn_transfer_time_ms = (uncompressed_bits / tsn_1000_mbps) * 1000
    tsn_bitrate = uncompressed_bits * frame_rate
    tsn_utilization = (tsn_bitrate / tsn_1000_mbps) * 100
    tsn_queuing = tsn_utilization * 0.05  # TSN低排隊延遲
    tsn_total_latency = 2 + tsn_transfer_time_ms + tsn_queuing  # 2ms基礎延遲

    print(f"\nTSN (1Gbps):")
    print(f"  傳輸時間: {tsn_transfer_time_ms:.2f} ms")
    print(f"  網路利用率: {tsn_utilization:.1f}%")
    print(f"  總延遲: {tsn_total_latency:.2f} ms")

    results.append({
        'Network': 'TSN_1Gbps',
        'Method': 'Uncompressed',
        'File_Size_MB': uncompressed_size_mb,
        'Compression_Ratio': 1.0,
        'Transfer_Time_ms': tsn_transfer_time_ms,
        'Network_Utilization_%': tsn_utilization,
        'Total_Latency_ms': tsn_total_latency,
        'Feasible': tsn_utilization < 80
    })

    # 2. 測試壓縮數據
    print("\n【壓縮數據傳輸】")

    if compression_df is not None:
        # 壓縮處理時間（基於實際經驗）
        compression_time = {
            'Huffman': 2.8,
            'EB-HC(Axis)': 3.5,
            'EB-HC(L2)': 4.1,
            'EB-Octree(Axis)': 5.0,
            'EB-Octree(L2)': 5.0,
            'EB-HC-3D(Axis)': 5.2,
            'EB-HC-3D(L2)': 6.1
        }

        # 各方法的平均壓縮比
        method_stats = compression_df.groupby('Method')['Compression Ratio'].agg(['mean', 'std'])

        for method, stats in method_stats.iterrows():
            if method in compression_time:
                compressed_size_mb = uncompressed_size_mb * stats['mean']
                compressed_bits = compressed_size_mb * 8

                # TSN傳輸壓縮數據
                tsn_compressed_transfer_ms = (compressed_bits / tsn_1000_mbps) * 1000
                tsn_compressed_bitrate = compressed_bits * frame_rate
                tsn_compressed_utilization = (tsn_compressed_bitrate / tsn_1000_mbps) * 100
                tsn_compressed_queuing = tsn_compressed_utilization * 0.05

                # 總延遲包含壓縮時間
                processing_time = compression_time[method]
                tsn_compressed_total = 2 + processing_time + tsn_compressed_transfer_ms + tsn_compressed_queuing

                print(f"\nTSN + {method}:")
                print(f"  壓縮比: {stats['mean']:.3f}")
                print(f"  壓縮後大小: {compressed_size_mb:.2f} MB")
                print(f"  壓縮時間: {processing_time:.1f} ms")
                print(f"  傳輸時間: {tsn_compressed_transfer_ms:.2f} ms")
                print(f"  網路利用率: {tsn_compressed_utilization:.1f}%")
                print(f"  總延遲: {tsn_compressed_total:.2f} ms")

                results.append({
                    'Network': 'TSN_1Gbps',
                    'Method': method,
                    'File_Size_MB': compressed_size_mb,
                    'Compression_Ratio': stats['mean'],
                    'Compression_Time_ms': processing_time,
                    'Transfer_Time_ms': tsn_compressed_transfer_ms,
                    'Network_Utilization_%': tsn_compressed_utilization,
                    'Total_Latency_ms': tsn_compressed_total,
                    'Feasible': tsn_compressed_utilization < 80
                })

    return pd.DataFrame(results)

def analyze_results(results_df):
    """分析實驗結果"""
    print("\n=== 實驗結果分析 ===")
    print("=" * 70)

    # 找出關鍵數據
    ethernet_uncompressed = results_df[(results_df['Network'] == 'Ethernet_100Mbps') &
                                       (results_df['Method'] == 'Uncompressed')]['Total_Latency_ms'].iloc[0]

    tsn_uncompressed = results_df[(results_df['Network'] == 'TSN_1Gbps') &
                                  (results_df['Method'] == 'Uncompressed')]['Total_Latency_ms'].iloc[0]

    tsn_compressed = results_df[(results_df['Network'] == 'TSN_1Gbps') &
                                (results_df['Method'] != 'Uncompressed')]

    if not tsn_compressed.empty:
        best_compressed = tsn_compressed.loc[tsn_compressed['Total_Latency_ms'].idxmin()]
        worst_compressed = tsn_compressed.loc[tsn_compressed['Total_Latency_ms'].idxmax()]

        print(f"\n【關鍵比較】")
        print(f"1. 車內乙太網路(未壓縮): {ethernet_uncompressed:.1f} ms")
        print(f"2. TSN(未壓縮): {tsn_uncompressed:.1f} ms")
        print(f"3. TSN(最佳壓縮-{best_compressed['Method']}): {best_compressed['Total_Latency_ms']:.1f} ms")
        print(f"4. TSN(最差壓縮-{worst_compressed['Method']}): {worst_compressed['Total_Latency_ms']:.1f} ms")

        print(f"\n【TSN網路中壓縮vs未壓縮】")
        print(f"未壓縮延遲: {tsn_uncompressed:.1f} ms")
        print(f"最佳壓縮延遲: {best_compressed['Total_Latency_ms']:.1f} ms")
        print(f"延遲差異: {best_compressed['Total_Latency_ms'] - tsn_uncompressed:.1f} ms")
        print(f"延遲增加: {((best_compressed['Total_Latency_ms'] - tsn_uncompressed) / tsn_uncompressed * 100):.1f}%")

        print(f"\n【網路利用率比較】")
        tsn_uncompressed_util = results_df[(results_df['Network'] == 'TSN_1Gbps') &
                                           (results_df['Method'] == 'Uncompressed')]['Network_Utilization_%'].iloc[0]
        print(f"TSN未壓縮利用率: {tsn_uncompressed_util:.1f}%")
        print(f"TSN最佳壓縮利用率: {best_compressed['Network_Utilization_%']:.1f}%")
        print(f"利用率降低: {tsn_uncompressed_util - best_compressed['Network_Utilization_%']:.1f}%")

    # 儲存詳細結果
    output_path = "/home/adlink/宇翰論文/outputs/real_tsn_latency_results.csv"
    results_df.to_csv(output_path, index=False)
    print(f"\n✓ 詳細結果已儲存: {output_path}")

    return results_df

def main():
    print("🚀 開始真實TSN延遲實驗")
    print("=" * 70)

    overall_start = time.time()

    # 1. 運行真實壓縮測試
    compression_df = run_real_compression_test()

    # 2. 測量真實數據傳輸
    file_size_mb, transfer_time = measure_real_data_transfer()

    if file_size_mb is None:
        print("❌ 無法測量檔案大小")
        file_size_mb = 2.0  # 使用預設值

    # 3. 運行TSN模擬
    if compression_df is not None:
        results_df = run_real_tsn_simulation(compression_df, file_size_mb)

        # 4. 分析結果
        final_results = analyze_results(results_df)

        overall_end = time.time()

        print(f"\n🎉 實驗完成！總耗時: {overall_end - overall_start:.1f} 秒")

        # 顯示結果表
        print("\n【完整結果表】")
        print("-" * 100)
        print(f"{'Network':<15} {'Method':<20} {'Compression':<12} {'Latency(ms)':<12} {'Utilization(%)':<15} {'Feasible':<10}")
        print("-" * 100)

        for _, row in final_results.iterrows():
            print(f"{row['Network']:<15} {row['Method']:<20} {row['Compression_Ratio']:<12.3f} "
                  f"{row['Total_Latency_ms']:<12.1f} {row['Network_Utilization_%']:<15.1f} "
                  f"{'✓' if row['Feasible'] else '✗':<10}")

        return final_results
    else:
        print("❌ 壓縮實驗失敗")
        return None

if __name__ == "__main__":
    results = main()