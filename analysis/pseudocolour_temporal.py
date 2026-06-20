from pathlib import Path

import matplotlib.image as mpimg
import matplotlib.pyplot as plt
import numpy as np

element = "He"

# root1 = Path(f"H_0.0_16")
root1 = Path("He_0.0028_16")
# root2 = Path("Kr_0.0_16")
root2 = Path("Kr_0.0028_16")
files1 = list(root1.glob("He_0.0*.png"))
files2 = list(root2.glob("Kr_0.0*.png"))
times = np.loadtxt(root1 / "interfaces.csv", delimiter=",")[:, 0]
files1.sort(key=lambda x: int(x.name.split("_")[-1].split(".")[0]))
files2.sort(key=lambda x: int(x.name.split("_")[-1].split(".")[0]))
files1 = files1[0::20]
files2 = files2[0::20]
times = times[0::20]

img = mpimg.imread(files1[0])
h, w = img.shape[:2]
left_margin = 0.14
bottom_margin = 0.08
right_margin = 0.99
top_margin = 0.99
width = right_margin - left_margin
height = top_margin - bottom_margin
rows = len(files1)
cols = 2


fig = plt.figure(figsize=(2 * w / 500, rows * h / 500))

for i in range(rows):
    ax = fig.add_axes(
        [
            left_margin + 0 * width / cols,
            bottom_margin + (rows - 1 - i) * height / rows,
            width / cols,
            height / rows,
        ]
    )

    ax.imshow(mpimg.imread(files1[i]))
    ax.axis("off")

    ax = fig.add_axes(
        [
            left_margin + 1 * width / cols,
            bottom_margin + (rows - 1 - i) * height / rows,
            width / cols,
            height / rows,
        ]
    )

    ax.imshow(mpimg.imread(files2[i]))
    ax.axis("off")

    y = bottom_margin + (rows - i - 0.5) * height / rows
    fig.text(0.11, y, f"{times[i]:.4f}", rotation=90, va="center", ha="center", fontsize=8)

x = left_margin + (0 + 0.5) * width / cols
fig.text(x, 0.07, "$a = 0.0$", va="center", ha="center", fontsize=8)
x = left_margin + (1 + 0.5) * width / cols
fig.text(x, 0.07, "$a = 0.0028$", va="center", ha="center", fontsize=8)


fig.supxlabel("Initial Amplitude / m", fontsize=12)
fig.supylabel("Time / s", fontsize=12)

plt.subplots_adjust(left=0, right=1, bottom=0, top=1)
plt.tight_layout()
plt.savefig("temporal.png", dpi=300, bbox_inches="tight", pad_inches=0)
plt.show()
