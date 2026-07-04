#!/usr/bin/env python3
"""Small pymoo-to-Slurm bridge for UCNS3D studies.

The user-facing interface is intentionally Python, not JSON/YAML. A driver
script defines parameters, a case factory, and an objective parser; this module
handles pymoo ask/tell orchestration, case directory creation, Slurm submission,
and checkpoint files.
"""

from __future__ import annotations

import argparse
import csv
import shutil
import subprocess
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from cases.generate_cases import CaseConfig, generate_case


@dataclass(frozen=True)
class Parameter:
    name: str
    lower: float
    upper: float


@dataclass(frozen=True)
class SlurmSettings:
    command: str = "srun -n 2 ./ucns3d_p"
    executable: Path | None = None
    copy_executable: bool = False
    job_time: str = "24:00:00"
    partition: str | None = None
    ntasks: int = 2
    cpus_per_task: int = 1
    account: str | None = None
    extra_sbatch: tuple[str, ...] = ()


@dataclass(frozen=True)
class Evaluation:
    index: int
    generation: int
    point_index: int
    run_dir: Path
    x: np.ndarray
    job_id: str | None = None


CaseFactory = Callable[[dict[str, float], int], CaseConfig]
ObjectiveFunction = Callable[[Path, dict[str, float]], Sequence[float]]


def parameter_dict(parameters: Sequence[Parameter], x: Sequence[float]) -> dict[str, float]:
    return {parameter.name: float(value) for parameter, value in zip(parameters, x, strict=True)}


def write_parameter_table(path: Path, parameters: Sequence[Parameter], values: dict[str, float]) -> None:
    with path.open("w", encoding="ascii", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["parameter", "value", "lower", "upper"])
        for parameter in parameters:
            writer.writerow([parameter.name, values[parameter.name], parameter.lower, parameter.upper])


def stage_executable(run_dir: Path, settings: SlurmSettings) -> None:
    if settings.executable is None:
        return
    source = settings.executable.resolve()
    if not source.is_file():
        raise FileNotFoundError(f"UCNS3D executable not found: {source}")
    target = run_dir / source.name
    if target.exists() or target.is_symlink():
        target.unlink()
    if settings.copy_executable:
        shutil.copy2(source, target)
    else:
        target.symlink_to(source)


def write_slurm_script(run_dir: Path, settings: SlurmSettings, job_name: str) -> Path:
    lines = [
        "#!/usr/bin/env bash",
        f"#SBATCH --job-name={job_name}",
        "#SBATCH --nodes=1",
        f"#SBATCH --ntasks={settings.ntasks}",
        f"#SBATCH --cpus-per-task={settings.cpus_per_task}",
        f"#SBATCH --time={settings.job_time}",
        "#SBATCH --output=slurm-%j.out",
        "#SBATCH --error=slurm-%j.err",
    ]
    if settings.partition:
        lines.append(f"#SBATCH --partition={settings.partition}")
    if settings.account:
        lines.append(f"#SBATCH --account={settings.account}")
    lines.extend(f"#SBATCH {line}" for line in settings.extra_sbatch)
    lines.extend(
        [
            "",
            "set -euo pipefail",
            'cd "${SLURM_SUBMIT_DIR}"',
            "date -Iseconds > start",
            "rm -f Errors.dat errors.dat fort* GRID* history.tct history.txt OUT*.vtu OUT*.pvtu "
            "RESTART.dat ucns3d.err ucns3d.out pos*",
            f"{settings.command} > ucns3d.out 2> ucns3d.err",
            "date -Iseconds > done",
            "",
        ]
    )
    script = run_dir / "run_ucns3d.sbatch"
    script.write_text("\n".join(lines), encoding="ascii")
    script.chmod(0o755)
    return script


