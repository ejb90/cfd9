""""""

import pathlib

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import vtk
from vtk.util.numpy_support import vtk_to_numpy

matplotlib.use("Qt5Agg")


def query_cell_data_pyvista(mesh, point, quantity_name, tolerance=1e-6):
    """
    Query a quantity from a cell based on a point coordinate using PyVista.

    Parameters:
    -----------
    mesh (pyvista.DataSet):     The PyVista mesh/dataset containing the data
    point (list):               3D coordinates [x, y, z] of the query point
    quantity_name (str):        Name of the cell data array to query
    tolerance (float):          Tolerance for point location (default: 1e-6)

    Returns:
        float, None:
    """

    # Ensure point is a numpy array with shape (1, 3) for PyVista
    point = np.array(point).reshape(1, 3)

    # Check if the quantity exists in cell data
    if quantity_name not in mesh.cell_data:
        raise ValueError(
            f"Quantity '{quantity_name}' not found in cell data. Available quantities: {list(mesh.cell_data.keys())}"
        )

    # Find the cell containing the point
    cell_id = mesh.find_containing_cell(point[0])

    # If point is not found in any cell, return None
    if cell_id == -1 or cell_id >= mesh.n_cells:
        return None

    # Return the quantity value from the cell
    return mesh.cell_data[quantity_name][cell_id]


def read_data_pyvista(fname):
    """"""
    # mesh = pv.read(fname)
    # x = query_cell_data(mesh, (-0.05, 0.05, 0.0), "density")
    # print(x)
    # x = query_cell_data(mesh, (-0.2, 0.05, 0.0), "density")
    # print(x)
    # x = query_cell_data(mesh, (0.2, 0.05, 0.0), "density")
    # print(x)


def load_data_vtk(fname):
    """Load data from VTK file to then query.

    Arguments:
        fname (str):        Path to file.

    Returns:
        ...
    """
    # Read the VTU file
    reader = vtk.vtkXMLUnstructuredGridReader()
    reader.SetFileName(fname)
    reader.Update()
    ug = reader.GetOutput()

    # Create a cell locator
    locator = vtk.vtkCellLocator()
    locator.SetDataSet(ug)
    locator.BuildLocator()

    return ug, locator


def query_cell_data_vtk(ug, locator, point: list[float], quant: str, tolerance: float = 1e6) -> float:
    """"""
    cell_id = locator.FindCell(point)
    vtkarray = ug.GetCellData().GetArray(quant)
    array = vtk_to_numpy(vtkarray)[cell_id]
    return array


def calculate_kinetic_energy(ug, locator, position):
    """Calculate cell KE."""
    u_velocity = query_cell_data_vtk(ug, locator, position, "U")
    v_velocity = query_cell_data_vtk(ug, locator, position, "V")
    cell_id = locator.FindCell(position)
    cell = ug.GetCell(cell_id)
    area = cell.ComputeArea()
    energy = 0.5 * area * u_velocity**2 + v_velocity**2
    return energy


def extract_density_vs_time(root, position):
    """Plot density at a point vs time (cell-average)."""
    times, densities = [], []
    for fname in root.glob("OUT_*.vtu"):
        ug, locator = load_data_vtk(fname)
        densities.append(query_cell_data_vtk(ug, locator, position, "density"))

        field_data = ug.GetFieldData()
        times.append(field_data.GetArray("TimeValue").GetTuple1(0))

    times, densities = zip(*sorted(zip(times, densities)))
    times, densities = list(times), list(densities)
    return times, densities


def plot_density_vs_time(root, position):
    """Plot density vs time."""
    times, densities = extract_density_vs_time(root, position)

    fig = plt.figure(figsize=(10, 10))
    ax = fig.add_subplot(111)
    ax.set_xlabel("Time / s")
    ax.set_ylabel("Density / g/cc")
    ax.grid()

    ax.plot(times, densities)

    ax.legend()
    plt.tight_layout()
    plt.show()


if __name__ == "__main__":
    res = "finex2"
    root = pathlib.Path(f"/home/ellis/Documents/cfd_msc/08_dissertation/provided/ELLIS-ucns3d/RUN_EXAMPLES/2D/{res}/")

    plot_density_vs_time(root, (-0.05, 0.05, 0.0))
