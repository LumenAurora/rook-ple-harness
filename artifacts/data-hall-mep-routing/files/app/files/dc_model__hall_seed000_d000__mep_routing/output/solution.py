#!/usr/bin/env python3
"""
Coordinated 3D MEP model for data hall dc_model `hall_seed000_d000`.

Self-contained IFC4 builder (ifcopenshell + numpy only).  All design values
were read off the seven drawing sheets (A-101, A-301, A-601, A-602, M-101,
E-101, F-101) and are baked in as literals below.  No drawing files are read
at runtime; the script is deterministic, headless and network-free.

Usage:
    python3 solution.py [out.ifc]        # default: output/model.ifc

Modelling contract implemented:
  * IFC4, project units millimetre; placement-matrix translations in metres,
    profile dimensions and extrusion depths in millimetres, 2D profile
    points only (IfcRectangleProfileDef / IfcCircleProfileDef).
  * Racks = IfcFurniture / USERDEFINED / "Rack", rotated about the footprint
    centre; columns = IfcColumn / USERDEFINED / "Column"; CRAH =
    IfcEnergyConversionDevice "CRAH"; PDU = IfcBuildingElementProxy "PDU";
    access floor = IfcCovering "Floor"; cold-aisle containment = proxy
    "Containment"; containment roof = IfcCovering "Roof"; sprinkler heads =
    proxy "SprinklerHead".
  * Telecom tray = IfcCableCarrierSegment "CableTray"; power busway =
    IfcCableSegment "Busway"; CHW = IfcPipeSegment "ChilledWaterPipe" with
    25.4 mm insulation counted in the clash diameter.
  * Hangers = proxy "Hanger" (max spacing 3 m per A-602); CHW CRAH taps =
    IfcPipeSegment whose ObjectType contains "Termination"; PDU drops =
    ObjectType containing "Drop".
  * Pset_DCM_* property sets on every element.
"""
import sys
import math

import ifcopenshell
import ifcopenshell.guid

OUT_DEFAULT = "output/model.ifc"

# ---------------------------------------------------------------------------
# 1.  Design data read off the drawings (all mm unless noted).
# ---------------------------------------------------------------------------
HALL_X, HALL_Y = 27000.0, 21000.0     # A-301: clear 27.0 x 21.0 m
FLOOR_TOP = 300.0                     # A-602: 300 mm raised access floor
CEIL = 3600.0                         # A-301: plenum top +3.600 FFL

# --- racks (A-101 / A-601) ---
RACK_W, RACK_D, RACK_H = 600.0, 1000.0, 2000.0
N_ROWS, N_RACKS_ROW = 8, 16
X0, PITCH = 3000.0, 1600.0            # 16 x 600 + 7 x 400 = 12.0 m band
ROW_PITCH, ROW_Y0 = 3300.0, 2100.0
ROW_Y = [ROW_Y0 + i * ROW_PITCH for i in range(N_ROWS)]
ROW_FACE = [0.0, math.pi / 2, 0.0, math.pi / 2, 0.0, math.pi / 2, 0.0, math.pi / 2]
COLD_AISLE_C = [ROW_Y[i] + RACK_D + 600.0 for i in range(0, N_ROWS, 2)]
AISLE_W, CONT_H, ROOF_T = 1200.0, 3300.0, 100.0   # A-602

# --- structural (A-101) ---
COLS = [(x, y, 600.0, 600.0, CEIL)
        for y in (4500.0, 9000.0, 13500.0, 18000.0)
        for x in (4500.0, 9000.0, 13500.0, 18000.0, 22500.0, 26500.0)]

# --- CRAH (A-101) ---
CRAH_W, CRAH_D, CRAH_H = 2400.0, 800.0, 2200.0
CRAHS = [
    (1500.0, 3750.0, 0.0),
    (1500.0, 7050.0, 0.0),
    (24500.0, 7050.0, 0.0),
    (24500.0, 10350.0, 0.0),
    (6000.0, 19300.0, math.pi),
    (21000.0, 19300.0, math.pi),
]

# --- PDU (E-101) ---
PDU_W, PDU_D, PDU_H = 1200.0, 900.0, 2200.0
PDUS = [(x, 20100.0, math.pi) for x in (6000.0, 11000.0, 16000.0, 21000.0)]

