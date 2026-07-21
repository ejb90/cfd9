import argparse
import re
from itertools import cycle
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import vtk
from vtk.util.numpy_support import vtk_to_numpy

mpl.rcParams.update({"font.size": 16})

INTERFACE_PLOTS = {
    1: ("Upstream", "--"),
    2: ("Downstream", "-"),
    3: ("Jet", ":"),
}


def get_bubble_interface_position_npz(
    volfrac: np.ndarray,
    centroids: np.ndarray,
    volfrac_cutoff: float = 0.5,
    symmetry_line: float | None = None,
) -> tuple[np.float64, np.float64, np.float64]:
    """Extract thresholded bubble extents and the axial jet position.

    A 0.5 volume-fraction contour is the conventional diffuse-interface
    location. Selecting the nearest centroid row to the symmetry line avoids a
    mesh-dependent fixed-width band around the axis.
    """
    if not 0.0 < volfrac_cutoff < 1.0:
        raise ValueError("volfrac_cutoff must lie strictly between 0 and 1")

    centroids2 = centroids[volfrac > volfrac_cutoff]
    if not centroids2.size:
        raise ValueError(f"no bubble cells exceed volume-fraction cutoff {volfrac_cutoff:g}")

    x_coords = centroids2[:, 0]
    if symmetry_line is None:
        symmetry_line = 0.5 * (centroids[:, 1].min() + centroids[:, 1].max())
    distance_from_axis = np.abs(centroids2[:, 1] - symmetry_line)
    nearest_distance = distance_from_axis.min()
    axial_centroid = centroids2[np.isclose(distance_from_axis, nearest_distance, rtol=0.0, atol=1e-12), 0]

    # Upstream is minimum x-extent
    upstream = x_coords.min()
    # Downstream is the maximum x-extent
    downstream = x_coords.max()
    # Jet is the minimum x-extent on the axis of symmetry
    if axial_centroid.size:
        jet = axial_centroid.min()
    else:
        jet = np.nan

    return upstream, downstream, jet


