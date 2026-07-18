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
import pickle
import shlex
import shutil
import signal
import subprocess
import sys
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
    executable: Path | None = None
    copy_executable: bool = False


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


class CampaignStoppedError(RuntimeError):
    """Raised after Slurm asks the serial optimisation controller to stop."""


_STOP_REQUESTED = False


def _request_stop(signum: int, _frame: object) -> None:
    global _STOP_REQUESTED
    _STOP_REQUESTED = True
    print(f"received signal {signum}; stopping the optimisation controller", flush=True)


def install_stop_handler() -> None:
    """Handle the advance warning sent before the controller wall-time limit."""
    for signal_name in ("SIGUSR1", "SIGTERM", "SIGINT"):
        if hasattr(signal, signal_name):
            signal.signal(getattr(signal, signal_name), _request_stop)


def stop_requested() -> bool:
    return _STOP_REQUESTED


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


def write_controller_script(
    *,
    driver: Path,
    argv: Sequence[str],
    work_dir: Path,
    wall_time: str = "72:00:00",
    partition: str = "serial",
) -> Path:
    """Write the one-core Slurm job which owns the optimiser and submits evaluations."""
    driver = driver.resolve()
    work_dir = work_dir.resolve()
    work_dir.mkdir(parents=True, exist_ok=True)
    forwarded = [argument for argument in argv if argument not in {"--launch", "--launch-controller"}]
    if "--submit" not in forwarded:
        forwarded.append("--submit")
    command = shlex.join([sys.executable, str(driver), *forwarded])
    lines = [
        "#!/usr/bin/env bash",
        "#SBATCH --job-name=optimisation-controller",
        "#SBATCH --comment=UCNS3D",
        "#SBATCH --nodes=1",
        "#SBATCH --ntasks-per-node=1",
        "#SBATCH --cpus-per-task=1",
        "#SBATCH --output=controller-%j.out",
        "#SBATCH --error=controller-%j.err",
        f"#SBATCH --time={wall_time}",
        "#SBATCH --mem-bind=local",
        f"#SBATCH --partition={partition}",
        "#SBATCH --mem=0",
        "#SBATCH --signal=B:USR1@300",
        "",
        "set -euo pipefail",
        "",
        "date -Iseconds > controller-start",
        "",
        "module purge",
        "module load gcc/12.3.0",
        "module load openmpi/4.1.6",
        "",
        f"cd {shlex.quote(str(driver.parents[1]))}",
        f"exec {command}",
        "",
    ]
    script = work_dir / "optimisation-controller.jcf"
    script.write_text("\n".join(lines), encoding="ascii")
    script.chmod(0o755)
    return script


def launch_controller(
    *,
    driver: Path,
    argv: Sequence[str],
    work_dir: Path,
    wall_time: str = "72:00:00",
    partition: str = "serial",
) -> str:
    """Write and submit the serial optimisation controller job."""
    script = write_controller_script(
        driver=driver,
        argv=argv,
        work_dir=work_dir,
        wall_time=wall_time,
        partition=partition,
    )
    result = subprocess.run(
        ["sbatch", "--parsable", script.name],
        cwd=script.parent,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"controller sbatch failed: {result.stderr.strip()}")
    job_id = result.stdout.strip().split(";", 1)[0]
    (script.parent / "controller_job_id").write_text(job_id + "\n", encoding="ascii")
    return job_id


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
    return Evaluation(index=index, generation=generation, point_index=point_index, run_dir=run_dir, x=np.array(x))


def submit(evaluation: Evaluation) -> Evaluation:
    result = subprocess.run(
        ["sbatch", "--parsable", "ucns3d.jcf"],
        cwd=evaluation.run_dir,
        text=True,
        capture_output=True,
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
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "squeue failed")
    active = {line.strip().split("_", 1)[0] for line in result.stdout.splitlines() if line.strip()}
    return job_ids & active


