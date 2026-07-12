#!/usr/bin/env python3
"""Load UCNS3D VTUs with Python VTK and report the density field."""

import glob
import math
import re
import sys

try:
    from vtkmodules.vtkIOXML import vtkXMLUnstructuredGridReader
except ImportError:
    from vtk import vtkXMLUnstructuredGridReader


def natural_key(path):
    return [int(part) if part.isdigit() else part for part in re.split(r"(\d+)", path)]


patterns = sys.argv[1:] or ["OUT_*.vtu"]
files = sorted({path for pattern in patterns for path in glob.glob(pattern)}, key=natural_key)
if not files:
    sys.exit("No VTU files matched: %s" % " ".join(patterns))

for path in files:
    reader = vtkXMLUnstructuredGridReader()
    reader.SetFileName(path)
    reader.Update()
    grid = reader.GetOutput()

    density = grid.GetCellData().GetArray("density")
    association = "cells"
    if density is None:
        density = grid.GetPointData().GetArray("density")
        association = "points"
    if density is None:
        sys.exit("%s: no density field" % path)

    density_range = density.GetRange()
    if not all(math.isfinite(value) for value in density_range) or density_range[0] > density_range[1]:
        sys.exit("%s: invalid/empty density range %r" % (path, density_range))

    print(
        "%s: %d points, %d cells; density on %s: %d values, range %.16g .. %.16g"
        % (
            path,
            grid.GetNumberOfPoints(),
            grid.GetNumberOfCells(),
            association,
            density.GetNumberOfTuples(),
            density_range[0],
            density_range[1],
        )
    )
