Run the statements in `01_*.sql` then `02_*.sql` one at a time with `scripts/admin/zsql.py "<statement>"` (REST), or paste into the Zetaris SQL Editor.
`CACHE TABLE` right after each REST table: uncached REST tables re-fetch on every query. To refresh after changing obs-service data: `UNCACHE TABLE obs_rest.<t>; CACHE TABLE obs_rest.<t>;`
