import argparse
import re
from itertools import cycle
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import vtk
from vtk.util.numpy_support import vtk_to_numpy

mpl.use("Qt5Agg")
mpl.rcParams.update({"font.size": 16})


def get_bubble_interface_position_npz(
    volfrac: np.ndarray,
    centroids: np.ndarray,
    volfrac_cutoff: float = 1e-3,
    symmetry_line: float | None = None,
    symmetry_line_tol: float = 5e-4,
) -> list[np.float64]:
    """Extract interface positions, as defined by Fig 15 of Tsoutsanis 2021.

    Uses VTU directly via pyvista. Memory fine."""
    centroids2 = []
    # Loop over the volfrac in every cell
    for i, vf in enumerate(volfrac):
        # If the volfrac is > some cutoff for the bubble material, add that cell to the list
        if vf > volfrac_cutoff:
            centroids2.append(centroids[i])
    centroids2 = np.asarray(centroids2)

    # Find if the cells are on the line of symmetry (dow the centre of the tube)
    x_coords = centroids2[:, 0]
    axial_centroid = centroids2[np.abs(centroids2[:, 1] - symmetry_line) < symmetry_line_tol][:, 0]

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


def extract_interface_positions_vtk(root: Path, component: int) -> list[np.ndarray]:
    """"""
    volume_fraction_field = f"volume_fraction{component}"
    cache_file = root / f"interfaces_{volume_fraction_field}.csv"
    if cache_file.is_file():
        sorted_array = np.loadtxt(cache_file, delimiter=",")

    else:
        data = []

        pattern = re.compile(r"OUT_\d+\.vtu$")
        files = [p for p in root.glob("OUT_*.vtu") if pattern.fullmatch(p.name)]

        for fname in files:
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

            # Compute centroids for all cells
            n_cells = ug.GetNumberOfCells()
            centroids = np.zeros((n_cells, 3))

            for i in range(n_cells):
                cell = ug.GetCell(i)
                pts = np.array([cell.GetPoints().GetPoint(j) for j in range(cell.GetNumberOfPoints())])
                centroids[i] = pts.mean(axis=0)

            bounds = ug.GetBounds()
            symmetry_line = (bounds[2] + bounds[3]) / 2.0

            upstream, downstream, jet = get_bubble_interface_position_npz(vf, centroids, symmetry_line=symmetry_line)
            data.append([time, upstream, downstream, jet])

        array = np.asarray(data)
        sorted_array = array[array[:, 0].argsort()]
        np.savetxt(cache_file, sorted_array, delimiter=",")
    return sorted_array


def plot_interface_vs_time(data, label=""):
    """"""
    fig = plt.figure(figsize=(10, 10))
    ax = fig.add_subplot(111)
    ax.set_ylabel("Time / s")
    ax.set_xlabel("Position / cm")
    ax.grid()
    ax.plot(data[:, 1], data[:, 0], label="Upstream")
    ax.plot(data[:, 2], data[:, 0], label="Downstream")
    ax.plot(data[:, 3], data[:, 0], label="Jet")

    ax.legend()
    plt.tight_layout()
    plt.show()
    fig.savefig(f"interfaces_{label}")


def plot_all_interfaces_vs_time(runs, labels, component: int):
    """Plot all interfaces vs time"""
    fig = plt.figure(figsize=(10, 10))
    ax = fig.add_subplot(111)
    ax.set_ylabel("Time / s")
    ax.set_xlabel("Position / cm")
    ax.grid()

    colors = plt.rcParams["axes.prop_cycle"].by_key()["color"]  # list of default colors
    color_cycle = cycle(colors)  # infinite iterator

    for i, run in enumerate(runs):
        data = extract_interface_positions_vtk(run, component)
        c = next(color_cycle)
        ax.plot(data[:, 1], data[:, 0], label=f"{labels[i]}: Upstream", ls="--", c=c)
        ax.plot(data[:, 2], data[:, 0], label=f"{labels[i]}: Downstream", ls="-", c=c)
        ax.plot(data[:, 3], data[:, 0], label=f"{labels[i]}: Jet", ls=":", c=c)

    ax.legend()
    plt.tight_layout()
    plt.show()
    fig.savefig("interfaces_convergence")


def plot_all_interfaces_vs_time_final(runs, labels, component: int):
    """Plot all interfaces vs time. Specific c/ls."""
    fig = plt.figure(figsize=(15, 10))
    ax = fig.add_subplot(111)
    ax.set_ylabel("Time / s")
    ax.set_xlabel("Position / cm")
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
):
    """Plot interfaces for two sets of runs."""
    fig = plt.figure(figsize=(10, 10))
    ax = fig.add_subplot(111)
    ax.set_ylabel("Time / s")
    ax.set_xlabel("Position / cm")
    ax.grid()

    colors = plt.rcParams["axes.prop_cycle"].by_key()["color"]  # list of default colors
    # color_cycle = cycle(colors)  # infinite iterator
    linestyle = ["-", "--", ":", ".-"]

    for runs, group_label, run_labels, line_style, component in zip(
        [runs1, runs2], group_labels, [run_labels1, run_labels2], linestyle, [component1, component2], strict=True
    ):
        color_cycle = cycle(colors)
        for j, run in enumerate(runs):
            data = extract_interface_positions_vtk(run, component)
            c = next(color_cycle)
            ax.plot(
                data[:, 1], data[:, 0], label=f"{group_label}: {run_labels[j]}: Upstream", ls=line_style, c=c
            )
            c = next(color_cycle)
            ax.plot(
                data[:, 2],
                data[:, 0],
                label=f"{group_label}: {run_labels[j]}: Downstream",
                ls=line_style,
                c=c,
            )
            # ax.plot(data[:, 3], data[:, 0], label=f"{labels1[i]}: {labels2[j]}: Jet", ls=":", c=c)

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
    return args


if __name__ == "__main__":
    args = parse_args()
    runs = find_run_directories(args.root)
    if not runs:
        raise SystemExit(f"No run directories containing OUT_*.vtu files found below {args.root}")
    labels = [run.name for run in runs]
    if args.comparison_root is None:
        plot_all_interfaces_vs_time(runs, labels, args.component)
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
        )
