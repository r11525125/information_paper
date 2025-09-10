import os
import sys
import argparse
import numpy as np
import csv
from typing import List, Dict


def resolve_eb_module():
    """
    Try to import EBpapercopy2:
    - Prefer local: ./scripts/EBpapercopy2.py if user copied it here
    - Fallback to: 下載/KITTI/EBpapercopy2.py (original location)
    """
    here = os.path.dirname(os.path.abspath(__file__))
    local_path = os.path.join(here, 'EBpapercopy2.py')
    fallback_path = os.path.expanduser(os.path.join('~', '下載', 'KITTI'))

    if os.path.isfile(local_path):
        sys.path.insert(0, here)
    elif os.path.isdir(fallback_path):
        sys.path.insert(0, fallback_path)
    else:
        raise RuntimeError(
            'EBpapercopy2.py not found. Copy it into ./scripts or keep it under 下載/KITTI/')

    import EBpapercopy2 as eb
    return eb


def load_bin_paths(data_dir: str, max_files: int) -> List[str]:
    files = [os.path.join(data_dir, f) for f in os.listdir(data_dir) if f.endswith('.bin')]
    files.sort()
    return files[:max_files]


def write_csv(rows: List[Dict], out_csv: str, fieldnames: List[str]):
    if not rows:
        print('[INFO] No rows to write')
        return
    os.makedirs(os.path.dirname(out_csv), exist_ok=True)
    with open(out_csv, 'w', newline='', encoding='utf-8') as fw:
        cw = csv.DictWriter(fw, fieldnames=fieldnames)
        cw.writeheader()
        cw.writerows(rows)
    print(f'[OK] CSV written: {out_csv} ({len(rows)} rows)')