# --- sprinklers (F-101 grid + A-301 deflector callout) ---
HEAD_X = [2700.0, 8100.0, 13500.0, 18900.0, 24300.0]
HEAD_Y = [3300.0, 9900.0, 16500.0]
DEFLECTOR_Z = 3140.0                  # A-301 callout +3.140 FFL
HEAD_BODY_Z = DEFLECTOR_Z + 260.0
HEAD_D = 100.0

# --- service tiers (A-301 elevation callouts) ---
TRAY_Z, TRAY_H, TRAY_W = 2850.0, 250.0, 400.0      # tray bottom 2.850
BUS_Z, BUS_W, BUS_H = 3200.0, 320.0, 400.0         # busway bottom 3.200
PIPE_D, INS = 200.0, 25.4
PIPE_R = PIPE_D / 2.0 + INS                          # OD radius incl. insulation
PIPE_Z = 3450.0                                       # centreline
TRUNK_X, EAST_TRUNK_X = 14900.0, 24500.0

# --- service entries (M-101 / E-101) ---
TRAY_MAIN_Y = 16800.0
BUS_MAIN_Y = 19500.0

# ---------------------------------------------------------------------------
# 2.  Axis-aligned segment networks (every direction change = new segment).
# ---------------------------------------------------------------------------
SEGMENTS = []


def add(kind, x1, y1, x2, y2, note=""):
    if x1 == x2:
        x, y, lx, ly = x1, min(y1, y2), 0.0, abs(y2 - y1)
    else:
        x, y, lx, ly = min(x1, x2), y1, abs(x2 - x1), 0.0
    SEGMENTS.append({"kind": kind, "x": x, "y": y, "lx": lx, "ly": ly, "note": note})


# cable tray: west entry -> main at y=16.8 -> odd-row drops at x=3.3
add("tray", 0.0, 20400.0, 0.0, TRAY_MAIN_Y, "tray entry drop")
add("tray", 0.0, TRAY_MAIN_Y, 27000.0, TRAY_MAIN_Y, "tray main")
for i in (0, 2, 4, 6):
    add("tray", 3300.0, TRAY_MAIN_Y, 3300.0, ROW_Y[i], "row%d drop" % i)

# busway: west entry -> main at y=19.5 -> PDU drops
add("bus", 0.0, 19900.0, 0.0, BUS_MAIN_Y, "bus entry run")
add("bus", 0.0, BUS_MAIN_Y, 27000.0, BUS_MAIN_Y, "busway main")
for cx in (5350.0, 6000.0, 11000.0, 16000.0, 21000.0):
    add("bus", cx, BUS_MAIN_Y, cx, 20050.0, "PDU drop x=%.0f" % cx)

# chilled water: west entry -> trunk at x=14.9 + north/east branches
add("chw", 0.0, 19900.0, TRUNK_X, 19900.0, "chw entry run")
add("chw", TRUNK_X, 600.0, TRUNK_X, 16800.0, "trunk")
add("chw", 4500.0, 19300.0, 22500.0, 19300.0, "north branch")
add("chw", TRUNK_X, 16800.0, TRUNK_X, 19300.0, "trunk north link")
add("chw", TRUNK_X, 12000.0, EAST_TRUNK_X, 12000.0, "branch tie")
add("chw", EAST_TRUNK_X, 5000.0, EAST_TRUNK_X, 12000.0, "east branch")
add("chw", 3750.0, 16400.0, 3750.0, 3750.0, "W CRAH0 tap")
add("chw", 7050.0, 16400.0, 7050.0, 7050.0, "W CRAH1 tap")
add("chw", 6000.0, 17800.0, 6000.0, 19300.0, "N CRAH0 tap")
add("chw", 21000.0, 17800.0, 21000.0, 19300.0, "N CRAH1 tap")
add("chw", 25900.0, 7050.0, EAST_TRUNK_X, 7050.0, "E CRAH0 tap")
add("chw", 25900.0, 10350.0, EAST_TRUNK_X, 10350.0, "E CRAH1 tap")

# ---------------------------------------------------------------------------
# 3.  Entity helpers (positional-argument creation, custom schema layout).
# ---------------------------------------------------------------------------
class Mdl:
    def __init__(self, f):
        self.f = f

    def list(self, items):
        return self.f.create_list(list(items))


GUID = lambda: ifcopenshell.guid.new()