def prepare_evaluation(
    *,
    index: int,
    generation: int,
    point_index: int,
    x: np.ndarray,
    parameters: Sequence[Parameter],
    work_dir: Path,
    make_case: CaseFactory,
    slurm: SlurmSettings,
) -> Evaluation:
    values = parameter_dict(parameters, x)
    case_config = make_case(values, index)
    run_dir = work_dir / f"gen_{generation:04d}" / f"eval_{index:06d}"
    generate_case(run_dir.parent, case_config)
    generated_dir = run_dir.parent / case_config.name
    if generated_dir != run_dir:
        if run_dir.exists():
            raise FileExistsError(run_dir)
        generated_dir.rename(run_dir)
    write_parameter_table(run_dir / "parameters.csv", parameters, values)
    stage_executable(run_dir, slurm)
    write_slurm_script(run_dir, slurm, job_name=f"opt-{index:06d}")
    return Evaluation(index=index, generation=generation, point_index=point_index, run_dir=run_dir, x=np.array(x))


def submit(evaluation: Evaluation) -> Evaluation:
    result = subprocess.run(
        ["sbatch", "--parsable", "run_ucns3d.sbatch"],
        cwd=evaluation.run_dir,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"sbatch failed in {evaluation.run_dir}: {result.stderr.strip()}")
    job_id = result.stdout.strip().split(";", 1)[0]
    (evaluation.run_dir / "slurm_job_id").write_text(job_id + "\n", encoding="ascii")
    return Evaluation(
        index=evaluation.index,
        generation=evaluation.generation,
        point_index=evaluation.point_index,
        run_dir=evaluation.run_dir,
        x=evaluation.x,
        job_id=job_id,
    )


