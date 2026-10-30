#!/usr/bin/env python3
"""Regenerate twice with the same seed/scale and compare per-file row counts and SHA-256 checksums."""
import hashlib, json, os, subprocess, sys, tempfile
seed, scale, ref = sys.argv[1], sys.argv[2], sys.argv[3]
def run(d):
    subprocess.run([sys.executable, "generate_data.py", "--seed", seed, "--scale", scale, "--out", d], check=True, capture_output=True)
    out = {}
    for fn in sorted(os.listdir(d)):
        if fn in ("source_manifest.json", "checksums.json"):
            continue
        b = open(os.path.join(d, fn), "rb").read()
        out[fn] = dict(rows=b.count(b"\n") - 1 if fn.endswith(".csv") else None, sha256=hashlib.sha256(b).hexdigest())
    return out
res = dict(seed=int(seed), scale=float(scale), runs={})
with tempfile.TemporaryDirectory() as t:
    for name in ("run_A", "run_B"):
        res["runs"][name] = run(os.path.join(t, name))
res["reference"] = {fn: dict(rows=(open(os.path.join(ref, fn), "rb").read().count(b"\n") - 1) if fn.endswith(".csv") else None,
                             sha256=hashlib.sha256(open(os.path.join(ref, fn), "rb").read()).hexdigest())
                    for fn in sorted(os.listdir(ref)) if fn in res["runs"]["run_A"]}
res["identical"] = res["runs"]["run_A"] == res["runs"]["run_B"] == res["reference"]
res["files_compared"] = len(res["reference"])
json.dump(res, open(os.path.join(ref, "reproducibility_check.json"), "w"), indent=1)
print("reproducible:", res["identical"], "files:", res["files_compared"])
sys.exit(0 if res["identical"] else 1)