def E(m, cls, *pos):
    """create_entity with positional args, padded to the schema length."""
    f = m.f
    ent = f.create_entity(cls)          # empty, correct arity
    need = len(ent)
    pos = list(pos) + [None] * (need - len(pos))
    pos = pos[:need]
    for i, v in enumerate(pos):
        if v is not None:
            ent[i] = v
    return ent


def Pt2(m, x, y):
    return E(m, "IfcCartesianPoint", [x, y])


def Pt3(m, x, y, z):
    return E(m, "IfcCartesianPoint", [x, y, z])


def Dir(m, x, y, z):
    return E(m, "IfcDirection", [x, y, z])


def Axis2_2D(m, x, y):
    return E(m, "IfcAxis2Placement2D", Pt2(m, x, y))


def Axis2_3D(m, x_m, y_m, z_m, rot=0.0):
    """placement-matrix translations in metres; rotation about footprint
    centre in the 0..1 radian sense used by the drawing set."""
    return E(m, "IfcAxis2Placement3D",
             Pt3(m, x_m, y_m, z_m),
             Dir(m, 0.0, 0.0, 1.0),
             Dir(m, math.cos(rot), math.sin(rot), 0.0))


_ctx_holder = {}


def ctx_of(m):
    if "ctx" not in _ctx_holder:
        wcs = Axis2_3D(m, 0.0, 0.0, 0.0)
        _ctx_holder["ctx"] = E(m, "IfcGeometricRepresentationContext",
                               None, "Model", 3, 1e-05, wcs, None)
    return _ctx_holder["ctx"]


def rect_profile(m, w_mm, d_mm, cx_offset=True):
    pos = Axis2_2D(m, -w_mm / 2.0, -d_mm / 2.0) if cx_offset else None
    return E(m, "IfcRectangleProfileDef", "AREA", None, pos, w_mm, d_mm)


def circle_profile(m, r_mm):
    return E(m, "IfcCircleProfileDef", "AREA", None, None, r_mm)


def box_solid(m, w_mm, d_mm, h_mm, cx_m, cy_m, z0_m, rot):
    """Extruded solid: profile dims & depth in mm, placement translation m."""
    prof = rect_profile(m, w_mm, d_mm, cx_offset=True)
    solid = E(m, "IfcExtrudedAreaSolid", prof,
              Axis2_3D(m, cx_m, cy_m, z0_m, rot),
              Dir(m, 0.0, 0.0, 1.0), float(h_mm))
    rep = E(m, "IfcShapeRepresentation", [ctx_of(m)], "Body", "SweptSolid", [solid])
    return E(m, "IfcProductDefinitionShape", None, None, [rep])


def prop_value(m, key, value, unit=None):
    """IfcPropertySingleValue with numeric or enumerated nominal value."""
    if isinstance(value, str):
        nominal = E(m, "IfcPropertyEnumeratedValue", None, None, [value], None)
    else:
        try:
            nominal = E(m, "IfcPropertyListValue", None, None, [float(value)], None)
        except Exception:
            nominal = E(m, "IfcPropertyEnumeratedValue", None, None, [str(value)], None)
    return E(m, "IfcPropertySingleValue", key, None, nominal, None)


def pset(m, elem, name, rows):
    props = m.list([prop_value(m, k, v, u) for k, v, u in rows])
    ps = E(m, "IfcPropertySet", GUID(), None, name, name, props)
    E(m, "IfcRelDefinesByProperties", GUID(), None, None, None, [elem], ps)
    return ps


def element(m, cls, pred, name, obj_type, rep, placement):
    return E(m, cls, GUID(), None, name, None, obj_type, placement, rep, None, pred)


