#!/usr/bin/env python3
import json
import gdspy
import numpy as np
import cv2
import imageio
from vcdvcd import VCDVCD
from tqdm import tqdm
import string
import os
import sys
from time import sleep
import copy
import argparse

parser = argparse.ArgumentParser(formatter_class=argparse.RawTextHelpFormatter)

parser.add_argument("--cell_models", help="Path to verilog models of SKY130 standard cells",
                    action="store", required=True)

parser.add_argument("--gl_netlist", help="Path to gate-level netlist used for simulation",
                    action="store", required=True)

parser.add_argument("--vcd", help="Path to VCD file from simulation (see docs for format)",
                    action="store", required=True)

parser.add_argument("--gds", help="Path to post-layout GDS of the chip/block to visualize",
                    action="store", required=True)

parser.add_argument("--outfile", help="Filename for the output GIF (default: vis.gif)",
                    action="store", default="vis.gif")

parser.add_argument("--mode", help="Comma-separated list of modes to visualize (default: 0,1,2,3,4,5)",
                    action="store", default="0,1,2,3,4,5")

parser.add_argument("--prefix", help="Signal-name prefix in VCD, including trailing dot (should be <tb name>.<uut name>.)",
                    action="store", required=True)

parser.add_argument("--status_var", help="Signal which is the status-string to show under each frame (should be <tb name>.status)",
                    action="store", required=True)

parser.add_argument("--rst", help="Reset signal (inside the uut)",
                    action="store", required=True)

parser.add_argument("--clk", help="Clock signal (inside the uut)",
                    action="store", required=True)

parser.add_argument("--start_status", help="Status string to wait for before starting visualization (optional)",
                    action="store", default="")

parser.add_argument("--ignore_ports", help="Comma-separated list of ports in standard cells to ignore (default: VPWR,VGND,VPB,VNB - should not need to be changed)",
                    action="store", default="VPWR,VGND,VPB,VNB")

parser.add_argument("--scale", help="Integer factor to scale cells by when making frames (default: 3)",
                    action="store", type=int, default=3)

parser.add_argument("--fps", help="Frames per second for the resulting gif (one frame = one clock cycle, default: 8)",
                    action="store", type=int, default=8)

parser.add_argument("--downscale", help="Factor to downscale the final frames (default: 1.0)",
                    action="store", type=float, default=1.0)

parser.add_argument("--blur", help="Integer factor to blur the frames by (improves look-and-feel of output, default: 7)",
                    action="store", type=int, default=7)

parser.add_argument("--font_thickness", help="Font thickness for status text in frames (default: 2.2)",
                    action="store", type=float, default=2.2)

parser.add_argument("--exp_grow", help="Exponential growth factor for mode 4 (default: 1.2)",
                    action="store", type=float, default=1.2)

parser.add_argument("--exp_decay", help="Exponential decay factor for modes 3 and 4 (default: 0.8)",
                    action="store", type=float, default=0.8)

parser.add_argument("--lin_grow", help="Linear growth factor for mode 5 (default: 0.15)",
                    action="store", type=float, default=0.15)

parser.add_argument("--lin_decay", help="Linear decay factor for mode 5 (default: 0.15)",
                    action="store", type=float, default=0.15)

parser.add_argument("--filler_prefixes", help="Comma-separated list of prefixes for filler-cells to ignore in visualization (default: FILLER_)",
                    action="store", default="FILLER_")

parser.add_argument("--phy_prefixes", help="Comma-separated list of prefixes for physical cells to ignore in visualization (default: clkbuf_,PHY_,ANTENNA_)",
                    action="store", default="clkbuf_,PHY_,ANTENNA_")

parser.add_argument("--build_dir", help="Directory to store temporary build products in (defaults to current directory)",
                    action="store", default="")

if len(sys.argv) < 2:
    parser.print_help()
    sys.exit(1)

args = parser.parse_args()

CELL_MODELS = args.cell_models
GL_NETLIST = args.gl_netlist
VCD_FILE = args.vcd
GDS_FILE = args.gds

OUTFILE = args.outfile
MODE = args.mode

PREFIX = args.prefix
LABEL = args.status_var
RST = args.rst
CLK = args.clk

START_LABEL = args.start_status

IGNORE_PORTS = args.ignore_ports

SCALE = int(args.scale)
FPS = int(args.fps)
POSTSCALE = float(args.downscale)

BLUR = int(args.blur)

FONT_THICKNESS = float(args.font_thickness)

EXP_GROW = float(args.exp_grow)
EXP_DECAY = float(args.exp_decay)

LIN_GROW = float(args.lin_grow)
LIN_DECAY = float(args.lin_decay)

