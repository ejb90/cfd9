"""Render a monochrome post-processed artificial schlieren image with VisIt.

The plotted scalar is the density-gradient magnitude::

    schlieren = magnitude(gradient(<density>))

Usage::

    /usr/local/visit/bin/visit -nowin -cli \
      -s analysis/postprocessed_schlieren.visit.py \
      /path/to/run output.png -1 < /dev/null

Arguments are the run directory, output PNG, and time-state index. The state
defaults to -1 (the final available PVTU state).

Older UCNS3D PVTU files sometimes refer to lower-case ``out_*.vtu`` pieces
even though the files on disk are upper-case ``OUT_*.vtu``. This script writes
a corrected temporary PVTU for the selected state; it does not alter the run.
"""

from pathlib import Path
import re
import sys
import tempfile


DEFAULT_RUN = Path(
    "/home/ellis/Documents/cfd_msc/08_dissertation/"
    "runs/mesh_convergence/try8/4xfine2"
)
DEFAULT_OUTPUT = Path.cwd() / "artificial_schlieren_4xfine2.png"


def numeric_suffix(path):
    """Return the integer output number in PAR_<number>.pvtu."""
    match = re.search(r"PAR_(\d+)\.pvtu$", path.name, re.IGNORECASE)
    return int(match.group(1)) if match else -1


args = [arg for arg in sys.argv[1:] if not arg.startswith("-")]
run_dir = Path(args[0]).expanduser().resolve() if args else DEFAULT_RUN
output_path = Path(args[1]).expanduser().resolve() if len(args) > 1 else DEFAULT_OUTPUT
state = int(args[2]) if len(args) > 2 else -1

pvtu_files = sorted(run_dir.glob("PAR_*.pvtu"), key=numeric_suffix)
if not pvtu_files:
    raise SystemExit("No PAR_*.pvtu files found in {}".format(run_dir))

if state < 0:
    state += len(pvtu_files)
if state < 0 or state >= len(pvtu_files):
    raise SystemExit("State {} is outside 0..{}".format(state, len(pvtu_files) - 1))

selected = pvtu_files[state]
output_path.parent.mkdir(parents=True, exist_ok=True)

with tempfile.TemporaryDirectory(prefix="visit-schlieren-") as temporary:
    corrected = Path(temporary) / selected.name
    pvtu_text = selected.read_text()

    def absolute_piece(match):
        piece_name = Path(match.group(1)).name
        upper_name = "OUT_" + piece_name.split("_", 1)[1]
        piece = run_dir / upper_name
        if not piece.exists():
            raise SystemExit("Missing PVTU piece: {}".format(piece))
        return 'Source="{}"'.format(piece)

    pvtu_text = re.sub(r'source="([Oo][Uu][Tt]_\d+_\d+\.vtu)"', absolute_piece, pvtu_text)
    corrected.write_text(pvtu_text)

    OpenDatabase(str(corrected), 0)
    DefineScalarExpression("rho_gradient_magnitude", "magnitude(gradient(<density>))")
    AddPlot("Pseudocolor", "rho_gradient_magnitude", 1, 0)
    DrawPlots()

    plot_atts = PseudocolorAttributes()
    plot_atts.colorTableName = "gray"
    plot_atts.legendFlag = 0
    plot_atts.minFlag = 1
    plot_atts.min = 0.0
    try:
        plot_atts.invertColorTable = 1
    except AttributeError:
        pass
    SetPlotOptions(plot_atts)

    annotations = AnnotationAttributes()
    annotations.axes2D.visible = 1
    annotations.axes2D.autoSetTicks = 1
    annotations.axes2D.autoSetScaling = 1
    annotations.axes2D.lineWidth = 0
    annotations.axes2D.tickLocation = annotations.axes2D.Outside
    annotations.axes2D.tickAxes = annotations.axes2D.BottomLeft
    annotations.axes2D.xAxis.title.visible = 1
    annotations.axes2D.xAxis.title.userTitle = 1
    annotations.axes2D.xAxis.title.title = "x"
    annotations.axes2D.xAxis.title.userUnits = 1
    annotations.axes2D.xAxis.title.units = "m"
    annotations.axes2D.xAxis.title.font.scale = 1.2
    annotations.axes2D.xAxis.label.visible = 1
    annotations.axes2D.xAxis.tickMarks.visible = 1
    annotations.axes2D.yAxis.title.visible = 1
    annotations.axes2D.yAxis.title.userTitle = 1
    annotations.axes2D.yAxis.title.title = "y"
    annotations.axes2D.yAxis.title.userUnits = 1
    annotations.axes2D.yAxis.title.units = "m"
    annotations.axes2D.yAxis.title.font.scale = 1.2
    annotations.axes2D.yAxis.label.visible = 1
    annotations.axes2D.yAxis.tickMarks.visible = 1
    annotations.userInfoFlag = 0
    annotations.databaseInfoFlag = 0
    annotations.timeInfoFlag = 0
    annotations.legendInfoFlag = 0
    annotations.backgroundMode = annotations.Solid
    annotations.backgroundColor = (255, 255, 255, 255)
    annotations.foregroundColor = (0, 0, 0, 255)
    SetAnnotationAttributes(annotations)

    # Focus on the shock–bubble interaction region used by the dissertation
    # comparisons rather than the much longer numerical shock-tube domain.
    view = View2DAttributes()
    view.windowCoords = (-0.02, 0.10, 0.0, 0.10)
    view.viewportCoords = (0.12, 0.96, 0.12, 0.94)
    view.fullFrameActivationMode = view.Auto
    SetView2D(view)

    save_atts = SaveWindowAttributes()
    save_atts.outputToCurrentDirectory = 0
    save_atts.outputDirectory = str(output_path.parent)
    save_atts.fileName = output_path.stem
    save_atts.family = 0
    save_atts.format = save_atts.PNG
    save_atts.width = 1920
    save_atts.height = 1080
    save_atts.screenCapture = 0
    save_atts.resConstraint = save_atts.NoConstraint
    SetSaveWindowAttributes(save_atts)

    result = SaveWindow()
    print("Saved state {} ({}) to {}".format(state, selected.name, result))
