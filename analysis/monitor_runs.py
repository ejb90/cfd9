#!/usr/bin/env python3
"""Monitor UCNS3D run directories."""

from __future__ import annotations

import argparse
import csv
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

FLOAT_RE = re.compile(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[EeDd][-+]?\d+)?")


@dataclass(frozen=True)
class SlurmJob:
    job_id: str
    state: str
    workdir: Path | None
    name: str
    elapsed_seconds: float | None = None


@dataclass(frozen=True)
class RunStatus:
    directory: Path
    mesh_cells: int | None
    target_time: float | None
    last_time: float | None
    status: str
    slurm_state: str
    job_id: str
    real_time_seconds: float | None


def parse_float(text: str) -> float | None:
    match = FLOAT_RE.search(text)
    if not match:
        return None
    return float(match.group(0).replace("D", "E").replace("d", "e"))


def find_run_dirs(roots: list[Path]) -> list[Path]:
    runs: set[Path] = set()
    for root in roots:
        root = root.resolve()
        if not root.exists():
            raise FileNotFoundError(root)
        for ucns3d_dat in root.rglob("UCNS3D.DAT"):
            run_dir = ucns3d_dat.parent
            if (run_dir / "grid.msh").is_file() or (run_dir / "grid.mesh").is_file():
                runs.add(run_dir)
    return sorted(runs)


def mesh_file(run_dir: Path) -> Path | None:
    for name in ("grid.msh", "grid.mesh"):
        path = run_dir / name
        if path.is_file():
            return path
    return None


def mesh_cell_count(run_dir: Path) -> int | None:
    path = mesh_file(run_dir)
    if path is None:
        return None

    total_re = re.compile(r"Total Number of Cells\s*:\s*(\d+)")
    cell_header_re = re.compile(r"^\(12\s+\(0\s+1\s+([0-9a-fA-F]+)\s+0\)")
    with path.open("r", encoding="ascii", errors="replace") as handle:
        for line in handle:
            match = total_re.search(line)
            if match:
                return int(match.group(1))
            match = cell_header_re.search(line.strip())
            if match:
                return int(match.group(1), 16)
    return None


def target_time(run_dir: Path) -> float | None:
    lines = (run_dir / "UCNS3D.DAT").read_text(errors="replace").splitlines()
    for idx, line in enumerate(lines):
        if "TOTAL SIMULATION TIME SECONDS" not in line:
            continue
        for candidate in lines[idx + 1 :]:
            value = parse_float(candidate)
            if value is not None:
                return value
    return None


def history_times(run_dir: Path) -> list[float]:
    path = run_dir / "history.txt"
    if not path.is_file():
        return []

    times = []
    patterns = (
        re.compile(r"finished writing output\s+(" + FLOAT_RE.pattern + r")"),
        re.compile(r"time step size\s+(" + FLOAT_RE.pattern + r")"),
    )
    with path.open("r", encoding="ascii", errors="replace") as handle:
        for line in handle:
            for pattern in patterns:
                match = pattern.search(line)
                if match:
                    times.append(float(match.group(1).replace("D", "E").replace("d", "e")))
                    break
    return times


def reduced_times(run_dir: Path) -> list[float]:
    path = run_dir / "reduced.dat"
    if not path.is_file():
        return []

    times = []
    with path.open("r", encoding="ascii", errors="replace") as handle:
        for line in handle:
            value = parse_float(line)
            if value is not None:
                times.append(value)
    return times


def last_solver_time(run_dir: Path) -> float | None:
    times = history_times(run_dir) + reduced_times(run_dir)
    return max(times) if times else None


def has_run_artifacts(run_dir: Path) -> bool:
    if (run_dir / "history.txt").is_file():
        return True

    artifact_patterns = (
        "OUT*.vtu",
        "OUT*.pvtu",
        "GRID*",
        "RESTART.dat",
        "reduced.dat",
        "ucns3d.out",
        "ucns3d.err",
        "errors.dat",
    )
    return any(next(run_dir.glob(pattern), None) is not None for pattern in artifact_patterns)


