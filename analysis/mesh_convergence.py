import copy
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import pyvista as pv
from rich.console import Console
from rich.table import Table

# define region
XMIN, XMAX = -0.05, 0.15
YMIN, YMAX = 0.0, 0.1
ZMIN, ZMAX = -1e9, 1e9

R_BUBBLE = 0.05
FNAME = "OUT_0.vtu"
# FNAME = "PAR_0.pvtu"
PPN = 16
END_TIME = 0.000983


mpl.rcParams.update({"font.size": 16})


class Run:
    """"""

    def __init__(self, dname: Path, name: str | None = None):
        """"""
        self.dname = dname
        self.name = name if name else self.dname.name
        self.wtime = 0.0
        self.nodes = 0
        self.ppn = PPN
        self._mesh = None
        self.ncells = 0
        self.mean_cell_size = 0.0
        self.mean_cell_size_subset = 0.0
        self.bubble_ratio = 0.0
        self.finished_cleanly = False
        self.finished_time = False
        self.time = []
        self.timestep = []

        self.ncells2 = 0
        self.spatial_order = 0
        self.spatial_method = 0
        self.l0_norm = -1.0
        self.l1_norm_norm = -1.0
        self.stennorm = -1.0
        self.other = -1.0

        self.extract_wtime()
        self.extract_timestep()
        self.extract_proccount()
        self.extract_mesh_data()
        self.extract_finished_cleanly()
        self.extract_finished_on_time()
        self.extract_errors()
        

    def extract_wtime(self) -> None:
        """Extract time."""
        fname_time = self.dname / "fort.120"
        fname_time2 = self.dname / "fort.123"
        if fname_time.is_file():
            with open(fname_time) as fobj:
                for line in fobj:
                    if "total time taken" in line:
                        self.wtime = float(line.split()[-2])
        if fname_time2.is_file():
            with open(fname_time2) as fobj:
                self.wtime = float(fobj.readlines()[0])

    def extract_mesh_data(self) -> None:
        """Extract mesh data."""
        fname_out0 = self.dname / FNAME
        if fname_out0.is_file:
            self._mesh = pv.read(fname_out0)

            centers = self._mesh.cell_centers().points

            mask = (centers[:, 0] >= XMIN) & (centers[:, 0] <= XMAX) & (centers[:, 1] >= YMIN) & (centers[:, 1] <= YMAX)
            subset = self._mesh.extract_cells(mask)

            # Compute per-cell sizes
            sized = self._mesh.compute_cell_sizes(area=True)
            subsized = subset.compute_cell_sizes(area=True)

            # Python list of every 2D cell area
            areas = sized.cell_data["Area"].tolist()
            subareas = subsized.cell_data["Area"].tolist()

            self.ncells = len(areas)
            self.mean_cell_size = np.sqrt(np.mean(areas))
            self.mean_cell_size_subset = np.sqrt(np.mean(subareas))
            self.bubble_ratio = R_BUBBLE / self.mean_cell_size_subset
    
    def extract_proccount(self) -> None:
        """Extract performance data."""
        fnames_mpinodes = list(self.dname.glob("mpi_nodes.*"))
        fnames_mpinodes.sort(key=lambda x: int(x.suffix[1:]))
        if fnames_mpinodes:
            fname_mpinodes = fnames_mpinodes[-1]
            with open(fname_mpinodes) as fobj:
                lines = fobj.readlines()
                self.nodes = len([i for i in lines if i.strip()])
    
    def extract_finished_cleanly(self) -> None:
        """Finish cleanly?"""
        fnames_stdout = list(self.dname.glob("*.o*"))
        fnames_stdout.sort(key=lambda x: int(x.suffix[2:]))
        if fnames_stdout:
            fname_stdout = fnames_stdout[-1]
            with open(fname_stdout) as fobj:
                for line in fobj:
                    if "ucns3d finished running" in line:
                        self.finished_cleanly = True
                        break
    
    def extract_timestep(self) -> None:
        """extract timestep vs simulation time."""
        fname_history = self.dname / "history.txt"
        if fname_history.is_file():
            with open(fname_history) as fobj:
                for line in fobj:
                    if "time step size" in line:
                        self.time.append(float(line.split()[-1]))
                        self.timestep.append(float(line.split()[0]))

    def extract_finished_on_time(self) -> None:
        """Did the simulation reach the desired time? Turns out there's an internal wc."""
        self.finished_time = self.time[-1] + 2e-6 >= END_TIME

    def extract_errors(self) -> None:
        """Extract info from errors.dat."""
        fname_errors = self.dname / "errors.dat"
        if fname_errors.is_file():
            with open(fname_errors) as fobj:
                # WRITE(30,'(I9,1X,I4,1X,I4,1X,E14.7,1X,E14.7,1X,E14.7,1X,E14.7)')IMAXE,iorder,spatiladiscret,L0NORM,SQRT(L1NORM/TOTALVOLUME),STENNORM/IMAXE,(CPUX3(1)-CPUX2(1))*isize
                for line in fobj:
                    self.ncells2 = int(line.split()[0])
                    self.spatial_order = int(line.split()[1]) + 1
                    self.spatial_method = int(line.split()[2])
                    self.l0_norm = float(line.split()[3])
                    self.l1_norm_norm = float(line.split()[4])
                    self.stennorm = float(line.split()[5])
                    self.other = float(line.split()[6])
        
        if not self.ncells2 and self.ncells:
            self.ncells2 = self.ncells

    @property
    def cores(self):
        return self.ppn * self.nodes

    @property
    def cpu_hours(self):
        return self.cores * self.wtime / 60.0 / 60.0
    
    @property
    def performance_metric(self):
        return self.cpu_hours / self.ncells


    @property
    def extrapolated_cpu_hours(self):
        return self.cpu_hours / self.time[-1] * END_TIME
    
    @property
    def extrapolated_performance_metric(self):
        return self.extrapolated_cpu_hours / self.ncells


