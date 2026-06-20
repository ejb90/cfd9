from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import vtk
from vtk.util.numpy_support import vtk_to_numpy

mpl.rcParams.update({"font.size": 16})


def extract_data(root: Path, tolerance: float = 0.05) -> dict:
    """"""
    data = {}
    for fname in root.glob("OUT_*.vtu"):
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
        rho1_array = ug.GetCellData().GetArray("rho vf1")
        vfs = vtk_to_numpy(vf_array)
        rho1 = vtk_to_numpy(rho1_array)

        # Compute cell sizes
        size_filter = vtk.vtkCellSizeFilter()
        size_filter.SetInputData(ug)

        # Only compute area
        size_filter.ComputeVertexCountOff()
        size_filter.ComputeLengthOff()
        size_filter.ComputeAreaOn()
        size_filter.ComputeVolumeOff()

        size_filter.Update()

        ug_with_sizes = size_filter.GetOutput()

        # The new cell-data array is usually called "Area"
        area_array = ug_with_sizes.GetCellData().GetArray("Area")
        areas = vtk_to_numpy(area_array)

        n_cells = ug.GetNumberOfCells()

        # masses_bubble = np.sum(areas * rho1 * vfs)
        # masses_bg = np.sum(areas * rho2 * (1.0 - vfs))
        masses_bubble = 0.0
        # masses_bg = 0.0
        areas_bubble = 0.0
        for i in range(n_cells):
            if vfs[i] < (1.0 - tolerance):
                masses_bubble += areas[i] * rho1[i] * vfs[i]
                areas_bubble += areas[i] * vfs[i]
                # masses_bg += areas[i] * rho1[i] * vfs[i]

        data[time] = [masses_bubble, areas_bubble]

    return data


def main(root: Path, tolerance: float = 0.1, element: str = "Kr", npertns: int = 16) -> None:
    """Main plotter."""
    fig = plt.figure(figsize=(15, 10))
    ax1 = fig.add_subplot(111)
    # ax2 = fig.add_subplot(212)

    for amp in (
        "0.0",
        "0.0004",
        "0.0008",
        "0.0012",
        "0.0016",
        "0.002",
        "0.0024",
        "0.0028",
    ):
        data = extract_data(root=root / f"{element}_{amp}_{npertns}", tolerance=tolerance)
        times = sorted(list(data.keys()))
        bubble_mass = [data[t][0] for t in times]
        # bubble_area = [data[t][1] for t in times]
        # bg_mass = [data[t][1] for t in times]
        ax1.plot(times, bubble_mass, label=f"{amp} m")
        # ax2.plot(times, bubble_area, label=f"{amp} m")

    ax1.set_xlabel("Time / s")
    ax1.set_ylabel(f"{element} Mixed Bubble Mass ({tolerance * 100:.1f} % Threshold) / kg")
    ax1.grid()
    ax1.legend()
    # ax2.set_xlabel("Time / s")
    # ax2.set_ylabel(f"Mixed Bubble \"Volume\" ({tolerance*100:.1f} % Threshold) / $m^3$")
    # ax2.grid()
    # ax2.legend()
    plt.tight_layout()
    plt.show()
    fig.savefig(f"mix_mass_vs_time_vs_amplitude_{element}")


if __name__ == "__main__":
    tolerance = 0.1
    root = Path()
    main(root, tolerance, element="He")
    main(root, tolerance, element="Kr")