def parse_slurm_elapsed(value: str) -> float | None:
    """Parse Slurm's [[days-]hours:]minutes:seconds elapsed-time format."""
    try:
        days_text, separator, time_text = value.strip().partition("-")
        days = int(days_text) if separator else 0
        fields = (time_text if separator else days_text).split(":")
        if len(fields) == 2:
            hours = 0
            minutes, seconds = map(int, fields)
        elif len(fields) == 3:
            hours, minutes, seconds = map(int, fields)
        else:
            return None
    except ValueError:
        return None
    return float(days * 86_400 + hours * 3_600 + minutes * 60 + seconds)


def marker_timestamp(path: Path) -> float | None:
    """Read the ISO-8601 timestamp written by generated UCNS3D job scripts."""
    if not path.is_file():
        return None
    try:
        value = datetime.fromisoformat(path.read_text(encoding="ascii").strip().replace("Z", "+00:00"))
    except (OSError, ValueError):
        return None
    return value.timestamp()


def run_real_time(run_dir: Path, running_elapsed: float | None = None) -> float | None:
    """Return Slurm elapsed time or the elapsed duration between run markers."""
    if running_elapsed is not None:
        return running_elapsed
    started = marker_timestamp(run_dir / "start")
    if started is None:
        return None
    finished = marker_timestamp(run_dir / "done")
    return max((finished if finished is not None else time.time()) - started, 0.0)


def query_slurm(timeout: float = 10.0) -> tuple[dict[Path, SlurmJob], str | None]:
    command = ["squeue", "-h", "-o", "%i|%T|%Z|%j|%M"]
    try:
        result = subprocess.run(
            command,
            check=False,
            text=True,
            capture_output=True,
            timeout=timeout,
        )
    except FileNotFoundError:
        return {}, "squeue not found; running jobs cannot be detected"
    except subprocess.TimeoutExpired:
        return {}, f"squeue timed out after {timeout:g} seconds; running jobs cannot be detected"

    if result.returncode != 0:
        message = result.stderr.strip() or "squeue failed"
        return {}, message

    jobs = {}
    for line in result.stdout.splitlines():
        fields = line.rsplit("|", 1)
        if len(fields) != 2:
            continue
        job_fields = fields[0].split("|", 3)
        if len(job_fields) != 4:
            continue
        job_id, state, workdir_text, name = job_fields
        elapsed_seconds = parse_slurm_elapsed(fields[1])
        workdir = None
        if workdir_text and workdir_text != "N/A":
            try:
                workdir = Path(workdir_text).resolve()
            except OSError:
                workdir = Path(workdir_text).absolute()
        if workdir is not None:
            jobs[workdir] = SlurmJob(job_id, state, workdir, name, elapsed_seconds)
    return jobs, None


def reached_end_time(last_time: float | None, end_time: float | None, tolerance: float) -> bool:
    if last_time is None or end_time is None:
        return False
    allowed_shortfall = max(abs(end_time) * tolerance, tolerance)
    return last_time + allowed_shortfall >= end_time


def classify_run(run_dir: Path, slurm_jobs: dict[Path, SlurmJob], tolerance: float) -> RunStatus:
    cells = mesh_cell_count(run_dir)
    end_time = target_time(run_dir)
    last_time = last_solver_time(run_dir)
    started = (run_dir / "start").is_file() or has_run_artifacts(run_dir)
    slurm_job = slurm_jobs.get(run_dir.resolve())
    successful = started and reached_end_time(last_time, end_time, tolerance)

    if slurm_job is not None:
        status = "running"
    elif successful:
        status = "success"
    elif not started:
        status = "not started"
    else:
        status = "failed"

    real_time = run_real_time(
        run_dir,
        slurm_job.elapsed_seconds if status == "running" and slurm_job is not None else None,
    )

    return RunStatus(
        directory=run_dir,
        mesh_cells=cells,
        target_time=end_time,
        last_time=last_time,
        status=status,
        slurm_state=slurm_job.state if slurm_job else "",
        job_id=slurm_job.job_id if slurm_job else "",
        real_time_seconds=real_time,
    )


