"""Vorticity pseudocolour plot for qualitative comparison.

```
module load visit
visit -nowin -cli -s vorticity.visit.py < /dev/null
```
"""

from pathlib import Path
import sys
dname = ""
slider_state = 75
bbox = -0.02, 0.08, 0.0, 0.10       # Could probably figure this out from the upstream/downstream/jet positions vs time.

dname = Path(dname).resolve()
OpenDatabase(str(dname / "OUT_*.vtu database"), 0)
SetTimeSliderState(slider_state)

# 2D out-of-plane vorticity:
# omega_z = dv/dx - du/dy
DefineScalarExpression(
    "vorticity",
    "gradient(v)[0] - gradient(u)[1]"
)
AddPlot("Pseudocolor", "vorticity")
DrawPlots()
SetTimeSliderState(slider_state)
SetActivePlots(0)

PseudocolorAtts = PseudocolorAttributes()
PseudocolorAtts.colorTableName = "difference"
PseudocolorAtts.minFlag = 1
PseudocolorAtts.maxFlag = 1
PseudocolorAtts.min = -4.5e4
PseudocolorAtts.max = 4.5e4
SetPlotOptions(PseudocolorAtts)

AddPlot("Contour", "vorticity", 1, 1)
DrawPlots()
ContourAtts = ContourAttributes()
ContourAtts.defaultPalette.smoothing = ContourAtts.defaultPalette.NONE  # NONE, Linear, CubicSpline
ContourAtts.defaultPalette.equalSpacingFlag = 1
ContourAtts.defaultPalette.discreteFlag = 1
ContourAtts.defaultPalette.tagNames = ("Default", "Discrete")
ContourAtts.changedColors = ()
ContourAtts.colorType = ContourAtts.ColorBySingleColor  # ColorBySingleColor, ColorByMultipleColors, ColorByColorTable
ContourAtts.colorTableName = "Default"
ContourAtts.legendFlag = 0
ContourAtts.lineWidth = 0
ContourAtts.singleColor = (0, 0, 0, 255)
ContourAtts.contourMethod = ContourAtts.Level  # Level, Value, Percent
ContourAtts.contourNLevels = 10
ContourAtts.minFlag = 0
ContourAtts.maxFlag = 0
ContourAtts.min = -4.5e4
ContourAtts.max = 4.5e4
ContourAtts.scaling = ContourAtts.Linear  # Linear, Log
ContourAtts.wireframe = 0
SetPlotOptions(ContourAtts)

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
legend.customTitle = "Voricity / "
legend.drawMinMax = 0
legend.managePosition = 0
legend.position = (0.05, 0.65)

SaveWindowAtts = SaveWindowAttributes()
SaveWindowAtts.outputToCurrentDirectory = 1
SaveWindowAtts.outputDirectory = "."
SaveWindowAtts.fileName = f"{dname.name}_vorticity_{slider_state}"
SaveWindowAtts.family = 0
SaveWindowAtts.format = SaveWindowAtts.PNG
SaveWindowAtts.width = 1024
SaveWindowAtts.height = 1024
SaveWindowAtts.screenCapture = 0

SetSaveWindowAttributes(SaveWindowAtts)
SaveWindow()
