#!/usr/bin/env python3
"""
綜合實驗分析：整理所有KITTI場景的公平實驗結果
Comprehensive analysis of fair experiments across all KITTI scenes
"""

import pandas as pd
import json
import numpy as np

def generate_comprehensive_analysis():
    """生成綜合實驗分析報告"""

    print("="*70)
    print("🔬 KITTI數據集完整實驗分析報告")
    print("="*70)

    # 載入實驗報告
    with open("/home/adlink/宇翰論文/outputs/fair_kitti_report.json", 'r', encoding='utf-8') as f:
        report = json.load(f)

    # 載入詳細數據
    compression_df = pd.read_csv("/home/adlink/宇翰論文/outputs/fair_kitti_compression.csv")
    tsn_df = pd.read_csv("/home/adlink/宇翰論文/outputs/fair_kitti_tsn.csv")
    ipfs_df = pd.read_csv("/home/adlink/宇翰論文/outputs/fair_kitti_ipfs.csv")

    print("\n📊 實驗範圍")
    print("-"*50)
    print(f"✓ 數據集規模: {report['dataset']['total_files']} 檔案, {report['dataset']['total_size_gb']} GB")
    print(f"✓ 測試場景: {', '.join(report['dataset']['scenes'])}")
    print(f"✓ 壓縮測試: {report['compression']['records']} 筆記錄")
    print(f"✓ 執行時間: {report['execution_time_seconds']:.1f} 秒")

    # 實驗一：TSN壓縮vs未壓縮比較
    print("\n"+"="*70)
    print("📈 實驗一：TSN網路 - 壓縮vs未壓縮傳輸比較")
    print("-"*70)

    # 計算各場景的平均值
    for scene in report['dataset']['scenes']:
        scene_tsn = tsn_df[tsn_df['Scene'] == scene]

        uncompressed = scene_tsn[scene_tsn['Method'] == 'Uncompressed'].iloc[0]
        compressed_best = scene_tsn[scene_tsn['Method'] != 'Uncompressed'].nsmallest(1, 'Total_Latency_ms').iloc[0]

        print(f"\n場景: {scene}")
        print(f"  未壓縮:")
        print(f"    • 延遲: {uncompressed['Total_Latency_ms']:.2f} ms")
        print(f"    • 網路利用率: {uncompressed['Network_Utilization_%']:.1f}%")
        print(f"  最佳壓縮 ({compressed_best['Method']}):")
        print(f"    • 延遲: {compressed_best['Total_Latency_ms']:.2f} ms")
        print(f"    • 網路利用率: {compressed_best['Network_Utilization_%']:.1f}%")
        print(f"    • 壓縮比: {compressed_best['Compression_Ratio']:.3f}")

    # 整體平均
    print("\n【整體平均結果】")
    uncompressed_avg = tsn_df[tsn_df['Method'] == 'Uncompressed']['Total_Latency_ms'].mean()
    compressed_avg = tsn_df[tsn_df['Method'] != 'Uncompressed']['Total_Latency_ms'].mean()

    print(f"TSN未壓縮平均延遲: {uncompressed_avg:.2f} ms")
    print(f"TSN壓縮平均延遲: {compressed_avg:.2f} ms")
    print(f"延遲增加: {(compressed_avg - uncompressed_avg):.2f} ms")
    print(f"延遲增加比例: {((compressed_avg - uncompressed_avg) / uncompressed_avg * 100):.1f}%")

    # 網路利用率改善
    uncompressed_util = tsn_df[tsn_df['Method'] == 'Uncompressed']['Network_Utilization_%'].mean()
    compressed_util = tsn_df[tsn_df['Method'] != 'Uncompressed']['Network_Utilization_%'].mean()
    print(f"\n網路利用率:")
    print(f"  未壓縮: {uncompressed_util:.1f}%")
    print(f"  壓縮後: {compressed_util:.1f}%")
    print(f"  降低: {(uncompressed_util - compressed_util):.1f}%")

    # 實驗二：IPFS儲存空間節省
    print("\n"+"="*70)
    print("💾 實驗二：IPFS儲存空間節省分析")
    print("-"*70)

    # 各場景儲存節省
    for scene in report['dataset']['scenes']:
        scene_ipfs = ipfs_df[ipfs_df['Scene'] == scene]
        scene_compressed = scene_ipfs[scene_ipfs['Method'] != 'Uncompressed']

        if not scene_compressed.empty:
            avg_savings = scene_compressed['Storage_Savings_%'].mean()
            best_savings = scene_compressed['Storage_Savings_%'].max()
            best_method = scene_compressed.loc[scene_compressed['Storage_Savings_%'].idxmax(), 'Method']

            print(f"\n場景: {scene}")
            print(f"  原始大小: {scene_ipfs.iloc[0]['Original_GB']:.3f} GB")
            print(f"  平均節省: {avg_savings:.1f}%")
            print(f"  最佳節省: {best_savings:.1f}% ({best_method})")

    # 整體統計
    print("\n【整體儲存節省】")
    overall_savings = ipfs_df[ipfs_df['Method'] != 'Uncompressed']['Storage_Savings_%'].mean()
    best_overall_savings = ipfs_df[ipfs_df['Method'] != 'Uncompressed']['Storage_Savings_%'].max()
    best_overall_method = ipfs_df.loc[ipfs_df['Storage_Savings_%'].idxmax(), 'Method']

    print(f"平均儲存節省: {overall_savings:.1f}%")
    print(f"最佳儲存節省: {best_overall_savings:.1f}% ({best_overall_method})")

    # IPFS上傳時間節省
    print("\n【IPFS上傳時間節省】")
    uncompressed_upload = ipfs_df[ipfs_df['Method'] == 'Uncompressed']['Upload_Time_Hours'].sum()
    compressed_upload = ipfs_df[ipfs_df['Method'] != 'Uncompressed'].groupby('Method')['Upload_Time_Hours'].sum()

    for method, upload_time in compressed_upload.items():
        time_saved = uncompressed_upload - upload_time
        time_saved_pct = (time_saved / uncompressed_upload) * 100
        print(f"{method}: 節省 {time_saved:.1f} 小時 ({time_saved_pct:.1f}%)")

    # 實驗三：延遲改善分析
    print("\n"+"="*70)
    print("⚡ 實驗三：延遲改善百分比計算")
    print("-"*70)

    # 對比車內乙太網路 (模擬100Mbps)
    ethernet_latency_uncompressed = 150  # ms (估計值：100Mbps傳輸2MB)
    tsn_latency_uncompressed = uncompressed_avg
    tsn_latency_compressed = compressed_avg

    print("\n【與車內乙太網路(100Mbps)比較】")
    print(f"車內乙太網路(未壓縮): {ethernet_latency_uncompressed:.1f} ms")
    print(f"TSN(1Gbps)未壓縮: {tsn_latency_uncompressed:.2f} ms")
    print(f"TSN(1Gbps)壓縮: {tsn_latency_compressed:.2f} ms")

    print("\n改善比例:")
    tsn_vs_ethernet = ((ethernet_latency_uncompressed - tsn_latency_uncompressed) / ethernet_latency_uncompressed) * 100
    tsn_compressed_vs_ethernet = ((ethernet_latency_uncompressed - tsn_latency_compressed) / ethernet_latency_uncompressed) * 100

    print(f"  TSN未壓縮 vs 乙太網路: 改善 {tsn_vs_ethernet:.1f}%")
    print(f"  TSN壓縮 vs 乙太網路: 改善 {tsn_compressed_vs_ethernet:.1f}%")

    # 最終總結
    print("\n"+"="*70)
    print("📋 實驗總結")
    print("="*70)

    print("\n✅ 關鍵發現:")
    print(f"1. TSN網路中，雖然壓縮增加約{(compressed_avg - uncompressed_avg):.1f}ms處理延遲")
    print(f"   但網路利用率從{uncompressed_util:.1f}%降至{compressed_util:.1f}%")
    print(f"2. IPFS儲存空間平均節省{overall_savings:.1f}%")
    print(f"3. 相較於車內乙太網路，TSN+壓縮可改善延遲{tsn_compressed_vs_ethernet:.1f}%")
    print(f"4. 所有配置的可行性達到{report['tsn']['feasibility_rate']:.1f}%")

    print("\n📊 最佳配置建議:")
    best_compression = report['compression']['best_method']
    best_ratio = report['compression']['best_ratio']
    print(f"• 壓縮方法: {best_compression}")
    print(f"• 壓縮比: {best_ratio:.3f}")
    print(f"• TSN延遲: {report['tsn']['min_latency_ms']:.2f} ms")
    print(f"• 儲存節省: {best_overall_savings:.1f}%")

    return {
        'tsn_latency_increase': compressed_avg - uncompressed_avg,
        'network_utilization_reduction': uncompressed_util - compressed_util,
        'storage_savings': overall_savings,
        'latency_improvement_vs_ethernet': tsn_compressed_vs_ethernet
    }

if __name__ == "__main__":
    results = generate_comprehensive_analysis()
    print("\n✅ 分析完成！使用完整KITTI數據集的公平實驗結果。")