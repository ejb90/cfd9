#!/bin/bash


if [[ -z $1 ]]; then
    git clone https://github.com/ejb90/cfd8-inputs.git
    inputs=$(pwd)/cfd8-inputs
else
    inputs=$1
fi

rundir=run-$(date -Iseconds)
mkdir $rundir
for i in $inputs/*.msh; do
    name=$(basename $(echo $i | rev | cut -c 5- | rev))
    mkdir $rundir/$name
    cp $inputs/{407.nml,MULTISPECIES.DAT,UCNS3D.DAT,ucns3d.jcf} $rundir/$name
    cp $i $rundir/$name/grid.msh
done