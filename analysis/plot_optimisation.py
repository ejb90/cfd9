#!/usr/bin/env python3
"""Plot the cumulative two-objective Pareto front from an optimisation campaign.

The default axes match ``water_air_single_bubble_driver.py``: maximise
``Ap95_target`` (stored as minimised ``F[:, 0]``) against minimised
``Mbad_target`` (``F[:, 1]``).
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

GENERATION_PATTERN = re.compile(r"generation_(\d+)_F\.csv$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work_dir", type=Path, help="campaign directory containing generation_XXXX_F.csv files")
    parser.add_argument(
        "--x-objective", type=int, default=1, metavar="INDEX", help="objective column for x (default: 1)"
    )
    parser.add_argument(
        "--y-objective", type=int, default=0, metavar="INDEX", help="objective column for y (default: 0)"
    )
    parser.add_argument("--x-output", metavar="NAME", help="named objective for the Pareto x-axis")
    parser.add_argument("--y-output", metavar="NAME", help="named objective for the Pareto y-axis")
    parser.add_argument("--left-output", metavar="NAME", help="named objective for the left design-space panel")
    parser.add_argument("--right-output", metavar="NAME", help="named objective for the right design-space panel")
    parser.add_argument(
        "--maximise",
        type=int,
        nargs="+",
        default=(0,),
        metavar="INDEX",
        help="objective columns stored with a negative sign for maximisation (default: 0)",
    )
    parser.add_argument(
        "--maximise-output",
        nargs="+",
        metavar="NAME",
        help="named outputs stored with a negative sign for maximisation",
    )
    parser.add_argument("--objective-names", nargs="+", metavar="NAME", help="objective names in F-column order")
    parser.add_argument("--parameter-names", nargs="+", metavar="NAME", help="parameter names in X-column order")
    parser.add_argument("--x-label", help="x-axis label (default: inferred from the objective index)")
    parser.add_argument("--y-label", help="y-axis label (default: inferred from the objective index)")
    parser.add_argument("--output", type=Path, help="PNG path (default: WORK_DIR/pareto_front.png)")
    parser.add_argument(
        "--design-output", type=Path, help="design-space PNG path (default: WORK_DIR/design_space.png)"
    )
    parser.add_argument(
        "--x-parameter", type=int, default=0, metavar="INDEX", help="parameter column for x (default: 0)"
    )
    parser.add_argument(
        "--y-parameter", type=int, default=1, metavar="INDEX", help="parameter column for y (default: 1)"
    )
    parser.add_argument("--x-input", metavar="NAME", help="named parameter for the design-map x-axis")
    parser.add_argument("--y-input", metavar="NAME", help="named parameter for the design-map y-axis")
    parser.add_argument("--x-parameter-label", help="design-map x-axis label")
    parser.add_argument("--y-parameter-label", help="design-map y-axis label")
    parser.add_argument("--dpi", type=int, default=220, help="PNG resolution (default: 220)")
    parser.add_argument(
        "--failure-penalty",
        type=float,
        default=1.0e30,
        help="exclude rows at this objective penalty (default: 1e30)",
    )
    args = parser.parse_args()
    if min(args.x_objective, args.y_objective, args.x_parameter, args.y_parameter) < 0:
        parser.error("objective and parameter indices must be non-negative")
    if args.x_objective == args.y_objective:
        parser.error("--x-objective and --y-objective must differ")
    if args.x_parameter == args.y_parameter:
        parser.error("--x-parameter and --y-parameter must differ")
    if args.dpi <= 0:
        parser.error("--dpi must be positive")
    if args.failure_penalty <= 0.0:
        parser.error("--failure-penalty must be positive")
    return args


def load_campaign(work_dir: Path, failure_penalty: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return parameter rows, objective rows, and zero-based generation numbers."""
    parameter_batches: list[np.ndarray] = []
    objective_batches: list[np.ndarray] = []
    generations: list[np.ndarray] = []
    for objective_path in sorted(work_dir.glob("generation_*_F.csv")):
        match = GENERATION_PATTERN.fullmatch(objective_path.name)
        if match is None:
            continue
        parameter_path = objective_path.with_name(f"generation_{match.group(1)}_X.csv")
        if not parameter_path.is_file():
            raise ValueError(f"missing parameter table for {objective_path}: {parameter_path}")
        objectives = np.atleast_2d(np.loadtxt(objective_path, delimiter=","))
        parameters = np.atleast_2d(np.loadtxt(parameter_path, delimiter=","))
        if len(parameters) != len(objectives):
            raise ValueError(f"parameter/objective row count differs for generation {match.group(1)}")
        valid = np.all(np.isfinite(parameters), axis=1) & np.all(np.isfinite(objectives), axis=1)
        valid &= np.all(np.abs(objectives) < failure_penalty, axis=1)
        if np.any(valid):
            parameter_batches.append(parameters[valid])
            objective_batches.append(objectives[valid])
            generations.append(np.full(np.count_nonzero(valid), int(match.group(1)), dtype=int))
    if not objective_batches:
        raise ValueError(f"no completed, unpenalised generation tables found in {work_dir}")
    return np.vstack(parameter_batches), np.vstack(objective_batches), np.concatenate(generations)


