from pathlib import Path

from rich.console import Console
from rich.table import Table

from mesh_convergence import Run


def print_table(runs: list[Run]) -> None:
    table = Table(title="Mesh Statistics")

    for col in (
        "Name", 
        "Time / hr", 
        "CPU.Hours /", 
        "L0",
        "L1 (normalised)",
        "stennorm ???",
        "other ???"
        ):
        table.add_column(col)

    for run in runs:
        style = "red" if (not run.finished_cleanly or not run.finished_time) else None

        table.add_row(
            f"{run.spatial_order}",
            f"{run.wtime / 60.0 / 60.0:.1f}",
            f"{run.cpu_hours:.1f}",
            f"{run.l0_norm:.4f}",
            f"{run.l1_norm_norm:.4f}",
            f"{run.stennorm:.4f}",
            f"{run.other:.4f}",
            style=style,
        )

    console = Console()
    console.print(table)



if __name__ == "__main__":
    root = Path()
    runs = [Run(run) for run in root.glob("*/")]
    runs.sort(key=lambda x: x.dname.name)
    print_table(runs)