FILLER_PREFIXES = args.filler_prefixes
PHY_PREFIXES = args.phy_prefixes

BUILD_DIR = args.build_dir

###########################################
# Verify config
###########################################

EXP_GROW = abs(EXP_GROW)
EXP_DECAY = abs(EXP_DECAY)
LIN_GROW = abs(LIN_GROW)
LIN_DECAY = abs(LIN_DECAY)

C_MODE_DIRECT = 0
C_MODE_DIRECT_FILTER = 1
C_MODE_CHANGED = 2
C_MODE_EXP_TIME = 3
C_MODE_EXP_HEATMAP = 4
C_MODE_LIN_HEATMAP = 5
ALL_MODES = [C_MODE_DIRECT, C_MODE_DIRECT_FILTER, C_MODE_CHANGED,
             C_MODE_EXP_TIME, C_MODE_EXP_HEATMAP, C_MODE_LIN_HEATMAP]

MODES = [int(x.strip()) for x in MODE.split(",")]
assert set(MODES) - set(ALL_MODES) == set()
MODES = sorted(list(set(MODES)))

OUTFILE_PREFIX, EXT = os.path.splitext(OUTFILE)

if not EXT.lower() == ".gif":
    print("Output filename must end with .gif extension")
    sys.exit(1)

assert len(MODES) > 0

MULTI_OUT = len(MODES) > 1

FILLER_PREFIXES = [x.strip() for x in FILLER_PREFIXES.split(",")]
PHY_PREFIXES = [x.strip() for x in PHY_PREFIXES.split(",")]

assert SCALE > 1
assert FPS > 0
assert POSTSCALE > 0.0

if BLUR < 3:
    BLUR = 3

if BLUR % 2 == 0:
    BLUR += 1

IGNORE_PORTS = [x.strip() for x in IGNORE_PORTS.split(",")]

###########################################
# Parse netlist
###########################################

print("Parsing netlist using yosys (slow)...")

# TODO this line may need to be changed if on windows
design_json = os.path.join(BUILD_DIR, "design.json")
yosys_log = os.path.join(BUILD_DIR, "yosys.log")
os.system(f'yosys -p "read_verilog -sv {CELL_MODELS} {GL_NETLIST} ; write_json {design_json};" > {yosys_log}')

print("Reading design")
with open(design_json) as f:
    design = json.load(f)

print(f"Version: {design['creator']}")

modules = design["modules"]
modules_sky130 = {k: v for k, v in modules.items() if k.startswith("sky130_")}
modules_design = {k: v for k, v in modules.items() if not k.startswith("sky130_")}

print(f"Design modules: {list(modules_design.keys())}")
assert len(modules_design.keys()) == 1
DESIGN_NAME = list(modules_design.keys())[0]
top = modules_design[DESIGN_NAME]

top_ports = {}
for name, data in top["ports"].items():
    if name in IGNORE_PORTS:
        continue

    for i, bit in enumerate(data["bits"]):
        top_ports[f"{name}"] = (data["direction"], bit)

print()
if len(top_ports) > 20:
    print(f"Top ports: {str(sorted(top_ports.keys())[:20])[:-1]}, ...")
else:
    print(f"Top ports: {str(sorted(top_ports.keys()))}")

print()

top_nets = {}
for name, data in top["netnames"].items():
    if name in IGNORE_PORTS:
        continue

    for i, bit in enumerate(data["bits"]):
        top_nets[f"{name}"] = bit

if len(top_nets) > 20:
    print(f"Top nets: {str(sorted(top_nets.keys())[:20])[:-1]}, ...")
else:
    print(f"Top nets: {str(sorted(top_nets.keys()))}")

print()

def startswithany(string, prefixes):
    return any(string.startswith(x) for x in prefixes)

phy_cells = {}
real_cells = {}

for name, data in top["cells"].items():
    if startswithany(name, FILLER_PREFIXES + PHY_PREFIXES):
        assert len(data["port_directions"]) == len(data["connections"])
        #assert name.startswith("clkbuf_") or name.startswith("ANTENNA_") or len(set(data["connections"].keys()) - set(IGNORE_PORTS)) == 0
        phy_cells[name] = data["type"]

    else:
        inputs = []
        outputs = []

        assert set(data["connections"].keys()) == set(data["port_directions"].keys())

        for pin, net in data["connections"].items():
            if pin in IGNORE_PORTS:
                continue

            assert len(net) == 1
            assert data["port_directions"][pin] in ["input", "output"]

            if data["port_directions"][pin] == "input":
                inputs.append((pin, net[0]))
            else:
                outputs.append((pin, net[0]))


        real_cells[name] = (data["type"], inputs, outputs)