def non_dominated_2d(minimisation_values: np.ndarray) -> np.ndarray:
    """Return the cumulative non-dominated mask for a two-objective minimisation problem."""
    order = np.lexsort((minimisation_values[:, 1], minimisation_values[:, 0]))
    mask = np.zeros(len(minimisation_values), dtype=bool)
    best_second = np.inf
    position = 0
    while position < len(order):
        group_end = position + 1
        first = minimisation_values[order[position], 0]
        while group_end < len(order) and minimisation_values[order[group_end], 0] == first:
            group_end += 1
        group = order[position:group_end]
        group_best = np.min(minimisation_values[group, 1])
        if group_best < best_second:
            mask[group[minimisation_values[group, 1] == group_best]] = True
            best_second = group_best
        position = group_end
    return mask


def axis_label(index: int, maximise: set[int], supplied: str | None) -> str:
    if supplied:
        return supplied
    if index == 0:
        return "Ap95_target" if index in maximise else "F0"
    if index == 1:
        return "Mbad_target" if index not in maximise else "-F1"
    return f"{'-' if index in maximise else ''}F{index}"


def parameter_label(index: int, supplied: str | None) -> str:
    if supplied:
        return supplied
    if index == 0:
        return "Bubble density [kg m$^{-3}$]"
    if index == 1:
        return "Bubble radius [mm]"
    return f"Parameter {index}"


def column_names(provided: list[str] | None, count: int, defaults: tuple[str, ...], kind: str) -> list[str]:
    if provided is not None:
        if len(provided) != count:
            raise ValueError(
                f"--{kind}-names supplies {len(provided)} names but the campaign has {count} {kind} columns"
            )
        if len(set(provided)) != len(provided):
            raise ValueError(f"--{kind}-names must be unique")
        return provided
    if count == len(defaults):
        return list(defaults)
    return [f"{kind}_{index}" for index in range(count)]


def selected_column(name: str | None, index: int, names: list[str], option: str) -> int:
    if name is None:
        return index
    try:
        return names.index(name)
    except ValueError as exc:
        available = ", ".join(names)
        raise ValueError(f"{option} {name!r} is not available; choose from {available}") from exc


