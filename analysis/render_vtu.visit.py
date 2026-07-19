"""VisIt-side renderer used by ``render_vtu_plots.py``.

This file runs inside VisIt's Python CLI. It intentionally contains no
case-specific dimensions, field limits, output paths, or labels.
"""

import json
import math
from pathlib import Path
import re
import sys


PLOT_DEFINITIONS = {
    "density": {
        "variable": "density",
        "colour_table": "hot_desaturated",
        "invert": False,
        "legend_title": "Density [kg m^-3]",
    },
    "schlieren": {
        "variable": "plot_schlieren",
        "colour_table": "gray",
        "invert": True,
        "legend_title": "|grad rho| [kg m^-4]",
    },
    "pressure": {
        "variable": "pressure",
        "colour_table": "hot_desaturated",
        "invert": False,
        "legend_title": "Pressure [Pa]",
    },
    "vorticity": {
        "variable": "plot_vorticity",
        "colour_table": "difference",
        "invert": False,
        "legend_title": "Vorticity [s^-1]",
    },
    "mixedness": {
        "variable": "plot_mixedness",
        "colour_table": "hot_desaturated",
        "invert": False,
        "legend_title": "Mixedness [-]",
    },
}
INTERFACE_COLOURS = (
    (230, 85, 13, 255),
    (0, 158, 115, 255),
    (204, 121, 167, 255),
    (0, 114, 178, 255),
    (240, 228, 66, 255),
)
SCHLIEREN_RANGE_CEILING = 1.0e10


def fail(message):
    print("VTU_RENDER_FAILED: {}".format(message))
    raise RuntimeError(message)


def load_config():
    candidates = [Path(arg) for arg in sys.argv[1:] if arg.endswith(".json")]
    candidates = [path for path in candidates if path.is_file()]
    if len(candidates) != 1:
        fail("expected exactly one existing JSON configuration path, found {}".format(candidates))
    return json.loads(candidates[0].read_text())


def scalar_names(metadata):
    return [metadata.GetScalars(index).name for index in range(metadata.GetNumScalars())]


def finite_range(value):
    numbers = [float(item) for item in value]
    if len(numbers) < 2 or not all(math.isfinite(item) for item in numbers[:2]):
        return None
    lower, upper = numbers[0], numbers[1]
    if lower > upper:
        return None
    if lower == upper:
        padding = max(abs(lower) * 1.0e-12, 1.0e-12)
        lower -= padding
        upper += padding
    return [lower, upper]


def query_range(label, allow_invalid=False):
    Query("MinMax")
    value = GetQueryOutputValue()
    result = finite_range(value)
    if result is None and not allow_invalid:
        fail("invalid MinMax query for {}: {}".format(label, value))
    return result


def add_scalar_plot(variable, label):
    """Make one scalar plot active and ready for a MinMax query or rendering."""
    DeleteAllPlots()
    if not AddPlot("Pseudocolor", variable, 1, 0):
        fail("could not add {} pseudocolour plot".format(label))
    if not DrawPlots():
        fail("could not draw {} pseudocolour plot".format(label))
    SetActivePlots(0)


def query_schlieren_range(variable="plot_schlieren_range"):
    """Query schlieren after discarding known non-physical numerical spikes."""
    add_scalar_plot(variable, "schlieren range")
    return query_range("schlieren", allow_invalid=True)


def configure_annotations(show_legends):
    attributes = AnnotationAttributes()
    attributes.axes2D.visible = 1
    attributes.axes3D.visible = 0
    attributes.userInfoFlag = 0
    attributes.databaseInfoFlag = 0
    attributes.timeInfoFlag = 0
    attributes.legendInfoFlag = 1 if show_legends else 0
    attributes.backgroundMode = attributes.Solid
    attributes.backgroundColor = (255, 255, 255, 255)
    attributes.foregroundColor = (0, 0, 0, 255)
    SetAnnotationAttributes(attributes)


