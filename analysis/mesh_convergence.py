#!/usr/bin/env python3
"""Summarise UCNS3D mesh-convergence runs and plot compute scaling."""

from __future__ import annotations

import argparse
import math
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from monitor_runs import (
    classify_run,
    find_run_dirs,
    history_times,
    mesh_cell_count,
    mesh_file,
    query_slurm,
)

try:
    from rich.console import Console
    from rich.table import Table
except ImportError:  # pragma: no cover - fallback for minimal environments.
    Console = None
    Table = None


XMIN, XMAX = -0.05, 0.15
YMIN, YMAX = 0.0, 0.1
R_BUBBLE = 0.05
PPN = 16
DEFAULT_OUTPUT = Path("compute_scaling.png")

FLOAT_RE = re.compile(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[EeDd][-+]?\d+)?")
SBATCH_RE = re.compile(
    r"^\s*#SBATCH\s+--(?P<option>nodes|ntasks-per-node|cpus-per-task|ntasks)(?:=|\s+)(?P<value>\S+)",
    re.IGNORECASE,
)
SLURM_ENV_RE = re.compile(
    r"\b(?P<option>SLURM_NNODES|SLURM_JOB_NUM_NODES|SLURM_NTASKS_PER_NODE|SLURM_CPUS_PER_TASK|SLURM_NTASKS)\s*=\s*(?P<value>\S+)",
)


@dataclass(frozen=True)
class MeshStats:
    ncells: int
    mean_cell_size: float
    mean_cell_size_subset: float


def parse_positive_int(text: str) -> int | None:
    """Extract the leading positive integer from a scheduler resource value."""
    match = re.search(r"\d+", text)
    if not match:
        return None
    value = int(match.group())
    return value if value > 0 else None


def slurm_layout(values: dict[str, str]) -> tuple[int | None, int | None]:
    """Return (nodes, cores per node) from Slurm resource values."""
    nodes = parse_positive_int(values.get("nodes", ""))
    tasks_per_node = parse_positive_int(values.get("ntasks-per-node", ""))
    cpus_per_task = parse_positive_int(values.get("cpus-per-task", "")) or 1
    tasks = parse_positive_int(values.get("ntasks", ""))

    if tasks_per_node:
        return nodes or 1, tasks_per_node * cpus_per_task
    if tasks:
        nodes = nodes or 1
        return nodes, math.ceil(tasks / nodes) * cpus_per_task
    return nodes, None


def slurm_layout_from_jcf(path: Path) -> tuple[int | None, int | None]:
    """Read Slurm node and task requests from a job-control file."""
    values: dict[str, str] = {}
    with path.open(errors="replace") as handle:
        for line in handle:
            match = SBATCH_RE.match(line)
            if match:
                values[match.group("option").lower()] = match.group("value")
    return slurm_layout(values)


def slurm_layout_from_output(path: Path) -> tuple[int | None, int | None]:
    """Read echoed Slurm allocation variables from a scheduler output file."""
    option_names = {
        "SLURM_NNODES": "nodes",
        "SLURM_JOB_NUM_NODES": "nodes",
        "SLURM_NTASKS_PER_NODE": "ntasks-per-node",
        "SLURM_CPUS_PER_TASK": "cpus-per-task",
        "SLURM_NTASKS": "ntasks",
    }
    values: dict[str, str] = {}
    with path.open(errors="replace") as handle:
        for line in handle:
            match = SLURM_ENV_RE.search(line)
            if match:
                values[option_names[match.group("option")]] = match.group("value")
    return slurm_layout(values)


def timestamp_from_file(path: Path) -> datetime | None:
    """Read an ISO-8601 timestamp, falling back to the file modification time."""
    if not path.is_file():
        return None
    try:
        return datetime.fromisoformat(path.read_text(errors="replace").strip())
    except ValueError:
        return datetime.fromtimestamp(path.stat().st_mtime)


def elapsed_from_run_markers(run_dir: Path) -> float | None:
    """Estimate elapsed wall time from start and, when available, done markers."""
    started = timestamp_from_file(run_dir / "start")
    if started is None:
        return None
    finished = timestamp_from_file(run_dir / "done")
    now = datetime.now(started.tzinfo) if started.tzinfo else datetime.now()
    elapsed = (finished or now).timestamp() - started.timestamp()
    return max(elapsed, 0.0)


def parse_float(text: str) -> float | None:
    match = FLOAT_RE.search(text)
    if not match:
        return None
    return float(match.group(0).replace("D", "E").replace("d", "e"))


