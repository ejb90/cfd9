from pathlib import Path
import re

import enstrophy


rundirs = [
    "/home/ellis/Documents/cfd_msc/08_dissertation/runs/mesh_convergence/try8/4xfine",
    "/home/ellis/Documents/cfd_msc/08_dissertation/runs/mesh_convergence/try8/fine",
    "/home/ellis/Documents/cfd_msc/08_dissertation/runs/fine_comp/4xfine_perturbation_0.0028_16",
    "/home/ellis/Documents/cfd_msc/08_dissertation/runs/sweep1/runs/He_0.0028_16",
]


for rundir in rundirs:
    rundir = Path(rundir)
    fnames = rundir.glob("OUT_*.vtu")
    fnames = [fname for fname in fnames if re.match(r"OUT_\d+\.vtu", fname.name)]
    enstrophy.calculate_total_enstrophy(fnames[20])