print(f"Phys cell types: {set(phy_cells.values())}")
print()
print(f"Real cell types: {set(x[0] for x in real_cells.values())}")
print()

print("Matching nets to cells...")
top_nets_inv = {}

for k, v in top_nets.items():
    if v not in top_nets_inv:
        top_nets_inv[v] = []
    top_nets_inv[v].append(k)

cell_to_output_nets = {}

for name, (cell_name, inputs, outputs) in real_cells.items():
    out_net_nums = [x[1] for x in outputs]
    cell_to_output_nets[name] = sum((top_nets_inv.get(x, []) for x in out_net_nums), [])

output_nets = set().union(*cell_to_output_nets.values())

cell_to_output_nets_inv = {}

for k, vv in cell_to_output_nets.items():
    for v in vv:
        if v not in cell_to_output_nets_inv:
            cell_to_output_nets_inv[v] = []
        cell_to_output_nets_inv[v].append(k)

assert all(len(cell_to_output_nets_inv[net]) == 1 for net in output_nets)
output_net_to_cell = {net: cell_to_output_nets_inv[net][0] for net in output_nets}

###########################################
# Parse VCD
###########################################

def int4(x):
    return {"0": 0, "1": 1, "x": 0, "z": 0}[x.lower()]

print("Loading VCD (slow)...")
vcd = VCDVCD(VCD_FILE)
print("VCD loaded")

assert all(x.startswith(PREFIX) or x.startswith(LABEL) for x in vcd.signals)
label_signal = [x for x in vcd.signals if x.startswith(LABEL)]
assert len(label_signal) == 1
label_signal = label_signal[0]

signals = [x[len(PREFIX):] for x in vcd.signals]
signals_name_map = {x.replace("\\", ""): x for x in signals}
signals_keep = list(signals_name_map.keys())

print("Searching for reset")
if len(RST) < 1:
    start_time = 0
else:
    start_time, start_rst = vcd[RST].tv[-1]
    assert start_rst == "0"

print(f"Start time = {start_time}")

print("Extracting clock-edge signals from VCD")
clk_ticks = []
last = -1
for time, val in vcd[CLK].tv:
    val = int(val)

    if time < start_time:
        continue

    if val == 1:
        if last != -1:
            clk_ticks.append((last, time))
        last = time

signals_of_interest = list(set(signals_keep).intersection(output_nets))
print(f"Found {len(signals_of_interest)} matching nets out of {len(signals_keep)} internal signals / {len(output_nets)} total nets")
print(f"{len(output_nets) - len(signals_of_interest)} unmatched nets (unless this number is large, it should be ignorable)")

values_over_time = []

print()
print("Statuses:")
last = ""
for start, end in clk_ticks:
    dat = {}
    for signal in signals_of_interest:
        dat[signal] = int4(vcd[PREFIX+signals_name_map[signal]][end-1])

    x = vcd[label_signal][end-1]
    x = hex(int(x, 2))[2:]
    if x == "0":
        x = "00"
    dat["M_LABEL"] = "".join(a if a in string.printable else " " for a in bytes.fromhex(x).decode())

    if dat["M_LABEL"] != last:
        last = dat["M_LABEL"]
        print("  " + dat["M_LABEL"])

    values_over_time.append(dat)

print()
print()
print(f"Number of clock cycles after reset: {len(values_over_time)}")
first_ind = [i for i, x in enumerate(values_over_time) if START_LABEL in x["M_LABEL"]]
if len(first_ind) == 0:
    print("ERROR: STATUS VARIABLE NEVER MATCHES EXPECTED STARTING STATUS")
    assert len(first_ind) > 0
first_ind = first_ind[0]

values_over_time = values_over_time[first_ind:]
print(f"Number of clock cycles after start-label: {len(values_over_time)}")
print()

###########################################
# Parse GDS
###########################################

print("Reading GDS (slow)...")
gds = gdspy.GdsLibrary(infile=GDS_FILE)
top_cell = gds.top_level()[0]
print("Parsed GDS")

bbox = list(top_cell.get_bounding_box().flatten())
print(f"Top-cell bounding box = {bbox}")
assert set().union(*[x.properties.keys() for x in top_cell.references]) == {98}

cells = [(x.properties[98], x.ref_cell.name, list(x.get_bounding_box().flatten())) for x in top_cell.references]