def parse_fluent_nodes(path: Path) -> list[tuple[float, float]]:
    nodes: list[tuple[float, float]] = []
    reading = False
    with path.open("r", encoding="ascii", errors="replace") as handle:
        for line in handle:
            if line.startswith("(10 (1 "):
                reading = True
                continue
            if reading and line.startswith("))"):
                break
            if reading:
                values = line.split()
                if len(values) >= 2:
                    try:
                        nodes.append((float(values[0]), float(values[1])))
                    except ValueError:
                        pass
    return nodes


def structured_subset_size(nodes: list[tuple[float, float]]) -> float | None:
    xs = sorted({round(x, 14) for x, _ in nodes})
    ys = sorted({round(y, 14) for _, y in nodes})
    if len(xs) * len(ys) != len(nodes):
        return None

    areas = []
    for x0, x1 in zip(xs, xs[1:]):
        xc = 0.5 * (x0 + x1)
        if not (XMIN <= xc <= XMAX):
            continue
        for y0, y1 in zip(ys, ys[1:]):
            yc = 0.5 * (y0 + y1)
            if YMIN <= yc <= YMAX:
                areas.append((x1 - x0) * (y1 - y0))
    if not areas:
        return None
    return math.sqrt(sum(areas) / len(areas))


def mesh_stats_from_plaintext(run_dir: Path) -> MeshStats:
    ncells = mesh_cell_count(run_dir) or 0
    path = mesh_file(run_dir)
    if path is None or ncells <= 0:
        return MeshStats(ncells=ncells, mean_cell_size=0.0, mean_cell_size_subset=0.0)

    nodes = parse_fluent_nodes(path)
    if not nodes:
        return MeshStats(ncells=ncells, mean_cell_size=0.0, mean_cell_size_subset=0.0)

    xs = [x for x, _ in nodes]
    ys = [y for _, y in nodes]
    domain_area = (max(xs) - min(xs)) * (max(ys) - min(ys))
    mean_cell_size = math.sqrt(domain_area / ncells) if domain_area > 0.0 else 0.0
    subset_size = structured_subset_size(nodes) or mean_cell_size
    return MeshStats(
        ncells=ncells,
        mean_cell_size=mean_cell_size,
        mean_cell_size_subset=subset_size,
    )


def mesh_stats_from_vtu(run_dir: Path, vtu_name: str) -> MeshStats | None:
    fname = run_dir / vtu_name
    if not fname.is_file():
        return None
    try:
        import pyvista as pv
    except ImportError:
        return None

    mesh = pv.read(fname)
    centers = mesh.cell_centers().points
    mask = (
        (centers[:, 0] >= XMIN)
        & (centers[:, 0] <= XMAX)
        & (centers[:, 1] >= YMIN)
        & (centers[:, 1] <= YMAX)
    )
    sized = mesh.compute_cell_sizes(area=True)
    subset = mesh.extract_cells(mask).compute_cell_sizes(area=True)
    areas = sized.cell_data["Area"]
    subareas = subset.cell_data["Area"]
    mean_size = math.sqrt(sum(areas) / len(areas)) if len(areas) else 0.0
    subset_size = math.sqrt(sum(subareas) / len(subareas)) if len(subareas) else mean_size
    return MeshStats(
        ncells=int(mesh.n_cells),
        mean_cell_size=mean_size,
        mean_cell_size_subset=subset_size,
    )


