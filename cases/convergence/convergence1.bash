#!/usr/bin/env bash

set -euo pipefail

usage() {
    cat <<'EOF'
Usage: scripts/convergence1.bash [inputs_dir] [ucns3d_p]

Build a mesh-convergence run directory from an inputs repository.

Defaults:
  inputs_dir: ../cfd8-inputs
  ucns3d_p:   ./ucns3d_p

The inputs directory must contain:
  407.nml MULTISPECIES.DAT UCNS3D.DAT ucns3d.jcf *.msh
EOF
}

die() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

rewrite_job_name() {
    local job_file="$1"
    local job_name="$2"
    local tmp_file

    tmp_file="${job_file}.tmp"
    awk -v job_name="$job_name" '
        /^#SBATCH[[:space:]]+--job-name=/ {
            print "#SBATCH --job-name=" job_name
            done = 1
            next
        }
        { print }
        END {
            if (!done) {
                print "#SBATCH --job-name=" job_name
            }
        }
    ' "$job_file" > "$tmp_file"
    mv "$tmp_file" "$job_file"
}

case "${1:-}" in
    -h|--help)
        usage
        exit 0
        ;;
esac

inputs="${1:-../cfd8-inputs}"
ucns3d_exe="${2:-./ucns3d_p}"

[[ "$#" -le 2 ]] || {
    usage >&2
    exit 1
}

[[ -d "$inputs" ]] || die "Input directory not found: $inputs"
[[ -f "$ucns3d_exe" ]] || die "UCNS3D executable not found: $ucns3d_exe"
[[ -x "$ucns3d_exe" ]] || die "UCNS3D executable is not executable: $ucns3d_exe"

inputs="$(cd "$inputs" && pwd -P)"
ucns3d_exe="$(cd "$(dirname "$ucns3d_exe")" && pwd -P)/$(basename "$ucns3d_exe")"

for required in 407.nml MULTISPECIES.DAT UCNS3D.DAT ucns3d.jcf; do
    [[ -f "$inputs/$required" ]] || die "Required input file missing: $inputs/$required"
done

mapfile -t meshes < <(find "$inputs" -maxdepth 1 -type f -name '*.msh' | sort)
[[ "${#meshes[@]}" -gt 0 ]] || die "No .msh files found in $inputs"

profile="$(awk '
    /^EQUATIONS:/ {
        getline
        print $2
        exit
    }
' "$inputs/UCNS3D.DAT")"
[[ "$profile" == "407" ]] || die "UCNS3D.DAT initial condition profile is '$profile', expected 407"

rundir="run-$(date -Iseconds)"
mkdir -p "$rundir"

for mesh in "${meshes[@]}"; do
    mesh_file="$(basename "$mesh")"
    name="${mesh_file%.msh}"
    case_dir="$rundir/$name"

    mkdir -p "$case_dir"
    cp "$inputs/407.nml" "$case_dir/"
    cp "$inputs/MULTISPECIES.DAT" "$case_dir/"
    cp "$inputs/UCNS3D.DAT" "$case_dir/"
    cp "$inputs/ucns3d.jcf" "$case_dir/"
    cp "$ucns3d_exe" "$case_dir/ucns3d_p"
    cp "$mesh" "$case_dir/grid.msh"

    rewrite_job_name "$case_dir/ucns3d.jcf" "$name"
done

printf 'Created %s with %d mesh cases.\n' "$rundir" "${#meshes[@]}"
