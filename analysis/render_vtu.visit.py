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
    "density": {"variable": "density", "colour_table": "hot_desaturated", "invert": False},
    "schlieren": {"variable": "plot_schlieren", "colour_table": "gray", "invert": True},
    "pressure": {"variable": "pressure", "colour_table": "hot_desaturated", "invert": False},
    "vorticity": {"variable": "plot_vorticity", "colour_table": "difference", "invert": False},
    "mixedness": {"variable": "plot_mixedness", "colour_table": "hot_desaturated", "invert": False},
}
INTERFACE_COLOURS = (
    (230, 85, 13, 255),
    (0, 158, 115, 255),
    (204, 121, 167, 255),
    (0, 114, 178, 255),
    (240, 228, 66, 255),
)


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


def finite_range(value, label):
    numbers = [float(item) for item in value]
    if len(numbers) < 2 or not all(math.isfinite(item) for item in numbers[:2]):
        fail("invalid MinMax query for {}: {}".format(label, value))
    lower, upper = numbers[0], numbers[1]
    if lower > upper:
        fail("reversed MinMax query for {}: {}".format(label, value))
    if lower == upper:
        padding = max(abs(lower) * 1.0e-12, 1.0e-12)
        lower -= padding
        upper += padding
    return [lower, upper]


def query_range(label):
    Query("MinMax")
    return finite_range(GetQueryOutputValue(), label)


def configure_annotations():
    attributes = AnnotationAttributes()
    attributes.axes2D.visible = 0
    attributes.axes3D.visible = 0
    attributes.userInfoFlag = 0
    attributes.databaseInfoFlag = 0
    attributes.timeInfoFlag = 0
    attributes.legendInfoFlag = 0
    attributes.backgroundMode = attributes.Solid
    attributes.backgroundColor = (255, 255, 255, 255)
    attributes.foregroundColor = (0, 0, 0, 255)
    SetAnnotationAttributes(attributes)


def configure_view(bounds):
    view = View2DAttributes()
    view.windowCoords = tuple(bounds)
    view.viewportCoords = (0.0, 1.0, 0.0, 1.0)
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


def configure_pseudocolour(definition, limits):
    attributes = PseudocolorAttributes()
    attributes.colorTableName = definition["colour_table"]
    attributes.legendFlag = 0
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

if "schlieren" in scalars:
    DefineScalarExpression("plot_schlieren", "<schlieren>")
else:
    DefineScalarExpression("plot_schlieren", "magnitude(gradient(<density>))")

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

configure_annotations()

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
    "plots": {},
}

for plot_name in config["plots"]:
    DeleteAllPlots()
    definition = PLOT_DEFINITIONS[plot_name]
    if not AddPlot("Pseudocolor", definition["variable"], 1, 0):
        fail("could not add {} pseudocolour plot".format(plot_name))
    if not DrawPlots():
        fail("could not draw {} pseudocolour plot".format(plot_name))
    SetActivePlots(0)
    data_range = query_range(plot_name)

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
    colour_table = configure_pseudocolour(definition, limits)

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

    manifest["plots"][plot_name] = {
        "file": str(output_dir / (filename + ".png")),
        "variable": definition["variable"],
        "data_range": data_range,
        "colour_limits": [float(limits[0]), float(limits[1])],
        "colour_table": colour_table,
    }

manifest["bounds"] = [float(value) for value in view_bounds]
manifest_path = output_dir / "{}_plots.json".format(config["prefix"])
manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")

DeleteAllPlots()
CloseDatabase(str(vtu))
print("VTU_RENDER_PASSED: wrote {} plots and {}".format(len(config["plots"]), manifest_path))
sys.exit(0)