filler_cells = [(name, cell_type, bbox) for name, cell_type, bbox in cells if startswithany(name, FILLER_PREFIXES)]
phy_cells = [(name, cell_type, bbox) for name, cell_type, bbox in cells if startswithany(name, PHY_PREFIXES)]
real_cells = [(name, cell_type, bbox) for name, cell_type, bbox in cells if not startswithany(name, FILLER_PREFIXES+PHY_PREFIXES)]

print(f"Filler cells ({len(filler_cells)}) types: {set(x[1] for x in filler_cells)}")
print()
print(f"Phy cells ({len(phy_cells)}) types: {set(x[1] for x in phy_cells)}")
print()
print(f"Real cells ({len(real_cells)}) types: {set(x[1] for x in real_cells)}")
print()

###########################################
# Prepare for Drawing Frames
###########################################

assert bbox[0] == 0
assert bbox[1] == 0
WIDTH = bbox[2]
HEIGHT = bbox[3]

FONT = cv2.FONT_HERSHEY_SIMPLEX
font_thickness = 4

def interpolate_colors(c1, c2, percentage):
    return (c1[0] + (c2[0] - c1[0]) * percentage,
            c1[1] + (c2[1] - c1[1]) * percentage,
            c1[2] + (c2[2] - c1[2]) * percentage)


top_x0 = min(x0 for name, cell_type, (x0, y0, x1, y1) in real_cells + filler_cells + phy_cells)
top_x1 = max(x1 for name, cell_type, (x0, y0, x1, y1) in real_cells + filler_cells + phy_cells)
top_y0 = min(y0 for name, cell_type, (x0, y0, x1, y1) in real_cells + filler_cells + phy_cells)
top_y1 = max(y1 for name, cell_type, (x0, y0, x1, y1) in real_cells + filler_cells + phy_cells)

warn = set()
def draw_frame(frame_data, brightness=False, blur=7, postscale=POSTSCALE, textscale_=None, textheight_=None):
    global textscale, textheight
    if textscale_ is None:
        textscale_ = textscale

    if textheight_ is None:
        textheight_ = textheight

    assert set().union(*[cell_to_output_nets[a[0]] for a in real_cells]) >= set(frame_data.keys() - {"M_LABEL"})

    width_scaled = int(SCALE * WIDTH + 1)
    height_scaled = int(SCALE * HEIGHT + 1)

    img = np.zeros((width_scaled, height_scaled, 3), dtype=np.uint8)

    extra_cells = [(filler_cells, (0x17, 0x3f, 0x5f)),
                   (phy_cells, (0x17, 0x3f, 0x5f))]

    on_color = (0xed, 0x55, 0x3b)
    off_color = (0x40, 0x40, 0x40)

    img[int(SCALE * top_x0):int(SCALE * top_x1), int(SCALE * top_y0):int(SCALE * top_y1)] = (0xd, 0x14, 0x18)

    for name, cell_type, (x0, y0, x1, y1) in real_cells:
        x0, y0, x1, y1 = int(SCALE * x0), int(SCALE * y0), int(SCALE * x1), int(SCALE * y1)
        assert x0 >= 0 and x1 < img.shape[0]
        assert y0 >= 0 and y1 < img.shape[1]

        out = cell_to_output_nets[name]
        if len(out) == 0:
            out = 0
        elif out[0] not in frame_data:
            warn.add(out[0])
            out = 0
        else:
            out = frame_data[out[0]]
            #if not out: continue

        if brightness:
            c = interpolate_colors(off_color, on_color, out)
        else:
            c = on_color if out else off_color

        img[x0:x1, y0:y1] = c

    blur_kernel = np.ones((blur, blur), np.float32) / (blur*blur)
    zeros = (img == (0, 0, 0))
    img = cv2.GaussianBlur(img, (blur, blur), 0)
    img[zeros] = 0

    img = cv2.resize(img, None, fx=postscale, fy=postscale)
    img_padded = np.zeros((img.shape[0] + int(1.3*textheight_), img.shape[1], img.shape[2]), dtype=img.dtype)
    img_padded[:img.shape[0], :, :] = img
    img_padded[img.shape[0]:, :, :] = img[-1, -1, :]

    tmp = np.mean(img_padded, axis=2)
    first_nonzero = tmp.any(1).argmax() + 4
    last_nonzero = (~tmp[first_nonzero:].any(1)).argmax() + first_nonzero

    lab = frame_data["M_LABEL"]
    if len(lab) < 2:
        lab = lab + " "
    cv2.putText(img_padded, lab, (10, last_nonzero + textheight_), FONT,
                textscale_, (255, 255, 255), font_thickness, cv2.LINE_AA) 

    return img_padded

# Calculate font size
textscale = 1.0
textheight = 50

