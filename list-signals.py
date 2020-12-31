#!/usr/bin/env python3
from vcdvcd import VCDVCD
import os
import sys

if len(sys.argv) < 2:
    print(f"Usage: {sys.argv[1]} <path to vcd file>")
    sys.exit(1)

vcd = VCDVCD(sys.argv[1])
for x in vcd.signals:
    print(x)