def running_job_ids(job_ids: set[str]) -> set[str]:
    if not job_ids:
        return set()
    result = subprocess.run(
        ["squeue", "-h", "-o", "%i"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "squeue failed")
    active = {line.strip().split("_", 1)[0] for line in result.stdout.splitlines() if line.strip()}
    return job_ids & active


def wait_for_jobs(evaluations: Sequence[Evaluation], poll_interval: float) -> None:
    pending = {evaluation.job_id for evaluation in evaluations if evaluation.job_id is not None}
    while pending:
        pending = running_job_ids(pending)
        if pending:
            time.sleep(poll_interval)


def evaluate_finished(
    evaluations: Sequence[Evaluation],
    parameters: Sequence[Parameter],
    objective: ObjectiveFunction,
    n_obj: int,
    failure_penalty: float,
) -> np.ndarray:
    rows = []
    for evaluation in evaluations:
        values = parameter_dict(parameters, evaluation.x)
        try:
            f = [float(value) for value in objective(evaluation.run_dir, values)]
        except Exception as exc:  # noqa: BLE001 - objective failures should penalise, not kill the campaign.
            (evaluation.run_dir / "objective_error.txt").write_text(str(exc) + "\n", encoding="utf-8")
            f = [failure_penalty] * n_obj
        if len(f) != n_obj:
            raise ValueError(f"objective returned {len(f)} values, expected {n_obj}: {evaluation.run_dir}")
        with (evaluation.run_dir / "objectives.csv").open("w", encoding="ascii", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow([f"f{i}" for i in range(n_obj)])
            writer.writerow(f)
        rows.append(f)
    return np.array(rows, dtype=float)


def algorithm_from_name(name: str, population: int):
    if name == "nsga2":
        from pymoo.algorithms.moo.nsga2 import NSGA2

        return NSGA2(pop_size=population)
    if name == "cmopso":
        from pymoo.algorithms.moo.cmopso import CMOPSO

        return CMOPSO(pop_size=population)
    raise ValueError(f"unknown algorithm: {name}")


def run_optimisation(
    *,
    parameters: Sequence[Parameter],
    make_case: CaseFactory,
    objective: ObjectiveFunction,
    n_obj: int,
    work_dir: Path,
    slurm: SlurmSettings,
    generations: int,
    population: int,
    algorithm_name: str = "nsga2",
    seed: int | None = None,
    prepare_only: bool = False,
    submit_jobs: bool = False,
    poll_interval: float = 60.0,
    max_concurrent: int | None = None,
    failure_penalty: float = 1.0e30,
) -> None:
    from pymoo.core.problem import Problem

    if prepare_only and submit_jobs:
        raise ValueError("prepare_only and submit_jobs are mutually exclusive")
    if not prepare_only and not submit_jobs:
        raise ValueError("pass --prepare-only to generate cases for inspection, or --submit to run them through Slurm")
    if generations < 1:
        raise ValueError("generations must be positive")
    if population < 1:
        raise ValueError("population must be positive")
    if n_obj < 1:
        raise ValueError("n_obj must be positive")
    if max_concurrent is not None and max_concurrent < 1:
        raise ValueError("max_concurrent must be positive")
    if poll_interval <= 0.0:
        raise ValueError("poll_interval must be positive")

    work_dir.mkdir(parents=True, exist_ok=True)
    problem = Problem(
        n_var=len(parameters),
        n_obj=n_obj,
        xl=np.array([parameter.lower for parameter in parameters], dtype=float),
        xu=np.array([parameter.upper for parameter in parameters], dtype=float),
    )
    algorithm = algorithm_from_name(algorithm_name, population)
    algorithm.setup(problem, seed=seed, verbose=False)

    evaluation_index = 0
    for generation in range(generations):
        infill = algorithm.ask()
        x_batch = np.asarray(infill.get("X"), dtype=float)
        evaluations = [
            prepare_evaluation(
                index=evaluation_index + i,
                generation=generation,
                point_index=i,
                x=x,
                parameters=parameters,
                work_dir=work_dir,
                make_case=make_case,
                slurm=slurm,
            )
            for i, x in enumerate(x_batch)
        ]
        evaluation_index += len(evaluations)

        if prepare_only:
            print(f"prepared generation {generation}: {len(evaluations)} cases")
            return

        if submit_jobs:
            submitted = []
            limit = max_concurrent or len(evaluations)
            for start in range(0, len(evaluations), limit):
                wave = [submit(evaluation) for evaluation in evaluations[start : start + limit]]
                submitted.extend(wave)
                wait_for_jobs(wave, poll_interval)
            evaluations = submitted
        f_batch = evaluate_finished(evaluations, parameters, objective, n_obj, failure_penalty)
        infill.set("F", f_batch)
        algorithm.tell(infills=infill)
        np.savetxt(work_dir / f"generation_{generation:04d}_X.csv", x_batch, delimiter=",")
        np.savetxt(work_dir / f"generation_{generation:04d}_F.csv", f_batch, delimiter=",")
        print(f"finished generation {generation}: {len(evaluations)} evaluations")


def add_common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--work-dir", type=Path, default=Path("optimisation_runs"))
    parser.add_argument("--generations", type=int, default=1)
    parser.add_argument("--population", type=int, default=4)
    parser.add_argument("--algorithm", choices=("nsga2", "cmopso"), default="nsga2")
    parser.add_argument("--seed", type=int)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--submit", action="store_true", help="Submit each generated case with sbatch.")
    parser.add_argument("--poll-interval", type=float, default=60.0)
    parser.add_argument("--max-concurrent", type=int)
    parser.add_argument("--failure-penalty", type=float, default=1.0e30)
    parser.add_argument("--ucns3d", type=Path, help="Path to ucns3d_p; symlinked into each run directory.")
    parser.add_argument("--copy-executable", action="store_true")
    parser.add_argument("--command", default="srun -n 2 ./ucns3d_p")
    parser.add_argument("--job-time", default="24:00:00")
    parser.add_argument("--partition")
    parser.add_argument("--ntasks", type=int, default=2)
    parser.add_argument("--cpus-per-task", type=int, default=1)
    parser.add_argument("--account")


def slurm_from_args(args: argparse.Namespace) -> SlurmSettings:
    return SlurmSettings(
        command=args.command,
        executable=args.ucns3d,
        copy_executable=args.copy_executable,
        job_time=args.job_time,
        partition=args.partition,
        ntasks=args.ntasks,
        cpus_per_task=args.cpus_per_task,
        account=args.account,
    )