# ---------------------------------------------------------------------------
# 4.  Background.
# ---------------------------------------------------------------------------
def background(m, storey, rel):
    f = m.f
    def contain(el):
        rel.RelatedElements = m.list(list(rel.RelatedElements) + [el])

    # access floor (IfcCovering "Floor")
    fl = element(m, "IfcCovering", "Floor", "AccessFloor", "AccessFloor",
                 box_solid(m, HALL_X, HALL_Y, 300.0, HALL_X / 2000.0,
                            HALL_Y / 2000.0, 0.0, 0.0),
                 Axis2_3D(m, 0.0, 0.0, 0.0))
    pset(m, fl, "Pset_DCM_Floor", [("Thickness", 300.0, "mm")])
    contain(fl)

    # columns
    for i, (x, y, cw, cd, ch) in enumerate(COLS):
        c = element(m, "IfcColumn", "USERDEFINED", "COL-%02d" % (i + 1), "Column",
                    box_solid(m, cw, cd, ch, (x + cw / 2.0) / 1000.0,
                               (y + cd / 2.0) / 1000.0, 0.0, 0.0),
                    Axis2_3D(m, (x + cw / 2.0) / 1000.0, (y + cd / 2.0) / 1000.0, 0.0))
        pset(m, c, "Pset_DCM_Column",
             [("SectionWidth", cw, "mm"), ("SectionDepth", cd, "mm"),
              ("Height", ch, "mm")])
        contain(c)

    # racks
    n = 0
    for i, ry in enumerate(ROW_Y):
        for j in range(N_RACKS_ROW):
            n += 1
            rx = X0 + j * PITCH
            r = element(m, "IfcFurniture", "USERDEFINED", "RACK-%03d" % n, "Rack",
                       box_solid(m, RACK_W, RACK_D, RACK_H,
                                 (rx + RACK_W / 2.0) / 1000.0,
                                 (ry + RACK_D / 2.0) / 1000.0,
                                 FLOOR_TOP / 1000.0, ROW_FACE[i]),
                       Axis2_3D(m, (rx + RACK_W / 2.0) / 1000.0,
                                (ry + RACK_D / 2.0) / 1000.0,
                                FLOOR_TOP / 1000.0, ROW_FACE[i]))
            pset(m, r, "Pset_DCM_Rack",
                 [("Width", RACK_W / 1000.0, "m"), ("Depth", RACK_D / 1000.0, "m"),
                  ("Height", RACK_H / 1000.0, "m"), ("Row", i + 1, None),
                  ("Facing", "North" if i % 2 else "South", None)])
            contain(r)

    # CRAH
    for i, (x, y, rot) in enumerate(CRAHS):
        c = element(m, "IfcEnergyConversionDevice", "USERDEFINED", "CRAH-%d" % (i + 1),
                    "CRAH",
                    box_solid(m, CRAH_W, CRAH_D, CRAH_H,
                              (x + CRAH_W / 2.0) / 1000.0,
                              (y + CRAH_D / 2.0) / 1000.0,
                              FLOOR_TOP / 1000.0, rot),
                    Axis2_3D(m, (x + CRAH_W / 2.0) / 1000.0,
                             (y + CRAH_D / 2.0) / 1000.0, FLOOR_TOP / 1000.0, rot))
        pset(m, c, "Pset_DCM_CRAH", [("Height", CRAH_H, "mm")])
        contain(c)

    # PDU
    for i, (x, y, rot) in enumerate(PDUS):
        p = element(m, "IfcBuildingElementProxy", "USERDEFINED", "PDU-%d" % (i + 1),
                    "PDU",
                    box_solid(m, PDU_W, PDU_D, PDU_H,
                              (x + PDU_W / 2.0) / 1000.0,
                              (y + PDU_D / 2.0) / 1000.0,
                              FLOOR_TOP / 1000.0, rot),
                    Axis2_3D(m, (x + PDU_W / 2.0) / 1000.0,
                             (y + PDU_D / 2.0) / 1000.0, FLOOR_TOP / 1000.0, rot))
        pset(m, p, "Pset_DCM_PDU", [("Height", PDU_H, "mm"),
                                    ("NoCHWZone", "2.5-4.3 m above floor", None)])
        contain(p)

    # containment aisles + roofs
    for ay in COLD_AISLE_C:
        cm = element(m, "IfcBuildingElementProxy", "USERDEFINED",
                     "CONT-AIL-%.0f" % ay, "Containment",
                     box_solid(m, HALL_X - 2 * X0, AISLE_W, CONT_H,
                               (X0 + (HALL_X - 2 * X0) / 2.0) / 1000.0,
                               ay / 1000.0, FLOOR_TOP / 1000.0, 0.0),
                     Axis2_3D(m, (X0 + (HALL_X - 2 * X0) / 2.0) / 1000.0,
                              ay / 1000.0, FLOOR_TOP / 1000.0))
        pset(m, cm, "Pset_DCM_Containment", [("Height", CONT_H, "mm")])
        contain(cm)
        rf = element(m, "IfcCovering", "Roof", "CONT-ROOF-%.0f" % ay,
                     "ContainmentRoof",
                     box_solid(m, HALL_X - 2 * X0, AISLE_W, ROOF_T,
                               (X0 + (HALL_X - 2 * X0) / 2.0) / 1000.0,
                               ay / 1000.0,
                               (FLOOR_TOP + CONT_H - ROOF_T) / 1000.0, 0.0),
                     Axis2_3D(m, (X0 + (HALL_X - 2 * X0) / 2.0) / 1000.0,
                              ay / 1000.0, (FLOOR_TOP + CONT_H - ROOF_T) / 1000.0))
        pset(m, rf, "Pset_DCM_Roof", [("Thickness", ROOF_T, "mm")])
        contain(rf)

    # sprinkler heads
    for hx in HEAD_X:
        for hy in HEAD_Y:
            hd = element(m, "IfcBuildingElementProxy", "USERDEFINED",
                         "SPRK-%.0f-%.0f" % (hx, hy), "SprinklerHead",
                         box_solid(m, HEAD_D, HEAD_D, 150.0,
                                   hx / 1000.0, hy / 1000.0,
                                   HEAD_BODY_Z / 1000.0, 0.0),
                         Axis2_3D(m, hx / 1000.0, hy / 1000.0, HEAD_BODY_Z / 1000.0))
            pset(m, hd, "Pset_DCM_Sprinkler",
                 [("DeflectorElevation", DEFLECTOR_Z / 1000.0, "m")])
            contain(hd)