def add_time_annotation(physical_time):
    """Place the frame's physical time in the lower-right corner."""
    annotation = CreateAnnotationObject("Text2D", "cfd9_time_label")
    if physical_time is None:
        annotation.text = "t = unavailable"
    else:
        annotation.text = "t = {:.4g} s".format(float(physical_time))
    annotation.position = (0.76, 0.035)
    annotation.height = 0.026
    annotation.fontBold = 1
    annotation.useForegroundForTextColor = 1
    annotation.fontShadow = 1
    return annotation


def configure_view(bounds, viewport=(0.0, 1.0, 0.0, 1.0)):
    view = View2DAttributes()
    view.windowCoords = tuple(bounds)
    view.viewportCoords = viewport
    view.fullFrameActivationMode = view.Off
    view.windowValid = 1
    SetView2D(view)


def add_interface_contour(field, cutoff, colour):
    # A white halo keeps the material-coloured line visible on both light and
    # dark backgrounds. The two contour plots share the same alpha level.
    for line_width, line_colour in ((4, (255, 255, 255, 255)), (2, colour)):
        if not AddPlot("Contour", field, 1, 0):
            fail("could not add interface contour for {}".format(field))
        attributes = ContourAttributes()
        attributes.colorType = attributes.ColorBySingleColor
        attributes.singleColor = line_colour
        attributes.legendFlag = 0
        attributes.lineWidth = line_width
        attributes.contourMethod = attributes.Value
        attributes.contourValue = (float(cutoff),)
        attributes.minFlag = 0
        attributes.maxFlag = 0
        SetPlotOptions(attributes)


def configure_pseudocolour(definition, limits, show_legend):
    attributes = PseudocolorAttributes()
    attributes.colorTableName = definition["colour_table"]
    attributes.legendFlag = 1 if show_legend else 0
    attributes.minFlag = 1
    attributes.maxFlag = 1
    attributes.min = float(limits[0])
    attributes.max = float(limits[1])
    try:
        attributes.invertColorTable = 1 if definition["invert"] else 0
    except AttributeError:
        pass
    SetPlotOptions(attributes)
    return attributes.colorTableName


def configure_legend(plot_index, title, active, separate=False):
    plot_name = GetPlotList().GetPlots(plot_index).plotName
    legend = GetAnnotationObject(plot_name)
    legend.active = 1 if active else 0
    legend.managePosition = 0
    legend.position = (0.68, 0.9) if separate else (0.72, 0.88)
    legend.xScale = 1.0 if separate else 1.5
    legend.yScale = 1.0 if separate else 1.15
    legend.orientation = legend.VerticalRight
    legend.numberFormat = "%.4g"
    legend.fontHeight = 0.025 if separate else 0.028
    legend.drawLabels = legend.Values
    legend.drawTitle = 1
    legend.drawMinMax = 0
    legend.controlTicks = 1
    legend.numTicks = 5
    legend.drawBoundingBox = 1 if not separate else 0
    legend.boundingBoxColor = (255, 255, 255, 210)
    try:
        legend.useCustomTitle = 1
        legend.customTitle = title
    except AttributeError:
        pass
    return legend


config = load_config()
vtu = Path(config["vtu"])
output_dir = Path(config["output_dir"])
output_dir.mkdir(parents=True, exist_ok=True)

if not OpenDatabase(str(vtu), 0, "VTK"):
    fail("could not open {} with VisIt's VTK reader".format(vtu))

metadata = GetMetaData(str(vtu))
scalars = scalar_names(metadata)
volume_fraction_fields = sorted(
    (name for name in scalars if re.match(r"^volume_fraction[0-9]+$", name)),
    key=lambda name: int(name.replace("volume_fraction", "")),
)
if len(volume_fraction_fields) < 2:
    fail("at least two numbered volume-fraction fields are required; found {}".format(volume_fraction_fields))

schlieren_uses_native = "schlieren" in scalars
DefineScalarExpression("plot_schlieren_fallback", "magnitude(gradient(<density>))")
if schlieren_uses_native:
    DefineScalarExpression("plot_schlieren", "<schlieren>")
