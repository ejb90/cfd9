from pathlib import Path

import matplotlib.image as mpimg
import matplotlib.pyplot as plt
import numpy as np

element = "Kr"
index = 75


files = list(Path().glob(f"{element}_0.0*_*.png"))

amplitudes_strs = set([i.name.split("_")[1] for i in files])
numbers_strs = set([i.name.split("_")[2].split(".")[0] for i in files])
amplitudes = sorted([float(i) for i in amplitudes_strs])
numbers = sorted([int(i) for i in numbers_strs])
cols = len(numbers)
rows = len(amplitudes)

img = mpimg.imread(files[0])
h, w = img.shape[:2]
left_margin = 0.08
bottom_margin = 0.08
right_margin = 0.99
top_margin = 0.99
width = right_margin - left_margin
height = top_margin - bottom_margin

fig = plt.figure(figsize=(cols * w / 500, rows * h / 500))

for c, number in enumerate(numbers):
    for r, amplitude in enumerate(amplitudes):
        amplitude_str = [i for i in amplitudes_strs if np.isclose(float(i), amplitude)][0]
        number_str = [i for i in numbers_strs if int(i) == number][0]
        # f = [i for i in files if i.name == f"{element}_{amplitude_str}_{number_str}.png"][0]
        f = [i for i in files if i.name == f"{element}_{amplitude_str}_{number_str}_density_volfrac_{index}.png"][0]

        ax = fig.add_axes(
            [
                left_margin + c * width / cols,
                bottom_margin + (rows - 1 - r) * height / rows,
                width / cols,
                height / rows,
            ]
        )

        if c == 0:
            y = bottom_margin + (rows - r - 0.5) * height / rows
            fig.text(
                0.07,
                y,
                f"{amplitude}",
                rotation=90,
                va="center",
                ha="center",
                fontsize=8,
            )

        if r == cols - 1:
            x = left_margin + (c + 0.5) * width / cols
            fig.text(x, 0.07, f"{number}", va="center", ha="center", fontsize=8)

        ax.imshow(mpimg.imread(f))
        ax.axis("off")

fig.supxlabel("Number of Perturbations / ", fontsize=12)
fig.supylabel("Initial Amplitude / m", fontsize=12)

plt.subplots_adjust(left=0, right=1, bottom=0, top=1)
plt.tight_layout()
plt.savefig("montage.png", dpi=300, bbox_inches="tight", pad_inches=0)
plt.show()
