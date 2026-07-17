"""VisIt 3.4 CLI regression test for UCNS3D type-5 VTU output."""

import os
import math
import sys


def fail(message):
    print("VTU_VISIT_TEST_FAILED: %s" % message)
    raise RuntimeError(message)


output_dir = os.environ.get("VISIT_VTU_DIR")
variable = os.environ.get("VISIT_VTU_VARIABLE", "density")
if not output_dir:
    fail("VISIT_VTU_DIR is not set")

database = os.path.join(output_dir, "OUT_*.vtu database")
print("Testing %s with VisIt %s" % (database, Version()))

if not OpenDatabase(database, 0, "VTK"):
    fail("OpenDatabase returned false")

nstates = TimeSliderGetNStates()
if nstates < 2:
    fail("expected at least two time states, found %d" % nstates)

if not AddPlot("Pseudocolor", variable):
    fail("could not add Pseudocolor plot for %s" % variable)
if not DrawPlots():
    fail("DrawPlots returned false")

save = SaveWindowAttributes()
save.outputToCurrentDirectory = 0
save.outputDirectory = output_dir
save.family = 0
save.format = save.PNG
save.width = 800
save.height = 600
SetSaveWindowAttributes(save)

for state, label in ((0, "first"), (nstates - 1, "last")):
    SetTimeSliderState(state)
    if not DrawPlots():
        fail("DrawPlots failed for state %d" % state)
    Query("MinMax")
    density_range = GetQueryOutputValue()
    if len(density_range) < 2:
        fail("MinMax query returned no range for state %d" % state)
    density_range = (float(density_range[0]), float(density_range[1]))
    if not all(math.isfinite(value) for value in density_range) or density_range[0] > density_range[1]:
        fail("invalid/empty density range %r for state %d" % (density_range, state))
    save.fileName = "visit_vtu_%s" % label
    SetSaveWindowAttributes(save)
    result = SaveWindow()
    if not result:
        fail("SaveWindow failed for state %d" % state)

DeleteAllPlots()
CloseDatabase(database)
print("VTU_VISIT_TEST_PASSED: %d states; rendered first and last" % nstates)