else:
    DefineScalarExpression("plot_schlieren", "<plot_schlieren_fallback>")
# UCNS3D occasionally writes isolated, non-physical schlieren values around
# 1e100. They are excluded from MinMax queries, rather than being allowed to
# make the useful range of the colour scale invisible.
DefineScalarExpression(
    "plot_schlieren_range",
    "if(lt(<plot_schlieren>,{}),<plot_schlieren>,0)".format(SCHLIEREN_RANGE_CEILING),
)
DefineScalarExpression(
    "plot_schlieren_fallback_range",
    "if(lt(<plot_schlieren_fallback>,{}),<plot_schlieren_fallback>,0)".format(SCHLIEREN_RANGE_CEILING),
)

if "u" not in scalars or "v" not in scalars:
    fail("vorticity requires scalar velocity fields 'u' and 'v'")
DefineScalarExpression("plot_vorticity", "curl({<u>,<v>,0*<u>})")

mixedness_terms = ["<{}>*<{}>".format(name, name) for name in volume_fraction_fields]
material_count = float(len(volume_fraction_fields))
mixedness_expression = "({}/{})*(1-({}))".format(
    material_count,
    material_count - 1.0,
    "+".join(mixedness_terms),
)
DefineScalarExpression("plot_mixedness", mixedness_expression)

ambient_field = "volume_fraction{}".format(config["ambient_component"])
if ambient_field not in volume_fraction_fields:
    fail("ambient field {} is absent; available fields: {}".format(ambient_field, volume_fraction_fields))

requested_components = config.get("interface_components")
if requested_components is None:
    interface_fields = [name for name in volume_fraction_fields if name != ambient_field]
else:
    interface_fields = ["volume_fraction{}".format(component) for component in requested_components]
    missing_interfaces = [name for name in interface_fields if name not in volume_fraction_fields]
    if missing_interfaces:
        fail("requested interface fields are absent: {}".format(missing_interfaces))

required_native_fields = {
    definition["variable"]
    for definition in PLOT_DEFINITIONS.values()
    if not definition["variable"].startswith("plot_")
}
missing_native_fields = sorted(required_native_fields.difference(scalars))
if missing_native_fields:
    fail("required scalar fields are absent: {}".format(missing_native_fields))

legend_mode = config.get("legend_mode", "embedded")
ranges_only = bool(config.get("ranges_only", False))
configure_annotations(legend_mode != "none")
time_annotation = add_time_annotation(config.get("physical_time"))

# Probe the common physical view before selecting the output height. By
# default, the raster aspect ratio follows the requested view and therefore
# contains no case-dependent letterboxing.
probe_variable = PLOT_DEFINITIONS[config["plots"][0]]["variable"]
if not AddPlot("Pseudocolor", probe_variable, 1, 0) or not DrawPlots():
    fail("could not draw the spatial-extent probe")
view_bounds = config.get("bounds")
if view_bounds is None:
    Query("SpatialExtents")
    extents = [float(value) for value in GetQueryOutputValue()]
    if len(extents) < 4:
        fail("invalid SpatialExtents query: {}".format(extents))
    view_bounds = extents[:4]
DeleteAllPlots()

save = SaveWindowAttributes()
save.outputToCurrentDirectory = 0
save.outputDirectory = str(output_dir)
save.family = 0
save.format = save.PNG
save.width = int(config["width"])
if config["height"] is None:
    x_span = float(view_bounds[1]) - float(view_bounds[0])
    y_span = float(view_bounds[3]) - float(view_bounds[2])
    save.height = max(1, int(round(save.width * y_span / x_span)))
else:
    save.height = int(config["height"])
save.screenCapture = 0
save.resConstraint = save.NoConstraint

