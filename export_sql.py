#!/usr/bin/env python3
"""Export INSERT statements (seed data) from the validated SQLite DB in parent-first order.
usage: export_sql.py <db> <out.sql[.gz]>"""
import gzip, re, sqlite3, sys
import schema_def as S
db, out = sys.argv[1], sys.argv[2]
con = sqlite3.connect(db)
by_table = {t: [] for t in S.TABLES}
for line in con.iterdump():
    m = re.match(r'INSERT INTO "?(\w+)"? VALUES', line)
    if m:
        by_table[m.group(1)].append(line)
opener = gzip.open if out.endswith(".gz") else open
with opener(out, "wt", encoding="utf-8") as fh:
    fh.write("-- Seed data (parent tables first; FK-safe). Load after schema.sql.\nBEGIN TRANSACTION;\n")
    for t in S.TABLES:
        fh.write(f"-- {t}: {len(by_table[t])} rows\n")
        for line in by_table[t]:
            fh.write(line + "\n")
    fh.write("COMMIT;\n")
