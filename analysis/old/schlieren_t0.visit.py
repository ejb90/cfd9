"""Render the t=0 synthetic schlieren VTU as a PNG with VisIt.

Run from the repository root, or pass the run directory explicitly:

```
visit -nowin -cli -s analysis/schlieren_t0.visit.py < /dev/null
visit -nowin -cli -s analysis/schlieren_t0.visit.py build/smoke/latest analysis/schlieren_t0.png < /dev/null
```
"""

from pathlib import Path
import sys


default_run_dir = Path.cwd()
default_output = Path.cwd() / "schlieren_t0.png"

args = [arg for arg in sys.argv[1:] if not arg.startswith("-")]
run_dir = Path(args[0]).expanduser().resolve() if len(args) >= 1 else default_run_dir
output_path = Path(args[1]).expanduser().resolve() if len(args) >= 2 else default_output

if not (run_dir / "OUT_0.vtu").exists():
    raise SystemExit(f"Missing t0 VTU: {run_dir / 'OUT_0.vtu'}")

output_path.parent.mkdir(parents=True, exist_ok=True)

# The OUT_*.vtu database lets this script stay useful once later timesteps exist,
# but the requested image is the initial state.
OpenDatabase(str(run_dir / "OUT_*.vtu database"), 0)
SetTimeSliderState(0)

AddPlot("Pseudocolor", "schlieren", 1, 0)
DrawPlots()
SetActivePlots(0)

PseudocolorAtts = PseudocolorAttributes()
PseudocolorAtts.colorTableName = "xray"
PseudocolorAtts.minFlag = 0
PseudocolorAtts.maxFlag = 0
PseudocolorAtts.legendFlag = 0
try:
    PseudocolorAtts.invertColorTable = 1
except AttributeError:
    pass
SetPlotOptions(PseudocolorAtts)

AnnotationAtts = AnnotationAttributes()
try:
    AnnotationAtts.axes2D.visible = 0
except AttributeError:
    AnnotationAtts.axes2D.xAxis.title.visible = 0
    AnnotationAtts.axes2D.yAxis.title.visible = 0
    AnnotationAtts.axes2D.xAxis.label.visible = 0
    AnnotationAtts.axes2D.yAxis.label.visible = 0
AnnotationAtts.userInfoFlag = 0
AnnotationAtts.databaseInfoFlag = 0
AnnotationAtts.timeInfoFlag = 0
AnnotationAtts.legendInfoFlag = 0
AnnotationAtts.backgroundMode = AnnotationAtts.Solid
AnnotationAtts.backgroundColor = (255, 255, 255, 255)
AnnotationAtts.foregroundColor = (0, 0, 0, 255)
SetAnnotationAttributes(AnnotationAtts)

SaveWindowAtts = SaveWindowAttributes()
SaveWindowAtts.outputToCurrentDirectory = 0
SaveWindowAtts.outputDirectory = str(output_path.parent)
SaveWindowAtts.fileName = output_path.stem
SaveWindowAtts.family = 0
SaveWindowAtts.format = SaveWindowAtts.PNG
SaveWindowAtts.width = 1600
SaveWindowAtts.height = 900
SaveWindowAtts.screenCapture = 0

SetSaveWindowAttributes(SaveWindowAtts)
SaveWindow()