def extract_interface_positions_vtk(
    root: Path,
    component: int,
    volfrac_cutoff: float = 0.5,
    symmetry_line: float | None = None,
) -> np.ndarray:
    """Extract and cache interface positions from the VTUs in one run.

    Outputs in which the bubble has mixed below ``volfrac_cutoff`` contribute
    no position row.  This preserves the preceding, physically meaningful
    interface history instead of treating bubble disappearance as an error.
    """
    volume_fraction_field = f"volume_fraction{component}"
    cutoff_tag = f"{volfrac_cutoff:g}".replace("-", "m").replace(".", "p")
    axis_tag = "auto" if symmetry_line is None else f"{symmetry_line:g}".replace("-", "m").replace(".", "p")
    cache_file = root / f"interfaces_{volume_fraction_field}_cutoff_{cutoff_tag}_axis_{axis_tag}.csv"

    pattern = re.compile(r"OUT_\d+\.vtu$")
    files = sorted(
        (p for p in root.glob("OUT_*.vtu") if pattern.fullmatch(p.name)),
        key=lambda path: int(path.stem.removeprefix("OUT_")),
    )
    if not files:
        raise ValueError(f"{root} does not contain numbered OUT_*.vtu files")

    cache_is_current = cache_file.is_file() and cache_file.stat().st_size > 0 and cache_file.stat().st_mtime_ns >= max(
        path.stat().st_mtime_ns for path in files
    )
    if cache_is_current:
        sorted_array = np.atleast_2d(np.loadtxt(cache_file, delimiter=","))

    else:
        data = []

        for file_index, fname in enumerate(files, start=1):
            print(
                f"\rProcessing {file_index}/{len(files)} in {root}: {fname.name}",
                end="",
                flush=True,
            )
            # Read the VTU file
            reader = vtk.vtkXMLUnstructuredGridReader()
            reader.SetFileName(fname)
            reader.Update()  # actually read the file

            # Get the unstructured grid object
            ug = reader.GetOutput()

            # Access field data (global data)
            time_array = ug.GetFieldData().GetArray("TimeValue")
            time = vtk_to_numpy(time_array)[0]

            vf_array = ug.GetCellData().GetArray(volume_fraction_field)
            if vf_array is None:
                raise ValueError(f"{fname} does not contain cell-data field {volume_fraction_field!r}")
            vf = vtk_to_numpy(vf_array)

            # Once mixing has reduced every cell below the threshold, there
            # is no interface position to track for this output.  Skip it
            # rather than aborting the entire time history.
            if not np.any(vf > volfrac_cutoff):
                continue

            # Compute centroids for all cells
            n_cells = ug.GetNumberOfCells()
            centroids = np.zeros((n_cells, 3))

            for i in range(n_cells):
                cell = ug.GetCell(i)
                pts = np.array([cell.GetPoints().GetPoint(j) for j in range(cell.GetNumberOfPoints())])
                centroids[i] = pts.mean(axis=0)

            selected = centroids[vf > volfrac_cutoff]

            current_symmetry_line = symmetry_line
            if current_symmetry_line is None:
                bounds = ug.GetBounds()
                lower_is_symmetry = np.isclose(selected[:, 1].min(), centroids[:, 1].min())
                upper_is_symmetry = np.isclose(selected[:, 1].max(), centroids[:, 1].max())
                if lower_is_symmetry and not upper_is_symmetry:
                    current_symmetry_line = bounds[2]
                elif upper_is_symmetry and not lower_is_symmetry:
                    current_symmetry_line = bounds[3]
                else:
                    current_symmetry_line = 0.5 * (bounds[2] + bounds[3])

            upstream, downstream, jet = get_bubble_interface_position_npz(
                vf,
                centroids,
                volfrac_cutoff=volfrac_cutoff,
                symmetry_line=current_symmetry_line,
            )
            data.append([time, upstream, downstream, jet])

        print()
        array = np.asarray(data, dtype=float).reshape(-1, 4)
        sorted_array = array[array[:, 0].argsort()]
        np.savetxt(cache_file, sorted_array, delimiter=",")
    return sorted_array


def plot_interface_vs_time(data, label=""):
    """"""
    fig = plt.figure(figsize=(10, 10))
    ax = fig.add_subplot(111)
    ax.set_ylabel("Time / s")
    ax.set_xlabel("Position / m")
    ax.grid()
    ax.plot(data[:, 1], data[:, 0], label="Upstream")
    ax.plot(data[:, 2], data[:, 0], label="Downstream")
    ax.plot(data[:, 3], data[:, 0], label="Jet")

    ax.legend()
    plt.tight_layout()
    plt.show()
    fig.savefig(f"interfaces_{label}")


def plot_all_interfaces_vs_time(
    runs,
    labels,
    component: int,
    volfrac_cutoff: float = 0.5,
    symmetry_line: float | None = None,
    interfaces: tuple[int, ...] = (1, 2, 3),
):
    """Plot all interfaces vs time"""
    fig = plt.figure(figsize=(10, 10))
    ax = fig.add_subplot(111)
    ax.set_ylabel("Time / s")
    ax.set_xlabel("Position / m")
    ax.grid()

    colors = plt.rcParams["axes.prop_cycle"].by_key()["color"]  # list of default colors
    color_cycle = cycle(colors)  # infinite iterator

    for i, run in enumerate(runs):
        data = extract_interface_positions_vtk(run, component, volfrac_cutoff, symmetry_line)
        c = next(color_cycle)
        for interface in interfaces:
            name, line_style = INTERFACE_PLOTS[interface]
            ax.plot(data[:, interface], data[:, 0], label=f"{labels[i]}: {name}", ls=line_style, c=c)

    ax.legend()
    plt.tight_layout()
    plt.show()
    fig.savefig("interfaces_convergence")


