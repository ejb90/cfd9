"""Read the mesh with pyvista, extract number of cells, and the D_b/l ratio for mesh convergence.

If using .pvtu files from UCNS3D, there are two bugs, fix with:

sed -i 's/out_0/OUT_0/g' *.pvtu
sed -i 's/\bsource=/Source=/g' *.pvtu
"""

import pyvista as pv

# mesh = pv.read("OUT_0.vtu")
mesh = pv.read("PAR2_0.pvtu")
# mesh = pv.read("combined.vtu")

# # define region
# xmin, xmax = -0.05, 0.15
# ymin, ymax = 0.0, 0.1
# zmin, zmax = -1e9, 1e9   # ignore z for 2D meshes

# centers = mesh.cell_centers().points

# mask = (
#     (centers[:,0] >= xmin) & (centers[:,0] <= xmax) &
#     (centers[:,1] >= ymin) & (centers[:,1] <= ymax)
# )
# subset = mesh.extract_cells(mask)

# # Compute per-cell sizes
# sized = mesh.compute_cell_sizes(area=True)
# subsized = subset.compute_cell_sizes(area=True)

# # Python list of every 2D cell area
# areas = sized.cell_data["Area"].tolist()
# subareas = subsized.cell_data["Area"].tolist()

# print("Number of cells:", len(areas))
# # print("Min area:", np.min(areas))
# # print("Max area:", np.max(areas))
# # print("Mean area:", np.mean(areas))
# # print()
# # print("Number of cells:", len(subareas))
# # print("Min area:", np.min(subareas))
# # print("Max area:", np.max(subareas))
# # print("Mean area:", np.mean(subareas))

# # # Plot histogram
# # fig = plt.figure(figsize=(8, 12))
# # ax1 = fig.add_subplot(211)
# # ax2 = fig.add_subplot(212)
# # ax1.hist(areas, bins=50)
# # ax2.hist(subareas, bins=50)
# # ax1.set_xlabel("Cell area")
# # ax1.set_ylabel("Number of cells")
# # ax2.set_xlabel("Cell area")
# # ax2.set_ylabel("Number of cells (selected area)")
# # ax1.set_xlim(0, 1e-5)
# # ax2.set_xlim(0, 1e-5)
# # ax1.grid()
# # ax2.grid()

# # plt.show()

# rbubble = 0.05
# print(Path().resolve().name, len(areas), rbubble / np.sqrt(np.mean(subareas)))
