#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
僅保留以下五種壓縮方法:
  (1) Huffman (無誤差)
  (2) EB-HC(Axis)
  (3) EB-HC(L2)
  (4) EB-Octree(Axis)
  (5) EB-Octree(L2)

# **本次需求：再加上 EB-HC-3D(Axis) 與 EB-HC-3D(L2) 兩個方法。**

此外：
Single 要對資料夾下所有 bin 檔逐一測試並在 CSV 記錄 filename；
Multi 保持串接測試的方式不變；
最終在主 CSV 中加上欄位 "Filename"，並額外輸出一個同場景 single 結果的平均 CSV。

再新增兩種評估指標：
 - Chamfer Distance
 - Occupancy IoU
"""

import os
import math
import struct
import csv
import time
import heapq
import zlib
import numpy as np
from typing import Dict, List, Tuple, Optional
from collections import defaultdict
from bitarray import bitarray
from scipy.spatial import cKDTree
import numba
from numba import njit
from numba.typed import List as NumbaList
import argparse

###############################################################################
# (1) 工具、I/O
###############################################################################
def find_bin_files(folder: str, max_count: int = 10) -> List[str]:
    """
    從指定資料夾中搜尋 .bin 檔案，回傳前 max_count 個檔案路徑 (排序後)。
    """
    if not os.path.isdir(folder):
        return []
    files = sorted([
        os.path.join(folder, f)
        for f in os.listdir(folder)
        if f.endswith(".bin")
    ])
    return files[:max_count]

def load_points_from_bin(bin_path: str) -> np.ndarray:
    """
    讀取 KITTI .bin 格式檔，回傳 shape=(N,3) 的點雲 (float32)。
    若檔案無法讀取或長度不合法，回傳空陣列。
    """
    if not os.path.isfile(bin_path):
        return np.empty((0, 3), dtype=np.float32)
    raw = open(bin_path, 'rb').read()
    if len(raw) % 16 != 0:
        return np.empty((0, 3), dtype=np.float32)
    pts = np.frombuffer(raw, dtype=np.float32).reshape(-1, 4)[:, :3]
    return pts

def write_results_to_csv(results: List[dict], csv_path: str, fieldnames: List[str]):
    """
    將 results (list of dict) 全部寫入指定的 csv_path，包含指定欄位(fieldnames)。
    """
    if not results:
        print(f"[INFO] No results to write for CSV={csv_path}")
        return
    with open(csv_path, 'w', newline='', encoding='utf-8') as fw:
        cw = csv.DictWriter(fw, fieldnames=fieldnames)
        cw.writeheader()
        cw.writerows(results)
    print(f"[INFO] => CSV written: {csv_path}, rows={len(results)}")


###############################################################################
# (2) Huffman (Method 1) - 無誤差
###############################################################################
class HuffmanNodeTree:
    def __init__(self, char=None, freq=0, left=None, right=None):
        self.char = char
        self.freq = freq
        self.left = left
        self.right = right
    def __lt__(self, other):
        return self.freq < other.freq

def build_frequency_dict(data_bytes: bytes) -> Dict[int,int]:
    freq={}
    for b in data_bytes:
        freq[b] = freq.get(b, 0) + 1
    return freq

def build_huffman_tree(freq_dict: Dict[int,int]) -> Optional[HuffmanNodeTree]:
    if not freq_dict:
        return None
    heap=[]
    for c,f in freq_dict.items():
        heapq.heappush(heap, HuffmanNodeTree(c, f))
    while len(heap) > 1:
        n1= heapq.heappop(heap)
        n2= heapq.heappop(heap)
        merged= HuffmanNodeTree(None, n1.freq+n2.freq, n1, n2)
        heapq.heappush(heap, merged)
    return heapq.heappop(heap) if heap else None

def build_encoding_dict(huffman_tree: HuffmanNodeTree, prefix="", edict=None) -> Dict[int,str]:
    if edict is None:
        edict={}
    if (huffman_tree.left is None) and (huffman_tree.right is None):
        edict[huffman_tree.char] = prefix if prefix else "0"
        return edict
    if huffman_tree.left:
        build_encoding_dict(huffman_tree.left, prefix + "0", edict)
    if huffman_tree.right:
        build_encoding_dict(huffman_tree.right, prefix + "1", edict)
    return edict

def huffman_encoding(data_bytes: bytes):
    freq= build_frequency_dict(data_bytes)
    total= sum(freq.values())
    if total == 0:
        bits= bitarray()
        return bits, None
    entropy= -sum((v/total)* math.log2(v/total) for v in freq.values())
    tree= build_huffman_tree(freq)
    code_dict= build_encoding_dict(tree)
    avg_len= sum(len(code_dict[b])*freq[b] for b in freq)/ total
    comp_eff= (entropy/avg_len) if avg_len>0 else 0
    print(f"    Huffman entropy={entropy:.3f}, avgLen={avg_len:.3f}, eff={comp_eff:.3f}")

    bits= bitarray()
    for b in data_bytes:
        bits.extend(code_dict[b])
    return bits, tree

def huffman_decoding(encoded_bits: bitarray, tree: Optional[HuffmanNodeTree])-> bytes:
    if (not encoded_bits) or (not tree):
        return b""
    # 如果只有單一節點
    if (tree.left is None) and (tree.right is None):
        return bytes([tree.char]* len(encoded_bits))
    out= bytearray()
    node= tree
    for bit in encoded_bits:
        node= node.left if bit==0 else node.right
        if not node:
            break
        if (node.left is None) and (node.right is None):
            out.append(node.char)
            node= tree
            if not node:
                break
    return bytes(out)


###############################################################################
# (3) EB-HC(Axis/L2) => 1D threshold + Huffman
###############################################################################
def merge_ints_by_threshold(arr: np.ndarray, threshold_int: int):
    """
    將 arr 中值 (int) 依 threshold_int 相近合併
    """
    if len(arr)==0:
        return {}, {}
    idx_s= np.argsort(arr)
    svals= arr[idx_s]
    freq={}
    map_dict={}
    curr= svals[0]
    freq[curr]=1
    map_dict[idx_s[0]]= curr
    for i in range(1, len(svals)):
        v= svals[i]
        idx= idx_s[i]
        if abs(v - curr) <= threshold_int:
            freq[curr]+=1
            map_dict[idx]= curr
        else:
            curr= v
            freq[curr]=1
            map_dict[idx]= curr
    val2rep={}
    for i in range(len(arr)):
        orgv= arr[i]
        rep= map_dict[i]
        val2rep[orgv]= rep
    return freq, val2rep

def build_huffman_encode_1d(data_list: List[int]):
    """
    對 1D 資料列表 (int) 做 Huffman 編碼
    回傳編碼後 bits 及 Huffman 樹
    """
    freq={}
    for v in data_list:
        freq[v]= freq.get(v,0)+1
    total= sum(freq.values())
    if total==0:
        from bitarray import bitarray
        return bitarray(), None
    entropy= -sum((v/total)* math.log2(v/total) for v in freq.values())
    tree= build_huffman_tree(freq)
    code_dict= build_encoding_dict(tree)
    avg_len= sum(len(code_dict[v])*freq[v] for v in freq)/ total
    comp_eff= (entropy/avg_len) if avg_len>0 else 0
    print(f"    Huffman(EB-HC) Entropy={entropy:.3f}, avgLen={avg_len:.3f}, eff={comp_eff:.3f}")

    from bitarray import bitarray
    bits= bitarray()
    for v in data_list:
        bits.extend(code_dict[v])
    return bits, tree

def ebhc_encode_axis(qpts: np.ndarray, be_cm=10.0, scale_factor=1000):
    """
    EB-HC(Axis) 實作：
      - threshold_int = floor((be_cm*scale_factor)/100.0) / 1.65
      - 分別對 X, Y, Z 合併後 Huffman
    """
    k=1.65  # 原程式中用於縮小 threshold
    thresh= int(math.floor(be_cm*scale_factor /(100.0*k)))
    arrX= qpts[:,0]
    arrY= qpts[:,1]
    arrZ= qpts[:,2]
    # X
    xfreq, xmap= merge_ints_by_threshold(arrX, thresh)
    x_syms= [xmap[v] for v in arrX]
    x_enc, x_tree= build_huffman_encode_1d(x_syms)
    # Y
    yfreq, ymap= merge_ints_by_threshold(arrY, thresh)
    y_syms= [ymap[v] for v in arrY]
    y_enc, y_tree= build_huffman_encode_1d(y_syms)
    # Z
    zfreq, zmap= merge_ints_by_threshold(arrZ, thresh)
    z_syms= [zmap[v] for v in arrZ]
    z_enc, z_tree= build_huffman_encode_1d(z_syms)

    hdr= struct.pack('III', len(x_enc), len(y_enc), len(z_enc))
    from bitarray import bitarray
    bits= bitarray()
    bits.extend(x_enc)
    bits.extend(y_enc)
    bits.extend(z_enc)
    return hdr+ bits.tobytes(), (x_tree,y_tree,z_tree)

def decode_1d_axis(bits: bitarray, tree: Optional[HuffmanNodeTree]) -> List[int]:
    """
    用 HuffmanNodeTree 解碼 1D 資料 (bits)
    """
    if (not bits) or (not tree):
        return []
    if (tree.left is None) and (tree.right is None):
        return [tree.char]* len(bits)
    out=[]
    node= tree
    for b in bits:
        node= node.left if b==0 else node.right
        if (node.left is None) and (node.right is None):
            out.append(node.char)
            node= tree
    return out

def ebhc_decode_axis(encoded_data: bytes, trees, N:int)-> np.ndarray:
    x_tree,y_tree,z_tree= trees
    hs= struct.calcsize('III')
    x_len, y_len, z_len= struct.unpack('III', encoded_data[:hs])
    data_bits= encoded_data[hs:]
    from bitarray import bitarray
    bits= bitarray()
    bits.frombytes(data_bits)

    x_bits= bits[:x_len]
    y_bits= bits[x_len:x_len+y_len]
    z_bits= bits[x_len+y_len:x_len+y_len+z_len]

    x_ids= decode_1d_axis(x_bits, x_tree)
    y_ids= decode_1d_axis(y_bits, y_tree)
    z_ids= decode_1d_axis(z_bits, z_tree)
    out= np.zeros((N,3), dtype=np.int32)
    for i in range(N):
        out[i,0]= x_ids[i] if i<len(x_ids) else 0
        out[i,1]= y_ids[i] if i<len(y_ids) else 0
        out[i,2]= z_ids[i] if i<len(z_ids) else 0
    return out

def ebhc_encode_l2(qpts: np.ndarray, be_cm=10.0, scale_factor=1000):
    """
    EB-HC(L2) 實作:
      - threshold_int = floor((be_cm*scale_factor)/(100*sqrt(3)))
      - 同樣對 X,Y,Z 分別 Huffman
    """
    thresh= int(math.floor(be_cm*scale_factor /100.0 /math.sqrt(3)))
    arrX= qpts[:,0]
    arrY= qpts[:,1]
    arrZ= qpts[:,2]
    xfreq, xmap= merge_ints_by_threshold(arrX, thresh)
    x_syms= [xmap[v] for v in arrX]
    x_enc, x_tree= build_huffman_encode_1d(x_syms)

    yfreq, ymap= merge_ints_by_threshold(arrY, thresh)
    y_syms= [ymap[v] for v in arrY]
    y_enc, y_tree= build_huffman_encode_1d(y_syms)

    zfreq, zmap= merge_ints_by_threshold(arrZ, thresh)
    z_syms= [zmap[v] for v in arrZ]
    z_enc, z_tree= build_huffman_encode_1d(z_syms)

    hdr= struct.pack('III', len(x_enc), len(y_enc), len(z_enc))
    from bitarray import bitarray
    bits= bitarray()
    bits.extend(x_enc)
    bits.extend(y_enc)
    bits.extend(z_enc)
    return hdr+ bits.tobytes(), (x_tree,y_tree,z_tree)

def ebhc_decode_l2(encoded_data: bytes, trees, N:int)-> np.ndarray:
    x_tree,y_tree,z_tree= trees
    hs= struct.calcsize('III')
    x_len, y_len, z_len= struct.unpack('III', encoded_data[:hs])
    data_bits= encoded_data[hs:]
    from bitarray import bitarray
    bits= bitarray()
    bits.frombytes(data_bits)

    x_bits= bits[:x_len]
    y_bits= bits[x_len:x_len+y_len]
    z_bits= bits[x_len+y_len:x_len+y_len+z_len]

    x_ids= decode_1d_axis(x_bits, x_tree)
    y_ids= decode_1d_axis(y_bits, y_tree)
    z_ids= decode_1d_axis(z_bits, z_tree)
    out= np.zeros((N,3), dtype=np.int32)
    for i in range(N):
        out[i,0]= x_ids[i] if i<len(x_ids) else 0
        out[i,1]= y_ids[i] if i<len(y_ids) else 0
        out[i,2]= z_ids[i] if i<len(z_ids) else 0
    return out


###############################################################################
# (4) EB-Octree(Axis)/(L2)
###############################################################################
@njit
def partition_points(points: np.ndarray, cx: float, cy: float, cz: float):
    """
    將 points 按 xyz 與 (cx,cy,cz) 比較拆成 8 個子集合 => octree
    回傳 out0~out7 (8個子集合)
    """
    n= points.shape[0]
    counts= np.zeros(8, dtype=numba.int32)
    for i in range(n):
        px= points[i,0]
        py= points[i,1]
        pz= points[i,2]
        idx=0
        if px>=cx: idx|=1
        if py>=cy: idx|=2
        if pz>=cz: idx|=4
        counts[idx]+=1

    out0= np.empty((counts[0],3), dtype=numba.float64)
    out1= np.empty((counts[1],3), dtype=numba.float64)
    out2= np.empty((counts[2],3), dtype=numba.float64)
    out3= np.empty((counts[3],3), dtype=numba.float64)
    out4= np.empty((counts[4],3), dtype=numba.float64)
    out5= np.empty((counts[5],3), dtype=numba.float64)
    out6= np.empty((counts[6],3), dtype=numba.float64)
    out7= np.empty((counts[7],3), dtype=numba.float64)

    ptr= np.zeros(8, dtype=numba.int32)
    for i in range(n):
        px= points[i,0]
        py= points[i,1]
        pz= points[i,2]
        idx=0
        if px>=cx: idx|=1
        if py>=cy: idx|=2
        if pz>=cz: idx|=4
        c= ptr[idx]
        if idx==0: out0[c,0]= px; out0[c,1]= py; out0[c,2]= pz
        elif idx==1: out1[c,0]= px; out1[c,1]= py; out1[c,2]= pz
        elif idx==2: out2[c,0]= px; out2[c,1]= py; out2[c,2]= pz
        elif idx==3: out3[c,0]= px; out3[c,1]= py; out3[c,2]= pz
        elif idx==4: out4[c,0]= px; out4[c,1]= py; out4[c,2]= pz
        elif idx==5: out5[c,0]= px; out5[c,1]= py; out5[c,2]= pz
        elif idx==6: out6[c,0]= px; out6[c,1]= py; out6[c,2]= pz
        else:        out7[c,0]= px; out7[c,1]= py; out7[c,2]= pz
        ptr[idx]+=1
    return out0,out1,out2,out3,out4,out5,out6,out7

class EntropyCompressor:
    """
    簡易 zlib + struct.pack, 用於將 int list 壓縮 / 解壓
    """
    def encode(self, arr: List[int])-> bytes:
        raw= struct.pack(f"{len(arr)}i", *arr)
        return zlib.compress(raw)

    def decode(self, data: bytes)-> List[int]:
        if not data:
            return []
        d= zlib.decompress(data)
        n= len(d)//4
        return list(struct.unpack(f"{n}i", d))

@njit
def min_per_axis(pts: np.ndarray):
    """
    返回 (minx, miny, minz)
    """
    n= pts.shape[0]
    if n==0:
        return (0.0,0.0,0.0)
    m0=1e30
    m1=1e30
    m2=1e30
    for i in range(n):
        px= pts[i,0]
        py= pts[i,1]
        pz= pts[i,2]
        if px<m0: m0=px
        if py<m1: m1=py
        if pz<m2: m2=pz
    return (m0,m1,m2)

@njit
def max_per_axis(pts: np.ndarray):
    """
    返回 (maxx, maxy, maxz)
    """
    n= pts.shape[0]
    if n==0:
        return (0.0,0.0,0.0)
    m0=-1e30
    m1=-1e30
    m2=-1e30
    for i in range(n):
        px= pts[i,0]
        py= pts[i,1]
        pz= pts[i,2]
        if px>m0: m0=px
        if py>m1: m1=py
        if pz>m2: m2=pz
    return (m0,m1,m2)

@njit
def sum_per_axis(pts: np.ndarray):
    """
    返回 (sumx, sumy, sumz)
    """
    n= pts.shape[0]
    s0=0.0
    s1=0.0
    s2=0.0
    for i in range(n):
        s0+= pts[i,0]
        s1+= pts[i,1]
        s2+= pts[i,2]
    return (s0,s1,s2)


###############################################################################
# (4a) EB-Octree(Axis) / EB-Octree(L2) => flatten
###############################################################################
@njit
def flatten_eb_octree_axis(points: np.ndarray,
                           be_m: float,
                           min_points: int,
                           scale_factor: float,
                           max_depth: int,
                           depth: int,
                           tree_list,  # typed list[int]
                           center_list # typed list[int]
                           ):
    """
    EB-Octree(Axis) => 遞迴
    """
    n= points.shape[0]
    if n==0:
        return

    s0,s1,s2= sum_per_axis(points)
    cx= s0/n
    cy= s1/n
    cz= s2/n

    c_intx= int(round(cx* scale_factor))
    c_inty= int(round(cy* scale_factor))
    c_intz= int(round(cz* scale_factor))
    repx= c_intx/ scale_factor
    repy= c_inty/ scale_factor
    repz= c_intz/ scale_factor

    # 計算 axis-wise 誤差
    max1d=0.0
    for i in range(n):
        dx= abs(points[i,0]- repx)
        dy= abs(points[i,1]- repy)
        dz= abs(points[i,2]- repz)
        local_max= dx if dx>dy else dy
        if dz> local_max:
            local_max= dz
        if local_max> max1d:
            max1d= local_max
    if (max1d <= be_m) or (n<=min_points) or (depth>=max_depth):
        # 先檢查 bounding box
        mnx,mny,mnz = min_per_axis(points)
        mxx,mxy,mxz = max_per_axis(points)
        len_x = (mxx - mnx)
        len_y = (mxy - mny)
        len_z = (mxz - mnz)
        half_x = 0.5*len_x
        half_y = 0.5*len_y
        half_z = 0.5*len_z
        fix_x = 0.75*len_x
        fix_y = 0.75*len_y
        fix_z = 0.75*len_z
        if max(fix_x, fix_y,fix_z) <= be_m:
            tree_list.append(0)
            center_list.append(c_intx)
            center_list.append(c_inty) 
            center_list.append(c_intz)
            return

    mask_pos= len(tree_list)
    tree_list.append(-1) # placeholder

    mnx,mny,mnz= min_per_axis(points)
    mxx,mxy,mxz= max_per_axis(points)
    cxx= 0.5*(mnx+ mxx)
    cyy= 0.5*(mny+ mxy)
    czz= 0.5*(mnz+ mxz)
    outs= partition_points(points, cxx, cyy, czz)
    mask_val=0
    for iChild in range(8):
        child= outs[iChild]
        if child.shape[0]>0:
            mask_val|= (1<< iChild)
            flatten_eb_octree_axis(child, be_m, min_points, scale_factor,
                                   max_depth, depth+1,
                                   tree_list, center_list)
    tree_list[mask_pos]= mask_val

@njit
def flatten_eb_octree_l2(points: np.ndarray,
                         be_m: float,
                         min_points: int,
                         scale_factor: float,
                         max_depth: int,
                         depth: int,
                         tree_list,
                         center_list):
    """
    EB-Octree(L2) => 遞迴
    """
    n= points.shape[0]
    if n==0:
        return
    s0,s1,s2= sum_per_axis(points)
    cx= s0/n
    cy= s1/n
    cz= s2/n

    cix= int(round(cx* scale_factor))
    ciy= int(round(cy* scale_factor))
    ciz= int(round(cz* scale_factor))
    rx= cix/ scale_factor
    ry= ciy/ scale_factor
    rz= ciz/ scale_factor

    # L2
    maxd=0.0
    for i in range(n):
        dx= points[i,0]- rx
        dy= points[i,1]- ry
        dz= points[i,2]- rz
        dd= dx*dx+ dy*dy+ dz*dz
        if dd> maxd:
            maxd= dd
    maxd= math.sqrt(maxd)

    if (maxd<= be_m) or (n<= min_points) or (depth>= max_depth):
        tree_list.append(0)
        center_list.append(cix)
        center_list.append(ciy)
        center_list.append(ciz)
        return

    mask_pos= len(tree_list)
    tree_list.append(-1)

    mnx,mny,mnz= min_per_axis(points)
    mxx,mxy,mxz= max_per_axis(points)
    cxx= 0.5*(mnx+ mxx)
    cyy= 0.5*(mny+ mxy)
    czz= 0.5*(mnz+ mxz)
    outs= partition_points(points, cxx, cyy, czz)
    mask_val=0
    for iChild in range(8):
        child= outs[iChild]
        if child.shape[0]>0:
            mask_val|= (1<< iChild)
            flatten_eb_octree_l2(child, be_m, min_points, scale_factor,
                                 max_depth, depth+1,
                                 tree_list, center_list)
    tree_list[mask_pos]= mask_val


###############################################################################
# (4b) EBOctreeAxisCompressor, EBOctreeL2Compressor
###############################################################################
class EBOctreeAxisCompressor:
    def __init__(self, be_m=0.1, min_points=1, scale_factor=1000.0, max_depth=32):
        self.be_m= be_m
        self.min_points= min_points
        self.scale_factor= scale_factor
        self.max_depth= max_depth

    def compress(self, points: np.ndarray)-> bytes:
        if len(points)==0:
            return b""
        from numba.typed import List as NumbaList
        tree_list= NumbaList.empty_list(numba.int32)
        center_list= NumbaList.empty_list(numba.int32)

        flatten_eb_octree_axis(points.astype(np.float64),
                               self.be_m,
                               self.min_points,
                               self.scale_factor,
                               self.max_depth,
                               0,
                               tree_list,
                               center_list)
        tb= list(tree_list)
        cb= list(center_list)
        ec= EntropyCompressor()
        tb_enc= ec.encode(tb)
        cb_enc= ec.encode(cb)
        be_int= int(round(self.be_m*100))
        hdr= struct.pack('iiii', be_int, self.min_points, int(self.scale_factor), self.max_depth)
        sz= struct.pack('QQ', len(tb_enc), len(cb_enc))
        return hdr+ sz+ tb_enc+ cb_enc

    def decompress(self, data: bytes)-> np.ndarray:
        if not data:
            return np.empty((0,3), dtype=np.float32)
        pos=0
        hdsize= struct.calcsize('iiii')
        be_int, mp, scf, md= struct.unpack('iiii', data[:hdsize])
        pos+= hdsize
        self.be_m= be_int/100.0
        self.min_points= mp
        self.scale_factor= float(scf)
        self.max_depth= md
        s2= struct.calcsize('QQ')
        t_size, c_size= struct.unpack('QQ', data[pos:pos+s2])
        pos+= s2
        tb_enc= data[pos:pos+t_size]
        pos+= t_size
        cb_enc= data[pos:pos+c_size]
        pos+= c_size
        dec= EntropyCompressor()
        tree_blocks= dec.decode(tb_enc)
        center_blocks= dec.decode(cb_enc)

        # BFS decode => 只還原葉 center
        rec_pts=[]
        st= [(0, 0)]  # (iT, iC)
        iT=0
        iC=0
        while len(st)>0:
            (curT,curC)= st.pop()
            if iT>= len(tree_blocks):
                break
            nodeVal= tree_blocks[iT]
            iT+=1
            if nodeVal==0:
                if iC+3> len(center_blocks):
                    break
                cx_i= center_blocks[iC]
                cy_i= center_blocks[iC+1]
                cz_i= center_blocks[iC+2]
                iC+=3
                cx= cx_i/self.scale_factor
                cy= cy_i/self.scale_factor
                cz= cz_i/self.scale_factor
                rec_pts.append((cx,cy,cz))
            else:
                mask= nodeVal
                for cID in range(7,-1,-1):
                    if (mask>>cID)&1:
                        st.append((iT,iC))

        return np.array(rec_pts, dtype=np.float32)


class EBOctreeL2Compressor:
    def __init__(self, be_m=0.1, min_points=1, scale_factor=1000.0, max_depth=32):
        self.be_m= be_m
        self.min_points= min_points
        self.scale_factor= scale_factor
        self.max_depth= max_depth

    def compress(self, points: np.ndarray)-> bytes:
        if len(points)==0:
            return b""
        from numba.typed import List as NumbaList
        tree_list= NumbaList.empty_list(numba.int32)
        center_list= NumbaList.empty_list(numba.int32)

        flatten_eb_octree_l2(points.astype(np.float64),
                             self.be_m,
                             self.min_points,
                             self.scale_factor,
                             self.max_depth,
                             0,
                             tree_list,
                             center_list)
        tb= list(tree_list)
        cb= list(center_list)
        ec= EntropyCompressor()
        tb_enc= ec.encode(tb)
        cb_enc= ec.encode(cb)
        be_int= int(round(self.be_m*100))
        hdr= struct.pack('iiii', be_int, self.min_points, int(self.scale_factor), self.max_depth)
        sz= struct.pack('QQ', len(tb_enc), len(cb_enc))
        return hdr+ sz+ tb_enc+ cb_enc

    def decompress(self, data: bytes)-> np.ndarray:
        if not data:
            return np.empty((0,3), dtype=np.float32)
        pos=0
        hdsize= struct.calcsize('iiii')
        be_int, mp, scf, md= struct.unpack('iiii', data[:hdsize])
        pos+= hdsize
        self.be_m= be_int/100.0
        self.min_points= mp
        self.scale_factor= float(scf)
        self.max_depth= md
        s2= struct.calcsize('QQ')
        t_size, c_size= struct.unpack('QQ', data[pos:pos+s2])
        pos+= s2
        tb_enc= data[pos:pos+t_size]
        pos+= t_size
        cb_enc= data[pos:pos+c_size]
        pos+= c_size
        dec= EntropyCompressor()
        tree_blocks= dec.decode(tb_enc)
        center_blocks= dec.decode(cb_enc)

        rec_pts=[]
        st= [(0,0)]
        iT=0
        iC=0
        while len(st)>0:
            (curT,curC)= st.pop()
            if iT>= len(tree_blocks):
                break
            nodeVal= tree_blocks[iT]
            iT+=1
            if nodeVal==0:
                if iC+3> len(center_blocks):
                    break
                cx_i= center_blocks[iC]
                cy_i= center_blocks[iC+1]
                cz_i= center_blocks[iC+2]
                iC+=3
                cx= cx_i/self.scale_factor
                cy= cy_i/self.scale_factor
                cz= cz_i/self.scale_factor
                rec_pts.append((cx,cy,cz))
            else:
                mask= nodeVal
                for cID in range(7,-1,-1):
                    if (mask>>cID)&1:
                        st.append((iT,iC))

        return np.array(rec_pts, dtype=np.float32)


###############################################################################
# (5) EB-HC-3D(Axis)/(L2)
###############################################################################
class HuffmanNode:
    def __init__(self, symbol=None, freq=0):
        self.symbol = symbol
        self.freq = freq
        self.left = None
        self.right = None
    def __lt__(self, other):
        return self.freq < other.freq

class HuffmanEncoder:
    def __init__(self):
        self.code_table = {}

    def build_tree(self, freq_dict: Dict[int, int]) -> HuffmanNode:
        import heapq
        heap = [HuffmanNode(sym, fr) for sym, fr in freq_dict.items()]
        heapq.heapify(heap)
        while len(heap) > 1:
            left = heapq.heappop(heap)
            right = heapq.heappop(heap)
            merged = HuffmanNode(freq=left.freq + right.freq)
            merged.left = left
            merged.right = right
            heapq.heappush(heap, merged)
        return heap[0] if heap else None

    def build_code_table(self, node, current_code=""):
        if node is None:
            return
        if node.symbol is not None:
            self.code_table[node.symbol] = current_code
            return
        self.build_code_table(node.left, current_code + "0")
        self.build_code_table(node.right, current_code + "1")

    def encode(self, data: List[int]) -> (bytes, int):
        encoded_bits = ''.join(self.code_table[sym] for sym in data)
        padding = 8 - (len(encoded_bits) % 8)
        if padding == 8:
            padding = 0
        encoded_bits += '0' * padding
        out_bytes = bytearray()
        for i in range(0, len(encoded_bits), 8):
            segment = encoded_bits[i:i+8]
            val = int(segment, 2)
            out_bytes.append(val)
        return bytes(out_bytes), padding

class HuffmanDecoder:
    def __init__(self, code_table: Dict[int, str]):
        self.root = HuffmanNode()
        for sym, code in code_table.items():
            node = self.root
            for bit in code:
                if bit == '0':
                    if not node.left:
                        node.left = HuffmanNode()
                    node = node.left
                else:
                    if not node.right:
                        node.right = HuffmanNode()
                    node = node.right
            node.symbol = sym

    def decode(self, encoded_data: bytes, padding: int) -> List[int]:
        bit_str = ''.join(f"{byte:08b}" for byte in encoded_data)
        if padding > 0:
            bit_str = bit_str[:-padding]
        decoded_symbols = []
        node = self.root
        for bit in bit_str:
            node = node.left if (bit == '0') else node.right
            if node.symbol is not None:
                decoded_symbols.append(node.symbol)
                node = self.root
        return decoded_symbols

@njit
def subdivide_axis_jit(points: np.ndarray, center: np.ndarray, size: float,
                       error_bound: float, max_depth: int, depth: int,
                       symbol_stream):
    """
    EB-HC-3D(Axis) => 3D Octree + Axis bound
    """
    N = points.shape[0]
    if N == 0:
        return

    max1d_err = 0.0
    for i in range(N):
        dx = abs(points[i,0] - center[0])
        dy = abs(points[i,1] - center[1])
        dz = abs(points[i,2] - center[2])
        local_max = dx
        if dy> local_max:
            local_max= dy
        if dz> local_max:
            local_max= dz
        if local_max> max1d_err:
            max1d_err= local_max

    if max1d_err <= error_bound or depth>= max_depth:
        symbol_stream.append(76) # 'L'
        n3 = (N>>24)&0xFF
        n2 = (N>>16)&0xFF
        n1 = (N>>8)&0xFF
        n0 = N &0xFF
        symbol_stream.append(n3)
        symbol_stream.append(n2)
        symbol_stream.append(n1)
        symbol_stream.append(n0)
        for i in range(N):
            qx = int(round((points[i,0] - center[0]) / error_bound))
            qy = int(round((points[i,1] - center[1]) / error_bound))
            qz = int(round((points[i,2] - center[2]) / error_bound))
            symbol_stream.append(qx+128)
            symbol_stream.append(qy+128)
            symbol_stream.append(qz+128)
        return

    i_pos= len(symbol_stream)
    symbol_stream.append(78)  # 'N'
    symbol_stream.append(0)   # child_mask

    half= size*0.5
    quarter= size*0.25

    idx_array= np.zeros(N, dtype=np.uint8)
    for i in range(N):
        px= points[i,0]
        py= points[i,1]
        pz= points[i,2]
        mask= 0
        if px>= center[0]:
            mask|=1
        if py>= center[1]:
            mask|=2
        if pz>= center[2]:
            mask|=4
        idx_array[i]= mask

    child_mask= 0
    for oct_idx in range(8):
        sel= (idx_array== oct_idx)
        if not np.any(sel):
            continue
        sub_pts= points[sel]
        newc= center.copy()
        if (oct_idx&1):
            newc[0]+= quarter
        else:
            newc[0]-= quarter
        if (oct_idx&2):
            newc[1]+= quarter
        else:
            newc[1]-= quarter
        if (oct_idx&4):
            newc[2]+= quarter
        else:
            newc[2]-= quarter
        child_mask|= (1<<oct_idx)
        subdivide_axis_jit(sub_pts, newc, half, error_bound,
                           max_depth, depth+1, symbol_stream)

    symbol_stream[i_pos+1] = child_mask

@njit
def subdivide_l2_jit(points: np.ndarray, center: np.ndarray, size: float,
                     error_bound: float, max_depth: int, depth: int,
                     symbol_stream):
    """
    EB-HC-3D(L2) => 3D Octree + L2 bound
    """
    N= points.shape[0]
    if N==0:
        return
    max_l2= 0.0
    for i in range(N):
        dx= points[i,0]- center[0]
        dy= points[i,1]- center[1]
        dz= points[i,2]- center[2]
        dist= math.sqrt(dx*dx+ dy*dy+ dz*dz)
        if dist> max_l2:
            max_l2= dist

    if max_l2<= error_bound or depth>= max_depth:
        symbol_stream.append(76) # 'L'
        n3= (N>>24)&0xFF
        n2= (N>>16)&0xFF
        n1= (N>>8)&0xFF
        n0= N &0xFF
        symbol_stream.append(n3)
        symbol_stream.append(n2)
        symbol_stream.append(n1)
        symbol_stream.append(n0)
        for i in range(N):
            dx= (points[i,0]- center[0])/ error_bound
            dy= (points[i,1]- center[1])/ error_bound
            dz= (points[i,2]- center[2])/ error_bound
            qx= int(round(dx))
            qy= int(round(dy))
            qz= int(round(dz))
            symbol_stream.append(qx+128)
            symbol_stream.append(qy+128)
            symbol_stream.append(qz+128)
        return

    i_pos= len(symbol_stream)
    symbol_stream.append(78) # 'N'
    symbol_stream.append(0)
    half= size*0.5
    quarter= size*0.25

    idx_array= np.zeros(N, dtype=np.uint8)
    for i in range(N):
        px= points[i,0]
        py= points[i,1]
        pz= points[i,2]
        mask= 0
        if px>= center[0]:
            mask|=1
        if py>= center[1]:
            mask|=2
        if pz>= center[2]:
            mask|=4
        idx_array[i]= mask

    child_mask= 0
    for oct_idx in range(8):
        sel= (idx_array== oct_idx)
        if not np.any(sel):
            continue
        sub_pts= points[sel]
        newc= center.copy()
        if (oct_idx&1):
            newc[0]+= quarter
        else:
            newc[0]-= quarter
        if (oct_idx&2):
            newc[1]+= quarter
        else:
            newc[1]-= quarter
        if (oct_idx&4):
            newc[2]+= quarter
        else:
            newc[2]-= quarter
        child_mask|= (1<<oct_idx)
        subdivide_l2_jit(sub_pts, newc, half, error_bound,
                         max_depth, depth+1, symbol_stream)

    symbol_stream[i_pos+1]= child_mask

class OctreeEncoderAxisNumba:
    def __init__(self, max_depth=10, error_bound=0.20):
        from numba.typed import List as NumbaList
        self.max_depth= max_depth
        self.error_bound= error_bound
        self.root_center= None
        self.root_size= 0.0
        self.symbol_stream= NumbaList.empty_list(numba.int32)

    def build_octree(self, pts: np.ndarray):
        if pts.shape[0]==0:
            return
        pts= pts.astype(np.float64, copy=False)
        mn= pts.min(axis=0)
        mx= pts.max(axis=0)
        center= (mn+ mx)*0.5
        size= float(np.max(mx- mn))
        self.root_center= center
        self.root_size= size
        subdivide_axis_jit(pts, center, size,
                           self.error_bound, self.max_depth, 0,
                           self.symbol_stream)

class OctreeEncoderL2Numba:
    def __init__(self, max_depth=10, error_bound=0.20):
        from numba.typed import List as NumbaList
        self.max_depth= max_depth
        self.error_bound= error_bound
        self.root_center= None
        self.root_size= 0.0
        self.symbol_stream= NumbaList.empty_list(numba.int32)

    def build_octree(self, pts: np.ndarray):
        pts= pts.astype(np.float64, copy=False)
        if pts.shape[0]==0:
            return
        mn= pts.min(axis=0)
        mx= pts.max(axis=0)
        center= (mn+ mx)*0.5
        size= float(np.max(mx- mn))
        self.root_center= center
        self.root_size= size
        subdivide_l2_jit(pts, center, size,
                         self.error_bound, self.max_depth, 0,
                         self.symbol_stream)

def ebhc3d_axis_compress(pts: np.ndarray, be_cm: float) -> bytes:
    """
    EB-HC-3D(Axis) => 3D Octree + Axis bound + Huffman
    """
    if len(pts)==0:
        return b""
    error_bound= be_cm/100.0
    max_depth= 10
    enc= OctreeEncoderAxisNumba(max_depth, error_bound)
    enc.build_octree(pts)
    symbol_stream_py= list(enc.symbol_stream)
    if len(symbol_stream_py)==0:
        return b""

    from collections import defaultdict
    freq= defaultdict(int)
    for s in symbol_stream_py:
        freq[s]+=1

    henc= HuffmanEncoder()
    root= henc.build_tree(freq)
    henc.build_code_table(root)
    encoded_data, real_padding= henc.encode(symbol_stream_py)

    mn= enc.root_center
    ms= enc.root_size
    meta= struct.pack("dddd", mn[0], mn[1], mn[2], ms)

    code_bytes= bytearray()
    for sym, code in henc.code_table.items():
        code_bytes.append(sym)
        code_bytes.append(len(code))
        code_bytes.extend(code.encode('ascii'))

    out= bytearray()
    out.extend(meta)
    out.extend(struct.pack('B', real_padding))
    out.extend(struct.pack('I', len(code_bytes)))
    out.extend(code_bytes)
    out.extend(struct.pack('I', len(encoded_data)))
    out.extend(encoded_data)
    return bytes(out)

def ebhc3d_l2_compress(pts: np.ndarray, be_cm: float) -> bytes:
    """
    EB-HC-3D(L2) => 3D Octree + L2 bound + Huffman
    """
    if len(pts)==0:
        return b""
    error_bound= be_cm/100.0
    max_depth= 10
    enc= OctreeEncoderL2Numba(max_depth, error_bound)
    enc.build_octree(pts)
    symbol_stream_py= list(enc.symbol_stream)
    if len(symbol_stream_py)==0:
        return b""

    from collections import defaultdict
    freq= defaultdict(int)
    for s in symbol_stream_py:
        freq[s]+=1

    henc= HuffmanEncoder()
    root= henc.build_tree(freq)
    henc.build_code_table(root)
    encoded_data, real_padding= henc.encode(symbol_stream_py)

    mn= enc.root_center
    ms= enc.root_size
    meta= struct.pack("dddd", mn[0], mn[1], mn[2], ms)

    code_bytes= bytearray()
    for sym, code in henc.code_table.items():
        code_bytes.append(sym)
        code_bytes.append(len(code))
        code_bytes.extend(code.encode('ascii'))

    out= bytearray()
    out.extend(meta)
    out.extend(struct.pack('B', real_padding))
    out.extend(struct.pack('I', len(code_bytes)))
    out.extend(code_bytes)
    out.extend(struct.pack('I', len(encoded_data)))
    out.extend(encoded_data)
    return bytes(out)

class OctreeDecoderAxis:
    def __init__(self, error_bound=0.20):
        self.error_bound= error_bound
        self.quant_step= error_bound
        self.decoded_points: List[List[float]]= []

    def decode(self, symbol_stream: List[int], center: np.ndarray, size: float):
        stack= [(center.copy(), size)]
        i=0
        n= len(symbol_stream)
        while stack and i<n:
            cC, cS= stack.pop()
            sym= symbol_stream[i]
            i+=1
            if sym==78: # 'N'
                child_mask= symbol_stream[i]
                i+=1
                quarter= cS/4
                half= cS/2
                for cidx in reversed(range(8)):
                    if (child_mask>>cidx)&1:
                        newc= cC.copy()
                        if (cidx&1):
                            newc[0]+= quarter
                        else:
                            newc[0]-= quarter
                        if (cidx&2):
                            newc[1]+= quarter
                        else:
                            newc[1]-= quarter
                        if (cidx&4):
                            newc[2]+= quarter
                        else:
                            newc[2]-= quarter
                        stack.append((newc, half))
            elif sym==76: # 'L'
                if i+3>= n:
                    break
                n3= symbol_stream[i]
                n2= symbol_stream[i+1]
                n1= symbol_stream[i+2]
                n0= symbol_stream[i+3]
                i+=4
                leaf_count= (n3<<24)|(n2<<16)|(n1<<8)|n0
                for _ in range(leaf_count):
                    if i+2>= n:
                        break
                    x= symbol_stream[i]
                    y= symbol_stream[i+1]
                    z= symbol_stream[i+2]
                    i+=3
                    rx= cC[0]+ (x-128)* self.quant_step
                    ry= cC[1]+ (y-128)* self.quant_step
                    rz= cC[2]+ (z-128)* self.quant_step
                    self.decoded_points.append([rx, ry, rz])
            else:
                break

def ebhc3d_axis_decompress(data: bytes, be_cm: float) -> np.ndarray:
    if not data:
        return np.empty((0,3), dtype=np.float32)
    pos=0
    meta= data[:32]
    cx, cy, cz, size= struct.unpack("dddd", meta)
    center= np.array([cx,cy,cz], dtype=np.float64)
    pos+=32

    real_padding= data[pos]
    pos+=1

    code_size= struct.unpack('I', data[pos:pos+4])[0]
    pos+=4
    code_bytes= data[pos:pos+code_size]
    pos+= code_size

    code_table={}
    i=0
    while i< len(code_bytes):
        sym= code_bytes[i]
        code_len= code_bytes[i+1]
        code_str= code_bytes[i+2:i+2+code_len].decode('ascii')
        code_table[sym]= code_str
        i+= (2+ code_len)

    data_size= struct.unpack('I', data[pos:pos+4])[0]
    pos+=4
    encoded_data= data[pos:pos+ data_size]
    pos+= data_size

    hdec= HuffmanDecoder(code_table)
    symbol_stream= hdec.decode(encoded_data, real_padding)

    error_bound= be_cm/100.0
    dec= OctreeDecoderAxis(error_bound)
    dec.decode(symbol_stream, center, size)
    return np.array(dec.decoded_points, dtype=np.float32)

class OctreeDecoderL2:
    def __init__(self, error_bound=0.20):
        self.error_bound= error_bound
        self.quant_step= error_bound
        self.decoded_points: List[List[float]]= []

    def decode(self, symbol_stream: List[int], center: np.ndarray, size: float):
        stack= [(center.copy(), size)]
        i=0
        n= len(symbol_stream)
        while stack and i<n:
            cC, cS= stack.pop()
            sym= symbol_stream[i]
            i+=1
            if sym==78: # 'N'
                child_mask= symbol_stream[i]
                i+=1
                quarter= cS/4
                half= cS/2
                for cidx in reversed(range(8)):
                    if (child_mask>>cidx)&1:
                        newc= cC.copy()
                        if (cidx&1):
                            newc[0]+= quarter
                        else:
                            newc[0]-= quarter
                        if (cidx&2):
                            newc[1]+= quarter
                        else:
                            newc[1]-= quarter
                        if (cidx&4):
                            newc[2]+= quarter
                        else:
                            newc[2]-= quarter
                        stack.append((newc, half))
            elif sym==76: # 'L'
                if i+3>=n:
                    break
                n3= symbol_stream[i]
                n2= symbol_stream[i+1]
                n1= symbol_stream[i+2]
                n0= symbol_stream[i+3]
                i+=4
                leaf_count= (n3<<24)|(n2<<16)|(n1<<8)|n0
                for _ in range(leaf_count):
                    if i+2>= n:
                        break
                    x= symbol_stream[i]
                    y= symbol_stream[i+1]
                    z= symbol_stream[i+2]
                    i+=3
                    rx= cC[0]+ (x-128)* self.quant_step
                    ry= cC[1]+ (y-128)* self.quant_step
                    rz= cC[2]+ (z-128)* self.quant_step
                    self.decoded_points.append([rx, ry, rz])
            else:
                break

def ebhc3d_l2_decompress(data: bytes, be_cm: float) -> np.ndarray:
    if not data:
        return np.empty((0,3), dtype=np.float32)
    pos=0
    meta= data[:32]
    cx, cy, cz, size= struct.unpack("dddd", meta)
    center= np.array([cx,cy,cz], dtype=np.float64)
    pos+=32

    real_padding= data[pos]
    pos+=1

    code_size= struct.unpack('I', data[pos:pos+4])[0]
    pos+=4
    code_bytes= data[pos:pos+code_size]
    pos+= code_size

    code_table={}
    i=0
    while i< len(code_bytes):
        sym= code_bytes[i]
        code_len= code_bytes[i+1]
        code_str= code_bytes[i+2:i+2+code_len].decode('ascii')
        code_table[sym]= code_str
        i+= (2+ code_len)

    data_size= struct.unpack('I', data[pos:pos+4])[0]
    pos+=4
    encoded_data= data[pos:pos+ data_size]
    pos+= data_size

    hdec= HuffmanDecoder(code_table)
    symbol_stream= hdec.decode(encoded_data, real_padding)

    error_bound= be_cm/100.0
    dec= OctreeDecoderL2(error_bound)
    dec.decode(symbol_stream, center, size)
    return np.array(dec.decoded_points, dtype=np.float32)


###############################################################################
# (新增) 計算 Chamfer Distance 與 Occupancy IoU
###############################################################################
def compute_chamfer_distance(ptsA: np.ndarray, ptsB: np.ndarray) -> float:
    """
    計算 Chamfer Distance (採用平均的 squared L2 distance):
      CD = mean_{x in A}(min_{y in B} ||x - y||^2) + mean_{y in B}(min_{x in A} ||x - y||^2)
    """
    # 若任一集合為空，回傳 NaN
    if len(ptsA) == 0 or len(ptsB) == 0:
        return float('nan')

    # A->B
    kdB = cKDTree(ptsB)
    distA, _ = kdB.query(ptsA, k=1)  # distA: 每個 A 到最近 B 的 L2距離
    distA_sq = distA**2
    forward = distA_sq.mean()

    # B->A
    kdA = cKDTree(ptsA)
    distB, _ = kdA.query(ptsB, k=1)  # distB: 每個 B 到最近 A 的 L2距離
    distB_sq = distB**2
    backward = distB_sq.mean()

    return forward + backward

def compute_occupancy_iou(ptsA: np.ndarray, ptsB: np.ndarray, voxel_size=0.1) -> float:
    """
    以簡易 voxel-based 方式計算 Occupancy IoU:
      1. 先找出 A ∪ B 的 bounding box
      2. 以 voxel_size 切成網格，將每個點歸屬到對應的 voxel index
      3. 分別得到 A 與 B 所佔據的 voxel set
      4. IoU = (#(A ∩ B)) / (#(A ∪ B))
    若 union=0，回傳 0 (或視情況可回傳 1)，此處回傳 0。
    """
    if len(ptsA) == 0 and len(ptsB) == 0:
        return 0.0
    if len(ptsA) == 0 or len(ptsB) == 0:
        return 0.0

    all_pts = np.concatenate([ptsA, ptsB], axis=0)
    mn = all_pts.min(axis=0)
    # mx = all_pts.max(axis=0)  # 若只需計算 voxel index，可不一定要用 mx

    def to_voxel_set(pts: np.ndarray) -> set:
        vset = set()
        for p in pts:
            vx = int((p[0] - mn[0]) // voxel_size)
            vy = int((p[1] - mn[1]) // voxel_size)
            vz = int((p[2] - mn[2]) // voxel_size)
            vset.add((vx, vy, vz))
        return vset

    setA = to_voxel_set(ptsA)
    setB = to_voxel_set(ptsB)
    inter = setA.intersection(setB)
    union = setA.union(setB)
    if len(union) == 0:
        return 0.0
    return len(inter) / len(union)


###############################################################################
# (整合) 計算各種誤差 (含 Axis/L2 + Chamfer Dist + Occupancy IoU)
###############################################################################
def compute_error(original_points: np.ndarray, decompressed_points: np.ndarray):
    """
    計算:
      - Mean/Max Axis (以最近點對應來計算)
      - Mean/Max L2   (以最近點對應來計算)
      - Chamfer Distance
      - Occupancy IoU
    """
    if len(original_points)==0 or len(decompressed_points)==0:
        return dict(
            mean_axis=np.nan, max_axis=np.nan,
            mean_l2=np.nan, max_l2=np.nan,
            chamfer_dist=np.nan,
            occupancy_iou=np.nan
        )

    # 最近點對應，計算 Axis / L2
    tree= cKDTree(decompressed_points)
    dist, nn_idx= tree.query(original_points, k=1)
    axis_err=[]
    for i,j in enumerate(nn_idx):
        dx= abs(original_points[i,0]- decompressed_points[j,0])
        dy= abs(original_points[i,1]- decompressed_points[j,1])
        dz= abs(original_points[i,2]- decompressed_points[j,2])
        axis_err.append(max(dx,dy,dz))
    axis_err= np.array(axis_err)
    dist= np.array(dist)

    # Chamfer Distance
    chamfer_dist = compute_chamfer_distance(original_points, decompressed_points)
    # Occupancy IoU
    occ_iou = compute_occupancy_iou(original_points, decompressed_points, voxel_size=0.1)

    return dict(
        mean_axis= float(axis_err.mean()),
        max_axis= float(axis_err.max()),
        mean_l2= float(dist.mean()),
        max_l2= float(dist.max()),
        chamfer_dist= chamfer_dist,
        occupancy_iou= occ_iou
    )


###############################################################################
# (6) 分組平均函式: aggregate_single_results
###############################################################################
def aggregate_single_results(scene_name: str, single_scene_results: List[dict]) -> List[dict]:
    """
    針對同一 scene 的 single-bin 結果:
      - 依 (Method, BE (cm)) 分組
      - 把 "Compression Ratio", "Compression Time (s)", "Decompression Time (s)",
        "Mean Error (Axis)", "Max Error (Axis)", "Mean Error (L2)", "Max Error (L2)",
        "Num Packets", "Chamfer Distance", "Occupancy IoU" 等數值做平均
    回傳的列表不區分不同檔名 => 'Filename' 統一標記為 'AVERAGE'
    """
    numeric_keys = [
        "Compression Ratio", "Compression Time (s)", "Decompression Time (s)",
        "Mean Error (Axis)", "Max Error (Axis)",
        "Mean Error (L2)", "Max Error (L2)",
        "Num Packets",
        "Chamfer Distance", 
        "Occupancy IoU"
    ]

    grouping = defaultdict(list)
    for r in single_scene_results:
        # 若是 multi => 跳過
        if r.get("Filename","") == "MULTI":
            continue
        method = r["Method"]
        be = r["BE (cm)"]
        grouping[(method,be)].append(r)

    aggregated_list = []
    for (method, be), items in grouping.items():
        if not items:
            continue
        count = len(items)
        avg_dict = {
            "Scene": scene_name,
            "Filename": "AVERAGE",
            "Method": method,
            "BE (cm)": be,
        }
        for key in numeric_keys:
            s = sum(x[key] for x in items)
            avg_dict[key] = s / count
        aggregated_list.append(avg_dict)

    return aggregated_list


###############################################################################
# (7) run_all_methods(pts, scene_label, filename="")
###############################################################################
def run_all_methods(pts: np.ndarray, scene_label: str, filename:str="") -> List[dict]:
    """
    同一批點做以下七種壓縮方法:
      1. Huffman
      2. EB-HC(Axis)
      3. EB-HC(L2)
      4. EB-Octree(Axis)
      5. EB-Octree(L2)
      6. EB-HC-3D(Axis)
      7. EB-HC-3D(L2)

    如 filename!= ""，則在結果 dict 中加上 "Filename" 欄位。
    
    * 除了原先的 Axis/L2 誤差外，亦計算 Chamfer Distance 與 Occupancy IoU。
    """
    results=[]
    scale_factor= 1000
    qpts= np.round(pts* scale_factor).astype(np.int32)
    raw_bits= qpts.size * 32

    # (1) Huffman => 無誤差
    print(f"[Method 1] Huffman => 無誤差, Scene={scene_label}, Filename={filename}")
    st= time.time()
    raw_bytes= qpts.tobytes()
    enc_bits, huff_tree= huffman_encoding(raw_bytes)
    c_time= time.time()- st
    c_bits= len(enc_bits)
    ratio= c_bits/ raw_bits if raw_bits>0 else 0
    st2= time.time()
    dec_b= huffman_decoding(enc_bits, huff_tree)
    dec_time= time.time()- st2

    if dec_b:
        dq= np.frombuffer(dec_b, dtype=np.int32).reshape(-1,3)
    else:
        dq= np.empty((0,3), dtype=np.int32)
    rec_pts= dq.astype(np.float32)/ scale_factor

    errs= compute_error(pts, rec_pts)
    row_huff = {
        'Scene': scene_label,
        'Method': 'Huffman',
        'BE (cm)': 0,
        'Compression Ratio': ratio,
        'Compression Time (s)': c_time,
        'Decompression Time (s)': dec_time,
        'Mean Error (Axis)': errs['mean_axis'],
        'Max Error (Axis)': errs['max_axis'],
        'Mean Error (L2)': errs['mean_l2'],
        'Max Error (L2)': errs['max_l2'],
        'Num Packets': math.ceil(c_bits/1000) if c_bits>0 else 0,
        'Chamfer Distance': errs['chamfer_dist'],
        'Occupancy IoU': errs['occupancy_iou']
    }
    if filename:
        row_huff["Filename"] = filename
    results.append(row_huff)

    # 測試 BE=0.25...20.0 cm
    BE_list_cm = np.arange(0.25, 20.01, 0.25)
    for be_cm in BE_list_cm:
        print(f"\n=== Scene={scene_label}, BE={be_cm} cm, Filename={filename} ===")

        # (2) EB-HC(Axis)
        print("[Method 2] EB-HC(Axis)")
        st= time.time()
        eb_data_axis, trees_axis= ebhc_encode_axis(qpts, be_cm, scale_factor)
        c_time= time.time()- st
        c_bits= len(eb_data_axis)*8
        ratio= c_bits/ raw_bits if raw_bits>0 else 0
        st2= time.time()
        dq_a= ebhc_decode_axis(eb_data_axis, trees_axis, len(qpts))
        dec_time= time.time()- st2
        rec_a= dq_a.astype(np.float32)/ scale_factor
        ea= compute_error(pts, rec_a)
        row_axis = {
            'Scene': scene_label,
            'Method': 'EB-HC(Axis)',
            'BE (cm)': be_cm,
            'Compression Ratio': ratio,
            'Compression Time (s)': c_time,
            'Decompression Time (s)': dec_time,
            'Mean Error (Axis)': ea['mean_axis'],
            'Max Error (Axis)': ea['max_axis'],
            'Mean Error (L2)': ea['mean_l2'],
            'Max Error (L2)': ea['max_l2'],
            'Num Packets': math.ceil(c_bits/1000) if c_bits>0 else 0,
            'Chamfer Distance': ea['chamfer_dist'],
            'Occupancy IoU': ea['occupancy_iou']
        }
        if filename:
            row_axis["Filename"] = filename
        results.append(row_axis)

        # (3) EB-HC(L2)
        print("[Method 3] EB-HC(L2)")
        st= time.time()
        eb_data_l2, trees_l2= ebhc_encode_l2(qpts, be_cm, scale_factor)
        c_time= time.time()- st
        c_bits= len(eb_data_l2)*8
        ratio= c_bits/ raw_bits if raw_bits>0 else 0
        st2= time.time()
        dq_l2= ebhc_decode_l2(eb_data_l2, trees_l2, len(qpts))
        dec_time= time.time()- st2
        rec_l2= dq_l2.astype(np.float32)/ scale_factor
        el2= compute_error(pts, rec_l2)
        row_l2 = {
            'Scene': scene_label,
            'Method': 'EB-HC(L2)',
            'BE (cm)': be_cm,
            'Compression Ratio': ratio,
            'Compression Time (s)': c_time,
            'Decompression Time (s)': dec_time,
            'Mean Error (Axis)': el2['mean_axis'],
            'Max Error (Axis)': el2['max_axis'],
            'Mean Error (L2)': el2['mean_l2'],
            'Max Error (L2)': el2['max_l2'],
            'Num Packets': math.ceil(c_bits/1000) if c_bits>0 else 0,
            'Chamfer Distance': el2['chamfer_dist'],
            'Occupancy IoU': el2['occupancy_iou']
        }
        if filename:
            row_l2["Filename"] = filename
        results.append(row_l2)

        # (4) EB-Octree(Axis)
        print("[Method 4] EB-Octree(Axis)")
        c_oct_a= EBOctreeAxisCompressor(be_cm/100.0,1,1000.0,32)
        st= time.time()
        data_oaxis= c_oct_a.compress(pts)
        c_time= time.time()- st
        c_bits= len(data_oaxis)*8
        ratio= c_bits/ raw_bits if raw_bits>0 else 0
        st2= time.time()
        dec_oaxis= c_oct_a.decompress(data_oaxis)
        dec_time= time.time()- st2
        eoax= compute_error(pts, dec_oaxis)
        row_oct_axis = {
            'Scene': scene_label,
            'Method': 'EB-Octree(Axis)',
            'BE (cm)': be_cm,
            'Compression Ratio': ratio,
            'Compression Time (s)': c_time,
            'Decompression Time (s)': dec_time,
            'Mean Error (Axis)': eoax['mean_axis'],
            'Max Error (Axis)': eoax['max_axis'],
            'Mean Error (L2)': eoax['mean_l2'],
            'Max Error (L2)': eoax['max_l2'],
            'Num Packets': math.ceil(c_bits/1000) if c_bits>0 else 0,
            'Chamfer Distance': eoax['chamfer_dist'],
            'Occupancy IoU': eoax['occupancy_iou']
        }
        if filename:
            row_oct_axis["Filename"] = filename
        results.append(row_oct_axis)

        # (5) EB-Octree(L2)
        print("[Method 5] EB-Octree(L2)")
        c_oct_l2= EBOctreeL2Compressor(be_cm/100.0,1,1000.0,32)
        st= time.time()
        data_ol2= c_oct_l2.compress(pts)
        c_time= time.time()- st
        c_bits= len(data_ol2)*8
        ratio= c_bits/ raw_bits if raw_bits>0 else 0
        st2= time.time()
        dec_ol2= c_oct_l2.decompress(data_ol2)
        dec_time= time.time()- st2
        eol2= compute_error(pts, dec_ol2)
        row_oct_l2 = {
            'Scene': scene_label,
            'Method': 'EB-Octree(L2)',
            'BE (cm)': be_cm,
            'Compression Ratio': ratio,
            'Compression Time (s)': c_time,
            'Decompression Time (s)': dec_time,
            'Mean Error (Axis)': eol2['mean_axis'],
            'Max Error (Axis)': eol2['max_axis'],
            'Mean Error (L2)': eol2['mean_l2'],
            'Max Error (L2)': eol2['max_l2'],
            'Num Packets': math.ceil(c_bits/1000) if c_bits>0 else 0,
            'Chamfer Distance': eol2['chamfer_dist'],
            'Occupancy IoU': eol2['occupancy_iou']
        }
        if filename:
            row_oct_l2["Filename"] = filename
        results.append(row_oct_l2)

        # (6) EB-HC-3D(Axis)
        print("[Method 6] EB-HC-3D(Axis)")
        st= time.time()
        cmp_data_3a= ebhc3d_axis_compress(pts, be_cm)
        c_time= time.time()- st
        c_bits= len(cmp_data_3a)*8
        ratio= c_bits/ raw_bits if raw_bits>0 else 0
        st2= time.time()
        dec_3a= ebhc3d_axis_decompress(cmp_data_3a, be_cm)
        dec_time= time.time()- st2
        e3a= compute_error(pts, dec_3a)
        row_3a = {
            'Scene': scene_label,
            'Method': 'EB-HC-3D(Axis)',
            'BE (cm)': be_cm,
            'Compression Ratio': ratio,
            'Compression Time (s)': c_time,
            'Decompression Time (s)': dec_time,
            'Mean Error (Axis)': e3a['mean_axis'],
            'Max Error (Axis)': e3a['max_axis'],
            'Mean Error (L2)': e3a['mean_l2'],
            'Max Error (L2)': e3a['max_l2'],
            'Num Packets': math.ceil(c_bits/1000) if c_bits>0 else 0,
            'Chamfer Distance': e3a['chamfer_dist'],
            'Occupancy IoU': e3a['occupancy_iou']
        }
        if filename:
            row_3a["Filename"] = filename
        results.append(row_3a)

        # (7) EB-HC-3D(L2)
        print("[Method 7] EB-HC-3D(L2)")
        st= time.time()
        cmp_data_3l2= ebhc3d_l2_compress(pts, be_cm)
        c_time= time.time()- st
        c_bits= len(cmp_data_3l2)*8
        ratio= c_bits/ raw_bits if raw_bits>0 else 0
        st2= time.time()
        dec_3l2= ebhc3d_l2_decompress(cmp_data_3l2, be_cm)
        dec_time= time.time()- st2
        e3l2= compute_error(pts, dec_3l2)
        row_3l2 = {
            'Scene': scene_label,
            'Method': 'EB-HC-3D(L2)',
            'BE (cm)': be_cm,
            'Compression Ratio': ratio,
            'Compression Time (s)': c_time,
            'Decompression Time (s)': dec_time,
            'Mean Error (Axis)': e3l2['mean_axis'],
            'Max Error (Axis)': e3l2['max_axis'],
            'Mean Error (L2)': e3l2['mean_l2'],
            'Max Error (L2)': e3l2['max_l2'],
            'Num Packets': math.ceil(c_bits/1000) if c_bits>0 else 0,
            'Chamfer Distance': e3l2['chamfer_dist'],
            'Occupancy IoU': e3l2['occupancy_iou']
        }
        if filename:
            row_3l2["Filename"] = filename
        results.append(row_3l2)

    return results


###############################################################################
# (8) 主程式
###############################################################################
def main():
    BASE_DIRS = {
        "campus": "KITTI/campus/2011_09_28/2011_09_28_drive_0016_sync/velodyne_points/data",
        # 可自行加入其他路徑:
        "city":        "KITTI/city/2011_09_26/2011_09_26_drive_0001_sync/velodyne_points/data",
        "person":      "KITTI/person/2011_09_28/2011_09_28_drive_0053_sync/velodyne_points/data",
        "residential": "KITTI/residential/2011_09_26/2011_09_26_drive_0019_sync/velodyne_points/data",
        "road":        "KITTI/road/2011_09_26/2011_09_26_drive_0015_sync/velodyne_points/data",
    }

    # 主 CSV
    out_csv = "compression_results_all_all.csv"
    cols= [
        'Scene','Filename','Method','BE (cm)',
        'Compression Ratio','Compression Time (s)','Decompression Time (s)',
        'Mean Error (Axis)','Max Error (Axis)',
        'Mean Error (L2)','Max Error (L2)',
        'Num Packets',
        'Chamfer Distance',
        'Occupancy IoU'
    ]

    all_results=[]

    for scene_name, folder in BASE_DIRS.items():
        print(f"\n=== [Scene: {scene_name}] ===")
        bin_files= find_bin_files(folder, max_count=10)
        if not bin_files:
            print(f"  => No bin files found in {folder}, skip.")
            continue

        # (A) Single: 對資料夾中「每一個 bin」都做壓縮測試
        single_scene_results = []
        for single_bin in bin_files:
            bn = os.path.basename(single_bin)
            print(f"  Single-bin = {bn}")
            pts_single= load_points_from_bin(single_bin)
            if len(pts_single)==0:
                print("    => Invalid or empty bin, skip single-frame test.")
                continue
            # 在 run_all_methods 時指定 filename
            r_single= run_all_methods(pts_single, f"{scene_name}_single", filename=bn)
            single_scene_results.extend(r_single)

        # 把 single 結果累加到 all_results
        all_results.extend(single_scene_results)

        # 對 single 的結果做 (Method, BE) 分組 => 取平均 => 另存一個 CSV
        if single_scene_results:
            avg_results = aggregate_single_results(scene_name, single_scene_results)
            avg_csv_path= f"scene_average_results_{scene_name}.csv"
            write_results_to_csv(avg_results, avg_csv_path, cols)

        # (B) Multi: 串接 max 10 bin
        print(f"  Multi-frame (max 10 bins) => total files = {len(bin_files)}")
        multi_pts=[]
        for bf in bin_files:
            p= load_points_from_bin(bf)
            if len(p)>0:
                multi_pts.append(p)
        if len(multi_pts)==0:
            print("    => All bins invalid/empty, skip multi-frame test.")
            continue
        big_pts= np.concatenate(multi_pts, axis=0)
        print(f"    => big_pts shape = {big_pts.shape}")
        # Multi => 若想在 CSV 中標 filename，可用 "MULTI"
        r_multi= run_all_methods(big_pts, f"{scene_name}_multi", filename="MULTI")
        all_results.extend(r_multi)

    # (C) 最後將 all_results 寫到主 CSV
    write_results_to_csv(all_results, out_csv, cols)
    print(f"\n=== All done. CSV => '{out_csv}' ===")


###############################################################################
# (9) EB-HC-3D Demo 主函式 (可自行呼叫)
###############################################################################
def main_ebhc3d_demo():
    """
    python EBpaper.py --input <some.bin> --method axis --be_cm 5
    """
    parser= argparse.ArgumentParser()
    parser.add_argument("--input",  type=str, required=True)
    parser.add_argument("--method", type=str, default="axis", choices=["axis","l2"])
    parser.add_argument("--be_cm",  type=float, default=5.0)
    args= parser.parse_args()

    bin_path= args.input
    method= args.method
    be_cm= args.be_cm

    # 讀檔
    from pathlib import Path
    if not Path(bin_path).is_file():
        print(f"File not found: {bin_path}")
        return
    raw= open(bin_path,'rb').read()
    if len(raw)%16 !=0:
        print(f"File size invalid: {bin_path}")
        return
    pts= np.frombuffer(raw, dtype=np.float32).reshape(-1,4)[:,:3]
    if len(pts)==0:
        print("Empty bin, exit")
        return

    print(f"[INFO] 讀入 {bin_path}, 點數={len(pts)}, method={method}, be_cm={be_cm}")

    start_c= time.time()
    if method=="axis":
        cmp_data= ebhc3d_axis_compress(pts, be_cm)
    else:
        cmp_data= ebhc3d_l2_compress(pts, be_cm)
    c_time= time.time()- start_c

    orig_bytes= pts.nbytes
    cmp_bytes= len(cmp_data)
    ratio= cmp_bytes/orig_bytes if orig_bytes>0 else 0
    print(f"[INFO] 原大小={orig_bytes} bytes, 壓縮後={cmp_bytes} bytes, ratio={ratio:.4f}")
    print(f"[INFO] 壓縮時間={c_time:.4f} s")

    start_d= time.time()
    if method=="axis":
        dec_pts= ebhc3d_axis_decompress(cmp_data, be_cm)
    else:
        dec_pts= ebhc3d_l2_decompress(cmp_data, be_cm)
    d_time= time.time()- start_d
    print(f"[INFO] 解壓後點數={len(dec_pts)}, 解壓時間={d_time:.4f} s")

    errs= compute_error(pts, dec_pts)
    print("[誤差統計]:")
    print(f"   mean_axis={errs['mean_axis']:.6f}, max_axis={errs['max_axis']:.6f}")
    print(f"   mean_l2={errs['mean_l2']:.6f},   max_l2={errs['max_l2']:.6f}")
    print(f"   chamfer_dist={errs['chamfer_dist']:.6f}, occupancy_iou={errs['occupancy_iou']:.4f}")


if __name__=="__main__":
    # 預設執行 main()，如需測試 EB-HC-3D Demo，請自行呼叫 main_ebhc3d_demo()
    main()
    # main_ebhc3d_demo()