class Run:
    """Collected convergence/performance data for one UCNS3D run directory."""

    def __init__(
        self,
        dname: Path,
        name: str | None = None,
        ppn: int = PPN,
        use_vtu: bool = False,
        vtu_name: str = "OUT_0.vtu",
        slurm_jobs: dict | None = None,
        tolerance: float = 1.0e-6,
    ):
        self.dname = dname.resolve()
        self.name = name if name else self.dname.name
        self.ppn = ppn
        self.wtime = 0.0
        self.nodes = 0
        self.ncells = 0
        self.mean_cell_size = 0.0
        self.mean_cell_size_subset = 0.0
        self.bubble_ratio = 0.0
        self.finished_cleanly = False
        self.finished_time = False
        self.time: list[float] = []
        self.timestep: list[float] = []

        self.ncells2 = 0
        self.spatial_order = 0
        self.spatial_method = 0
        self.l0_norm = -1.0
        self.l1_norm_norm = -1.0
        self.stennorm = -1.0
        self.other = -1.0

        slurm_jobs = slurm_jobs or {}
        self.slurm_job = slurm_jobs.get(self.dname)
        self.status_row = classify_run(self.dname, slurm_jobs, tolerance)
        self.extract_wtime()
        self.extract_timestep()
        self.extract_proccount()
        self.extract_mesh_data(use_vtu=use_vtu, vtu_name=vtu_name)
        self.extract_finished()
        self.extract_errors()

    def extract_wtime(self) -> None:
        for fname in (self.dname / "fort.120", self.dname / "fort.123"):
            if not fname.is_file():
                continue
            with fname.open(errors="replace") as handle:
                for line in handle:
                    if "total time taken" in line:
                        values = [parse_float(part) for part in line.split()]
                        values = [value for value in values if value is not None]
                        if values:
                            self.wtime = values[-1]
                    elif self.wtime == 0.0:
                        value = parse_float(line)
                        if value is not None:
                            self.wtime = value
        if self.wtime > 0.0:
            return

        if self.slurm_job and self.slurm_job.elapsed_seconds and self.slurm_job.elapsed_seconds > 0.0:
            self.wtime = self.slurm_job.elapsed_seconds
            return

        self.wtime = elapsed_from_run_markers(self.dname) or 0.0

    def extract_mesh_data(self, use_vtu: bool, vtu_name: str) -> None:
        stats = mesh_stats_from_vtu(self.dname, vtu_name) if use_vtu else None
        if stats is None:
            stats = mesh_stats_from_plaintext(self.dname)
        self.ncells = stats.ncells
        self.mean_cell_size = stats.mean_cell_size
        self.mean_cell_size_subset = stats.mean_cell_size_subset
        self.bubble_ratio = (
            R_BUBBLE / self.mean_cell_size_subset if self.mean_cell_size_subset > 0.0 else 0.0
        )

    def extract_proccount(self) -> None:
        """Determine the allocation, preferring legacy qsub data when present."""
        fnames = sorted(
            self.dname.glob("mpi_nodes.*"),
            key=lambda path: int(path.suffix[1:]) if path.suffix[1:].isdigit() else -1,
        )
        if fnames:
            with fnames[-1].open(errors="replace") as handle:
                self.nodes = len([line for line in handle if line.strip()])
            return

        job_files = [
            path
            for pattern in ("*.jcf", "*.sbatch", "*.slurm")
            for path in sorted(self.dname.glob(pattern))
            if path.is_file()
        ]
        output_files = [
            path
            for pattern in ("slurm-*.out", "slurm-*.err", "out", "err")
            for path in sorted(self.dname.glob(pattern))
            if path.is_file()
        ]
        for parser, paths in (
            (slurm_layout_from_jcf, job_files),
            (slurm_layout_from_output, output_files),
        ):
            for path in paths:
                nodes, ppn = parser(path)
                if nodes is None and ppn is None:
                    continue
                if nodes is not None:
                    self.nodes = nodes
                if ppn is not None:
                    self.ppn = ppn
                return

    def extract_finished(self) -> None:
        self.finished_cleanly = self.status_row.status == "success"
        self.finished_time = self.status_row.status == "success"

    def extract_timestep(self) -> None:
        path = self.dname / "history.txt"
        if path.is_file():
            with path.open(errors="replace") as handle:
                for line in handle:
                    if "time step size" in line:
                        parts = line.split()
                        if len(parts) >= 2:
                            self.timestep.append(float(parts[0].replace("D", "E")))
                            self.time.append(float(parts[-1].replace("D", "E")))
        if not self.time:
            self.time = history_times(self.dname)

    def extract_errors(self) -> None:
        path = self.dname / "errors.dat"
        if path.is_file():
            with path.open(errors="replace") as handle:
                for line in handle:
                    parts = line.split()
                    if len(parts) < 7:
                        continue
                    self.ncells2 = int(parts[0])
                    self.spatial_order = int(parts[1]) + 1
                    self.spatial_method = int(parts[2])
                    self.l0_norm = float(parts[3])
                    self.l1_norm_norm = float(parts[4])
                    self.stennorm = float(parts[5])
                    self.other = float(parts[6])
        if not self.ncells2 and self.ncells:
            self.ncells2 = self.ncells

    @property
    def cores(self) -> int:
        return self.ppn * self.nodes

    @property
    def cpu_hours(self) -> float:
        return self.cores * self.wtime / 3600.0

    @property
    def performance_metric(self) -> float:
        return self.cpu_hours / self.ncells if self.ncells else 0.0

    @property
    def extrapolated_cpu_hours(self) -> float:
        last_time = self.status_row.last_time or (self.time[-1] if self.time else None)
        target_time = self.status_row.target_time
        if not last_time or not target_time:
            return 0.0
        return self.cpu_hours / last_time * target_time

    @property
    def extrapolated_performance_metric(self) -> float:
        return self.extrapolated_cpu_hours / self.ncells if self.ncells else 0.0


