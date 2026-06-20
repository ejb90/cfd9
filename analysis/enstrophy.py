#!/usr/bin/env python3

"""
calculate_enstrophy.py

Load one or more VTU files with PyVista and calculate total 2D enstrophy.

Assumes:
  - unstructured 2D grid
  - velocity components are stored as cell data named "u" and "v"
  - enstrophy = 0.5 * integral(omega_z^2 dA)

Usage:
  python calculate_enstrophy.py OUT_0.vtu
  python calculate_enstrophy.py OUT_*.vtu
  python calculate_enstrophy.py --u-name u --v-name v OUT_*.vtu
"""

import argparse
from pathlib import Path
import re

import numpy as np
import pyvista as pv


def get_time_value(mesh):
    """Try to read TimeValue from VTK field data."""
    if "TimeValue" in mesh.field_data:
        arr = np.asarray(mesh.field_data["TimeValue"])
        if arr.size > 0:
            return float(arr.ravel()[0])
    return np.nan


def calculate_total_enstrophy(
    filename,
    u_name="u",
    v_name="v",
    velocity_name="velocity",
    use_point_gradient=True,
):
    """
    Calculate total enstrophy for a 2D unstructured VTU file.

    Parameters
    ----------
    filename : str or Path
        Path to VTU file.
    u_name, v_name : str
        Names of x- and y-velocity components.
    velocity_name : str
        Temporary vector field name.
    use_point_gradient : bool
        If True, convert cell data to point data before computing gradients.
        This is often more stable with VTK/PyVista derivative filters.

    Returns
    -------
    dict
        Contains filename, time, enstrophy, mean_enstrophy, area, min/max omega.
    """

    mesh = pv.read(filename)

    if u_name not in mesh.cell_data:
        raise KeyError(
            f"Could not find cell data array {u_name!r} in {filename}. "
            f"Available cell data: {list(mesh.cell_data.keys())}"
        )

    if v_name not in mesh.cell_data:
        raise KeyError(
            f"Could not find cell data array {v_name!r} in {filename}. "
            f"Available cell data: {list(mesh.cell_data.keys())}"
        )

    u = np.asarray(mesh.cell_data[u_name])
    v = np.asarray(mesh.cell_data[v_name])

    if u.shape != v.shape:
        raise ValueError(
            f"u and v arrays have different shapes in {filename}: "
            f"{u.shape} vs {v.shape}"
        )

    # Build a 3-component velocity vector. The z-component is zero for 2D.
    mesh.cell_data[velocity_name] = np.column_stack(
        [u, v, np.zeros_like(u)]
    )

    if use_point_gradient:
        # VTK's derivative filter usually operates more naturally on point data.
        # This converts cell-centred velocity to point-centred velocity.
        work = mesh.cell_data_to_point_data(pass_cell_data=True)

        deriv = work.compute_derivative(
            scalars=velocity_name,
            gradient=True,
            vorticity=True,
            preference="point",
        )

        # Convert point-centred vorticity back to cells so it lines up with cell areas.
        deriv_cell = deriv.point_data_to_cell_data(pass_point_data=False)

        if "vorticity" not in deriv_cell.cell_data:
            raise RuntimeError(
                f"PyVista did not produce a 'vorticity' array for {filename}"
            )

        omega_vec = np.asarray(deriv_cell.cell_data["vorticity"])
        omega_z = omega_vec[:, 2]

    else:
        # Try computing directly on cell data.
        deriv = mesh.compute_derivative(
            scalars=velocity_name,
            gradient=True,
            vorticity=True,
            preference="cell",
        )

        if "vorticity" not in deriv.cell_data:
            raise RuntimeError(
                f"PyVista did not produce a cell-data 'vorticity' array for {filename}"
            )

        omega_vec = np.asarray(deriv.cell_data["vorticity"])
        omega_z = omega_vec[:, 2]

    # Cell areas. For a 2D mesh, PyVista/VTK stores these in "Area".
    sized = mesh.compute_cell_sizes(
        length=False,
        area=True,
        volume=False,
    )

    if "Area" not in sized.cell_data:
        raise RuntimeError(f"Could not compute cell areas for {filename}")

    cell_area = np.asarray(sized.cell_data["Area"])

    if omega_z.shape[0] != cell_area.shape[0]:
        raise ValueError(
            f"omega_z and cell_area have different lengths in {filename}: "
            f"{omega_z.shape[0]} vs {cell_area.shape[0]}"
        )

    total_area = np.sum(cell_area)

    total_enstrophy = 0.5 * np.sum(omega_z**2 * cell_area)
    mean_enstrophy = total_enstrophy / total_area

    print(filename)
    print(np.sum(omega_z))
    print(total_area)
    print(total_enstrophy)
    print()


    return {
        "filename": str(filename),
        "time": get_time_value(mesh),
        "total_area": total_area,
        "total_enstrophy": total_enstrophy,
        "mean_enstrophy": mean_enstrophy,
        "omega_min": np.min(omega_z),
        "omega_max": np.max(omega_z),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Calculate total 2D enstrophy from VTU files."
    )

    # parser.add_argument(
    #     "files",
    #     nargs="+",
    #     help="Input VTU files, e.g. OUT_*.vtu",
    # )

    parser.add_argument(
        "--u-name",
        default="u",
        help="Name of x-velocity cell-data array. Default: u",
    )

    parser.add_argument(
        "--v-name",
        default="v",
        help="Name of y-velocity cell-data array. Default: v",
    )

    parser.add_argument(
        "--cell-gradient",
        action="store_true",
        help="Try computing derivative directly from cell data instead of converting to point data first.",
    )

    parser.add_argument(
        "--csv",
        default=None,
        help="Optional output CSV file.",
    )

    args = parser.parse_args()

    results = []

    root = Path()
    pattern = re.compile(r"OUT_\d+\.vtu$")
    args.files = [p for p in root.glob("OUT_*.vtu") if pattern.fullmatch(p.name)]
    args.files.sort(key=lambda x: int(x.name.split("_")[1].split(".")[0]))

    for fname in sorted(args.files):
        result = calculate_total_enstrophy(
            fname,
            u_name=args.u_name,
            v_name=args.v_name,
            use_point_gradient=not args.cell_gradient,
        )
        results.append(result)

        print(
            f"{Path(fname).name:30s} "
            f"time={result['time']:.8e} "
            f"area={result['total_area']:.8e} "
            f"enstrophy={result['total_enstrophy']:.8e} "
            f"mean_enstrophy={result['mean_enstrophy']:.8e} "
            f"omega_min={result['omega_min']:.8e} "
            f"omega_max={result['omega_max']:.8e}"
        )

    if args.csv is not None:
        import csv

        keys = [
            "filename",
            "time",
            "total_area",
            "total_enstrophy",
            "mean_enstrophy",
            "omega_min",
            "omega_max",
        ]

        with open(args.csv, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            writer.writerows(results)

        print(f"\nWrote {args.csv}")


if __name__ == "__main__":
    main()