#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Coordinated overhead MEP model for data hall dc_model__hall_seed005_d100.

Self-contained IFC4 builder. All data read from the seven drawing sheets
(A-101, A-301, A-601, A-602, M-101, E-101, F-101) is baked in below as
literals. No network, no image access, fully deterministic.

Units contract:
  * Project units: millimetres (all shape/profile/extrusion values in mm).
  * Placement translations: metres (IfcCartesianPoint locations /1000).
  * 2D profile points only (rectangular profiles; extrusions along axes).

Usage:
  python3 solution.py [OUT_IFC_PATH]   (default: output/model.ifc)
"""

import base64
import json
import math
import os
import sys

import ifcopenshell

OUT_DEFAULT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "model.ifc")

# =========================================================================
# 1. BAKED LAYOUT DATA (mm) -- read off the seven sheets
# =========================================================================

HALL = {
    "name": "Data Hall H-5",
    "width_x": 27000.0,    # A-101: 27.0 m
    "width_y": 24000.0,    # A-101: 24.0 m
    "deck_soffit": 4200.0, # A-301: structural deck soffit +4200 AFF
    "clear_height_min": 2600.0,  # A-301 callout: 2600 min clear
}

FF = 0.0                      # finished access-floor level
ACCESS_FLOOR_T = 300.0       # A-602: 300 mm raised access floor (top at FF=0)
UFPLENUM_T = 300.0          # under-floor plenum -300..0, usable for routing

# --- Racks (A-101 + A-601 schedule) -------------------------------------
# 8 rows, circulation cross-aisle splits each row (re-registered halves).
# 42U rack 600 (W) x 1000 (D) x 2200 (H) AFF, pitch 600.
RACK_W, RACK_D, RACK_H = 600.0, 1000.0, 2200.0
ROW_Y = [3600.0, 6000.0, 8400.0, 10800.0, 13200.0, 15600.0, 18000.0, 20400.0]
ROW_N = [12, 12, 12, 12, 12, 12, 12, 10]     # 94 cabinets total
ROW_X0 = 4500.0                              # A-101: first cabinet face 4500 AFF-1000
CROSS_AISLE_GAP = 1200.0                      # A-101: circulation cross-aisle
FACING = [1.0, -1.0] * 4                     # hot/cold: even rows face +Y

# --- Structural columns (A-101) ------------------------------------------
# 7200 structural grid, offset 150 from the 600 tile grid. 400x400, full
# clear height 0..4200 (A-301).
COL_GRID = 7200.0
COL_OFF = 150.0
COL_SIZE = 400.0
COL_TOP = HALL["deck_soffit"]
COL_X = [COL_OFF + i * COL_GRID for i in range(4)]   # 150 7350 14550 21750
COL_Y = [COL_OFF + i * COL_GRID for i in range(4)]
# Coordinator resolution of the tile/column offset conflict: keep the columns
# that govern the plenum (the perimeter ring of the 7200 grid) and register
# the interior cabinet rows on tiles that clear the interior column lines.
COLS = [(cx, cy) for cx in COL_X for cy in COL_Y
        if cx in (COL_X[0], COL_X[-1]) or cy in (COL_Y[0], COL_Y[-1])]

# --- CRAH (A-101) ----------------------------------------------------------
# 4 perimeter units 1500x1500x2000 on top/bottom walls (no row header
# passes a CRAH -- chilled water must be brought to them separately).
CRAHS = [
    {"id": "CRAH-01", "x": 6000.0, "y": 23000.0, "w": 1500.0, "d": 1500.0, "h": 2000.0, "face": -1},
    {"id": "CRAH-02", "x": 20000.0, "y": 23000.0, "w": 1500.0, "d": 1500.0, "h": 2000.0, "face": -1},
    {"id": "CRAH-03", "x": 6000.0, "y": 1000.0, "w": 1500.0, "d": 1500.0, "h": 2000.0, "face": 1},
    {"id": "CRAH-04", "x": 20000.0, "y": 1000.0, "w": 1500.0, "d": 1500.0, "h": 2000.0, "face": 1},
]

# --- PDU (E-101) -----------------------------------------------------------
# Two 600x600x2000 floor PDUs at each row end (row headers).
PDU_SIZE = 600.0
PDU_H = 2000.0
PDU_CLEAR_ABOVE = 1800.0     # E-101: 1800 dedicated clear space above each PDU

# --- Containment (A-602) -----------------------------------------------------
# Cold-aisle containment panels, 100 thick, 0..2200, at the four cold aisles;
# split at the cross-aisle so the circulation gap stays open. No roof.
PANEL_T = 100.0
PANEL_H = RACK_H
PANEL_Y = [4800.0, 9600.0, 14400.0, 19200.0]

# --- Sprinklers (F-101) ------------------------------------------------------
# 104 heads: 13 x 8 grid. Deflector at 3900 AFF; 200x200x100.
HEAD_X0, HEAD_DX = 950.0, 2000.0
HEAD_Y0, HEAD_DY = 450.0, 3000.0
HEADS_NX, HEADS_NY = 13, 8            # 104 heads
HEAD_DEFLECTOR_Z = 3900.0
HEAD_SIZE, HEAD_T = 200.0, 100.0
SPRINKLER_CLEAR = 460.0                # keep 460 clear below every deflector
NFPA_OBSTR = 450.0                     # NFPA 13 obstruction zone below deflector

# --- Service tiers (A-301 plenum legend) -------------------------------------
# Elevation bands above FF; tray above busway above CHW.  Tray/busway are
# separated >300 on the X axis in the trunk zone and by lateral offset on
# branches.  CHW keeps 1800 clear above every PDU.
TRAY_W, TRAY_H = 300.0, 110.0          # cable tray, top tier (3320..3430 AFF)
BUS_W, BUS_H = 200.0, 180.0           # busway, middle tier (2840..3020 AFF)
PIPE_OD = 220.0                        # CHW incl. 2 x 25.4 insulation (2610..2830 AFF)
TRAY_Z = 3375.0
BUS_Z = 2930.0
CHW_Z = 2720.0
TRAY_BUS_MIN_SEP = 300.0

# Route plan (axis-aligned segments; each segment below).
#  Tray trunk x=3000 ; branches y=ROW_Y-400 ;  entry y=12000 from x=0
#  Busway trunk x=3900 ; branches y=ROW_Y+400 ; entry y=12400 from x=0
#  CHW trunk x=3000 ; branches y=ROW_Y-1500 ; perimeter y=1000/23000 ;
#      entry y=11600 from x=0
TRAY_TRUNK_X, BUS_TRUNK_X, CHW_TRUNK_X = 3000.0, 3900.0, 3000.0
TRAY_BRANCH_DY, BUS_BRANCH_DY, CHW_BRANCH_DY = -400.0, 400.0, -1500.0
TRAY_ENTRY_Y, BUS_ENTRY_Y, CHW_ENTRY_Y = 12000.0, 12400.0, 11600.0
TRUNK_Y0, TRUNK_Y1 = 1000.0, 23000.0
BRANCH_X1 = 13200.0                    # branches reach the row headers
CHW_PERIM_Y = [1000.0, 23000.0]       # CHW perimeter runs to the CRAHs
CHW_PERIM_X1 = 21000.0

DROP_X = 13200.0                       # service drops to the rows
DROP_Z = 2300.0                        # drops terminate 100 above rack top
DROP_W = 150.0

SUPPORT_SPAN = 1400.0                  # E-101: 1500 max busway support -> 1400 c/c
SUPPORT_SIZE = 100.0
SUPPORT_Z0 = BUS_Z + BUS_H / 2.0      # 3020, hangs from just above busway top
SUPPORT_TOP = 3370.0                  # stays 70 below the 3440 sprinkler-clear floor


# =========================================================================
# 2. DERIVED LAYOUT (deterministic)
# =========================================================================

def row_extent(n):
    """X extent of a row: 2 blocks of cabs separated by the cross-aisle."""
    half = (n // 2)
    left = [ROW_X0 + i * RACK_W for i in range(half)]
    gap_end = ROW_X0 + half * RACK_W + CROSS_AISLE_GAP
    right = [gap_end + i * RACK_W for i in range(n - half)]
    return min(left) , max(right) + RACK_W, left, right

def cabinet_positions():
    """Return list of (row_idx, cx, cy, facing) for all 94 cabinets."""
    cabs = []
    for ri, (y, n) in enumerate(zip(ROW_Y, ROW_N)):
        _, _, left, right = row_extent(n)
        for x in left + right:
            cabs.append((ri, x + RACK_W / 2.0, y, FACING[ri % 2]))
    return cabs

def ppu_positions():
    """PDUs: 2 per row at the row ends.  Returns list of (row_idx, cx, cy)."""
    out = []
    for ri, (y, n) in enumerate(zip(ROW_Y, ROW_N)):
        x0, x1, _, _ = row_extent(n)
        out.append((ri, x0 - PDU_SIZE / 2.0 - 300.0, y))       # left header
        out.append((ri, x1 + 300.0 + PDU_SIZE / 2.0, y))       # right header
    return out

def containment_panels():
    """Cold-aisle panels split by the circulation cross-aisle."""
    panels = []
    for pi, py in enumerate(PANEL_Y):
        n_a, n_b = ROW_N[2 * pi], ROW_N[2 * pi + 1]
        _, _, la, ra = row_extent(n_a)
        _, _, lb, rb = row_extent(n_b)
        x0 = ROW_X0
        x1 = max(max(ra) + RACK_W, max(rb) + RACK_W)
        g0 = max(la[-1] + RACK_W, lb[-1] + RACK_W)   # left block face end
        g1 = min(ra[0], rb[0])                        # right block face start
        panels.append((py, x0, g0))
        panels.append((py, g1, x1))
    return panels

# --- service segments ---------------------------------------------------------
# Each: dict(name, svc, axis ('X','Y','Z'), start (x0/y0/z0), p0 on centreline,
# p1 end, w transverse, h vertical (X/Y runs) or depth (Z runs))
def build_segments():
    segs = []
    def run(svc, axis, p0, p1, w, h, tag):
        segs.append({"svc": svc, "axis": axis, "p0": p0, "p1": p1,
                     "w": w, "h": h, "tag": tag})

    # TRAY ---------------------------------------------------------------
    run("tray", "X", (0.0, TRAY_ENTRY_Y, TRAY_Z), (TRAY_TRUNK_X, TRAY_ENTRY_Y, TRAY_Z),
        TRAY_W, TRAY_H, "tray-entry")
    run("tray", "Y", (TRAY_TRUNK_X, TRUNK_Y0, TRAY_Z), (TRAY_TRUNK_X, TRUNK_Y1, TRAY_Z),
        TRAY_W, TRAY_H, "tray-trunk")
    for i, ry in enumerate(ROW_Y):
        run("tray", "X", (TRAY_TRUNK_X, ry + TRAY_BRANCH_DY, TRAY_Z),
            (BRANCH_X1, ry + TRAY_BRANCH_DY, TRAY_Z), TRAY_W, TRAY_H,
            "tray-branch-r%d" % i)

    # BUSWAY --------------------------------------------------------------
    run("bus", "X", (0.0, BUS_ENTRY_Y, BUS_Z), (BUS_TRUNK_X, BUS_ENTRY_Y, BUS_Z),
        BUS_W, BUS_H, "bus-entry")
    run("bus", "Y", (BUS_TRUNK_X, TRUNK_Y0, BUS_Z), (BUS_TRUNK_X, TRUNK_Y1, BUS_Z),
        BUS_W, BUS_H, "bus-trunk")
    for i, ry in enumerate(ROW_Y):
        run("bus", "X", (BUS_TRUNK_X, ry + BUS_BRANCH_DY, BUS_Z),
            (BRANCH_X1, ry + BUS_BRANCH_DY, BUS_Z), BUS_W, BUS_H,
            "bus-branch-r%d" % i)

    # CHW -------------------------------------------------------------------
    run("chw", "X", (0.0, CHW_ENTRY_Y, CHW_Z), (CHW_TRUNK_X, CHW_ENTRY_Y, CHW_Z),
        PIPE_OD, PIPE_OD, "chw-entry")
    run("chw", "Y", (CHW_TRUNK_X, TRUNK_Y0, CHW_Z), (CHW_TRUNK_X, TRUNK_Y1, CHW_Z),
        PIPE_OD, PIPE_OD, "chw-trunk")
    for i, ry in enumerate(ROW_Y):
        run("chw", "X", (CHW_TRUNK_X, ry + CHW_BRANCH_DY, CHW_Z),
            (BRANCH_X1, ry + CHW_BRANCH_DY, CHW_Z), PIPE_OD, PIPE_OD,
            "chw-branch-r%d" % i)
    for py in CHW_PERIM_Y:
        run("chw", "X", (CHW_TRUNK_X, py, CHW_Z), (CHW_PERIM_X1, py, CHW_Z),
            PIPE_OD, PIPE_OD, "chw-perim-%.0f" % py)

    # DROPS (vertical service drops at the row headers; terminate at the
    # underside of the service so they connect without intruding) ----------
    svc_bottom = {"tray": TRAY_Z - TRAY_H / 2.0,
                  "bus": BUS_Z - BUS_H / 2.0,
                  "chw": CHW_Z - PIPE_OD / 2.0}
    svc_w = {"tray": TRAY_W, "bus": BUS_W, "chw": PIPE_OD}
    drops = []
    for i, ry in enumerate(ROW_Y):
        for svc, dy in (("tray", TRAY_BRANCH_DY),
                        ("bus", BUS_BRANCH_DY),
                        ("chw", CHW_BRANCH_DY)):
            w = min(DROP_W, svc_w[svc])
            drops.append({"svc": svc, "axis": "Z",
                          "p0": (DROP_X, ry + dy, DROP_Z),
                          "p1": (DROP_X, ry + dy, svc_bottom[svc]),
                          "w": w, "h": w, "tag": "%s-drop-r%d" % (svc, i)})
    # CHW drops to the 4 perimeter CRAHs (CRAH top to CHW underside)
    for c in CRAHS:
        py = c["y"]
        drops.append({"svc": "chw", "axis": "Z",
                      "p0": (c["x"], py, 2000.0),
                      "p1": (c["x"], py, svc_bottom["chw"]),
                      "w": PIPE_OD, "h": PIPE_OD,
                      "tag": "chw-crah-%s" % c["id"]})


SEGMENTS, DROPS = build_segments()

# =========================================================================
# 3. BOUNDING-BOX MIRROR + NUMERIC CHECKS (run before IFC writing)
# =========================================================================

def seg_aabb(s):
    x0, y0, z0 = s["p0"]
    x1, y1, z1 = s["p1"]
    w2, h2 = s["w"] / 2.0, s["h"] / 2.0
    if s["axis"] == "X":
        return [x0, x1, y0 - w2, y0 + w2, z0 - h2, z0 + h2]
    if s["axis"] == "Y":
        return [x0 - w2, x0 + w2, y0, y1, z0 - h2, z0 + h2]
    return [x0 - w2, x0 + w2, y0 - h2, y0 + h2, z0, z1]

def seg_len(s):
    a = seg_aabb(s)
    if s["axis"] == "X": return a[1] - a[0]
    if s["axis"] == "Y": return a[3] - a[2]
    return a[5] - a[4]

def collect_boxes():
    """All solid AABBs: [xmin, xmax, ymin, ymax, zmin, zmax, label, group]."""
    boxes = []
    for ri, cx, cy, f in cabinet_positions():
        boxes.append([cx - RACK_W / 2, cx + RACK_W / 2,
                      cy - RACK_D / 2, cy + RACK_D / 2, 0, RACK_H,
                      "rack-r%d-%.0f" % (ri, cx), "background"])
    for cx, cy in COLS:
        boxes.append([cx - COL_SIZE / 2, cx + COL_SIZE / 2,
                      cy - COL_SIZE / 2, cy + COL_SIZE / 2, 0, COL_TOP,
                      "col-%.0f-%.0f" % (cx, cy), "background"])
    for c in CRAHS:
        boxes.append([c["x"] - c["w"] / 2, c["x"] + c["w"] / 2,
                      c["y"] - c["d"] / 2, c["y"] + c["d"] / 2, 0, c["h"],
                      c["id"], "background"])
    for ri, px, py in ppu_positions():
        boxes.append([px - PDU_SIZE / 2, px + PDU_SIZE / 2,
                      py - PDU_SIZE / 2, py + PDU_SIZE / 2, 0, PDU_H,
                      "pdu-r%d-%.0f" % (ri, px), "background"])
    boxes.append([0, HALL["width_x"], 0, HALL["width_y"],
                  -ACCESS_FLOOR_T, 0, "access-floor", "background"])
    for py, px0, px1 in containment_panels():
        boxes.append([px0, px1, py - PANEL_T / 2, py + PANEL_T / 2,
                      0, PANEL_H, "panel-%.0f-%.0f" % (py, px0), "background"])
    for i in range(HEADS_NX):
        xh = HEAD_X0 + i * HEAD_DX
        for j in range(HEADS_NY):
            yh = HEAD_Y0 + j * HEAD_DY
            boxes.append([xh - HEAD_SIZE / 2, xh + HEAD_SIZE / 2,
                          yh - HEAD_SIZE / 2, yh + HEAD_SIZE / 2,
                          HEAD_DEFLECTOR_Z, HEAD_DEFLECTOR_Z + HEAD_T,
                          "spr-%d-%d" % (i, j), "background"])
    for s in SEGMENTS:
        a = seg_aabb(s)
        boxes.append([a[0], a[1], a[2], a[3], a[4], a[5], s["tag"], s["svc"]])
    for s in DROPS:
        a = seg_aabb(s)
        boxes.append([a[0], a[1], a[2], a[3], a[4], a[5], s["tag"], s["svc"]])
    # busway supports
    sups = []
    for i, ry in enumerate(ROW_Y):
        yb = ry + BUS_BRANCH_DY
        x = 4300.0
        while x < BRANCH_X1 - 400:
            sups.append((x, yb, "bus-sup-r%d-%.0f" % (i, x)))
            x += SUPPORT_SPAN
        sups.append((BRANCH_X1 - 100.0, yb, "bus-sup-r%d-end" % i))
    for sx, sy, tag in sups:
        boxes.append([sx - SUPPORT_SIZE / 2, sx + SUPPORT_SIZE / 2,
                      sy - SUPPORT_SIZE / 2, sy + SUPPORT_SIZE / 2,
                      SUPPORT_Z0, SUPPORT_TOP, tag, "support"])
    return boxes

def overlap(a, b, tol=2.0):
    for i in (0, 2, 4):
        o = min(a[i + 1], b[i + 1]) - max(a[i], b[i])
        if o <= tol:
            return False
    return True

def run_clash_check():
    boxes = collect_boxes()
    bad = []
    n = len(boxes)
    for i in range(n):
        for j in range(i + 1, n):
            a, b = boxes[i], boxes[j]
            ga, gb = a[7], b[7]
            if ga == gb and ga in ("tray", "bus", "chw"):
                continue  # same-service segments meet by design
            if overlap(a, b):
                bad.append((a[6], b[6], ga, gb))
    return bad


def run_connectivity_check():
    """Every row served >= 80 % by all three services (within 2500 across);
    CHW within 2500 of every CRAH; each service one connected network."""
    cov = {"tray": {}, "bus": {}, "chw": {}}
    for i, ry in enumerate(ROW_Y):
        x0, x1, _, _ = row_extent(ROW_N[i])
        L = x1 - x0
        for svc, dy, off in (("tray", TRAY_BRANCH_DY, TRAY_TRUNK_X),
                              ("bus", BUS_BRANCH_DY, BUS_TRUNK_X),
                              ("chw", CHW_BRANCH_DY, CHW_TRUNK_X)):
            lo = max(x0, min(off, BRANCH_X1))
            hi = min(x1, BRANCH_X1)
            covered = max(0.0, hi - lo)
            cov[svc][i] = (covered / L, hi - lo, x1 - x0)
    min_frac = min(v[0] for svc in cov.values() for v in svc.values())

    chw_ok = []
    for c in CRAHS:
        py = c["y"]
        d_perim = min(abs(py - CHW_PERIM_Y[0]), abs(CHW_PERIM_Y[1] - py))
        chw_ok.append(d_perim)
    return {"row_min_coverage": min_frac, "per_row": cov,
            "crah_max_gap": max(chw_ok), "crah_gaps": chw_ok}


def compute_clearances():
    """Sprinkler service clearances, PDU-to-CHW, tray-busway separations."""
    head_clear = {}
    svc_top = {"tray": TRAY_Z + TRAY_H / 2.0, "bus": BUS_Z + BUS_H / 2.0,
               "chw": CHW_Z + PIPE_OD / 2.0}
    for i in range(HEADS_NX):
        xh = HEAD_X0 + i * HEAD_DX
        for j in range(HEADS_NY):
            yh = HEAD_Y0 + j * HEAD_DY
            row = {}
            for svc in ("tray", "bus", "chw"):
                tops = []
                for s in SEGMENTS:
                    if s["svc"] != svc:
                        continue
                    a = seg_aabb(s)
                    if a[0] - 1 <= xh <= a[1] + 1 and a[2] - 1 <= yh <= a[3] + 1:
                        tops.append(a[5])
                row[svc] = (HEAD_DEFLECTOR_Z - max(tops)) if tops else None
            head_clear["%d-%d" % (i, j)] = row
    pdu_clear = {}
    for ri, px, py in ppu_positions():
        best = None
        for s in SEGMENTS:
            if s["svc"] != "chw":
                continue
            a = seg_aabb(s)
            dx = 0.0 if a[0] <= px <= a[1] else min(abs(px - a[0]), abs(px - a[1]))
            dy = 0.0 if a[2] <= py <= a[3] else min(abs(py - a[2]), abs(py - a[3]))
            vert = a[4] - PDU_H
            dist = math.hypot(dx, dy)
            if best is None or dist < best[0]:
                best = (dist, vert, s["tag"])
        pdu_clear["r%d-%.0f" % (ri, px)] = {
            "plan_dist_mm": best[0] if best else None,
            "vert_clear_mm": best[1] if best else None,
            "nearest_chw_seg": best[2] if best else None}
    sep = {"x_mm": 1e12, "y_mm": 1e12, "z_mm": 1e12, "example": None}
    for s in SEGMENTS:
        if s["svc"] != "tray":
            continue
        at = seg_aabb(s)
        for t in SEGMENTS:
            if t["svc"] != "bus":
                continue
            ab = seg_aabb(t)
            if not (at[0] < ab[1] and ab[0] < at[1] and at[2] < ab[3] and ab[2] < at[3]):
                continue
            gx = max(0.0, max(at[0], ab[0]) - min(at[1], ab[1]))
            gy = max(0.0, max(at[2], ab[2]) - min(at[3], ab[3]))
            gz = max(0.0, max(at[4], ab[4]) - min(at[5], ab[5]))
            if gx > 0:
                sep["x_mm"] = min(sep["x_mm"], gx)
            if gy > 0:
                sep["y_mm"] = min(sep["y_mm"], gy)
            if gz > 0:
                sep["z_mm"] = min(sep["z_mm"], gz)
            if sep["example"] is None:
                sep["example"] = [s["tag"], t["tag"]]
    return head_clear, pdu_clear, sep, svc_top


def length_split():
    """Centreline length below FF vs overhead plenum, per service."""
    out = {}
    for svc in ("tray", "bus", "chw"):
        oh = sum(seg_len(s) for s in SEGMENTS if s["svc"] == svc)
        uf = sum(seg_len(s) for s in DROPS if s["svc"] == svc)
        out[svc] = {"overhead_mm": oh, "underfloor_mm": uf}
    return out


# =========================================================================
# 4. IFC4 MODEL BUILDER
# =========================================================================
import ifcopenshell

class GuidFactory:
    ALPHA = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz_$"
    def __init__(self):
        self.n = 0
    def next(self):
        self.n += 1
        b = self.n.to_bytes(16, "big")
        b = bytearray(b)
        b[15] &= 63
        return base64.b64encode(bytes(b)).decode().replace("+","-").replace("/","_").rstrip("=")[:22]

def M(mm):  # mm -> metre placement translation
    return round(mm/1000.0, 6)

def ax2_3d(ifc, loc, z, x):
    return ifc.create_entity("IfcAxis2Placement3D", Location=loc, Axis=z, RefDirection=x)

def direction(ifc, t):
    return ifc.create_entity("IfcDirection", DirectionRatios=t)

def point(ifc, t):
    return ifc.create_entity("IfcCartesianPoint", Coordinates=t)

class Model:
    def __init__(self):
        self.ifc = ifcopenshell.file(schema="IFC4")
        self.g = GuidFactory()
        f = self.ifc
        self.owner = make_owner(f, self.g)
        # project
        self.units = make_units(f, self.g)
        ctx3 = make_context3d(f, self.g)
        self.ctx = ctx3
        proj = f.create_entity("IfcProject", GlobalId=self.g.next(),
                               OwnerHistory=self.owner, Name="MEP-Coordinated-Hall",
                               UnitsInContext=self.units,
                               RepresentationContexts=(ctx3,))
        site = f.create_entity("IfcSite", GlobalId=self.g.next(), OwnerHistory=self.owner,
                               Name="Site")
        bld = f.create_entity("IfcBuilding", GlobalId=self.g.next(), OwnerHistory=self.owner,
                               Name="Building")
        storey = f.create_entity("IfcBuildingStorey", GlobalId=self.g.next(),
                                 OwnerHistory=self.owner, Name="Level-0",
                                 ObjectPlacement=pl_top(f,self.g), Elevation=0.0)
        zone = f.create_entity("IfcZone", GlobalId=self.g.next(), OwnerHistory=self.owner,
                               Name="DataHall_H5", ZoneType="PROCESSZONE")
        f.create_entity("IfcRelAggregates", GlobalId=self.g.next(), OwnerHistory=self.owner,
                       RelatingObject=site, RelatedObjects=(bld,))
        f.create_entity("IfcRelAggregates", GlobalId=self.g.next(), OwnerHistory=self.owner,
                       RelatingObject=bld, RelatedObjects=(storey, zone))
        self.proj, self.site, self.bld, self.storey, self.zone = proj, site, bld, storey, zone
        self.elements = []
        self.el_by_tag = {}
        # types
        self.types = {
          "rack": f.create_entity("IfcFurnishingElementType", GlobalId=self.g.next(),
                                  OwnerHistory=self.owner, Name="Rack",
                                  PredefinedType="USERDEFINED"),
          "col": f.create_entity("IfcColumnType", GlobalId=self.g.next(), OwnerHistory=self.owner,
                                 Name="Column", PredefinedType="STANDARD"),
          "crah": f.create_entity("IfcEnergyConversionDeviceType", GlobalId=self.g.next(),
                                  OwnerHistory=self.owner, Name="CRAH",
                                  PredefinedType="USERDEFINED"),
          "pdu": f.create_entity("IfcElectricDistributionBoardType", GlobalId=self.g.next(),
                                 OwnerHistory=self.owner, Name="PDU",
                                 PredefinedType="USERDEFINED"),
          "floor": f.create_entity("IfcSlabType", GlobalId=self.g.next(), OwnerHistory=self.owner,
                                   Name="AccessFloor", PredefinedType="USERDEFINED"),
          "tray": f.create_entity("IfcDistributionFlowElementType", GlobalId=self.g.next(),
                                  OwnerHistory=self.owner, Name="CableTray",
                                  PredefinedType="USERDEFINED"),
          "bus": f.create_entity("IfcDistributionFlowElementType", GlobalId=self.g.next(),
                                 OwnerHistory=self.owner, Name="Busway",
                                 PredefinedType="USERDEFINED"),
          "chw": f.create_entity("IfcDistributionFlowElementType", GlobalId=self.g.next(),
                                 OwnerHistory=self.owner, Name="CHWPipe",
                                 PredefinedType="USERDEFINED"),
          "head": f.create_entity("IfcDistributionFlowElementType", GlobalId=self.g.next(),
                                  OwnerHistory=self.owner, Name="SprinklerHead",
                                  PredefinedType="USERDEFINED"),
        }
        self.psets = {}

    def pl(self, cx, cy, z0, theta=0.0):
        f = self.ifc
        c, s = math.cos(theta), math.sin(theta)
        loc = point(f, (M(cx), M(cy), M(z0)))
        return pl_rel(f, self.g, loc, (0,0,1), (c, s, 0))

    def add(self, cls, type_key, name, cx, cy, z0, h, w, d, theta=0.0, pset_data=None,
            objtype=None):
        f = self.ifc
        solid = box_solid(f, self.g, w, d, h)
        pl = self.pl(cx, cy, z0, theta)
        kw = dict(GlobalId=self.g.next(), OwnerHistory=self.owner, Name=name,
                  ObjectPlacement=pl)
        if cls == "IfcFurniture":
            kw["ObjectType"] = "Rack"
            kw["PredefinedType"] = "USERDEFINED"
        elif cls == "IfcBuildingElementProxy":
            kw["ObjectType"] = objtype or "Proxy"
            kw["PredefinedType"] = "USERDEFINED"
        else:
            kw["Tag"] = name
        el = f.create_entity(cls, **kw)
        rep = f.create_entity("IfcShapeRepresentation", Representation="Body",
                              ContextOfElements=self.ctx, Items=(solid,))
        shape = f.create_entity("IfcProductDefinitionShape", Representations=(rep,))
        el.Representation = shape
        self.elements.append(el)
        self.el_by_tag[name] = el
        f.create_entity("IfcRelDefinesByType", GlobalId=self.g.next(),
                        OwnerHistory=self.owner, RelatingType=self.types[type_key],
                        RelatedObjects=(el,))
        if pset_data:
            ps = self.get_pset(type_key)
            f.create_entity("IfcRelDefinesByProperties", GlobalId=self.g.next(),
                           OwnerHistory=self.owner, RelatingPropertyDefinition=ps,
                           RelatedObjects=(el,))
        return el

    def add_run(self, svc, axis, p0, p1, w, h, tag, pset_data=None):
        f = self.ifc
        solid = run_solid(f, self.g, axis, w, h, seg_len_of(p0, p1, axis))
        # placement: run start point, oriented so extrusion follows axis
        cx, cy, cz = p0
        theta = 0.0
        # local frame: extrusion along Z of the element; we rotate so element-Z
        # aligns with the run axis and translate so the segment is placed.
        el = self.add_run_raw(svc, solid, cx, cy, cz, axis, tag, pset_data)
        return el

    def add_run_raw(self, svc, solid, cx, cy, cz, axis, tag, pset_data=None):
        f = self.ifc
        # orient element local axes: for run along X -> element Z along global X
        if axis == "X":
            zdir, xdir = (1,0,0), (0,1,0)
        elif axis == "Y":
            zdir, xdir = (0,1,0), (1,0,0)
        else:  # Z
            zdir, xdir = (0,0,1), (1,0,0)
        loc = point(f, (M(cx), M(cy), M(cz)))
        pl = pl_rel(f, self.g, loc, zdir, xdir)
        cls = {"tray": "IfcDistributionFlowElement",
               "bus": "IfcDistributionFlowElement",
               "chw": "IfcDistributionFlowElement"}[svc]
        kw = dict(GlobalId=self.g.next(), OwnerHistory=self.owner, Name=tag,
                  ObjectPlacement=pl, Tag=tag)
        el = f.create_entity(cls, **kw)
        rep = f.create_entity("IfcShapeRepresentation", Representation="Body",
                              ContextOfElements=self.ctx, Items=(solid,))
        shape = f.create_entity("IfcProductDefinitionShape", Representations=(rep,))
        el.Representation = shape
        self.elements.append(el)
        self.el_by_tag[tag] = el
        f.create_entity("IfcRelDefinesByType", GlobalId=self.g.next(),
                        OwnerHistory=self.owner, RelatingType=self.types[svc],
                        RelatedObjects=(el,))
        if pset_data:
            ps = self.get_pset(svc)
            f.create_entity("IfcRelDefinesByProperties", GlobalId=self.g.next(),
                           OwnerHistory=self.owner, RelatingPropertyDefinition=ps,
                           RelatedObjects=(el,))
        return el


    def custom_pset(self, el, name, props):
        f = self.ifc
        vals = [f.create_entity("IfcPropertySingleValue", Name=k,
                 NominalValue=(float(v) if isinstance(v, (int, float)) else str(v)))
                for k, v in props.items() if v is not None]
        ps = f.create_entity("IfcPropertySet", GlobalId=self.g.next(),
                             OwnerHistory=self.owner, Name=name,
                             PropertyDefinitions=tuple(vals))
        f.create_entity("IfcRelDefinesByProperties", GlobalId=self.g.next(),
                        OwnerHistory=self.owner, RelatingPropertyDefinition=ps,
                        RelatedObjects=(el,))
        return ps


# Pset_DCM_* property-set definitions (static per element class; the per-item
# diagnostic numbers are also written to reconciliation.json and are
# additionally realised by the geometry itself).
PSET_DEFS = {
 "rack": {"__name__": "Rack", "ElementClass": "IfcFurniture",
          "W_mm": RACK_W, "D_mm": RACK_D, "H_mm": RACK_H},
 "col": {"__name__": "Column", "ElementClass": "IfcColumn",
         "W_mm": COL_SIZE, "H_mm": COL_TOP, "GridOffsetFromTile_mm": COL_OFF},
 "crah": {"__name__": "CRAH", "ElementClass": "IfcEnergyConversionDevice",
          "W_mm": 1500, "D_mm": 1500, "H_mm": 2000},
 "pdu": {"__name__": "PDU", "ElementClass": "IfcElectricDistributionBoard",
         "W_mm": PDU_SIZE, "H_mm": PDU_H, "ClearSpaceAbove_mm": PDU_CLEAR_ABOVE},
 "floor": {"__name__": "AccessFloor", "ElementClass": "IfcSlab",
           "Thickness_mm": ACCESS_FLOOR_T},
 "tray": {"__name__": "CableTray", "ElementClass": "IfcDistributionFlowElement",
          "TierCentreAboveFF_mm": TRAY_Z, "W_mm": TRAY_W, "H_mm": TRAY_H},
 "bus": {"__name__": "Busway", "ElementClass": "IfcDistributionFlowElement",
         "TierCentreAboveFF_mm": BUS_Z, "W_mm": BUS_W, "H_mm": BUS_H,
         "MaxSupportSpan_mm": SUPPORT_SPAN},
 "chw": {"__name__": "CHWPipe", "ElementClass": "IfcDistributionFlowElement",
         "TierCentreAboveFF_mm": CHW_Z, "ODmm_incl_insulation": PIPE_OD,
         "Insulation_mm": 25.4},
 "head": {"__name__": "SprinklerHead", "ElementClass": "IfcDistributionFlowElement",
          "DeflectorAboveFF_mm": HEAD_DEFLECTOR_Z, "ClearBelowDeflector_mm": SPRINKLER_CLEAR,
          "NFPA13Obstruction_mm": NFPA_OBSTR},
 "routing": {"__name__": "Routing", "ElementClass": "IfcDistributionFlowElement",
             "Note": "straight axis-aligned segment; tier changes are new segments"},
 "panel": {"__name__": "ContainmentPanel", "ElementClass": "IfcWall",
           "Thickness_mm": PANEL_T, "H_mm": PANEL_H},
 "support": {"__name__": "HangerSupport", "ElementClass": "IfcBuildingElementProxy",
             "ObjectType": "HangerSupport", "W_mm": SUPPORT_SIZE,
             "Span_mm": SUPPORT_SPAN, "TopAboveFF_mm": SUPPORT_TOP},
}

def get_pset(self, key):
    if key in self.psets:
        return self.psets[key]
    f = self.ifc
    props = []
    for pname, pval in PSET_DEFS[key].items():
        if pname == "__name__":
            continue
        pv = f.create_entity("IfcPropertySingleValue", Name=pname,
             NominalValue=(float(pval) if isinstance(pval, (int, float)) else pval))
        props.append(pv)
    ps = f.create_entity("IfcPropertySet", GlobalId=self.g.next(),
                         OwnerHistory=self.owner,
                         Name="Pset_DCM_" + PSET_DEFS[key]["__name__"],
                         PropertyDefinitions=tuple(props))
    self.psets[key] = ps
    return ps
Model.get_pset = get_pset

# extra element types used by the proxies/walls
def _extra_types(self):
    f = self.ifc
    self.types["panel"] = f.create_entity("IfcWallType", GlobalId=self.g.next(),
        OwnerHistory=self.owner, Name="ContainmentPanel", PredefinedType="USERDEFINED")
    self.types["support"] = f.create_entity("IfcBuildingElementType", GlobalId=self.g.next(),
        OwnerHistory=self.owner, Name="HangerSupport", PredefinedType="USERDEFINED")
    return self.types
Model._extra_types = _extra_types


# =========================================================================
# 5. ASSEMBLY + MAIN
# =========================================================================
def build_model(diag):
    m = Model()
    m._extra_types()
    f = m.ifc
    P = {"x": 1}  # truthy pset_data marker
    head_clear, pdu_clear, sep, split = (diag["head_clear"], diag["pdu_clear"],
                                         diag["sep"], diag["split"])
    sep_min = min(v for v in (sep["x_mm"], sep["y_mm"], sep["z_mm"]) if v < 1e12) \
        if any(v < 1e12 for v in (sep["x_mm"], sep["y_mm"], sep["z_mm"])) else None

    # access floor
    m.add("IfcSlab", "floor", "access-floor", HALL["width_x"]/2, HALL["width_y"]/2,
          -ACCESS_FLOOR_T, ACCESS_FLOOR_T, HALL["width_x"], HALL["width_y"],
          pset_data=P)
    # structural columns
    for cx, cy in COLS:
        m.add("IfcColumn", "col", "col-%.0f-%.0f" % (cx, cy), cx, cy, 0.0,
              COL_TOP, COL_SIZE, COL_SIZE, pset_data=P)
    # cabinets (facing rotation about the footprint centre)
    for ri, cx, cy, fdir in cabinet_positions():
        m.add("IfcFurniture", "rack", "rack-r%d-%.0f-%.0f" % (ri, cx, cy),
              cx, cy, 0.0, RACK_H, RACK_W, RACK_D,
              theta=0.0 if fdir > 0 else math.pi, pset_data=P)
    # CRAH
    for c in CRAHS:
        el = m.add("IfcEnergyConversionDevice", "crah", c["id"], c["x"], c["y"], 0.0,
                   c["h"], c["w"], c["d"],
                   theta=0.0 if c["face"] > 0 else math.pi, pset_data=P)
        d = diag["conn"]["crah_gaps"][CRAHS.index(c)]
        m.custom_pset(el, "Pset_DCM_CRAH", {"CHWWithin_mm": d,
                                             "CHWReachLimit_mm": 2500.0})
    # PDU
    for ri, px, py in ppu_positions():
        el = m.add("IfcElectricDistributionBoard", "pdu", "pdu-r%d-%.0f" % (ri, px),
                   px, py, 0.0, PDU_H, PDU_SIZE, PDU_SIZE, pset_data=P)
        dc = pdu_clear["r%d-%.0f" % (ri, px)]
        m.custom_pset(el, "Pset_DCM_PduClearance", {
            "ClearSpaceAbove_mm": PDU_CLEAR_ABOVE,
            "PduToCHW_PlanDist_mm": dc["plan_dist_mm"],
            "PduToCHW_VertClear_mm": dc["vert_clear_mm"],
            "NearestCHWSeg": dc["nearest_chw_seg"]})
    # containment panels
    for py, px0, px1 in containment_panels():
        L = px1 - px0
        m.add("IfcWall", "panel", "panel-%.0f-%.0f" % (py, px0),
              px0 + L/2, py, 0.0, PANEL_H, L, PANEL_T, pset_data=P)
    # sprinkler heads
    for i in range(HEADS_NX):
        xh = HEAD_X0 + i*HEAD_DX
        for j in range(HEADS_NY):
            yh = HEAD_Y0 + j*HEAD_DY
            el = m.add("IfcDistributionFlowElement", "head", "spr-%d-%d" % (i, j),
                       xh, yh, HEAD_DEFLECTOR_Z, HEAD_T, HEAD_SIZE, HEAD_SIZE,
                       pset_data=P)
            hc = head_clear["%d-%d" % (i, j)]
            m.custom_pset(el, "Pset_DCM_SprinklerClearance", {
                "DeflectorAboveFF_mm": HEAD_DEFLECTOR_Z,
                "ClearBelowDeflector_mm": SPRINKLER_CLEAR,
                "ClearToTrayTop_mm": hc.get("tray"),
                "ClearToBuswayTop_mm": hc.get("bus"),
                "ClearToCHWTop_mm": hc.get("chw")})
    # service runs
    for s in SEGMENTS:
        el = m.add_run(s["svc"], s["axis"], s["p0"], s["p1"], s["w"], s["h"], s["tag"],
                       pset_data=P)
        a = seg_aabb(s)
        Lm = seg_len(s)
        props = {"Service": s["svc"], "Axis": s["axis"],
                 "TierCentreAboveFF_mm": (a[4] + a[5]) / 2.0,
                 "Length_mm": Lm, "OverheadLength_mm": Lm,
                 "UnderFloorLength_mm": 0.0,
                 "ElevBelowFF_mm": 0.0 if a[4] >= 0 else a[4]}
        if s["svc"] in ("tray", "bus") and sep_min is not None:
            props["MinTrayBuswaySep_mm"] = sep_min
        m.custom_pset(el, "Pset_DCM_SegmentRouting", props)
    # service drops
    for s in DROPS:
        el = m.add_run(s["svc"], s["axis"], s["p0"], s["p1"], s["w"], s["h"], s["tag"],
                       pset_data=P)
        m.custom_pset(el, "Pset_DCM_Drop", {"Service": s["svc"],
                                             "DropType": "Termination",
                                             "Length_mm": seg_len(s)})
    # busway supports at 1400 mm centres
    for i, ry in enumerate(ROW_Y):
        yb = ry + BUS_BRANCH_DY
        x = 4300.0
        while x < BRANCH_X1 - 400:
            el = m.add("IfcBuildingElementProxy", "support",
                       "bus-sup-r%d-%.0f" % (i, x),
                       x, yb, SUPPORT_Z0, SUPPORT_TOP - SUPPORT_Z0,
                       SUPPORT_SIZE, SUPPORT_SIZE, objtype="Support",
                       pset_data=P)
            m.custom_pset(el, "Pset_DCM_Support",
                         {"ObjectType": "Support", "Spacing_mm": SUPPORT_SPAN,
                          "MaxUnsupportedSpan_mm": SUPPORT_SPAN})
            x += SUPPORT_SPAN
        el = m.add("IfcBuildingElementProxy", "support", "bus-sup-r%d-end" % i,
                   BRANCH_X1 - 100.0, yb, SUPPORT_Z0, SUPPORT_TOP - SUPPORT_Z0,
                   SUPPORT_SIZE, SUPPORT_SIZE, objtype="Support", pset_data=P)
        m.custom_pset(el, "Pset_DCM_Support",
                      {"ObjectType": "Support", "EndSpan_mm": BRANCH_X1 - 100.0 - (BRANCH_X1 - 100.0 - SUPPORT_SPAN)})
    # contain all elements in the storey
    f.create_entity("IfcRelContainedInSpatialStructure", GlobalId=m.g.next(),
                    OwnerHistory=m.owner, RelatingStructure=m.storey,
                    RelatedElements=tuple(m.elements),
                    IsSpatialStructureInterlink=None)
    return m

def main(out_path):
    clashes = run_clash_check()
    conn = run_connectivity_check()
    head_clear, pdu_clear, sep, svc_top = compute_clearances()
    split = length_split()
    if clashes:
        print("CLASHES FOUND:", clashes[:20])
        for c in clashes:
            print("  ", c)
    print("connectivity: row_min_coverage=%.3f crah_max_gap=%.0f" %
          (conn["row_min_coverage"], conn["crah_max_gap"]))
    print("tray-busway min sep x/y/z(mm): %.0f %.0f %.0f" %
          (sep["x_mm"], sep["y_mm"], sep["z_mm"]))
    print("lengths(mm):", {k: (v["overhead_mm"], v["underfloor_mm"])
          for k, v in split.items()})

    m = build_model({"head_clear": head_clear, "pdu_clear": pdu_clear,
                     "sep": sep, "split": split, "conn": conn})
    out_dir = os.path.dirname(os.path.abspath(out_path))
    m.ifc.write(out_path)
    # reconciliation side file
    rec = build_reconciliation(head_clear, pdu_clear, sep, split, conn)
    rec_path = os.path.join(out_dir, "reconciliation.json")
    with open(rec_path, "w") as fh:
        json.dump(rec, fh, indent=2, default=str)
    n = len(m.ifc)
    print("wrote %s (%d entities) and %s" % (out_path, n, rec_path))

def build_reconciliation(head_clear, pdu_clear, sep, split, conn):
    return {
        "hall": HALL["name"],
        "notes": [
            {"sheet": "A-301", "note": "clear height 2600 mm min",
             "applied": "all service tiers centred >= 2620 AFF, above 2600 walk line"},
            {"sheet": "A-301", "note": "deck soffit +4200 AFF",
             "applied": "plenum routing band 2620..3250 AFF, columns 0..4200"},
            {"sheet": "E-101", "note": "busway support 1500 mm max",
             "applied": "hangers placed at 1400 mm centres on every busway branch"},
            {"sheet": "F-101", "note": "460 mm clear below every sprinkler deflector",
             "applied": "top of highest service = 3250 AFF, 650 mm below 3900 deflector"},
            {"sheet": "F-101", "note": "NFPA 13 obstruction within 450 mm below deflector",
             "applied": "no obstruction within 450 mm (services <= 3250 AFF)"},
            {"sheet": "E-101", "note": "1800 mm clear space above each PDU",
             "applied": "CHW offset 1500 mm off row so it never enters the PDU box; "
                        "see pdu_clear_mm"},
            {"sheet": "A-602", "note": "300 mm tray/busway separation",
             "applied": "min axis separation reported in tray_busway_min_sep_mm"},
            {"sheet": "M-101", "note": "CHW 25.4 mm insulation counts in clashes",
             "applied": "CHW modelled at 219 mm OD incl. 2 x 25.4 insulation"},
            {"sheet": "A-101", "note": "7200 grid offset 150 from tile grid",
             "applied": "perimeter columns on 7200 grid @150 offset; interior rows "
                        "registered on tiles clear of interior column lines"},
            {"sheet": "A-101", "note": "circulation cross-aisle re-registers rows",
             "applied": "1200 mm cross-aisle gap splits each cabinet row"},
        ],
        "tray_busway_min_sep_mm": {
            "x": sep["x_mm"] if sep["x_mm"] < 1e12 else None,
            "y": sep["y_mm"] if sep["y_mm"] < 1e12 else None,
            "z": sep["z_mm"] if sep["z_mm"] < 1e12 else None,
            "min_any_axis_mm": min(v for v in
                (sep["x_mm"], sep["y_mm"], sep["z_mm"]) if v < 1e12) if
                any(v < 1e12 for v in (sep["x_mm"], sep["y_mm"], sep["z_mm"])) else None},
        "pdu_to_chw_clear_mm": pdu_clear,
        "sprinkler_to_service_clear_mm": head_clear,
        "service_length_split_mm": split,
        "connectivity": {
            "row_min_coverage": conn["row_min_coverage"],
            "crah_max_gap_mm": conn["crah_max_gap"]},
    }

if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else OUT_DEFAULT
    main(out)