img_width = draw_frame(values_over_time[0]).shape[1]
print(f"Image width: {img_width}")

texts = set([x["M_LABEL"] for x in values_over_time] + ["------------"])
text_width_desired = img_width - 20

# TODO this could be cleaner
print("Calculating text scale")
tw = max(cv2.getTextSize(x, FONT, textscale, font_thickness)[0][0] for x in texts)
while tw > text_width_desired or (text_width_desired - tw) > 8:
    textscale -= 0.0001 * (tw - text_width_desired)
    font_thickness = int(FONT_THICKNESS * textscale)

    tw = max(cv2.getTextSize(x, FONT, textscale, font_thickness)[0][0] for x in texts)
textheight = max(h+b for (w, h), b in [cv2.getTextSize(x, FONT, textscale, font_thickness) for x in texts])

print(f"Text scale: {'{:.2f}'.format(textscale)}")
print(f"Max text height: {textheight}")

###########################################
# Process Signals
###########################################

print("Filtering signals...")
no_change = set([x for x in values_over_time[0].keys() if all(a[x] for a in values_over_time)])
mode_0_data = values_over_time[:]
mode_1_data = [{k: 0 if (k in no_change and k != "M_LABEL") else v for k, v in x.items()} for x in values_over_time]

print("Finding edges in signals...")
last = values_over_time[0]
mode_2_data = [{x: 0 if x != "M_LABEL" else last[x] for x in last.keys()}]
mode_3_data = [{x: 0 if x != "M_LABEL" else last[x] for x in last.keys()}]
mode_4_data = [{x: 0.0 if x != "M_LABEL" else last[x] for x in last.keys()}]
mode_5_data = [{x: 0.0 if x != "M_LABEL" else last[x] for x in last.keys()}]

for i, x in list(enumerate(values_over_time[1:])):
    changed = {}
    for k, v in x.items():
        if k == "M_LABEL":
            changed[k] = v
        else:
            changed[k] = (v != last[k])
    last = x

    mode_3_brightness = copy.deepcopy(mode_3_data[-1])
    for k in mode_3_brightness:
        if k == "M_LABEL":
            mode_3_brightness[k] = changed[k]
        elif changed[k]:
            mode_3_brightness[k] = 1.0
        else:
            mode_3_brightness[k] = mode_3_brightness[k] * EXP_DECAY

    mode_4_brightness = copy.deepcopy(mode_4_data[-1])
    for k in mode_4_brightness:
        if k == "M_LABEL":
            mode_4_brightness[k] = changed[k]
        elif changed[k]:
            mode_4_brightness[k] = min((mode_4_brightness[k] + 0.5) * EXP_GROW, 1.5) - 0.5
        else:
            mode_4_brightness[k] = max((mode_4_brightness[k] + 0.5) * EXP_DECAY, 0.5) - 0.5

    mode_5_brightness = copy.deepcopy(mode_5_data[-1])
    for k in mode_5_brightness:
        if k == "M_LABEL":
            mode_5_brightness[k] = changed[k]
        elif changed[k]:
            mode_5_brightness[k] = min((mode_5_brightness[k] + 0.5) + LIN_GROW, 1.5) - 0.5
        else:
            mode_5_brightness[k] = max((mode_5_brightness[k] + 0.5) - LIN_DECAY, 0.5) - 0.5

    assert changed.keys() == x.keys()

    mode_2_data.append(changed)
    mode_3_data.append(mode_3_brightness)
    mode_4_data.append(mode_4_brightness)
    mode_5_data.append(mode_5_brightness)

###########################################
# Draw frames
###########################################

warn = set()

for mode in MODES:
    frames = []
    print(f"Generating frames for mode {mode} (very slow)...")
    sleep(0.4)

    br = mode in [C_MODE_EXP_TIME, C_MODE_EXP_HEATMAP, C_MODE_LIN_HEATMAP]
    dat = {
        C_MODE_DIRECT: mode_0_data,
        C_MODE_DIRECT_FILTER: mode_1_data,
        C_MODE_CHANGED: mode_2_data,
        C_MODE_EXP_TIME: mode_3_data,
        C_MODE_EXP_HEATMAP: mode_4_data,
        C_MODE_LIN_HEATMAP: mode_5_data
    }[mode]

    for c in tqdm(dat):
        frames.append(draw_frame(c, brightness=br, blur=BLUR))

    print(f"Writing GIF for mode {mode}...")
    filename = OUTFILE_PREFIX + "_" + str(mode) + ".gif" if MULTI_OUT else OUTFILE
    imageio.mimsave(filename, frames, fps=FPS)
    print(f"Done with mode {mode}")

