#!/usr/bin/env python3
"""Generate predefined UCNS3D mesh suites."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from make_channel_mesh import (
    DEFAULT_XMAX,
    DEFAULT_XMIN,
    DEFAULT_YMAX,
    DEFAULT_YMIN,
    DEFAULT_X_CENTER_MAX,
    DEFAULT_X_CENTER_MIN,
    linspace,
    piecewise_x,
    write_mesh,
)


@dataclass(frozen=True)
class MeshSpec:
    name: str
    y_cells: int
    x_left_cells: int
    x_center_cells: int
    x_right_cells: int
    reference_cells: int | None = None

    @property
    def x_cells(self) -> int:
        return self.x_left_cells + self.x_center_cells + self.x_right_cells

    @property
    def cell_count(self) -> int:
        return self.x_cells * self.y_cells

    @property
    def central_h(self) -> float:
        return (DEFAULT_YMAX - DEFAULT_YMIN) / self.y_cells


@dataclass(frozen=True)
class MeshSuite:
    name: str
    description: str
    specs: tuple[MeshSpec, ...]


PROVIDED_LIKE_SUITE = MeshSuite(
    name="provided_like",
    description="Cell counts close to the Pointwise meshes in ../cfd8-inputs.",
    specs=(
        MeshSpec("coarse", 39, 18, 117, 19, 6012),
        MeshSpec("medium", 64, 41, 192, 41, 17533),
        MeshSpec("fine", 121, 58, 363, 57, 57838),
        MeshSpec("2xfine", 242, 109, 726, 109, 228418),
        MeshSpec("4xfine", 321, 112, 963, 113, 381377),
        MeshSpec("8xfine", 642, 136, 1926, 136, 1411427),
    ),
)

HALVING_SUITE = MeshSuite(
    name="halving",
    description=(
        "Consistent sequence with total cells doubled each level; central "
        "edge size halves every other level."
    ),
    specs=(
        MeshSpec("mesh_6400", 40, 20, 120, 20),
        MeshSpec("mesh_12939", 57, 28, 171, 28),
        MeshSpec("mesh_25600", 80, 40, 240, 40),
        MeshSpec("mesh_50963", 113, 56, 339, 56),
        MeshSpec("mesh_102400", 160, 80, 480, 80),
        MeshSpec("mesh_204304", 226, 113, 678, 113),
        MeshSpec("mesh_409600", 320, 160, 960, 160),
        MeshSpec("mesh_820383", 453, 226, 1359, 226),
        MeshSpec("mesh_1638400", 640, 320, 1920, 320),
    ),
)

MESH_SUITES = {
    PROVIDED_LIKE_SUITE.name: PROVIDED_LIKE_SUITE,
    HALVING_SUITE.name: HALVING_SUITE,
}


def coordinates_for_spec(spec: MeshSpec) -> tuple[list[float], list[float]]:
    xs = piecewise_x(
        DEFAULT_XMIN,
        DEFAULT_XMAX,
        DEFAULT_X_CENTER_MIN,
        DEFAULT_X_CENTER_MAX,
        spec.x_cells,
        spec.x_left_cells,
        spec.x_center_cells,
        spec.x_right_cells,
    )
    ys = linspace(DEFAULT_YMIN, DEFAULT_YMAX, spec.y_cells)
    return xs, ys


def write_spec(spec: MeshSpec, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / f"{spec.name}.msh"
    xs, ys = coordinates_for_spec(spec)
    write_mesh(output, xs, ys)
    return output


def generate_mesh_suite(
    suite: MeshSuite,
    output_dir: Path,
    limit: int | None = None,
) -> list[Path]:
    specs = suite.specs if limit is None else suite.specs[:limit]
    written = []

    print(
        f"{'mesh':<12} {'ny':>8} {'left':>8} {'center':>8} {'right':>8} "
        f"{'cells':>10} {'central_h':>12} {'reference':>12} path"
    )
    for spec in specs:
        output = write_spec(spec, output_dir)
        reference = "-" if spec.reference_cells is None else str(spec.reference_cells)
        print(
            f"{spec.name:<12} {spec.y_cells:>8} {spec.x_left_cells:>8} "
            f"{spec.x_center_cells:>8} {spec.x_right_cells:>8} "
            f"{spec.cell_count:>10} {spec.central_h:>12.6g} "
            f"{reference:>12} {output}"
        )
        written.append(output)

    return written


def generate_mesh_cases(
    output_dir: Path,
    case: str = "all",
    limit: int | None = None,
) -> list[Path]:
    if case == "all":
        suites = tuple(MESH_SUITES.values())
    else:
        suites = (MESH_SUITES[case],)

    written = []
    for suite in suites:
        suite_dir = output_dir / suite.name if case == "all" else output_dir
        print(f"\n{suite.name}: {suite.description}")
        written.extend(generate_mesh_suite(suite, suite_dir, limit))
    return written


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--case",
        choices=("provided_like", "halving", "all"),
        default="all",
        help="Mesh suite to generate.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("meshing/generated"),
        help="Output directory.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Generate only the first N meshes from each selected suite.",
    )
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be positive")
    return args


def main() -> None:
    args = parse_args()
    generate_mesh_cases(args.output_dir, args.case, args.limit)


if __name__ == "__main__":
    main()