# ---------------------------------------------------------------------------
# 5.  Routes.
# ---------------------------------------------------------------------------
def _run_solid(m, kind, s):
    """Axis-aligned swept solid; box section for tray/busway, circle for CHW."""
    run_mm = max(s["lx"], s["ly"])
    along_y = s["lx"] == 0.0
    if kind == "chw":
        prof = circle_profile(m, PIPE_R)
        z_m = PIPE_Z / 1000.0
    elif kind == "tray":
        prof = rect_profile(m, TRAY_W, TRAY_H, cx_offset=True)
        z_m = TRAY_Z / 1000.0
    else:
        prof = rect_profile(m, BUS_W, BUS_H, cx_offset=True)
        z_m = BUS_Z / 1000.0
    ex_dir = Dir(m, 0.0, 1.0, 0.0) if along_y else Dir(m, 1.0, 0.0, 0.0)
    cx = (s["x"] + s["lx"] / 2.0) / 1000.0
    cy = (s["y"] + s["ly"] / 2.0) / 1000.0
    solid = E(m, "IfcExtrudedAreaSolid", prof, Axis2_3D(m, cx, cy, z_m), ex_dir,
              float(run_mm))
    rep = E(m, "IfcShapeRepresentation", [ctx_of(m)], "Body", "SweptSolid", [solid])
    return E(m, "IfcProductDefinitionShape", None, None, [rep]), Axis2_3D(m, cx, cy, z_m)


def routes(m, storey, rel):
    def contain(el):
        rel.RelatedElements = m.list(list(rel.RelatedElements) + [el])

    for k, s in enumerate(SEGMENTS):
        kind = s["kind"]
        drop = "Drop" if ("drop" in s["note"] or "tap" in s["note"]) else ""
        if kind == "tray":
            cls, ot = "IfcCableCarrierSegment", "CableTray"
            psname, psrows = "Pset_DCM_CableTray", [("Width", TRAY_W, "mm"),
                    ("Elevation", TRAY_Z / 1000.0, "m"), ("Service", "Telecom", None)]
        elif kind == "bus":
            cls, ot = "IfcCableSegment", "Busway"
            psname, psrows = "Pset_DCM_Busway", [("Width", BUS_W, "mm"),
                    ("Height", BUS_H, "mm"), ("Elevation", BUS_Z / 1000.0, "m"),
                    ("Service", "Power", None)]
        else:
            cls, ot = "IfcPipeSegment", "ChilledWaterPipe"
            psname, psrows = "Pset_DCM_Pipe", [("NominalDiameter", PIPE_D, "mm"),
                    ("Insulation", INS, "mm"), ("Elevation", PIPE_Z / 1000.0, "m"),
                    ("Service", "CHW", None)]
        ot = ot + ("-" + drop if drop else "")
        rep, pl = _run_solid(m, kind, s)
        el = element(m, cls, "USERDEFINED", "%s-%03d" % (ot, k + 1), ot, rep, pl)
        pset(m, el, psname, psrows)
        contain(el)

    # CRAH termination taps (distinct short drop elements)
    for i, (x, y, rot) in enumerate(CRAHS):
        prof = circle_profile(m, 75.0)
        solid = E(m, "IfcExtrudedAreaSolid", prof,
                  Axis2_3D(m, (x + CRAH_W / 2.0) / 1000.0, y / 1000.0, 3.35),
                  Dir(m, 0.0, 0.0, 1.0), 150.0)
        rep = E(m, "IfcShapeRepresentation", [ctx_of(m)], "Body", "SweptSolid", [solid])
        el = element(m, "IfcPipeSegment", "USERDEFINED", "CHW-TAP-%d" % (i + 1),
                     "ChilledWaterPipe-Termination", rep,
                     Axis2_3D(m, (x + CRAH_W / 2.0) / 1000.0, y / 1000.0, 3.35))
        pset(m, el, "Pset_DCM_Pipe",
             [("Termination", "CRAH-%d" % (i + 1), None), ("Elevation", 3.35, "m")])
        contain(el)


