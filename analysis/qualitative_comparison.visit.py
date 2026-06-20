"""Generic pseudocolour plot for qualitative comparison.

```
module load visit
visit -nowin -cli -s qualitative_comparison.visit.py < /dev/null
magick finex2.png -trim +repage -gravity center -extent 105%x105% test.png
```
"""

from pathlib import Path
import sys


# dname = "/home/ellis/Documents/cfd_msc/08_dissertation/provided/ELLIS-ucns3d/RUN_EXAMPLES/2D/finex2/"
dname = ""
# slider_state = int(
#     sys.argv[-3]
# )  # This is probably inconsistent between runs but just use it to find closest time.
slider_state = 75                   # This is probably inconsistent between runs but just use it to find closest time.
# bbox = (
#     float(sys.argv[-2]),
#     float(sys.argv[-1]),
#     0.0,
#     0.10,
# )  # Could probably figure this out from the upstream/downstream/jet positions vs time.
# bbox = -0.05, 0.05, 0.0, 0.10       # Could probably figure this out from the upstream/downstream/jet positions vs time.
bbox = -0.02, 0.08, 0.0, 0.10       # Could probably figure this out from the upstream/downstream/jet positions vs time.

maxdens = 2.0           # He
# maxdens = 4.6  # Kr

dname = Path(dname).resolve()
OpenDatabase(str(dname / "OUT_*.vtu database"), 0)
# OpenDatabase(str(dname / "PAR_*.pvtu database"), 0)
AddPlot("Pseudocolor", "density", 1, 0)
AddPlot("Pseudocolor", "volume_fraction", 1, 0)
DrawPlots()
SetTimeSliderState(slider_state)

SetActivePlots((0, 1))
SetActivePlots(0)

PseudocolorAtts = PseudocolorAttributes()
PseudocolorAtts.colorTableName = "hot_desaturated"
PseudocolorAtts.minFlag = 1
PseudocolorAtts.maxFlag = 1
PseudocolorAtts.min = 0.12
PseudocolorAtts.max = maxdens
SetPlotOptions(PseudocolorAtts)

SetActivePlots((0, 1))
SetActivePlots(1)
PseudocolorAtts = PseudocolorAttributes()
PseudocolorAtts.minFlag = 1
PseudocolorAtts.maxFlag = 1
PseudocolorAtts.min = 0
PseudocolorAtts.max = 1
PseudocolorAtts.colorTableName = "RdBu"
SetPlotOptions(PseudocolorAtts)

SetActivePlots((0, 1))
SetActivePlots(0)
AddOperator("Clip", 0)
ClipAtts = ClipAttributes()
ClipAtts.funcType = ClipAtts.Plane
ClipAtts.plane1Status = 1
ClipAtts.plane1Origin = (0, 0.05, 0)
ClipAtts.plane1Normal = (0, -1, 0)
ClipAtts.planeToolControlledClipPlane = ClipAtts.Plane1
SetOperatorOptions(ClipAtts, -1, 0)
SetActivePlots((0, 1))
SetActivePlots(1)

AddOperator("Clip", 0)
ClipAtts = ClipAttributes()
ClipAtts.funcType = ClipAtts.Plane
ClipAtts.plane1Status = 1
ClipAtts.plane1Origin = (0, 0.05, 0)
ClipAtts.plane1Normal = (0, 1, 0)
ClipAtts.planeInverse = 0
ClipAtts.planeToolControlledClipPlane = ClipAtts.Plane1
SetOperatorOptions(ClipAtts, -1, 0)
DrawPlots()

View2DAtts = View2DAttributes()
View2DAtts.windowCoords = bbox
View2DAtts.viewportCoords = (0.3, 0.95, 0.15, 0.95)
SetView2D(View2DAtts)

AnnotationAtts = AnnotationAttributes()
AnnotationAtts.axes2D.xAxis.title.visible = 0
AnnotationAtts.axes2D.yAxis.title.visible = 0
AnnotationAtts.userInfoFlag = 0
AnnotationAtts.databaseInfoFlag = 0
AnnotationAtts.timeInfoFlag = 0
AnnotationAtts.legendInfoFlag = 1
SetAnnotationAttributes(AnnotationAtts)

plotName = GetPlotList().GetPlots(0).plotName
legend = GetAnnotationObject(plotName)
legend.drawTitle = 1
legend.useCustomTitle = 1
legend.customTitle = "Density / kg/m^3"
legend.drawMinMax = 0
legend.managePosition = 0
legend.position = (0.05, 0.85)

plotName = GetPlotList().GetPlots(1).plotName
legend = GetAnnotationObject(plotName)
legend.drawTitle = 1
legend.useCustomTitle = 1
legend.customTitle = "Volume Fraction /"
legend.drawMinMax = 0
legend.managePosition = 0
legend.position = (0.05, 0.45)

SaveWindowAtts = SaveWindowAttributes()
SaveWindowAtts.outputToCurrentDirectory = 1
SaveWindowAtts.outputDirectory = "."
SaveWindowAtts.fileName = f"{dname.name}_density_volfrac_{slider_state}"
SaveWindowAtts.family = 0
SaveWindowAtts.format = SaveWindowAtts.PNG
SaveWindowAtts.width = 1024
SaveWindowAtts.height = 1024
SaveWindowAtts.screenCapture = 0

SetSaveWindowAttributes(SaveWindowAtts)
SaveWindow()
