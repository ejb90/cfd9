element=Kr
index=75

left=295
right=45
top=200
bottom=145

xstrings=()
ystrings=()
files=()
for i in 0.0 0.0004 0.0008 0.0012 0.0016 0.002 0.0024 0.0028; do
    for j in 2 4 8 16 32 64; do
        dir=${element}_${i}_${j}
        png=$dir/${element}_${i}_${j}_density_volfrac_${index}.png
        if [[ ! -d $dir  ]]; then
            echo $dir "missing, stopping"
            exit 1
        fi
        if [[ ! -f $png  ]]; then
            echo $png "missing, stopping"
            exit 1
        fi

        tmp="${element}_${i}_${j}_${index}.png"
        magick $png -crop $((1024-left-right))x$((1024-top-bottom))+$left+$top +repage $tmp
        files+=($tmp)

        if [[ $i == 0.0 ]]; then
            xstrings+=($j)
        fi

    done
    ystrings+=($i) 
done


# montage "${files[@]}" -tile 6x8 -geometry +0+0 ${element}_${index}.png
# rm "${files[@]}"

# magick "${element}_${index}.png" -background white -gravity west -splice 300x0 -gravity north -splice 0x300 -gravity south -splice 0x750 output.png


# xlabel=$(printf "%-38s" "${xstrings[@]}")
# ylabel=$(printf "%-36s" "${ystrings[@]}")

# magick output.png -gravity north -pointsize 100 -annotate +0+10 "Number of Perturbations" output.png
# magick output.png -gravity north -pointsize 60 -annotate +450+200 "${xlabel}" output.png

# magick \( -background white -fill black -pointsize 100 label:"Initial Amplitude" -rotate -90 -gravity north -splice 0x3000 \) output.png +append output.png
# magick \( -background white -fill black -pointsize 60 label:"${ylabel}" -rotate -90 -gravity north -splice 0x0 \) output.png +append output.png

