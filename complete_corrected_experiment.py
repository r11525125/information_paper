#!/usr/bin/env python3
"""
完整修正的KITTI LiDAR壓縮實驗
包含真實數據測試、TSN網路分析、IPFS儲存評估
Complete corrected experiment with real KITTI data
"""

import os
import sys
import time
import subprocess
import pandas as pd
import numpy as np
import json
from datetime import datetime
from pathlib import Path

class CompleteKITTIExperiment:
    def __init__(self):
        """初始化實驗環境"""
        self.base_dir = Path("/home/adlink/宇翰論文")
        self.kitti_dir = Path("/home/adlink/下載/KITTI/KITTI")
        self.output_dir = self.base_dir / "outputs"
        self.venv_path = self.base_dir / ".venv"

        # 確保輸出目錄存在
        self.output_dir.mkdir(exist_ok=True)

        # Velodyne HDL-64E 規格
        self.lidar_specs = {
            'frame_rate': 10,  # Hz (每秒10個frame)
            'frame_period_ms': 100,  # ms (每個frame 100ms)
            'avg_frame_size_mb': 1.88,  # MB (平均每個frame大小)
        }

        # 網路規格
        self.network_specs = {
            'ethernet_100': {'bandwidth_mbps': 100, 'base_latency_ms': 5},
            'tsn_1000': {'bandwidth_mbps': 1000, 'base_latency_ms': 2}
        }

        # 壓縮方法處理時間 (ms)
        self.compression_delays = {
            'Huffman': 2.8,
            'EB-HC(Axis)': 3.5,
            'EB-HC(L2)': 4.1,
            'EB-Octree(Axis)': 5.0,
            'EB-Octree(L2)': 5.0,
            'EB-HC-3D(Axis)': 5.2,
            'EB-HC-3D(L2)': 6.1
        }

        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    def verify_kitti_dataset(self):
        """驗證KITTI數據集完整性"""
        print("\n" + "="*70)
        print("📂 步驟1: 驗證KITTI數據集")
        print("="*70)

        scenes = ['campus', 'city', 'person', 'residential', 'road']
        dataset_info = {}
        total_files = 0
        total_size_gb = 0

        for scene in scenes:
            scene_path = self.kitti_dir / scene
            if not scene_path.exists():
                print(f"❌ 場景 {scene} 不存在!")
                return False

            # 統計.bin檔案
            bin_files = list(scene_path.rglob("*.bin"))
            file_count = len(bin_files)

            # 計算總大小
            size_bytes = sum(f.stat().st_size for f in bin_files)
            size_gb = size_bytes / (1024**3)

            dataset_info[scene] = {
                'files': file_count,
                'size_gb': size_gb
            }

            total_files += file_count
            total_size_gb += size_gb

            print(f"✓ {scene:12s}: {file_count:4d} 檔案, {size_gb:.3f} GB")

        print(f"\n總計: {total_files} 檔案, {total_size_gb:.2f} GB")

        # 儲存數據集資訊
        self.dataset_info = dataset_info
        self.total_files = total_files
        self.total_size_gb = total_size_gb

        return True

    def run_real_compression(self, sample_size=3):
        """執行真實壓縮實驗"""
        print("\n" + "="*70)
        print("🔬 步驟2: 執行真實壓縮實驗")
        print("="*70)

        all_results = []

        for scene, info in self.dataset_info.items():
            print(f"\n處理 {scene} 場景 (採樣 {sample_size}/{info['files']} 檔案)...")

            scene_dir = self.kitti_dir / scene
            output_csv = self.output_dir / f"compression_{scene}_{self.timestamp}.csv"

            # 執行壓縮實驗
            cmd = [
                "bash", "-c",
                f"source {self.venv_path}/bin/activate && "
                f"python {self.base_dir}/scripts/run_subset_experiments.py "
                f"--data-dir {scene_dir} "
                f"--max-files {sample_size} "
                f"--be-list 1.0 "
                f"--out-csv {output_csv}"
            ]

            try:
                print(f"  執行壓縮測試...")
                start = time.time()
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
                elapsed = time.time() - start

                if result.returncode == 0 and output_csv.exists():
                    df = pd.read_csv(output_csv)
                    df['Scene'] = scene
                    all_results.append(df)
                    print(f"  ✓ 成功: {len(df)} 筆記錄 ({elapsed:.1f}秒)")
                else:
                    print(f"  ❌ 失敗: {result.stderr[:200]}")

            except Exception as e:
                print(f"  ❌ 錯誤: {e}")

        if all_results:
            # 合併所有結果
            self.compression_df = pd.concat(all_results, ignore_index=True)
            output_path = self.output_dir / f"compression_all_{self.timestamp}.csv"
            self.compression_df.to_csv(output_path, index=False)

            print(f"\n✓ 壓縮實驗完成: {len(self.compression_df)} 筆記錄")
            print(f"  儲存至: {output_path}")

            # 計算平均壓縮率
            avg_ratios = self.compression_df.groupby('Method')['Compression Ratio'].mean()
            print("\n平均壓縮率:")
            for method, ratio in avg_ratios.items():
                print(f"  {method:20s}: {ratio:.4f}")

            return True
        return False

    def analyze_tsn_performance(self):
        """分析TSN網路性能"""
        print("\n" + "="*70)
        print("📡 步驟3: TSN網路性能分析")
        print("="*70)

        results = []

        # LiDAR數據參數
        frame_rate = self.lidar_specs['frame_rate']
        frame_size_mb = self.lidar_specs['avg_frame_size_mb']
        frame_period_ms = self.lidar_specs['frame_period_ms']

        # 計算比特率
        bitrate_mbps = frame_size_mb * 8 * frame_rate

        print(f"\nLiDAR數據流:")
        print(f"  Frame率: {frame_rate} Hz")
        print(f"  Frame大小: {frame_size_mb} MB")
        print(f"  數據率: {bitrate_mbps:.1f} Mbps")

        # 1. 車內乙太網路 (100 Mbps) - 未壓縮
        print("\n【車內乙太網路 100Mbps】")
        eth_bw = self.network_specs['ethernet_100']['bandwidth_mbps']
        eth_latency = self.network_specs['ethernet_100']['base_latency_ms']

        eth_util = (bitrate_mbps / eth_bw) * 100
        eth_trans_ms = (frame_size_mb * 8 / eth_bw) * 1000

        if eth_util > 100:
            print(f"  ❌ 頻寬不足! 需要 {bitrate_mbps:.1f} Mbps > {eth_bw} Mbps")
            print(f"  網路利用率: {eth_util:.1f}% (過載)")
            print(f"  會造成封包累積和丟失")
            eth_total_latency = float('inf')  # 表示無法處理
        else:
            eth_queuing = eth_util * 0.15  # 排隊延遲
            eth_total_latency = eth_latency + eth_trans_ms + eth_queuing
            print(f"  網路利用率: {eth_util:.1f}%")
            print(f"  總延遲: {eth_total_latency:.2f} ms")

        results.append({
            'Network': 'Ethernet_100Mbps',
            'Method': 'Uncompressed',
            'Compression_Ratio': 1.0,
            'Frame_Size_MB': frame_size_mb,
            'Bitrate_Mbps': bitrate_mbps,
            'Network_Utilization_%': eth_util,
            'Transmission_Time_ms': eth_trans_ms,
            'Total_Latency_ms': eth_total_latency,
            'Feasible': eth_util < 90,
            'Meets_Deadline': eth_total_latency < frame_period_ms
        })

        # 2. TSN (1 Gbps) - 未壓縮
        print("\n【TSN 1Gbps - 未壓縮】")
        tsn_bw = self.network_specs['tsn_1000']['bandwidth_mbps']
        tsn_latency = self.network_specs['tsn_1000']['base_latency_ms']

        tsn_util = (bitrate_mbps / tsn_bw) * 100
        tsn_trans_ms = (frame_size_mb * 8 / tsn_bw) * 1000
        tsn_queuing = tsn_util * 0.05  # TSN低排隊延遲
        tsn_total_latency = tsn_latency + tsn_trans_ms + tsn_queuing

        print(f"  網路利用率: {tsn_util:.1f}%")
        print(f"  傳輸時間: {tsn_trans_ms:.3f} ms")
        print(f"  總延遲: {tsn_total_latency:.2f} ms")
        print(f"  ✓ 滿足100ms deadline: {tsn_total_latency < frame_period_ms}")

        results.append({
            'Network': 'TSN_1Gbps',
            'Method': 'Uncompressed',
            'Compression_Ratio': 1.0,
            'Frame_Size_MB': frame_size_mb,
            'Bitrate_Mbps': bitrate_mbps,
            'Network_Utilization_%': tsn_util,
            'Transmission_Time_ms': tsn_trans_ms,
            'Total_Latency_ms': tsn_total_latency,
            'Feasible': True,
            'Meets_Deadline': tsn_total_latency < frame_period_ms
        })

        # 3. TSN + 壓縮
        if hasattr(self, 'compression_df'):
            print("\n【TSN 1Gbps - 壓縮】")

            avg_ratios = self.compression_df.groupby('Method')['Compression Ratio'].mean()

            for method, ratio in avg_ratios.items():
                if method in self.compression_delays:
                    compressed_size_mb = frame_size_mb * ratio
                    compressed_bitrate = compressed_size_mb * 8 * frame_rate
                    compressed_util = (compressed_bitrate / tsn_bw) * 100
                    compressed_trans_ms = (compressed_size_mb * 8 / tsn_bw) * 1000

                    processing_ms = self.compression_delays[method]
                    compressed_queuing = compressed_util * 0.05
                    compressed_total = tsn_latency + processing_ms + compressed_trans_ms + compressed_queuing

                    print(f"\n  {method}:")
                    print(f"    壓縮比: {ratio:.4f}")
                    print(f"    壓縮處理: {processing_ms:.1f} ms")
                    print(f"    網路利用率: {compressed_util:.1f}%")
                    print(f"    總延遲: {compressed_total:.2f} ms")
                    print(f"    滿足deadline: {'✓' if compressed_total < frame_period_ms else '✗'}")

                    results.append({
                        'Network': 'TSN_1Gbps',
                        'Method': method,
                        'Compression_Ratio': ratio,
                        'Frame_Size_MB': compressed_size_mb,
                        'Bitrate_Mbps': compressed_bitrate,
                        'Network_Utilization_%': compressed_util,
                        'Processing_Time_ms': processing_ms,
                        'Transmission_Time_ms': compressed_trans_ms,
                        'Total_Latency_ms': compressed_total,
                        'Feasible': True,
                        'Meets_Deadline': compressed_total < frame_period_ms
                    })

        # 儲存結果
        self.tsn_df = pd.DataFrame(results)
        output_path = self.output_dir / f"tsn_analysis_{self.timestamp}.csv"
        self.tsn_df.to_csv(output_path, index=False)

        print(f"\n✓ TSN分析完成，儲存至: {output_path}")
        return True

    def analyze_ipfs_storage(self):
        """分析IPFS儲存節省"""
        print("\n" + "="*70)
        print("💾 步驟4: IPFS儲存分析")
        print("="*70)

        results = []

        # IPFS參數
        upload_speed_mbps = 10  # 典型上傳速度
        daily_hours = 12  # 每天運行時數
        days_per_year = 365

        # 計算年度數據量
        frames_per_day = self.lidar_specs['frame_rate'] * 3600 * daily_hours
        frames_per_year = frames_per_day * days_per_year

        print(f"\n儲存需求估算:")
        print(f"  每日運行: {daily_hours} 小時")
        print(f"  每日frames: {frames_per_day:,}")
        print(f"  年度frames: {frames_per_year:,}")

        # 未壓縮儲存
        uncompressed_gb_per_year = (frames_per_year * self.lidar_specs['avg_frame_size_mb']) / 1024
        uncompressed_upload_hours = (uncompressed_gb_per_year * 1024 * 8) / (upload_speed_mbps * 3600)

        print(f"\n【未壓縮】")
        print(f"  年度儲存: {uncompressed_gb_per_year:.1f} GB")
        print(f"  上傳時間: {uncompressed_upload_hours:.1f} 小時")

        results.append({
            'Method': 'Uncompressed',
            'Compression_Ratio': 1.0,
            'Annual_Storage_GB': uncompressed_gb_per_year,
            'Storage_Savings_%': 0,
            'Upload_Time_Hours': uncompressed_upload_hours,
            'Upload_Time_Savings_%': 0
        })

        # 壓縮儲存
        if hasattr(self, 'compression_df'):
            print("\n【壓縮儲存節省】")

            avg_ratios = self.compression_df.groupby('Method')['Compression Ratio'].mean()

            for method, ratio in avg_ratios.items():
                compressed_gb = uncompressed_gb_per_year * ratio
                storage_savings = (1 - ratio) * 100
                compressed_upload_hours = (compressed_gb * 1024 * 8) / (upload_speed_mbps * 3600)
                upload_savings = (1 - ratio) * 100

                print(f"\n  {method}:")
                print(f"    壓縮比: {ratio:.4f}")
                print(f"    年度儲存: {compressed_gb:.1f} GB")
                print(f"    儲存節省: {storage_savings:.1f}%")
                print(f"    上傳時間: {compressed_upload_hours:.1f} 小時")
                print(f"    時間節省: {upload_savings:.1f}%")

                results.append({
                    'Method': method,
                    'Compression_Ratio': ratio,
                    'Annual_Storage_GB': compressed_gb,
                    'Storage_Savings_%': storage_savings,
                    'Upload_Time_Hours': compressed_upload_hours,
                    'Upload_Time_Savings_%': upload_savings
                })

        # 儲存結果
        self.ipfs_df = pd.DataFrame(results)
        output_path = self.output_dir / f"ipfs_analysis_{self.timestamp}.csv"
        self.ipfs_df.to_csv(output_path, index=False)

        print(f"\n✓ IPFS分析完成，儲存至: {output_path}")
        return True

    def generate_final_report(self):
        """生成最終實驗報告"""
        print("\n" + "="*70)
        print("📊 步驟5: 生成最終報告")
        print("="*70)

        report = {
            'experiment': '完整KITTI LiDAR壓縮實驗',
            'timestamp': self.timestamp,
            'lidar_specs': self.lidar_specs,
            'dataset': {
                'total_files': self.total_files,
                'total_size_gb': round(self.total_size_gb, 2),
                'scenes': list(self.dataset_info.keys())
            }
        }

        # 壓縮結果
        if hasattr(self, 'compression_df'):
            avg_ratios = self.compression_df.groupby('Method')['Compression Ratio'].mean()
            best_method = avg_ratios.idxmin()

            report['compression'] = {
                'records': len(self.compression_df),
                'best_method': best_method,
                'best_ratio': float(avg_ratios[best_method]),
                'methods': {method: float(ratio) for method, ratio in avg_ratios.items()}
            }

        # TSN結果
        if hasattr(self, 'tsn_df'):
            tsn_uncompressed = self.tsn_df[
                (self.tsn_df['Network'] == 'TSN_1Gbps') &
                (self.tsn_df['Method'] == 'Uncompressed')
            ].iloc[0]

            tsn_compressed = self.tsn_df[
                (self.tsn_df['Network'] == 'TSN_1Gbps') &
                (self.tsn_df['Method'] != 'Uncompressed')
            ]

            if not tsn_compressed.empty:
                best_compressed = tsn_compressed.loc[tsn_compressed['Total_Latency_ms'].idxmin()]

                report['tsn'] = {
                    'uncompressed_latency_ms': float(tsn_uncompressed['Total_Latency_ms']),
                    'uncompressed_utilization_%': float(tsn_uncompressed['Network_Utilization_%']),
                    'best_compressed_method': best_compressed['Method'],
                    'best_compressed_latency_ms': float(best_compressed['Total_Latency_ms']),
                    'best_compressed_utilization_%': float(best_compressed['Network_Utilization_%']),
                    'latency_increase_ms': float(best_compressed['Total_Latency_ms'] - tsn_uncompressed['Total_Latency_ms']),
                    'utilization_reduction_%': float(tsn_uncompressed['Network_Utilization_%'] - best_compressed['Network_Utilization_%'])
                }

        # IPFS結果
        if hasattr(self, 'ipfs_df'):
            best_storage = self.ipfs_df.loc[self.ipfs_df['Storage_Savings_%'].idxmax()]

            report['ipfs'] = {
                'best_method': best_storage['Method'],
                'best_storage_savings_%': float(best_storage['Storage_Savings_%']),
                'best_upload_time_savings_%': float(best_storage['Upload_Time_Savings_%']),
                'annual_storage_gb_saved': float(
                    self.ipfs_df[self.ipfs_df['Method'] == 'Uncompressed']['Annual_Storage_GB'].iloc[0] -
                    best_storage['Annual_Storage_GB']
                )
            }

        # 儲存JSON報告
        report_path = self.output_dir / f"final_report_{self.timestamp}.json"
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        # 顯示關鍵結果
        print("\n" + "="*70)
        print("🎯 關鍵實驗結果")
        print("="*70)

        print(f"\n📂 數據集:")
        print(f"  • 總檔案: {report['dataset']['total_files']} frames")
        print(f"  • 總大小: {report['dataset']['total_size_gb']} GB")

        if 'compression' in report:
            print(f"\n🔬 壓縮:")
            print(f"  • 最佳方法: {report['compression']['best_method']}")
            print(f"  • 壓縮比: {report['compression']['best_ratio']:.4f}")

        if 'tsn' in report:
            print(f"\n📡 TSN網路:")
            print(f"  • 未壓縮延遲: {report['tsn']['uncompressed_latency_ms']:.2f} ms")
            print(f"  • 最佳壓縮延遲: {report['tsn']['best_compressed_latency_ms']:.2f} ms")
            print(f"  • 延遲增加: {report['tsn']['latency_increase_ms']:.2f} ms")
            print(f"  • 網路利用率降低: {report['tsn']['utilization_reduction_%']:.1f}%")

        if 'ipfs' in report:
            print(f"\n💾 IPFS儲存:")
            print(f"  • 最佳方法: {report['ipfs']['best_method']}")
            print(f"  • 儲存節省: {report['ipfs']['best_storage_savings_%']:.1f}%")
            print(f"  • 上傳時間節省: {report['ipfs']['best_upload_time_savings_%']:.1f}%")

        print(f"\n✓ 完整報告已儲存: {report_path}")
        return report

    def run(self):
        """執行完整實驗"""
        print("\n" + "="*80)
        print("🚀 開始完整KITTI LiDAR壓縮實驗")
        print("="*80)

        start_time = time.time()

        # 步驟1: 驗證數據集
        if not self.verify_kitti_dataset():
            print("❌ 數據集驗證失敗")
            return False

        # 步驟2: 執行壓縮實驗
        if not self.run_real_compression(sample_size=5):  # 每個場景測試5個檔案
            print("❌ 壓縮實驗失敗")
            return False

        # 步驟3: TSN性能分析
        if not self.analyze_tsn_performance():
            print("❌ TSN分析失敗")
            return False

        # 步驟4: IPFS儲存分析
        if not self.analyze_ipfs_storage():
            print("❌ IPFS分析失敗")
            return False

        # 步驟5: 生成報告
        report = self.generate_final_report()

        elapsed_time = time.time() - start_time

        print("\n" + "="*80)
        print(f"✅ 實驗完成！總耗時: {elapsed_time:.1f} 秒")
        print("="*80)

        return report


def main():
    """主函數"""
    experiment = CompleteKITTIExperiment()
    report = experiment.run()

    if report:
        print("\n🎉 所有實驗成功完成！")
        print("📁 輸出檔案位於: outputs/")
        return 0
    else:
        print("\n❌ 實驗執行失敗")
        return 1


if __name__ == "__main__":
    sys.exit(main())