def run_subset_on_points(eb, pts: np.ndarray, scene_label: str, be_list_cm: List[float]) -> List[Dict]:
    results = []
    scale_factor = 1000
    qpts = np.round(pts * scale_factor).astype(np.int32)
    raw_bits = qpts.size * 32

    # Huffman baseline
    raw_bytes = qpts.tobytes()
    enc_bits, huff_tree = eb.huffman_encoding(raw_bytes)
    c_bits = len(enc_bits)
    ratio = c_bits / raw_bits if raw_bits > 0 else 0
    dec_bytes = eb.huffman_decoding(enc_bits, huff_tree)
    if dec_bytes:
        dq = np.frombuffer(dec_bytes, dtype=np.int32).reshape(-1, 3)
    else:
        dq = np.empty((0, 3), dtype=np.int32)
    rec_pts = dq.astype(np.float32) / scale_factor
    errs = eb.compute_error(pts, rec_pts)
    results.append({
        'Scene': scene_label,
        'Method': 'Huffman',
        'BE (cm)': 0,
        'Compression Ratio': ratio,
        'Compression Time (s)': np.nan,
        'Decompression Time (s)': np.nan,
        'Mean Error (Axis)': errs['mean_axis'],
        'Max Error (Axis)': errs['max_axis'],
        'Mean Error (L2)': errs['mean_l2'],
        'Max Error (L2)': errs['max_l2'],
        'Num Packets': int(np.ceil(c_bits/1000)) if c_bits > 0 else 0,
        'Chamfer Distance': errs['chamfer_dist'],
        'Occupancy IoU': errs['occupancy_iou'],
    })

    for be_cm in be_list_cm:
        # EB-HC(Axis)
        eb_data_axis, trees_axis = eb.ebhc_encode_axis(qpts, be_cm, scale_factor)
        c_bits = len(eb_data_axis) * 8
        ratio = c_bits / raw_bits if raw_bits > 0 else 0
        dq_a = eb.ebhc_decode_axis(eb_data_axis, trees_axis, len(qpts))
        rec_a = dq_a.astype(np.float32) / scale_factor
        ea = eb.compute_error(pts, rec_a)
        results.append({
            'Scene': scene_label,
            'Method': 'EB-HC(Axis)',
            'BE (cm)': be_cm,
            'Compression Ratio': ratio,
            'Compression Time (s)': np.nan,
            'Decompression Time (s)': np.nan,
            'Mean Error (Axis)': ea['mean_axis'],
            'Max Error (Axis)': ea['max_axis'],
            'Mean Error (L2)': ea['mean_l2'],
            'Max Error (L2)': ea['max_l2'],
            'Num Packets': int(np.ceil(c_bits/1000)) if c_bits > 0 else 0,
            'Chamfer Distance': ea['chamfer_dist'],
            'Occupancy IoU': ea['occupancy_iou'],
        })

        # EB-HC(L2)
        eb_data_l2, trees_l2 = eb.ebhc_encode_l2(qpts, be_cm, scale_factor)
        c_bits = len(eb_data_l2) * 8
        ratio = c_bits / raw_bits if raw_bits > 0 else 0
        dq_l2 = eb.ebhc_decode_l2(eb_data_l2, trees_l2, len(qpts))
        rec_l2 = dq_l2.astype(np.float32) / scale_factor
        el2 = eb.compute_error(pts, rec_l2)
        results.append({
            'Scene': scene_label,
            'Method': 'EB-HC(L2)',
            'BE (cm)': be_cm,
            'Compression Ratio': ratio,
            'Compression Time (s)': np.nan,
            'Decompression Time (s)': np.nan,
            'Mean Error (Axis)': el2['mean_axis'],
            'Max Error (Axis)': el2['max_axis'],
            'Mean Error (L2)': el2['mean_l2'],
            'Max Error (L2)': el2['max_l2'],
            'Num Packets': int(np.ceil(c_bits/1000)) if c_bits > 0 else 0,
            'Chamfer Distance': el2['chamfer_dist'],
            'Occupancy IoU': el2['occupancy_iou'],
        })

        # EB-3D = EB-Octree(Axis)
        c_oct_a = eb.EBOctreeAxisCompressor(be_cm/100.0, 1, 1000.0, 32)
        data_oaxis = c_oct_a.compress(pts)
        c_bits = len(data_oaxis) * 8
        ratio = c_bits / raw_bits if raw_bits > 0 else 0
        dec_oaxis = c_oct_a.decompress(data_oaxis)
        eoax = eb.compute_error(pts, dec_oaxis)
        results.append({
            'Scene': scene_label,
            'Method': 'EB-Octree(Axis)',
            'BE (cm)': be_cm,
            'Compression Ratio': ratio,
            'Compression Time (s)': np.nan,
            'Decompression Time (s)': np.nan,
            'Mean Error (Axis)': eoax['mean_axis'],
            'Max Error (Axis)': eoax['max_axis'],
            'Mean Error (L2)': eoax['mean_l2'],
            'Max Error (L2)': eoax['max_l2'],
            'Num Packets': int(np.ceil(c_bits/1000)) if c_bits > 0 else 0,
            'Chamfer Distance': eoax['chamfer_dist'],
            'Occupancy IoU': eoax['occupancy_iou'],
        })

        # EB-3D = EB-Octree(L2)
        c_oct_l2 = eb.EBOctreeL2Compressor(be_cm/100.0, 1, 1000.0, 32)
        data_ol2 = c_oct_l2.compress(pts)
        c_bits = len(data_ol2) * 8
        ratio = c_bits / raw_bits if raw_bits > 0 else 0
        dec_ol2 = c_oct_l2.decompress(data_ol2)
        eol2 = eb.compute_error(pts, dec_ol2)
        results.append({
            'Scene': scene_label,
            'Method': 'EB-Octree(L2)',
            'BE (cm)': be_cm,
            'Compression Ratio': ratio,
            'Compression Time (s)': np.nan,
            'Decompression Time (s)': np.nan,
            'Mean Error (Axis)': eol2['mean_axis'],
            'Max Error (Axis)': eol2['max_axis'],
            'Mean Error (L2)': eol2['mean_l2'],
            'Max Error (L2)': eol2['max_l2'],
            'Num Packets': int(np.ceil(c_bits/1000)) if c_bits > 0 else 0,
            'Chamfer Distance': eol2['chamfer_dist'],
            'Occupancy IoU': eol2['occupancy_iou'],
        })

        # EB-HC-3D(Axis)
        cmp_data_3a = eb.ebhc3d_axis_compress(pts, be_cm)
        c_bits = len(cmp_data_3a) * 8
        ratio = c_bits / raw_bits if raw_bits > 0 else 0
        dec_3a = eb.ebhc3d_axis_decompress(cmp_data_3a, be_cm)
        e3a = eb.compute_error(pts, dec_3a)
        results.append({
            'Scene': scene_label,
            'Method': 'EB-HC-3D(Axis)',
            'BE (cm)': be_cm,
            'Compression Ratio': ratio,
            'Compression Time (s)': np.nan,
            'Decompression Time (s)': np.nan,
            'Mean Error (Axis)': e3a['mean_axis'],
            'Max Error (Axis)': e3a['max_axis'],
            'Mean Error (L2)': e3a['mean_l2'],
            'Max Error (L2)': e3a['max_l2'],
            'Num Packets': int(np.ceil(c_bits/1000)) if c_bits > 0 else 0,
            'Chamfer Distance': e3a['chamfer_dist'],
            'Occupancy IoU': e3a['occupancy_iou'],
        })

        # EB-HC-3D(L2)
        cmp_data_3l2 = eb.ebhc3d_l2_compress(pts, be_cm)
        c_bits = len(cmp_data_3l2) * 8
        ratio = c_bits / raw_bits if raw_bits > 0 else 0
        dec_3l2 = eb.ebhc3d_l2_decompress(cmp_data_3l2, be_cm)
        e3l2 = eb.compute_error(pts, dec_3l2)
        results.append({
            'Scene': scene_label,
            'Method': 'EB-HC-3D(L2)',
            'BE (cm)': be_cm,
            'Compression Ratio': ratio,
            'Compression Time (s)': np.nan,
            'Decompression Time (s)': np.nan,
            'Mean Error (Axis)': e3l2['mean_axis'],
            'Max Error (Axis)': e3l2['max_axis'],
            'Mean Error (L2)': e3l2['mean_l2'],
            'Max Error (L2)': e3l2['max_l2'],
            'Num Packets': int(np.ceil(c_bits/1000)) if c_bits > 0 else 0,
            'Chamfer Distance': e3l2['chamfer_dist'],
            'Occupancy IoU': e3l2['occupancy_iou'],
        })

    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--data-dir', type=str, default=os.path.join(os.path.dirname(__file__), '..', 'data'))
    parser.add_argument('--max-files', type=int, default=1)
    parser.add_argument('--be-list', type=float, nargs='+', default=[0.5, 1.0, 2.0])
    parser.add_argument('--out-csv', type=str, default=os.path.join(os.path.dirname(__file__), '..', 'outputs', 'compression_results_subset.csv'))
    args = parser.parse_args()

    eb = resolve_eb_module()
    bin_paths = load_bin_paths(args.data_dir, args.max_files)
    if not bin_paths:
        print(f'[WARN] No .bin found under {args.data_dir}')
        return

    all_rows: List[Dict] = []
    for i, bp in enumerate(bin_paths):
        raw = open(bp, 'rb').read()
        if len(raw) % 16 != 0:
            print(f'[SKIP] Invalid .bin: {bp}')
            continue
        pts = np.frombuffer(raw, dtype=np.float32).reshape(-1, 4)[:, :3]
        rows = run_subset_on_points(eb, pts, scene_label=f'sample_{i}', be_list_cm=args.be_list)
        # 在每筆結果補上檔名欄位
        for r in rows:
            r['Filename'] = os.path.basename(bp)
        all_rows.extend(rows)

    cols = [
        'Scene','Filename','Method','BE (cm)',
        'Compression Ratio','Compression Time (s)','Decompression Time (s)',
        'Mean Error (Axis)','Max Error (Axis)',
        'Mean Error (L2)','Max Error (L2)',
        'Num Packets','Chamfer Distance','Occupancy IoU'
    ]
    write_csv(all_rows, args.out_csv, cols)


if __name__ == '__main__':
    main()

