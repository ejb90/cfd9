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


def extract_interface_positions_vtk(root: Path) -> list[np.ndarray]:
    """"""
    if (root / "interfaces.csv").is_file():
        sorted_array = np.loadtxt(root / "interfaces.csv", delimiter=",")

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

            vf_array = ug.GetCellData().GetArray("volume_fraction")
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
        np.savetxt(root / "interfaces.csv", sorted_array, delimiter=",")
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


def plot_all_interfaces_vs_time(runs, labels):
    """Plot all interfaces vs time"""
    fig = plt.figure(figsize=(10, 10))
    ax = fig.add_subplot(111)
    ax.set_ylabel("Time / s")
    ax.set_xlabel("Position / cm")
    ax.grid()

    colors = plt.rcParams["axes.prop_cycle"].by_key()["color"]  # list of default colors
    color_cycle = cycle(colors)  # infinite iterator

    for i, run in enumerate(runs):
        data = extract_interface_positions_vtk(run)
        c = next(color_cycle)
        ax.plot(data[:, 1], data[:, 0], label=f"{labels[i]}: Upstream", ls="--", c=c)
        ax.plot(data[:, 2], data[:, 0], label=f"{labels[i]}: Downstream", ls="-", c=c)
        ax.plot(data[:, 3], data[:, 0], label=f"{labels[i]}: Jet", ls=":", c=c)

    ax.legend()
    plt.tight_layout()
    plt.show()
    fig.savefig("interfaces_convergence")


def plot_all_interfaces_vs_time_final(runs, labels):
    """Plot all interfaces vs time. Specific c/ls."""
    fig = plt.figure(figsize=(15, 10))
    ax = fig.add_subplot(111)
    ax.set_ylabel("Time / s")
    ax.set_xlabel("Position / cm")
    ax.grid()

    colors = plt.rcParams["axes.prop_cycle"].by_key()["color"]  # list of default colors
    color_cycle = cycle(colors)  # infinite iterator
    linestyle = ["-", "--", ":", ".-"]

    for i, run in enumerate(runs):
        data = extract_interface_positions_vtk(run)
        ax.plot(data[:, 1], data[:, 0], label=f"{labels[i]}: Upstream", ls=linestyle[i])
        ax.plot(data[:, 2], data[:, 0], label=f"{labels[i]}: Downstream", ls=linestyle[i])
        ax.plot(data[:, 3], data[:, 0], label=f"{labels[i]}: Jet", ls=linestyle[i])
        plt.gca().set_prop_cycle(None)

    ax.legend()
    plt.tight_layout()
    plt.show()
    fig.savefig("interfaces_all")


def plot_all_interfaces_vs_time_comparison(runs1, runs2, labels1, labels2):
    """Plot all interfaces vs time"""
    fig = plt.figure(figsize=(10, 10))
    ax = fig.add_subplot(111)
    ax.set_ylabel("Time / s")
    ax.set_xlabel("Position / cm")
    ax.grid()

    colors = plt.rcParams["axes.prop_cycle"].by_key()["color"]  # list of default colors
    # color_cycle = cycle(colors)  # infinite iterator
    linestyle = ["-", "--", ":", ".-"]

    for i, runs in enumerate([runs1, runs2]):
        color_cycle = cycle(colors)
        for j, run in enumerate(runs):
            data = extract_interface_positions_vtk(run)
            c = next(color_cycle)
            ax.plot(data[:, 1], data[:, 0], label=f"{labels1[i]}: {labels2[j]}: Upstream", ls=linestyle[i], c=c)
            c = next(color_cycle)
            ax.plot(
                data[:, 2],
                data[:, 0],
                label=f"{labels1[i]}: {labels2[j]}: Downstream",
                ls=linestyle[i],
                c=c,
            )
            # ax.plot(data[:, 3], data[:, 0], label=f"{labels1[i]}: {labels2[j]}: Jet", ls=":", c=c)

    ax.legend()
    plt.tight_layout()
    plt.show()
    fig.savefig("interfaces_convergence")


def plot_single(root, res=""):
    """"""
    data = extract_interface_positions_vtk(root)
    # data = extract_interface_positions_npz(root)
    # data = extract_interface_positions_vtu(root)
    plot_interface_vs_time(data, label=res)


if __name__ == "__main__":
    # plot_all_interfaces_vs_time(root.glob("*"))
    # plot_single(root=Path("/home/ellis/Documents/cfd_msc/08_dissertation/provided/ELLIS-ucns3d/RUN_EXAMPLES/2D/finex2/"))
    # plot_single(root=Path("/home/ellis/Documents/cfd_msc/08_dissertation/tests/UCNS3D/try6/run1"))
    # plot_single(root=Path("/home/ellis/Documents/cfd_msc/08_dissertation/tests/UCNS3D/try6/run1_more_prints"))
    # plot_single(root=Path())

    # perturbation comparison
    # root = Path()
    # run1 = root / "He_0.0_16"
    # run2 = root / "He_0.0028_16"
    # plot_all_interfaces_vs_time_final([run1, run2], ["$a = 0.0$","$a = 0.0028$"])

    # convergence comparison
    runs = list(Path().glob("*/"))
    labels = [run.name for run in runs]
    plot_all_interfaces_vs_time(runs, labels)

    # # Comparison divergent/convergent
    # root = Path()
    # run1 = root / "He_0.0_16"
    # run2 = root / "He_0.0028_16"
    # run3 = root / "Kr_0.0_16"
    # run4 = root / "Kr_0.0028_16"
    # plot_all_interfaces_vs_time_comparison(
    #     [run1, run2],
    #     [run3, run4],
    #     labels1=["He", "Kr"],
    #     labels2=["$a = 0.0$", "$a = 0.0028$"],
    # )