def plot_all_interfaces_vs_time_final(runs, labels, component: int):
    """Plot all interfaces vs time. Specific c/ls."""
    fig = plt.figure(figsize=(15, 10))
    ax = fig.add_subplot(111)
    ax.set_ylabel("Time / s")
    ax.set_xlabel("Position / m")
    ax.grid()

    linestyle = ["-", "--", ":", ".-"]

    for i, run in enumerate(runs):
        data = extract_interface_positions_vtk(run, component)
        ax.plot(data[:, 1], data[:, 0], label=f"{labels[i]}: Upstream", ls=linestyle[i])
        ax.plot(data[:, 2], data[:, 0], label=f"{labels[i]}: Downstream", ls=linestyle[i])
        ax.plot(data[:, 3], data[:, 0], label=f"{labels[i]}: Jet", ls=linestyle[i])
        plt.gca().set_prop_cycle(None)

    ax.legend()
    plt.tight_layout()
    plt.show()
    fig.savefig("interfaces_all")


def plot_all_interfaces_vs_time_comparison(
    runs1,
    runs2,
    group_labels: tuple[str, str] | list[str],
    run_labels1,
    run_labels2,
    component1: int,
    component2: int,
    volfrac_cutoff: float = 0.5,
    symmetry_line: float | None = None,
    interfaces: tuple[int, ...] = (1, 2, 3),
):
    """Plot interfaces for two sets of runs."""
    fig = plt.figure(figsize=(10, 10))
    ax = fig.add_subplot(111)
    ax.set_ylabel("Time / s")
    ax.set_xlabel("Position / m")
    ax.grid()

    colors = plt.rcParams["axes.prop_cycle"].by_key()["color"]  # list of default colors
    # color_cycle = cycle(colors)  # infinite iterator
    linestyles = ["-", "--"]

    for runs, group_label, run_labels, line_style, component in zip(
        [runs1, runs2],
        group_labels,
        [run_labels1, run_labels2],
        linestyles,
        [component1, component2],
        strict=True,
    ):
        color_cycle = cycle(colors)
        for j, run in enumerate(runs):
            data = extract_interface_positions_vtk(run, component, volfrac_cutoff, symmetry_line)
            for interface in interfaces:
                name, _ = INTERFACE_PLOTS[interface]
                c = next(color_cycle)
                ax.plot(
                    data[:, interface],
                    data[:, 0],
                    label=f"{group_label}: {run_labels[j]}: {name}",
                    ls=line_style,
                    c=c,
                )

    ax.legend()
    plt.tight_layout()
    plt.show()
    fig.savefig("interfaces_convergence")


def plot_single(root, component: int, res=""):
    """"""
    data = extract_interface_positions_vtk(root, component)
    # data = extract_interface_positions_npz(root)
    # data = extract_interface_positions_vtu(root)
    plot_interface_vs_time(data, label=res)


def find_run_directories(root: Path) -> list[Path]:
    """Return directories below *root* that contain numbered OUT VTU files."""
    pattern = re.compile(r"OUT_\d+\.vtu$")
    return sorted(
        {path.parent for path in root.rglob("OUT_*.vtu") if pattern.fullmatch(path.name)},
        key=lambda path: str(path),
    )


