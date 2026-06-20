# cfd9
IRP

# UCNS3D

## Building

### Local Build

```
bash local.bash
```

## #Docker Build

N/A

## Running

```
cp build/UCNS3D/src/ucns3d_p .
cp path/to/inputs/{grid.msh,MULTISPECIES.DAT,UCNS3D.DAT} .
mpirun ./ucns3d_p
```
