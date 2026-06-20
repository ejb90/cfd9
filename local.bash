#!/bin/bash

mkdir build
cd build

if [[ $1 == "crescent" ]]; then
    module purge
    module load CMake
    # Fix for GKlib static library link on Crescent, for some reason?
    ln -s $HOME/local/lib64 $HOME/local/lib
fi

git clone https://github.com/KarypisLab/GKlib.git
make -C GKlib config cc=gcc
cd GKlib
make install
cd ..

if [[ $1 != "crescent" ]]; then
    git clone https://github.com/KarypisLab/METIS.git
    make -C METIS config cc=gcc
    cd METIS
    make install
    cd ..

    git clone https://github.com/KarypisLab/ParMETIS.git
    make -C ParMETIS config cc=mpicc
    cd ParMETIS
    make install
    cd ..
fi

# git clone git@github.com:ucns3d-team/UCNS3D.git
# git clone git@github.com:ucns3d-team/UCNS3D.git -b v4_gpu
# git clone git@github.com:ejb90/UCNS3D.git -b s421784
git clone git@github.com:ejb90/UCNS3D.git -b s421784_v4_gpu
cd UCNS3D/src
ln -sf ../bin/lib/tecplot/libtecio.a


if [[ $1 == "crescent" ]]; then
    # This seems to be (somewhat) performant but timestepping? is broken
    module use /apps/modules/all
    module load intel
    ln -sf ../../GKlib/build/Linux-x86_64/libGKlib.a
    ln -sf ../bin/lib/metis/libmetis.a
    ln -sf ../bin/lib/parmetis/libparmetis.a
    make -f ../bin/intel-compiler/Makefile clean all
elif [[ $1 == "crescent-v2" ]]; then
    # This is very slow but at least everything works
    module use /apps/modules/all
    module load OpenMPI
    ln -sf ../../GKlib/build/Linux-x86_64/libGKlib.a
    ln -sf ../../METIS/build/libmetis/libmetis.a
    ln -sf ../../ParMETIS/build/Linux-x86_64/libparmetis/libparmetis.a
    make -f ../bin/gnu-compiler/Makefile clean all
else
    # Works on WS/MALFI, is fast, works
    ln -sf ../../GKlib/build/Linux-x86_64/libGKlib.a
    ln -sf ../../METIS/build/libmetis/libmetis.a
    ln -sf ../../ParMETIS/build/Linux-x86_64/libparmetis/libparmetis.a
    make -f ../bin/gnu-compiler/Makefile clean all
fi