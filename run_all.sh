#!/usr/bin/env bash
# Full pipeline: generate -> validate -> export SQL -> reproducibility check.   Usage: ./run_all.sh [seed]
set -euo pipefail
SEED=${1:-20261022}
for cfg in "data_starter 0.05" "data_full 1.0"; do
  set -- $cfg; OUT=$1; SCALE=$2
  python3 generate_data.py --seed "$SEED" --scale "$SCALE" --out "$OUT"
  python3 validate_data.py "$OUT" "/tmp/$OUT.sqlite"
  if [ "$OUT" = data_full ]; then python3 export_sql.py "/tmp/$OUT.sqlite" "$OUT/seed_data.sql.gz"; else python3 export_sql.py "/tmp/$OUT.sqlite" "$OUT/seed_data.sql"; fi
  python3 check_reproducibility.py "$SEED" "$SCALE" "$OUT"
done
