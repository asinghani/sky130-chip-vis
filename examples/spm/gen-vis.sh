#!/bin/sh
PDK=sky130_fd_sc_hd
GL=spm.gl.v
GDS=spm.gds
VCD=build/spm.vcd

echo "PDK = $PDK"
echo "PDK_ROOT = $PDK_ROOT"
CELLS=$PDK_ROOT/open_pdks/sky130/sky130A/libs.ref/$PDK/verilog/$PDK.v

if [ ! -f "$CELLS" ]; then
    echo "Verilog cell models not found. Ensure that PDK and PDK_ROOT are set correctly, and that a recent version of the PDK has been installed"
    exit 1
fi

# Hack to fix cells to work with yosys verilog parser
mkdir -p build
cp $CELLS build/tmp_${PDK}_cells_fixed.v
sed -i 's/wire 1/wire __1/g' build/tmp_${PDK}_cells_fixed.v

if [ ! -f "$GL" ]; then
    echo "Gate-level netlist not found."
    exit 1
fi

if [ ! -f "$GDS" ]; then
    echo "GDS file not found."
    exit 1
fi

if [ ! -f "$VCD" ]; then
    echo "VCD file not found. Please ensure the simulation was run and the results were not deleted."
    exit 1
fi

mkdir -p out
python3 ../../chip-vis.py \
                    --cell_models build/tmp_${PDK}_cells_fixed.v \
                    --gl_netlist $GL \
                    --vcd $VCD \
                    --gds $GDS \
                    --prefix "spm_tb.uut." \
                    --status_var "spm_tb.status" \
                    --rst "spm_tb.uut.rst" \
                    --clk "spm_tb.uut.clk" \
                    --start_status "Calc" \
                    --outfile "out/spm_vis.gif" \
                    --mode 0,1,2,3,4,5 \
                    --scale 3 \
                    --fps 8 \
                    --downscale 1.2 \
                    --blur 7 \
                    --exp_grow 1.2 \
                    --exp_decay 0.8 \
                    --lin_grow 0.15 \
                    --lin_decay 0.15 \
                    --build_dir build


# Options: (note that cells update after each rising edge of the clock)
#     Mode 0: Highlights cells with output high on each clock cycle
#     Mode 1: Highlights cells with output high on each clock cycle (excluding always-high outputs)
#     Mode 2: Highlights cells whose output changed on each clock cycle
#     Mode 3: Highlights cells with brightness exponentially based on time since output changed
#     Mode 4: Highlights each cell with a brightness exponentially based on the number of output-changes in past cycles
#     Mode 5: Highlights each cell with a brightness linearly based on the number of output-changes in past cycles
#     Option 2 or 3 (with default exp_decay) is optimal for most designs. 