def main() -> None:
    args = parse_args()
    work_dir = args.work_dir.expanduser().resolve()
    if not work_dir.is_dir():
        raise SystemExit(f"campaign directory does not exist: {work_dir}")

    parameters, objectives, generation = load_campaign(work_dir, args.failure_penalty)
    if max(args.x_objective, args.y_objective) >= objectives.shape[1]:
        raise SystemExit(f"requested objective column is outside the {objectives.shape[1]} columns in {work_dir}")
    if max(args.x_parameter, args.y_parameter) >= parameters.shape[1]:
        raise SystemExit(f"requested parameter column is outside the {parameters.shape[1]} columns in {work_dir}")
    try:
        output_names = column_names(
            args.objective_names, objectives.shape[1], ("Ap95_target", "Mbad_target"), "objective"
        )
        input_names = column_names(
            args.parameter_names,
            parameters.shape[1],
            ("bubble_density_kg_m3", "bubble_radius_mm"),
            "parameter",
        )
        x_objective = selected_column(args.x_output, args.x_objective, output_names, "--x-output")
        y_objective = selected_column(args.y_output, args.y_objective, output_names, "--y-output")
        left_objective = selected_column(args.left_output, y_objective, output_names, "--left-output")
        right_objective = selected_column(args.right_output, x_objective, output_names, "--right-output")
        x_parameter = selected_column(args.x_input, args.x_parameter, input_names, "--x-input")
        y_parameter = selected_column(args.y_input, args.y_parameter, input_names, "--y-input")
        maximise = set(args.maximise)
        maximise.update(
            selected_column(name, 0, output_names, "--maximise-output") for name in args.maximise_output or ()
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    if x_objective == y_objective:
        raise SystemExit("selected x and y outputs must differ")
    if x_parameter == y_parameter:
        raise SystemExit("selected x and y inputs must differ")

    x_min = objectives[:, x_objective]
    y_min = objectives[:, y_objective]
    x = -x_min if x_objective in maximise else x_min
    y = -y_min if y_objective in maximise else y_min
    pareto = non_dominated_2d(np.column_stack((x_min, y_min)))

    x_objective_label = axis_label(x_objective, maximise, args.x_label or output_names[x_objective])
    y_objective_label = axis_label(y_objective, maximise, args.y_label or output_names[y_objective])

    fig, ax = plt.subplots(figsize=(8.0, 6.5), constrained_layout=True)
    points = ax.scatter(x, y, c=generation, cmap="viridis", s=30, alpha=0.7, linewidths=0, label="Evaluations")
    ax.scatter(
        x[pareto],
        y[pareto],
        facecolors="none",
        edgecolors="black",
        linewidths=1.1,
        s=82,
        label="Cumulative non-dominated set",
        zorder=3,
    )
    colourbar = fig.colorbar(points, ax=ax)
    colourbar.set_label("Generation")
    ax.set_xlabel(x_objective_label)
    ax.set_ylabel(y_objective_label)
    ax.set_title("Optimisation trade-off")
    ax.grid(True, alpha=0.25)
    ax.legend(loc="best")

    output = args.output.expanduser().resolve() if args.output else work_dir / "pareto_front.png"
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=args.dpi)

    design_output = args.design_output.expanduser().resolve() if args.design_output else work_dir / "design_space.png"
    design_output.parent.mkdir(parents=True, exist_ok=True)
    design_x = parameters[:, x_parameter]
    design_y = parameters[:, y_parameter]
    figure, axes = plt.subplots(1, 2, figsize=(13.0, 5.6), sharex=True, sharey=True, constrained_layout=True)
    for axis, objective, label in zip(
        axes,
        (left_objective, right_objective),
        (output_names[left_objective], output_names[right_objective]),
        strict=True,
    ):
        values = -objectives[:, objective] if objective in maximise else objectives[:, objective]
        map_points = axis.scatter(design_x, design_y, c=values, cmap="viridis", s=34, alpha=0.8, linewidths=0)
        axis.scatter(
            design_x[pareto],
            design_y[pareto],
            facecolors="none",
            edgecolors="black",
            linewidths=1.1,
            s=82,
            zorder=3,
        )
        colourbar = figure.colorbar(map_points, ax=axis)
        colourbar.set_label(label)
        axis.set_title(label)
        axis.grid(True, alpha=0.25)
    axes[0].set_ylabel(parameter_label(y_parameter, args.y_parameter_label or input_names[y_parameter]))
    for axis in axes:
        axis.set_xlabel(parameter_label(x_parameter, args.x_parameter_label or input_names[x_parameter]))
    figure.savefig(design_output, dpi=args.dpi)
    print(
        f"wrote {output} and {design_output} from {len(objectives)} evaluations; "
        f"{np.count_nonzero(pareto)} are non-dominated"
    )


if __name__ == "__main__":
    main()
