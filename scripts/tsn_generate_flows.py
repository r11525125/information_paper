import os
import csv
import argparse
import math


def read_results_csv(path):
    rows = []
    with open(path, 'r', encoding='utf-8') as fr:
        cr = csv.DictReader(fr)
        for r in cr:
            rows.append(r)
    return rows


def bin_bits(data_dir, filename):
    fp = os.path.join(data_dir, filename)
    if os.path.exists(fp):
        size = os.path.getsize(fp)
        return size * 8
    # fallback: search recursively for first matching filename
    for root, _, files in os.walk(data_dir):
        if filename in files:
            size = os.path.getsize(os.path.join(root, filename))
            return size * 8
    raise FileNotFoundError(f"{filename} not found under {data_dir}")


def main():
    p = argparse.ArgumentParser(description='Generate TSN flow spec from compression results')
    p.add_argument('--results-csv', type=str, default=os.path.join(os.path.dirname(__file__), '..', 'outputs', 'compression_results_subset.csv'))
    p.add_argument('--data-dir', type=str, default=os.path.join(os.path.dirname(__file__), '..', 'data'))
    p.add_argument('--frame-rate', type=float, default=10.0)
    p.add_argument('--packet-size-bits', type=int, default=1000)
    p.add_argument('--priority', type=int, default=7)
    p.add_argument('--out', type=str, default=os.path.join(os.path.dirname(__file__), '..', 'outputs', 'tsn_flows.csv'))
    p.add_argument('--method', type=str, default='', help='Optional method filter, e.g., EB-HC-3D(L2)')
    args = p.parse_args()

    rows = read_results_csv(args.results_csv)
    out_rows = []

    stream_id = 1
    for r in rows:
        if args.method and r.get('Method') != args.method:
            continue
        filename = r.get('Filename', '')
        if not filename or filename == 'MULTI':
            continue

        # Parse numbers
        try:
            ratio = float(r.get('Compression Ratio', '0'))
            be_str = r.get('BE (cm)', '0').replace('cm', '').strip()
            be_cm = float(be_str)
            num_packets = int(r.get('Num Packets', '0'))
        except Exception:
            continue

        raw_bits = bin_bits(args.data_dir, filename)
        compressed_bits_per_frame = ratio * raw_bits
        bitrate_bps = compressed_bits_per_frame * args.frame_rate

        # Derive packets/frame if not provided
        packets_per_frame = num_packets if num_packets > 0 else int(math.ceil(compressed_bits_per_frame / args.packet_size_bits))

        out_rows.append({
            'StreamId': stream_id,
            'Filename': filename,
            'Method': r.get('Method'),
            'BE_cm': be_cm,
            'Bitrate_bps': int(bitrate_bps),
            'PacketsPerFrame': packets_per_frame,
            'PacketSize_bits': args.packet_size_bits,
            'FrameRate_Hz': args.frame_rate,
            'Priority': args.priority,
        })
        stream_id += 1

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, 'w', newline='', encoding='utf-8') as fw:
        fn = ['StreamId','Filename','Method','BE_cm','Bitrate_bps','PacketsPerFrame','PacketSize_bits','FrameRate_Hz','Priority']
        cw = csv.DictWriter(fw, fieldnames=fn)
        cw.writeheader()
        cw.writerows(out_rows)

    print(f'[OK] TSN flows written: {args.out} ({len(out_rows)} streams)')


if __name__ == '__main__':
    main()