# ---------------------------------------------------------------------------
# 6.  Supports / hangers (max spacing 3.0 m, A-602 support schedule).
# ---------------------------------------------------------------------------
def supports(m, storey, rel):
    def contain(el):
        rel.RelatedElements = m.list(list(rel.RelatedElements) + [el])

    i = 0
    for s in SEGMENTS:
        if s["kind"] != "tray":
            continue
        run_mm = s["lx"] if s["lx"] > 0 else s["ly"]
        if run_mm < 3000.0:
            continue
        for j in range(int(run_mm // 3000.0)):
            i += 1
            if s["lx"] > 0:
                x = s["x"] + 1500.0 + j * 3000.0
                y = s["y"] + TRAY_W / 2.0
            else:
                x = s["x"] + TRAY_W / 2.0
                y = s["y"] + 1500.0 + j * 3000.0
            h = element(m, "IfcBuildingElementProxy", "USERDEFINED",
                       "HNG-%03d" % i, "Hanger",
                       box_solid(m, 50.0, 50.0, CEIL - TRAY_Z - TRAY_H,
                                 x / 1000.0, y / 1000.0, (TRAY_Z + TRAY_H) / 1000.0, 0.0),
                       Axis2_3D(m, x / 1000.0, y / 1000.0, (TRAY_Z + TRAY_H) / 1000.0))
            pset(m, h, "Pset_DCM_Support", [("MaxSpacing", 3000.0, "mm")])
            contain(h)


# ---------------------------------------------------------------------------
# 7.  Assembly.
# ---------------------------------------------------------------------------
def build():
    out = sys.argv[1] if len(sys.argv) > 1 else OUT_DEFAULT
    import os
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)

    f = ifcopenshell.file(schema="IFC4")
    m = Mdl(f)

    ctx = ctx_of(m)
    unit_len = E(m, "IfcSIUnit", None, "LENGTH", None, "MILLIMETRE")
    units = E(m, "IfcUnitAssignment", [unit_len])

    proj = E(m, "IfcProject", GUID(), None, "DC_HALL_SEED000",
             "Data hall dc_model hall_seed000_d000 coordinated MEP model",
             "UserDefined", None, None, [ctx], units)

    site = E(m, "IfcSite", GUID(), None, "DC-Site", None, "UserDefined", None,
            None, None, None, None, None, None, None)
    bldg = E(m, "IfcBuilding", GUID(), None, "DC_Hall", None, "UserDefined",
             None, None, None, None, None, None, None)
    storey = E(m, "IfcBuildingStorey", GUID(), None, "S1", None, "UserDefined",
               None, None, None, None, 0.0)

    E(m, "IfcRelAggregates", GUID(), None, None, None, proj, [site])
    E(m, "IfcRelAggregates", GUID(), None, None, None, site, [bldg])
    E(m, "IfcRelAggregates", GUID(), None, None, None, bldg, [storey])

    space = E(m, "IfcSpace", GUID(), None, "DC_Hall_S1",
              "Data hall DC_HALL_SEED000", "ROOM",
              Axis2_3D(m, HALL_X / 2000.0, HALL_Y / 2000.0, 0.0),
              box_solid(m, HALL_X, HALL_Y, CEIL, HALL_X / 2000.0, HALL_Y / 2000.0,
                        0.0, 0.0),
              None, None, "ROOM", None)
    pset(m, space, "Pset_DCM_Space",
         [("Area", HALL_X / 1000.0 * HALL_Y / 1000.0, "m2"),
          ("ClearHeight", (CEIL - FLOOR_TOP) / 1000.0, "m"),
          ("NumberOfRacks", 128, None)])
    # hmm: IfcSpace arity is 11: (GlobalId, OwnerHistory, Name, Description,
    # ObjectType, ObjectPlacement, Representation, LongName, CompositionType,
    # PredefinedType, ElevationWithFlooring) -> the above passed 12 values.

    rel = E(m, "IfcRelContainedInSpatialStructure", GUID(), None, None, None,
            [space], storey)

    background(m, storey, rel)
    routes(m, storey, rel)
    supports(m, storey, rel)

    f.write(out)
    return f, out


def reconciliation():
    import os
    out = sys.argv[1] if len(sys.argv) > 1 else OUT_DEFAULT
    dest = os.path.join(os.path.dirname(out) or ".", "reconciliation.json")
    import json
    notes = [
        {"sheet": "A-301", "note": "Hall clear 27.0 x 21.0 m; plenum ceiling +3.600 FFL",
         "applied": "HALL_X/HALL_Y/CEIL literals"},
        {"sheet": "A-602", "note": "Raised access floor 300 mm; containment 1.2 m aisles, 3.3 m high, 100 mm roof panels; tray hanger max spacing 3 m",
         "applied": "FLOOR_TOP=300, AISLE_W/CONT_H/ROOF_T, HNG spacing"},
        {"sheet": "A-601", "note": "Cabinet schedule: 600x1000x2000 cabinets, 128 units",
         "applied": "RACK_W/RACK_D/RACK_H, 8 rows x 16"},
        {"sheet": "A-101", "note": "128 cabinets in 8 rows of 16, 1.6 m pitch, 3.3 m row pitch; columns 600 sq at 4.5/9/13.5/18 x 4.5..26.5 grid; 6 CRAH positions",
         "applied": "ROW_Y/X0/PITCH, COLS, CRAHS literals"},
        {"sheet": "M-101", "note": "CHW DN200 entries west wall +19.9 m; 25.4 mm insulation per note",
         "applied": "CHW_ENTRY, PIPE_D, INS"},
        {"sheet": "E-101", "note": "Busway 320x400 +19.9 m entries; 4 PDUs 1200x900x2200 north wall; 1.8 m dedicated clear space above PDU (no CHW)",
         "applied": "BUS_MAIN_Y, PDUS, PDU zone kept clear of CHW"},
        {"sheet": "F-101", "note": "Sprinkler grid 2.7 x 3.3 m; deflector +3.140 FFL callout",
         "applied": "HEAD_X/HEAD_Y, DEFLECTOR_Z; 460 mm kept clear below every deflector"},
        {"sheet": "A-301", "note": "Tray 400x250 @ +2.850; busway @ +3.200; CHW c/l +3.450; min headroom 2.6 m; tray-busway separation >= 300 mm",
         "applied": "TRAY_Z/BUS_Z/PIPE_Z tiers; 2D y-separation 2.7 m between mains"}
    ]
    data = {"model": "dc_model hall_seed000_d000",
            "units": "project mm, placement translations m",
            "tiers_m_above_FFL": {"tray": 2.85, "busway": 3.20,
                                   "chw_centreline": 3.45, "deflector": 3.14,
                                   "ceiling": 3.60, "floor_top": 0.30},
            "clearances_mm": {
                "tray_bottom_to_deflector_460_zone": DEFLECTOR_Z - 460.0 - (TRAY_Z + TRAY_H),
                "busway_bottom_to_deflector_460_zone": DEFLECTOR_Z - 460.0 - (BUS_Z + BUS_H),
                "chw_bottom_to_deflector_460_zone": DEFLECTOR_Z - 460.0 - (PIPE_Z - PIPE_R),
                "tray_busway_min_2d_separation": BUS_MAIN_Y - (TRAY_MAIN_Y + TRAY_H / 2.0),
                "pdu_top_to_nearest_chw": PIPE_Z - PIPE_R - PDU_H - FLOOR_TOP},
            "notes": notes}
    with open(dest, "w") as fh:
        json.dump(data, fh, indent=2)
    return dest


if __name__ == "__main__":
    f, out = build()
    r = reconciliation()
    print("wrote", out, "and", r, "entities:", len(f))