def select_run_directories(runs: list[Path], resolutions: list[str] | None) -> list[Path]:
    """Select run directories by basename, preserving the requested order."""
    if resolutions is None:
        return runs

    duplicate_requests = sorted({name for name in resolutions if resolutions.count(name) > 1})
    if duplicate_requests:
        names = ", ".join(duplicate_requests)
        raise ValueError(f"resolution names were requested more than once: {names}")

    runs_by_name: dict[str, list[Path]] = {}
    for run in runs:
        runs_by_name.setdefault(run.name, []).append(run)

    missing = [name for name in resolutions if name not in runs_by_name]
    if missing:
        available = ", ".join(sorted(runs_by_name)) or "none"
        raise ValueError(
            f"resolution directories not found: {', '.join(missing)}; available resolutions: {available}"
        )

    ambiguous = {name: runs_by_name[name] for name in resolutions if len(runs_by_name[name]) > 1}
    if ambiguous:
        details = "; ".join(f"{name}: {', '.join(map(str, paths))}" for name, paths in ambiguous.items())
        raise ValueError(f"resolution names are ambiguous below the root; use unique directory names ({details})")

    return [runs_by_name[name][0] for name in resolutions]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Plot bubble-interface positions for all runs below a root directory."
    )
    parser.add_argument(
        "root",
        nargs="?",
        type=Path,
        default=Path.cwd(),
        help="directory to search recursively for runs (default: current directory)",
    )
    parser.add_argument(
        "comparison_root",
        nargs="?",
        type=Path,
        help="optional second directory to search and plot as a comparison set",
    )
    parser.add_argument(
        "-c",
        "--component",
        type=int,
        required=True,
        metavar="N",
        help="component index to track using the volume_fraction<N> cell-data field",
    )
    parser.add_argument(
        "--component2",
        type=int,
        metavar="N",
        help="component index for the comparison root (default: --component)",
    )
    parser.add_argument(
        "-r",
        "--resolutions",
        nargs="+",
        metavar="NAME",
        help=(
            "plot only these resolution directory names from a single root, "
            "in the order given (for example: --resolutions mesh_6400 mesh_25600)"
        ),
    )
    parser.add_argument(
        "--volfrac-cutoff",
        type=float,
        default=0.5,
        metavar="F",
        help="bubble-interface volume-fraction threshold (default: 0.5)",
    )
    parser.add_argument(
        "--symmetry-line",
        type=float,
        metavar="Y",
        help="y coordinate of the symmetry axis (default: infer boundary or domain midpoint)",
    )
    parser.add_argument(
        "--interfaces",
        type=int,
        nargs="+",
        choices=tuple(INTERFACE_PLOTS),
        default=(1, 2, 3),
        metavar="N",
        help="interface traces to plot: 1=upstream, 2=downstream, 3=jet (default: all)",
    )
    args = parser.parse_args()
    if not args.root.is_dir():
        parser.error(f"root directory does not exist: {args.root}")
    if args.comparison_root is not None and not args.comparison_root.is_dir():
        parser.error(f"comparison root directory does not exist: {args.comparison_root}")
    if args.component < 0:
        parser.error("component index must be non-negative")
    if args.component2 is not None and args.component2 < 0:
        parser.error("component2 index must be non-negative")
    if args.component2 is not None and args.comparison_root is None:
        parser.error("--component2 requires a comparison root")
    if args.resolutions is not None and args.comparison_root is not None:
        parser.error("--resolutions is only supported for a single convergence root")
    if not 0.0 < args.volfrac_cutoff < 1.0:
        parser.error("--volfrac-cutoff must lie strictly between 0 and 1")
    if len(set(args.interfaces)) != len(args.interfaces):
        parser.error("--interfaces values must not be repeated")
    args.interfaces = tuple(args.interfaces)
    return args


if __name__ == "__main__":
    args = parse_args()
    runs = find_run_directories(args.root)
    if not runs:
        raise SystemExit(f"No run directories containing OUT_*.vtu files found below {args.root}")
    try:
        runs = select_run_directories(runs, args.resolutions)
    except ValueError as exc:
        raise SystemExit(f"Invalid --resolutions selection: {exc}") from exc
    labels = [run.name for run in runs]
    if args.comparison_root is None:
        plot_all_interfaces_vs_time(
            runs,
            labels,
            args.component,
            args.volfrac_cutoff,
            args.symmetry_line,
            args.interfaces,
        )
    else:
        comparison_runs = find_run_directories(args.comparison_root)
        if not comparison_runs:
            raise SystemExit(
                f"No run directories containing OUT_*.vtu files found below {args.comparison_root}"
            )
        plot_all_interfaces_vs_time_comparison(
            runs,
            comparison_runs,
            [args.root.name, args.comparison_root.name],
            labels,
            [run.name for run in comparison_runs],
            args.component,
            args.component2 if args.component2 is not None else args.component,
            args.volfrac_cutoff,
            args.symmetry_line,
            args.interfaces,
        )
