#!/bin/sh
PDK=sky130_fd_sc_hd
GL_NETLIST=spm.gl.v
TB=spm_tb.v
VCD=spm.vcd

echo "PDK = $PDK"
echo "PDK_ROOT = $PDK_ROOT"

PRIMITIVES=$PDK_ROOT/open_pdks/sky130/sky130A/libs.ref/$PDK/verilog/primitives.v
CELLS=$PDK_ROOT/open_pdks/sky130/sky130A/libs.ref/$PDK/verilog/$PDK.v

if [ ! -f "$PRIMITIVES" ]; then
    echo "Verilog cell models not found. Ensure that PDK and PDK_ROOT are set correctly, and that a recent version of the PDK has been installed"
    exit 1
fi

if [ ! -f "$CELLS" ]; then
    echo "Verilog cell models not found. Ensure that PDK and PDK_ROOT are set correctly, and that a recent version of the PDK has been installed"
    exit 1
fi

mkdir -p build
echo "Compiling..." && iverilog -o build/sim -g2012 -DFUNCTIONAL -DSIM -DGL -DUNIT_DELAY="#1" -DUSE_POWER_PINS -I . $PRIMITIVES $CELLS $GL_NETLIST $TB && echo "Running sim..." && ./build/sim && mv $VCD build/$VCD
