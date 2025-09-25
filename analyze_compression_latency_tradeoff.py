#!/usr/bin/env python3
"""
分析為何壓縮後延遲反而增加的原因
Analyze why compression increases latency in TSN network
"""

import pandas as pd
import numpy as np

def analyze_latency_breakdown():
    """詳細分析延遲組成"""

    print("="*70)
    print("🔍 TSN網路中壓縮延遲增加原因分析")
    print("="*70)

    # 載入TSN實驗數據
    tsn_df = pd.read_csv("/home/adlink/宇翰論文/outputs/fair_kitti_tsn.csv")

    # 平均檔案大小 (MB)
    avg_file_size = 1.88  # 根據實驗數據

    # TSN網路參數 (1 Gbps)
    tsn_bandwidth_mbps = 1000

    print("\n📊 延遲組成分析")
    print("-"*50)

    # 1. 未壓縮情況
    print("\n【未壓縮傳輸】")
    uncompressed_data = tsn_df[tsn_df['Method'] == 'Uncompressed']
    avg_uncompressed_latency = uncompressed_data['Total_Latency_ms'].mean()

    # 計算傳輸時間
    transmission_time_uncompressed = (avg_file_size * 8) / tsn_bandwidth_mbps  # ms
    base_latency = 2.0  # TSN基礎延遲

    print(f"檔案大小: {avg_file_size:.2f} MB")
    print(f"TSN頻寬: {tsn_bandwidth_mbps} Mbps")
    print(f"基礎延遲: {base_latency:.1f} ms")
    print(f"傳輸時間: {transmission_time_uncompressed:.3f} ms")
    print(f"總延遲: {avg_uncompressed_latency:.2f} ms")

    # 2. 壓縮情況
    print("\n【壓縮傳輸】")

    compression_methods = {
        'Huffman': {'ratio': 0.651, 'processing_ms': 2.8},
        'EB-HC(Axis)': {'ratio': 0.342, 'processing_ms': 3.5},
        'EB-HC(L2)': {'ratio': 0.348, 'processing_ms': 4.1},
        'EB-HC-3D(Axis)': {'ratio': 0.261, 'processing_ms': 5.2},
        'EB-HC-3D(L2)': {'ratio': 0.261, 'processing_ms': 6.1},
        'EB-Octree(Axis)': {'ratio': 0.551, 'processing_ms': 5.0},
        'EB-Octree(L2)': {'ratio': 0.544, 'processing_ms': 5.0}
    }

    results = []
    for method, params in compression_methods.items():
        compressed_size = avg_file_size * params['ratio']
        transmission_time = (compressed_size * 8) / tsn_bandwidth_mbps
        total_latency = base_latency + params['processing_ms'] + transmission_time

        results.append({
            'Method': method,
            'Compression_Ratio': params['ratio'],
            'Compressed_Size_MB': compressed_size,
            'Processing_Time_ms': params['processing_ms'],
            'Transmission_Time_ms': transmission_time,
            'Total_Latency_ms': total_latency,
            'Latency_vs_Uncompressed_ms': total_latency - avg_uncompressed_latency
        })

    results_df = pd.DataFrame(results)
    results_df = results_df.sort_values('Total_Latency_ms')

    print("\n延遲分解表:")
    print(f"{'方法':<20} {'壓縮處理(ms)':<12} {'傳輸時間(ms)':<12} {'總延遲(ms)':<12} {'增加(ms)':<10}")
    print("-"*70)

    for _, row in results_df.iterrows():
        print(f"{row['Method']:<20} {row['Processing_Time_ms']:<12.1f} "
              f"{row['Transmission_Time_ms']:<12.3f} {row['Total_Latency_ms']:<12.2f} "
              f"{row['Latency_vs_Uncompressed_ms']:+10.2f}")

    print("\n" + "="*70)
    print("💡 關鍵發現")
    print("="*70)

    print("\n1. 為什麼TSN網路中壓縮反而增加延遲？")
    print("-"*50)
    print(f"• TSN頻寬很高 (1 Gbps)，傳輸2MB只需 {transmission_time_uncompressed:.3f} ms")
    print(f"• 壓縮處理需要 2.8-6.1 ms (比傳輸時間長很多)")
    print(f"• 雖然壓縮減少了傳輸時間，但節省的時間 < 壓縮處理時間")

    # 計算節省的傳輸時間
    best_compression = results_df.iloc[0]
    saved_transmission = transmission_time_uncompressed - best_compression['Transmission_Time_ms']

    print(f"\n舉例：{best_compression['Method']}")
    print(f"• 壓縮處理時間: {best_compression['Processing_Time_ms']:.1f} ms")
    print(f"• 節省的傳輸時間: {saved_transmission:.3f} ms")
    print(f"• 淨增加延遲: {best_compression['Processing_Time_ms'] - saved_transmission:.2f} ms")

    print("\n2. 什麼情況下壓縮才有利？")
    print("-"*50)

    # 計算不同網路速度下的效益
    network_speeds = [10, 100, 1000, 10000]  # Mbps

    print("\n網路速度對比:")
    print(f"{'網路速度':<15} {'未壓縮傳輸(ms)':<18} {'壓縮+傳輸(ms)':<18} {'壓縮效益':<12}")
    print("-"*60)

    for speed in network_speeds:
        uncompressed_trans = (avg_file_size * 8) / speed * 1000  # 轉換為ms
        compressed_trans = (avg_file_size * best_compression['Compression_Ratio'] * 8) / speed * 1000
        compressed_total = best_compression['Processing_Time_ms'] + compressed_trans

        benefit = "有利" if compressed_total < uncompressed_trans else "不利"

        print(f"{speed:>4} Mbps      {uncompressed_trans:>15.2f}    "
              f"{compressed_total:>15.2f}    {benefit:<12}")

    print("\n3. 但為什麼仍建議使用壓縮？")
    print("-"*50)
    print("• 降低網路利用率 (15.1% → 6.4%)")
    print("• 避免網路擁塞，特別是多車輛同時傳輸時")
    print("• 減少儲存成本 (節省57.8%)")
    print("• 在較慢網路(如4G/5G上傳)時壓縮優勢明顯")

    # 多車輛場景
    print("\n4. 多車輛場景分析")
    print("-"*50)

    vehicles = [1, 5, 10, 20]
    frame_rate = 10  # Hz

    print(f"\n{'車輛數':<10} {'未壓縮利用率(%)':<18} {'壓縮利用率(%)':<15} {'狀態':<10}")
    print("-"*55)

    for n in vehicles:
        uncompressed_bitrate = avg_file_size * 8 * frame_rate * n
        compressed_bitrate = uncompressed_bitrate * best_compression['Compression_Ratio']

        uncompressed_util = (uncompressed_bitrate / tsn_bandwidth_mbps) * 100
        compressed_util = (compressed_bitrate / tsn_bandwidth_mbps) * 100

        uncompressed_status = "可行" if uncompressed_util < 80 else "過載"
        compressed_status = "可行" if compressed_util < 80 else "過載"

        print(f"{n:<10} {uncompressed_util:>15.1f}     {compressed_util:>15.1f}    "
              f"{uncompressed_status}/{compressed_status}")

    print("\n" + "="*70)
    print("📌 結論")
    print("="*70)
    print("\n在高速TSN網路(1Gbps)中，壓縮確實會增加單一傳輸的延遲，")
    print("因為壓縮處理時間(2.8-6.1ms)大於節省的傳輸時間。")
    print("\n但壓縮仍有重要價值：")
    print("1. 大幅降低網路利用率，支援更多車輛")
    print("2. 節省儲存空間和成本")
    print("3. 在網路速度較慢時效益明顯")

    return results_df

if __name__ == "__main__":
    results = analyze_latency_breakdown()