def cancel_jobs(evaluations: Sequence[Evaluation]) -> None:
    """Cancel evaluation jobs still owned by this controller."""
    job_ids = [evaluation.job_id for evaluation in evaluations if evaluation.job_id is not None]
    if not job_ids:
        return
    result = subprocess.run(
        ["scancel", *job_ids],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        print(f"warning: scancel failed: {result.stderr.strip()}", file=sys.stderr, flush=True)


def submit_and_wait(
    evaluations: Sequence[Evaluation],
    *,
    max_concurrent: int | None,
    poll_interval: float,
) -> list[Evaluation]:
    """Submit evaluations with a rolling concurrency limit and wait for all of them."""
    limit = max_concurrent or len(evaluations)
    waiting = list(evaluations)
    submitted: list[Evaluation] = []
    active: dict[str, Evaluation] = {}

    try:
        while waiting or active:
            if stop_requested():
                raise CampaignStoppedError

            while waiting and len(active) < limit:
                evaluation = submit(waiting.pop(0))
                if evaluation.job_id is None:
                    raise RuntimeError(f"sbatch returned no job ID for {evaluation.run_dir}")
                submitted.append(evaluation)
                active[evaluation.job_id] = evaluation

            if active:
                time.sleep(poll_interval)
                if stop_requested():
                    raise CampaignStoppedError
                running = running_job_ids(set(active))
                active = {job_id: evaluation for job_id, evaluation in active.items() if job_id in running}
    except CampaignStoppedError:
        cancel_jobs(list(active.values()))
        raise

    return submitted


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


def save_checkpoint(
    path: Path,
    *,
    algorithm: object,
    next_generation: int,
    evaluation_index: int,
    parameters: Sequence[Parameter],
    n_obj: int,
    population: int,
    algorithm_name: str,
) -> None:
    """Atomically save the optimiser after a completed generation."""
    payload = {
        "algorithm": algorithm,
        "next_generation": next_generation,
        "evaluation_index": evaluation_index,
        "parameters": tuple((parameter.name, parameter.lower, parameter.upper) for parameter in parameters),
        "n_obj": n_obj,
        "population": population,
        "algorithm_name": algorithm_name,
    }
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("wb") as handle:
        pickle.dump(payload, handle, protocol=pickle.HIGHEST_PROTOCOL)
    temporary.replace(path)


def load_checkpoint(
    path: Path,
    *,
    parameters: Sequence[Parameter],
    n_obj: int,
    population: int,
    algorithm_name: str,
) -> tuple[object, int, int]:
    """Load a checkpoint and reject incompatible study definitions."""
    with path.open("rb") as handle:
        payload = pickle.load(handle)  # noqa: S301 - checkpoint is a trusted local campaign file.
    expected_parameters = tuple((parameter.name, parameter.lower, parameter.upper) for parameter in parameters)
    checks = {
        "parameters": expected_parameters,
        "n_obj": n_obj,
        "population": population,
        "algorithm_name": algorithm_name,
    }
    for key, expected in checks.items():
        if payload.get(key) != expected:
            raise ValueError(f"checkpoint {key} does not match this study: {payload.get(key)!r} != {expected!r}")
    return payload["algorithm"], int(payload["next_generation"]), int(payload["evaluation_index"])


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
    resume: bool = False,
) -> None:
    from pymoo.core.problem import Problem

    if prepare_only and submit_jobs:
        raise ValueError("prepare_only and submit_jobs are mutually exclusive")
    if prepare_only and resume:
        raise ValueError("prepare_only and resume are mutually exclusive")
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
    checkpoint = work_dir / "optimiser-checkpoint.pkl"
    if resume:
        if not checkpoint.is_file():
            raise FileNotFoundError(f"no optimiser checkpoint found: {checkpoint}")
        algorithm, first_generation, evaluation_index = load_checkpoint(
            checkpoint,
            parameters=parameters,
            n_obj=n_obj,
            population=population,
            algorithm_name=algorithm_name,
        )
        print(f"resuming at generation {first_generation}", flush=True)
    else:
        if checkpoint.exists() and not prepare_only:
            raise FileExistsError(
                f"checkpoint already exists; pass --resume or choose another --work-dir: {checkpoint}"
            )
        problem = Problem(
            n_var=len(parameters),
            n_obj=n_obj,
            xl=np.array([parameter.lower for parameter in parameters], dtype=float),
            xu=np.array([parameter.upper for parameter in parameters], dtype=float),
        )
        algorithm = algorithm_from_name(algorithm_name, population)
        algorithm.setup(problem, seed=seed, verbose=False)
        first_generation = 0
        evaluation_index = 0
        if not prepare_only:
            save_checkpoint(
                checkpoint,
                algorithm=algorithm,
                next_generation=first_generation,
                evaluation_index=evaluation_index,
                parameters=parameters,
                n_obj=n_obj,
                population=population,
                algorithm_name=algorithm_name,
            )

    install_stop_handler()
    for generation in range(first_generation, generations):
        if stop_requested():
            print("controller stop requested before starting another generation", flush=True)
            return
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
            try:
                evaluations = submit_and_wait(
                    evaluations,
                    max_concurrent=max_concurrent,
                    poll_interval=poll_interval,
                )
            except CampaignStoppedError:
                print(
                    "controller wall time is ending; active evaluations were cancelled and the last completed "
                    "generation remains checkpointed",
                    flush=True,
                )
                return
        f_batch = evaluate_finished(evaluations, parameters, objective, n_obj, failure_penalty)
        infill.set("F", f_batch)
        algorithm.tell(infills=infill)
        np.savetxt(work_dir / f"generation_{generation:04d}_X.csv", x_batch, delimiter=",")
        np.savetxt(work_dir / f"generation_{generation:04d}_F.csv", f_batch, delimiter=",")
        save_checkpoint(
            checkpoint,
            algorithm=algorithm,
            next_generation=generation + 1,
            evaluation_index=evaluation_index,
            parameters=parameters,
            n_obj=n_obj,
            population=population,
            algorithm_name=algorithm_name,
        )
        print(f"finished generation {generation}: {len(evaluations)} evaluations")


def add_common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--work-dir", type=Path, default=Path("optimisation_runs"))
    parser.add_argument("--generations", type=int, default=1)
    parser.add_argument("--population", type=int, default=4)
    parser.add_argument("--algorithm", choices=("nsga2", "cmopso"), default="nsga2")
    parser.add_argument("--seed", type=int)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--submit", action="store_true", help="Submit each generated case with sbatch.")
    parser.add_argument(
        "--launch-controller",
        "--launch",
        action="store_true",
        help="Submit this driver as a three-day, one-core serial Slurm controller job.",
    )
    parser.add_argument("--controller-time", default="72:00:00")
    parser.add_argument("--controller-partition", default="serial")
    parser.add_argument("--poll-interval", type=float, default=60.0)
    parser.add_argument("--max-concurrent", type=int)
    parser.add_argument("--failure-penalty", type=float, default=1.0e30)
    parser.add_argument("--resume", action="store_true", help="Resume from the last completed-generation checkpoint.")
    parser.add_argument("--ucns3d", type=Path, help="Path to ucns3d_p; symlinked into each run directory.")
    parser.add_argument("--copy-executable", action="store_true")


def slurm_from_args(args: argparse.Namespace) -> SlurmSettings:
    return SlurmSettings(
        executable=args.ucns3d,
        copy_executable=args.copy_executable,
    )
