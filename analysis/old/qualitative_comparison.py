from pathlib import Path

import numpy as np

root = Path()
fnames = list(root.glob("OUT_*.vtu"))
fnames.sort(key=lambda x: int(x.name.split("_")[1].split(".")[0]))
data = np.loadtxt(root / "interfaces.csv", delimiter=",")
time = data[:, 0]
upstream = data[:, 1]
downstream = data[:, 2]
jet = data[:, 3]

for i, (upst, downst) in enumerate(zip(upstream, downstream, strict=True)):
    mid = (upst + downst) / 2.0
    lower = mid - 0.05
    upper = mid + 0.05
    print(
        f"/usr/local/visit/bin/visit -nowin -cli -s /home/ellis/Documents/cfd_msc/08_dissertation/cfd8/analysis/qualitative_comparison.visit.py {i + 1} {lower} {upper} < /dev/null"
    )