def format_value(value: object) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.8g}"
    return str(value)


def format_duration(value: float | None) -> str:
    if value is None:
        return "-"
    seconds = max(0, int(round(value)))
    days, seconds = divmod(seconds, 86_400)
    hours, seconds = divmod(seconds, 3_600)
    minutes, seconds = divmod(seconds, 60)
    prefix = f"{days}-" if days else ""
    return f"{prefix}{hours:02d}:{minutes:02d}:{seconds:02d}"


def colour_duration(value: str, status: str, enabled: bool) -> str:
    if not enabled or value == "-":
        return value
    colours = {"success": "32", "running": "33", "failed": "31"}
    colour = colours.get(status)
    return f"\033[{colour}m{value}\033[0m" if colour else value


def write_markdown(rows: list[RunStatus], handle, colour: bool = False) -> None:
    headers = ["directory", "mesh_cells", "status", "real_time", "target_time", "last_time", "slurm", "job_id"]
    table = [
        [
            str(row.directory),
            format_value(row.mesh_cells),
            row.status,
            format_duration(row.real_time_seconds),
            format_value(row.target_time),
            format_value(row.last_time),
            row.slurm_state or "-",
            row.job_id or "-",
        ]
        for row in rows
    ]
    widths = [
        max(len(headers[col]), *(len(row[col]) for row in table)) if table else len(headers[col])
        for col in range(len(headers))
    ]

    print("| " + " | ".join(headers[i].ljust(widths[i]) for i in range(len(headers))) + " |", file=handle)
    print("| " + " | ".join("-" * widths[i] for i in range(len(headers))) + " |", file=handle)
    for values, row in zip(table, rows, strict=True):
        cells = [value.ljust(widths[index]) for index, value in enumerate(values)]
        cells[3] = colour_duration(cells[3], row.status, colour)
        print("| " + " | ".join(cells) + " |", file=handle)


def write_csv(rows: list[RunStatus], handle) -> None:
    writer = csv.writer(handle)
    writer.writerow(
        ["directory", "mesh_cells", "status", "real_time_seconds", "target_time", "last_time", "slurm", "job_id"]
    )
    for row in rows:
        writer.writerow(
            [
                row.directory,
                row.mesh_cells,
                row.status,
                row.real_time_seconds,
                row.target_time,
                row.last_time,
                row.slurm_state,
                row.job_id,
            ]
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directories", nargs="+", type=Path)
    parser.add_argument("--output", "-o", type=Path, help="Write the table to this file.")
    parser.add_argument(
        "--format",
        choices=("markdown", "csv"),
        default="markdown",
        help="Output table format.",
    )
    parser.add_argument(
        "--tolerance",
        type=float,
        default=1.0e-6,
        help="Relative/absolute tolerance used when comparing last time to target time.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=10.0,
        metavar="SECONDS",
        help="Timeout for each subprocess command in seconds (default: 10).",
    )
    parser.add_argument(
        "--colour",
        choices=("auto", "always", "never"),
        default="auto",
        help="Colour the real-time field by run status (default: auto).",
    )
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("--timeout must be greater than zero")
    return args


def main() -> int:
    args = parse_args()
    slurm_jobs, slurm_warning = query_slurm(args.timeout)
    run_dirs = find_run_dirs(args.directories)
    rows = [classify_run(run_dir, slurm_jobs, args.tolerance) for run_dir in run_dirs]

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("w", newline="") as handle:
            if args.format == "csv":
                write_csv(rows, handle)
            else:
                write_markdown(rows, handle)
    else:
        if args.format == "csv":
            write_csv(rows, sys.stdout)
        else:
            colour = args.colour == "always" or (args.colour == "auto" and sys.stdout.isatty())
            write_markdown(rows, sys.stdout, colour=colour)

    if slurm_warning:
        print(f"warning: {slurm_warning}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