manifest = {
    "schema_version": config["schema_version"],
    "visit_version": Version(),
    "input_vtu": str(vtu),
    "physical_time": config.get("physical_time"),
    "output_index": config.get("output_index"),
    "image_size": [save.width, save.height],
    "volume_fraction_fields": volume_fraction_fields,
    "ambient_field": ambient_field,
    "interface_fields": interface_fields if config["draw_interfaces"] else [],
    "interface_cutoff": config["interface_cutoff"],
    "legend_mode": legend_mode,
    "time_annotation": time_annotation.text,
    "plots": {},
}

for plot_name in config["plots"]:
    definition = PLOT_DEFINITIONS[plot_name]
    add_scalar_plot(definition["variable"], plot_name)
    data_range = query_schlieren_range() if plot_name == "schlieren" else query_range(plot_name)
    if data_range is None:
        # Some solver outputs contain non-finite values in their stored
        # schlieren array.  Recompute the diagnostic from density so a bad
        # native diagnostic cannot prevent the other plot tiles from being
        # rendered.
        definition = dict(definition, variable="plot_schlieren_fallback")
        data_range = query_schlieren_range("plot_schlieren_fallback_range")

    limits = config["limits"].get(plot_name)
    if limits is None:
        if plot_name == "schlieren":
            limits = [0.0, max(data_range[1], 1.0e-12)]
        elif plot_name == "vorticity":
            magnitude = max(abs(data_range[0]), abs(data_range[1]), 1.0e-12)
            limits = [-magnitude, magnitude]
        elif plot_name == "mixedness":
            limits = [0.0, 1.0]
        else:
            limits = data_range
    # The schlieren range query briefly makes its masked helper expression the
    # active plot. Restore the real field before setting plot attributes.
    add_scalar_plot(definition["variable"], plot_name)
    if ranges_only:
        manifest["plots"][plot_name] = {
            "file": None,
            "variable": definition["variable"],
            "data_range": data_range,
            "colour_limits": [float(limits[0]), float(limits[1])],
        }
        continue
    colour_table = configure_pseudocolour(definition, limits, legend_mode != "none")
    legend = configure_legend(
        0,
        definition["legend_title"],
        active=legend_mode == "embedded",
    )

    if config["draw_interfaces"]:
        for index, field in enumerate(interface_fields):
            colour = INTERFACE_COLOURS[index % len(INTERFACE_COLOURS)]
            add_interface_contour(field, config["interface_cutoff"], colour)

    if not DrawPlots():
        fail("could not draw completed {} plot".format(plot_name))
    configure_view(view_bounds)
    filename = "{}_{}".format(config["prefix"], plot_name)
    save.fileName = filename
    SetSaveWindowAttributes(save)
    result = SaveWindow()
    if not result:
        fail("SaveWindow failed for {}".format(plot_name))

    legend_file = None
    if legend_mode == "separate":
        configure_legend(0, definition["legend_title"], active=True, separate=True)
        configure_view(view_bounds, viewport=(0.0, 0.62, 0.0, 1.0))
        tile_width, tile_height = save.width, save.height
        save.width = 800
        save.height = 600
        save.fileName = "{}_{}_legend_source".format(config["prefix"], plot_name)
        SetSaveWindowAttributes(save)
        if not SaveWindow():
            fail("SaveWindow failed for the {} legend".format(plot_name))
        save.width, save.height = tile_width, tile_height
        legend.active = 0
        legend_file = str(output_dir / ("{}_{}_legend.png".format(config["prefix"], plot_name)))

    manifest["plots"][plot_name] = {
        "file": str(output_dir / (filename + ".png")),
        "variable": definition["variable"],
        "data_range": data_range,
        "colour_limits": [float(limits[0]), float(limits[1])],
        "colour_table": colour_table,
        "legend_embedded": legend_mode == "embedded",
        "legend_file": legend_file,
    }

manifest["bounds"] = [float(value) for value in view_bounds]
manifest_path = output_dir / "{}_plots.json".format(config["prefix"])
manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")

DeleteAllPlots()
CloseDatabase(str(vtu))
print("VTU_RENDER_PASSED: wrote {} plots and {}".format(len(config["plots"]), manifest_path))
sys.exit(0)