def print_table(runs: list[Run]) -> None:
    headers = (
        "Name",
        "Status",
        "Number of Cells",
        "Mean Cell Size",
        "Bubble Ratio",
        "Time / hr",
        "CPU.Hours /",
        "Extrap. CPU.Hours /",
        "Nodes",
        "Performance Metric",
        "Extrap. Performance Metric",
    )

    if Table and Console:
        table = Table(title="Mesh Statistics")
        for col in headers:
            table.add_column(col)
        for run in runs:
            style = "red" if run.status_row.status not in ("success", "running") else None
            table.add_row(*table_row(run), style=style)
        Console().print(table)
        return

    print("\t".join(headers))
    for run in runs:
        print("\t".join(table_row(run)))


def table_row(run: Run) -> tuple[str, ...]:
    return (
        run.name,
        run.status_row.status,
        f"{run.ncells}",
        f"{run.mean_cell_size_subset:.4e}",
        f"{run.bubble_ratio:.1f}",
        f"{run.wtime / 3600.0:.1f}",
        f"{run.cpu_hours:.1f}",
        f"{run.extrapolated_cpu_hours:.1f}",
        f"{run.nodes}",
        f"{run.performance_metric:.4f}",
        f"{run.extrapolated_performance_metric:.4f}",
    )


def plot_scaling(runs: list[Run], output: Path, show: bool = False) -> None:
    os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")
    try:
        import matplotlib as mpl
        import matplotlib.pyplot as plt
    except ImportError:
        print("warning: matplotlib is not installed; skipping plot", file=sys.stderr)
        return

    mpl.rcParams.update({"font.size": 16})

    valid = [run for run in runs if run.ncells2 > 0 and run.cpu_hours > 0.0]
    if not valid:
        print("warning: no runs have both cell counts and CPU hours; skipping plot", file=sys.stderr)
        return

    sfc = valid[0].cpu_hours / valid[0].ncells2**1.5
    fig = plt.figure(figsize=(15, 10))
    ax1 = fig.add_subplot(211)
    ax2 = fig.add_subplot(212)
    ax1.set_xlabel("Number of Cells /")
    ax1.set_ylabel("Compute / CPU.hrs")
    ax2.set_xlabel("Number of Cells /")
    ax2.set_ylabel("Efficiency (Idealised/Actual Compute ratio) /")

    cells = [run.ncells2 for run in valid]
    cpu_hours = [run.cpu_hours for run in valid]
    ideal = [sfc * ncells**1.5 for ncells in cells]
    ax1.plot(cells, cpu_hours, marker="o", label="Actual")
    ax1.plot(cells, ideal, marker="o", label="Optimal")
    ax2.plot(cells, [target / actual for target, actual in zip(ideal, cpu_hours)], marker="o", label="Scaling")

    for axis in (ax1, ax2):
        axis.semilogx()
        axis.grid()
        axis.legend()
    plt.tight_layout()
    fig.savefig(output)
    if show:
        plt.show()
    plt.close(fig)


def extract_data(args: argparse.Namespace) -> list[Run]:
    slurm_jobs, slurm_warning = query_slurm()
    if slurm_warning:
        print(f"warning: {slurm_warning}", file=sys.stderr)
    run_dirs = find_run_dirs(args.directories)
    runs = [
        Run(
            run_dir,
            ppn=args.ppn,
            use_vtu=args.use_vtu,
            vtu_name=args.vtu_name,
            slurm_jobs=slurm_jobs,
            tolerance=args.tolerance,
        )
        for run_dir in run_dirs
    ]
    runs.sort(key=lambda run: (run.ncells2 or run.ncells, run.name))
    return runs


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directories", nargs="*", type=Path, default=[Path(".")])
    parser.add_argument("--ppn", type=int, default=PPN, help="Cores per node.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Scaling plot output path.")
    parser.add_argument("--show", action="store_true", help="Show the scaling plot interactively.")
    parser.add_argument(
        "--use-vtu",
        action="store_true",
        help="Use PyVista/VTU geometry for exact subset cell-size statistics.",
    )
    parser.add_argument("--vtu-name", default="OUT_0.vtu", help="VTU file used with --use-vtu.")
    parser.add_argument("--tolerance", type=float, default=1.0e-6)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    runs = extract_data(args)
    print_table(runs)
    plot_scaling(runs, args.output, show=args.show)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
