from pathlib import Path

import pyvista as pv

for fname in Path().glob("PAR_*.pvtu"):
    print(fname)
    step = fname.name.split("_")[1].split(".")[0]
    meshes = [pv.read(f) for f in Path().glob(f"OUT_{step}_*.vtu")]
    combined = meshes[0].merge(meshes[1:])
    combined.save(f"OUT_{step}.vtu")


# meshes = [pv.read(f) for f in Path().glob(f"OUT_2071_*.vtu")]
# combined = meshes[0].merge(meshes[1:])
# combined.save("combined.vtu")
