#!/usr/bin/env python3
"""
Cost-Benefit Analysis for Integrated LiDAR Framework
Based on experimental results from compression_results_full.csv
"""

import pandas as pd
import numpy as np
import os

def calculate_system_benefits():
    # Load compression results
    results_path = os.path.join(os.path.dirname(__file__), 'compression_results_full.csv')
    df = pd.read_csv(results_path)

    # Calculate average compression ratios
    avg_compression = df.groupby(['Method', 'BE (cm)'])['Compression Ratio'].mean()

    # System parameters
    lidar_fps = 10  # Hz
    vehicles_per_intersection = 8
    hours_per_day = 24
    days_per_year = 365
    avg_raw_size_mb = 2.0  # MB per frame

    # Cost parameters (USD)
    aws_s3_cost_gb_month = 0.023
    ipfs_pinning_cost_gb_month = 0.15
    bandwidth_cost_gb = 0.05
    tsn_equipment_cost_vehicle = 500

    print("=== LiDAR Integrated Framework Cost-Benefit Analysis ===\n")

    # 1. Storage Cost Analysis
    print("1. STORAGE COST ANALYSIS")
    print("-" * 40)

    # Annual data volume per vehicle
    annual_frames = lidar_fps * 3600 * hours_per_day * days_per_year
    annual_raw_data_gb = (annual_frames * avg_raw_size_mb) / 1024

    best_compression_ratio = avg_compression.min()  # ~0.23 for EB-HC-3D
    annual_compressed_data_gb = annual_raw_data_gb * best_compression_ratio

    print(f"Raw LiDAR data per vehicle/year: {annual_raw_data_gb:.1f} GB")
    print(f"Compressed data per vehicle/year: {annual_compressed_data_gb:.1f} GB")
    print(f"Data reduction: {(1-best_compression_ratio)*100:.1f}%")

    # Storage costs
    traditional_storage_cost = annual_raw_data_gb * aws_s3_cost_gb_month * 12
    ipfs_raw_cost = annual_raw_data_gb * ipfs_pinning_cost_gb_month * 12
    ipfs_compressed_cost = annual_compressed_data_gb * ipfs_pinning_cost_gb_month * 12

    print(f"\nTraditional cloud storage (raw): ${traditional_storage_cost:.2f}/vehicle/year")
    print(f"IPFS storage (raw): ${ipfs_raw_cost:.2f}/vehicle/year")
    print(f"IPFS storage (compressed): ${ipfs_compressed_cost:.2f}/vehicle/year")
    print(f"Storage cost savings: ${ipfs_raw_cost - ipfs_compressed_cost:.2f}/vehicle/year")

    # 2. Network Bandwidth Analysis
    print("\n2. NETWORK BANDWIDTH ANALYSIS")
    print("-" * 40)

    # Peak bandwidth requirements
    raw_bandwidth_mbps = avg_raw_size_mb * 8 * lidar_fps  # Mbps per vehicle
    compressed_bandwidth_mbps = raw_bandwidth_mbps * best_compression_ratio

    intersection_raw_bandwidth = raw_bandwidth_mbps * vehicles_per_intersection
    intersection_compressed_bandwidth = compressed_bandwidth_mbps * vehicles_per_intersection

    print(f"Raw bandwidth per vehicle: {raw_bandwidth_mbps:.1f} Mbps")
    print(f"Compressed bandwidth per vehicle: {compressed_bandwidth_mbps:.1f} Mbps")
    print(f"8-vehicle intersection (raw): {intersection_raw_bandwidth:.1f} Mbps")
    print(f"8-vehicle intersection (compressed): {intersection_compressed_bandwidth:.1f} Mbps")
    print(f"Network load reduction: {(1-best_compression_ratio)*100:.1f}%")

    # 3. TSN Infrastructure Benefits
    print("\n3. TSN INFRASTRUCTURE BENEFITS")
    print("-" * 40)

    # TSN can support more flows with compressed data
    tsn_capacity_mbps = 1000  # 1 Gbps
    vehicles_supported_raw = int(tsn_capacity_mbps / raw_bandwidth_mbps)
    vehicles_supported_compressed = int(tsn_capacity_mbps / compressed_bandwidth_mbps)

    print(f"TSN capacity: {tsn_capacity_mbps} Mbps")
    print(f"Vehicles supported (raw data): {vehicles_supported_raw}")
    print(f"Vehicles supported (compressed): {vehicles_supported_compressed}")
    print(f"Capacity improvement: {vehicles_supported_compressed/vehicles_supported_raw:.1f}x")

    # 4. Total Economic Impact
    print("\n4. TOTAL ECONOMIC IMPACT (per intersection/year)")
    print("-" * 50)

    total_vehicles = vehicles_per_intersection

    # Benefits
    storage_savings = (ipfs_raw_cost - ipfs_compressed_cost) * total_vehicles
    bandwidth_savings = (annual_raw_data_gb - annual_compressed_data_gb) * bandwidth_cost_gb * total_vehicles

    # Costs
    tsn_infrastructure_cost = tsn_equipment_cost_vehicle * total_vehicles

    # ROI calculation
    total_annual_savings = storage_savings + bandwidth_savings
    roi_years = tsn_infrastructure_cost / total_annual_savings if total_annual_savings > 0 else float('inf')

    print(f"Annual storage cost savings: ${storage_savings:.0f}")
    print(f"Annual bandwidth cost savings: ${bandwidth_savings:.0f}")
    print(f"Total annual savings: ${total_annual_savings:.0f}")
    print(f"TSN infrastructure investment: ${tsn_infrastructure_cost:.0f}")
    print(f"Return on Investment (ROI): {roi_years:.1f} years")

    # 5. Quality Metrics
    print("\n5. DATA QUALITY PRESERVATION")
    print("-" * 40)

    # Get quality metrics for best compression method
    best_method_data = df[df['Method'] == 'EB-HC-3D(Axis)']
    if not best_method_data.empty:
        avg_chamfer = best_method_data['Chamfer Distance'].mean()
        avg_iou = best_method_data['Occupancy IoU'].mean()

        print(f"Average Chamfer Distance: {avg_chamfer:.6f}")
        print(f"Average Occupancy IoU: {avg_iou:.4f}")
        print(f"Geometric accuracy preservation: {avg_iou*100:.2f}%")

    return {
        'compression_ratio': best_compression_ratio,
        'annual_savings': total_annual_savings,
        'roi_years': roi_years,
        'capacity_improvement': vehicles_supported_compressed/vehicles_supported_raw
    }

if __name__ == "__main__":
    results = calculate_system_benefits()
    print(f"\n=== SUMMARY ===")
    print(f"Best compression ratio: {results['compression_ratio']:.3f}")
    print(f"Annual economic benefit: ${results['annual_savings']:.0f}/intersection")
    print(f"ROI period: {results['roi_years']:.1f} years")
    print(f"Network capacity improvement: {results['capacity_improvement']:.1f}x")