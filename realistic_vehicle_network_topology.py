#!/usr/bin/env python3
"""
設計真實的車體網路拓樸和LiDAR傳輸流
Design realistic in-vehicle network topology and LiDAR transmission flows
"""

import json
import pandas as pd

def design_realistic_topology():
    """設計符合實際的車體網路拓樸"""

    print("="*70)
    print("🚗 真實車體網路拓樸設計")
    print("="*70)

    print("\n【實際LiDAR規格】")
    print("-"*50)
    print("基於 Velodyne HDL-64E (KITTI使用的LiDAR):")
    print("• 旋轉頻率: 10 Hz (每秒10轉)")
    print("• 每轉點數: ~130,000 points")
    print("• 每點數據: 4 bytes (X,Y,Z,intensity)")
    print("• 原始數據率: 10 Hz × 130,000 × 4 bytes = 5.2 MB/s")
    print("• 實際KITTI檔案: ~1.88 MB/frame (經過初步處理)")

    print("\n【車體網路拓樸設計】")
    print("-"*50)
    print("""
    實際自動駕駛車輛網路架構:

    ┌────────────────────────────────────────────────────┐
    │                  域控制器架構                        │
    ├────────────────────────────────────────────────────┤
    │                                                    │
    │  感測器域                    中央計算域             │
    │  ┌─────────┐              ┌──────────────┐       │
    │  │ LiDAR   │─────TSN──────>│              │       │
    │  │ 10Hz    │  1Gbps       │   感知融合    │       │
    │  └─────────┘              │     模組      │       │
    │                           │              │       │
    │  ┌─────────┐              │              │       │
    │  │Camera×4 │─────TSN──────>│              │       │
    │  │ 30fps   │  1Gbps       └──────────────┘       │
    │  └─────────┘                     │                │
    │                                  │                │
    │  ┌─────────┐                     ↓                │
    │  │Radar×8  │              ┌──────────────┐       │
    │  │ 20Hz    │─────CAN──────>│   決策規劃   │       │
    │  └─────────┘  500kbps     │     模組     │       │
    │                           └──────────────┘       │
    └────────────────────────────────────────────────────┘
    """)

    # TSN流量定義
    print("\n【TSN Flow定義】")
    print("-"*50)

    tsn_flows = {
        "LiDAR_Flow": {
            "source": "LiDAR",
            "destination": "感知融合模組",
            "period_ms": 100,  # 10Hz = 100ms週期
            "frame_size_bytes": 1880000,  # 1.88MB
            "deadline_ms": 50,  # 必須在50ms內送達
            "priority": "Critical",
            "bandwidth_mbps": 150.4
        },
        "Camera_Flow": {
            "source": "Camera×4",
            "destination": "感知融合模組",
            "period_ms": 33.3,  # 30fps = 33.3ms週期
            "frame_size_bytes": 2073600,  # 1920×1080×4cameras
            "deadline_ms": 20,
            "priority": "Critical",
            "bandwidth_mbps": 497.7
        },
        "Radar_Flow": {
            "source": "Radar×8",
            "destination": "感知融合模組",
            "period_ms": 50,  # 20Hz
            "frame_size_bytes": 10240,  # 較小的雷達數據
            "deadline_ms": 30,
            "priority": "High",
            "bandwidth_mbps": 1.6
        }
    }

    print("\nTSN流量表:")
    print(f"{'Flow名稱':<15} {'週期(ms)':<10} {'大小(MB)':<10} {'頻寬(Mbps)':<12} {'優先級':<10}")
    print("-"*65)

    total_bandwidth = 0
    for flow_name, flow_params in tsn_flows.items():
        size_mb = flow_params['frame_size_bytes'] / (1024*1024)
        print(f"{flow_name:<15} {flow_params['period_ms']:<10.1f} "
              f"{size_mb:<10.2f} {flow_params['bandwidth_mbps']:<12.1f} "
              f"{flow_params['priority']:<10}")
        if "Camera" not in flow_name and "Radar" not in flow_name:
            total_bandwidth += flow_params['bandwidth_mbps']

    print(f"\n僅LiDAR總頻寬需求: {total_bandwidth:.1f} Mbps")

    # 時間窗口分析
    print("\n【TSN時間窗口調度】")
    print("-"*50)
    print("""
    100ms週期內的調度窗口:

    時間(ms)  0    10    20    30    40    50    60    70    80    90   100
             |-----|-----|-----|-----|-----|-----|-----|-----|-----|-----|
    LiDAR:   [■■■■■■■■■■■■■■■■■■■■]                                      新週期
             ├─────傳輸窗口──────┤

    處理:                        [████████████]
                                 ├──壓縮處理──┤
    """)

    # 比較不同網路技術
    print("\n【網路技術比較】")
    print("-"*50)

    network_comparison = {
        "傳統CAN": {
            "bandwidth_mbps": 0.5,
            "latency_ms": 10,
            "deterministic": False,
            "can_handle_lidar": False
        },
        "車載乙太網": {
            "bandwidth_mbps": 100,
            "latency_ms": 5,
            "deterministic": False,
            "can_handle_lidar": False  # 150.4 > 100
        },
        "TSN(IEEE 802.1)": {
            "bandwidth_mbps": 1000,
            "latency_ms": 2,
            "deterministic": True,
            "can_handle_lidar": True
        }
    }

    print(f"{'技術':<15} {'頻寬(Mbps)':<12} {'延遲(ms)':<10} {'確定性':<10} {'支援LiDAR':<12}")
    print("-"*65)

    for tech, specs in network_comparison.items():
        deterministic = "是" if specs['deterministic'] else "否"
        can_handle = "✓" if specs['can_handle_lidar'] else "✗"
        print(f"{tech:<15} {specs['bandwidth_mbps']:<12} "
              f"{specs['latency_ms']:<10} {deterministic:<10} {can_handle:<12}")

    # 計算實際延遲
    print("\n" + "="*70)
    print("⏱️ 端到端延遲分析")
    print("="*70)

    print("\n【LiDAR數據流程時序】")
    print("-"*50)

    # 未壓縮流程
    print("\n1. 未壓縮流程:")
    lidar_acquisition = 100  # ms (一個完整掃描週期)

    # 100Mbps乙太網路
    ethernet_transmission = (1.88 * 8 / 100) * 1000  # ms (修正: 100Mbps)
    ethernet_queuing = 5  # ms
    ethernet_processing = 10  # ms
    ethernet_total = ethernet_transmission + ethernet_queuing + ethernet_processing

    print(f"   車載乙太網路(100Mbps):")
    print(f"   • 數據採集: {lidar_acquisition} ms")
    print(f"   • 網路傳輸: {ethernet_transmission:.1f} ms")
    print(f"   • 排隊延遲: {ethernet_queuing} ms")
    print(f"   • 處理時間: {ethernet_processing} ms")
    print(f"   • 總延遲: {lidar_acquisition + ethernet_total:.1f} ms")
    print(f"   • 問題: 頻寬不足(需150.4Mbps > 100Mbps)，會造成累積延遲!")

    # TSN
    tsn_transmission = (1.88 * 8 / 1000) * 1000  # ms (修正: 1000Mbps)
    tsn_queuing = 0.5  # ms (TSN保證低延遲)
    tsn_processing = 10  # ms
    tsn_total = tsn_transmission + tsn_queuing + tsn_processing

    print(f"\n   TSN(1Gbps):")
    print(f"   • 數據採集: {lidar_acquisition} ms")
    print(f"   • 網路傳輸: {tsn_transmission:.1f} ms")
    print(f"   • 排隊延遲: {tsn_queuing} ms")
    print(f"   • 處理時間: {tsn_processing} ms")
    print(f"   • 總延遲: {lidar_acquisition + tsn_total:.1f} ms")

    # 壓縮流程
    print("\n2. 壓縮流程(EB-HC-3D):")
    compression_ratio = 0.261
    compression_time = 5.2  # ms
    compressed_size = 1.88 * compression_ratio

    tsn_compressed_transmission = (compressed_size * 8 / 1000) * 1000  # ms (修正: 1000Mbps)
    tsn_compressed_total = compression_time + tsn_compressed_transmission + tsn_queuing + tsn_processing

    print(f"   TSN + 壓縮:")
    print(f"   • 數據採集: {lidar_acquisition} ms")
    print(f"   • 壓縮處理: {compression_time} ms")
    print(f"   • 網路傳輸: {tsn_compressed_transmission:.1f} ms")
    print(f"   • 排隊延遲: {tsn_queuing} ms")
    print(f"   • 解壓處理: {tsn_processing} ms")
    print(f"   • 總延遲: {lidar_acquisition + tsn_compressed_total:.1f} ms")

    # 保存TSN配置
    print("\n" + "="*70)
    print("💾 生成TSN配置文件")
    print("="*70)

    tsn_config = {
        "network_topology": {
            "switches": ["TSN_Switch_1"],
            "end_stations": ["LiDAR", "Camera_ECU", "Radar_ECU", "Compute_Unit"],
            "links": [
                {"from": "LiDAR", "to": "TSN_Switch_1", "bandwidth_mbps": 1000},
                {"from": "TSN_Switch_1", "to": "Compute_Unit", "bandwidth_mbps": 1000}
            ]
        },
        "streams": tsn_flows,
        "schedule": {
            "cycle_time_us": 100000,  # 100ms
            "time_slots": [
                {"stream": "LiDAR_Flow", "start_us": 0, "duration_us": 15000},
                {"stream": "Camera_Flow", "start_us": 15000, "duration_us": 50000},
                {"stream": "Radar_Flow", "start_us": 65000, "duration_us": 5000}
            ]
        }
    }

    with open("/home/adlink/宇翰論文/outputs/tsn_vehicle_config.json", "w") as f:
        json.dump(tsn_config, f, indent=2)

    print("✓ TSN配置已保存: tsn_vehicle_config.json")

    print("\n【關鍵結論】")
    print("-"*50)
    print("1. LiDAR以10Hz更新，每100ms產生1.88MB數據")
    print("2. 100Mbps乙太網路無法及時傳輸(需150.4Mbps)")
    print("3. TSN提供確定性傳輸，保證50ms內送達")
    print("4. 壓縮降低頻寬需求但增加處理延遲")
    print("5. TSN時隙調度確保關鍵數據優先傳輸")

    return tsn_config

if __name__ == "__main__":
    config = design_realistic_topology()