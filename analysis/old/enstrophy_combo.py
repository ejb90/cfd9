from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np

mpl.rcParams.update({"font.size": 16})


class Enstrophy:
    def __init__(self, csv):
        self._csv = csv
        self.time = []
        self.total_area = []
        self.total_enstrophy = []
        self.mean_enstrophy = []
        self.omega_min = []
        self.omega_max = []
    
        self.extract()
        self.sort()

    @property
    def order(self) -> int:
        try:
            return int(self._csv.parent.name[4:])
        except ValueError:
            return 5

    def extract(self):
        data = np.loadtxt(self._csv, delimiter=",", skiprows=1, usecols=(1, 2, 3, 4, 5, 6))
        self.time = data[:, 0]
        self.total_area = data[:, 1]
        self.total_enstrophy = data[:, 2]
        self.mean_enstrophy = data[:, 3]
        self.omega_min = data[:, 4]
        self.omega_max = data[:, 5]

    def sort(self):
        idx = np.argsort(self.time)
        self.time = self.time[idx]
        self.total_area = self.total_area[idx]
        self.total_enstrophy = self.total_enstrophy[idx]
        self.mean_enstrophy = self.mean_enstrophy[idx]
        self.omega_min = self.omega_min[idx]
        self.omega_max = self.omega_max[idx]

        print(self.time)

root = Path()
runs = [Enstrophy(fname) for fname in root.glob("WENO*/enstrophy.csv")]
runs.sort(key=lambda x: x.order)

# fine = Enstrophy(Path("/home/ellis/Documents/cfd_msc/08_dissertation/runs/mesh_convergence/try8/fine/enstrophy.csv"))
# finex2 = Enstrophy(Path("/home/ellis/Documents/cfd_msc/08_dissertation/runs/mesh_convergence/try8/2xfine/enstrophy.csv"))
finex4 = Enstrophy(Path("/home/ellis/Documents/cfd_msc/08_dissertation/runs/fine_comp/4xfine_perturbation_0.0028_16/enstrophy.csv"))

fig = plt.figure(figsize=(10, 10))
ax = fig.add_subplot(111)
ax.set_xlabel("Time / s")
ax.set_ylabel("Total Enstrophy / ")
ax.grid()

ax.plot(runs[0].time, runs[0].total_enstrophy, label=f"x1 Resolution, 3rd order")
ax.plot(runs[1].time, runs[1].total_enstrophy, label=f"x1 Resolution, 5th order")
ax.plot(runs[2].time, runs[2].total_enstrophy, label=f"x1 Resolution, 7th order")
ax.plot(finex4.time, finex4.total_enstrophy, ls="--", label="x4 Resolution, 5th order")

ax.legend()
plt.tight_layout()
plt.show()
fig.savefig("enstrophy_vs_time")