def print_table(runs: list[Run]) -> None:
    table = Table(title="Mesh Statistics")

    for col in (
        "Name", 
        "Number of Cells", 
        "Mean Cell Size",
        "Bubble Ratio", 
        "Time / hr", 
        "CPU.Hours /", 
        "Extrap. CPU.Hours /", 
        "Nodes", 
        "Performance Metric",
        "Extrap. Performance Metric"
        ):
        table.add_column(col)

    for run in runs:
        style = "red" if (not run.finished_cleanly or not run.finished_time) else None

        table.add_row(
            run.name,
            f"{run.ncells}",
            f"{run.mean_cell_size_subset:.4e}",
            f"{run.bubble_ratio:.1f}",
            f"{run.wtime / 60.0 / 60.0:.1f}",
            f"{run.cpu_hours:.1f}",
            f"{run.extrapolated_cpu_hours:.1f}",
            f"{run.nodes}",
            f"{run.performance_metric:.4f}",
            f"{run.extrapolated_performance_metric:.4f}",
            style=style,
        )
    
    console = Console()
    console.print(table)


# def plot_scaling(cruns, mruns):
#     """Plot compute performance scaling."""
#     sfc = cruns[0].cpu_hours / cruns[0].ncells2**1.5
#     sfm = mruns[0].cpu_hours / mruns[0].ncells2**1.5

#     fig = plt.figure(figsize=(15, 10))
#     ax1 = fig.add_subplot(211)
#     ax2 = fig.add_subplot(212)
#     ax1.set_xlabel("Number of Cells / ")
#     ax1.set_ylabel("Compute / CPU.hrs")
#     ax2.set_xlabel("Number of Cells / ")
#     ax2.set_ylabel("Efficiency (Idealised/Actual Compute ratio) /")

#     ax1.plot([r.ncells2 for r in cruns], [r.cpu_hours for r in cruns], label="Crescent2, Actual")
#     ax1.plot([r.ncells2 for r in cruns], [sfc * r.ncells2**1.5 for r in cruns], label="Cresent2, Optimal")
#     ax1.plot([r.ncells2 for r in mruns], [r.cpu_hours for r in mruns], label="MALFI, Actual")
#     ax1.plot([r.ncells2 for r in mruns], [sfm * r.ncells2**1.5 for r in mruns], label="MALFI, Optimal")

#     ax2.plot([r.ncells2 for r in cruns], [(sfc * r.ncells2**1.5) / r.cpu_hours for r in cruns], label="Cresent2 scaling")
#     ax2.plot([r.ncells2 for r in mruns], [(sfm * r.ncells2**1.5) / r.cpu_hours for r in mruns], label="MALFI scaling")
    
#     ax1.semilogx()
#     ax1.grid()
#     ax1.legend()
#     ax2.semilogx()
#     ax2.grid()
#     ax2.legend()
#     plt.tight_layout()
#     plt.show()
#     fig.savefig(f"compute_scaling")


def plot_scaling(runs):
    """Plot compute performance scaling."""
    sfc = runs[0].cpu_hours / runs[0].ncells2**1.5

    fig = plt.figure(figsize=(15, 10))
    ax1 = fig.add_subplot(211)
    ax2 = fig.add_subplot(212)
    ax1.set_xlabel("Number of Cells / ")
    ax1.set_ylabel("Compute / CPU.hrs")
    ax2.set_xlabel("Number of Cells / ")
    ax2.set_ylabel("Efficiency (Idealised/Actual Compute ratio) /")

    ax1.plot([r.ncells2 for r in runs], [r.cpu_hours for r in runs], label="Actual")
    ax1.plot([r.ncells2 for r in runs], [sfc * r.ncells2**1.5 for r in runs], label="Optimal")

    ax2.plot([r.ncells2 for r in runs], [(sfc * r.ncells2**1.5) / r.cpu_hours for r in runs], label="Scaling")
    
    ax1.semilogx()
    ax1.grid()
    ax1.legend()
    ax2.semilogx()
    ax2.grid()
    ax2.legend()
    plt.tight_layout()
    plt.show()
    fig.savefig(f"compute_scaling")



def build_malfi(runs):
    malfi = copy.deepcopy(runs)
    malfi[0].wtime = 14.0
    malfi[1].wtime = 45.0
    malfi[2].wtime = 275.0
    malfi[3].wtime = 2909.0
    malfi[4].wtime = 8218.0
    malfi[0].ppn = 64
    malfi[1].ppn = 128
    malfi[2].ppn = 128
    malfi[3].ppn = 128
    malfi[4].ppn = 128
    malfi[0].nodes = 1
    malfi[1].nodes = 1
    malfi[2].nodes = 1
    malfi[3].nodes = 1
    malfi[4].nodes = 1
    malfi[4].time = malfi[3].time
    malfi[4].finished_time = True
    return malfi

def extract_data():
    root = Path()
    runs = [Run(run) for run in root.glob("*/")]
    runs.sort(key=lambda x: x.ncells2)
    return runs


def print_results(runs):
    """Print compute scaling results."""
    print_table(runs)


if __name__ == "__main__":
    runs = extract_data()
    # malfi = build_malfi(runs)
    print_results(runs)
    # plot_scaling(runs, malfi)
    plot_scaling(runs)

