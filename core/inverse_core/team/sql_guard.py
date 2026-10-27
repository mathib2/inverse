"""The read-only SQL guard every query passes through, Scout's and the run_sql tool's alike: one SELECT on the known obs.* tables,
nothing that writes, no second statement, no comment tricks. SCHEMA is the table description the agents see."""
from __future__ import annotations

import re


SCHEMA = """Tables (Zetaris, read-only; always the obs. prefix; text values in single quotes; no semicolon):
obs.equipment_table(equipment_id text like 'P-104' or 'T-200', name text, mass_kg number, baseline_dataset text: a dataset id or the text 'none', current_dataset text)
obs.sensors_table(sensor_id text like 'P104-DISP-1': a sensor named in the task is selected by sensor_id, equipment_id text, quantity text: 'x' is displacement and 'v' is velocity, unit text, sigma number = the noise level, sampling_hz number = the sampling rate)
obs.maintenance_table(record_id text like 'M-001', equipment_id text, date text 'YYYY-MM-DD', note text)
obs.p104_baseline_samples, obs.p104_current_samples, obs.trap_current_samples(dataset_id text, t number in seconds, x number, v number): use COUNT(*), MIN, MAX or AVG on these, never SELECT *.
Examples of the dialect: SELECT COUNT(*) AS n FROM obs.p104_baseline_samples | SELECT sigma, sampling_hz FROM obs.sensors_table WHERE equipment_id = 'P-104' AND quantity = 'x' | SELECT record_id, date, note FROM obs.maintenance_table WHERE equipment_id = 'P-104' ORDER BY date | SELECT equipment_id FROM obs.equipment_table WHERE baseline_dataset = 'none'"""

ALLOWED_TABLES = {"equipment_table", "sensors_table", "maintenance_table", "p104_baseline_samples", "p104_current_samples", "trap_current_samples"}

FORBIDDEN = re.compile(r"\b(insert|update|delete|drop|create|alter|truncate|merge|grant|cache|call|exec)\b|;|--|/\*"
                       r"|\b(reflect|java_method|input_file_name|transform|current_user|exec_java)\s*\(", re.I)   # Spark built-ins that reach the JVM

class UnsafeSQL(ValueError):
    pass

_CLAUSE_END = re.compile(r"(?i)\b(where|group\s+by|order\s+by|having|limit|union|on|inner|left|right|full|cross|join)\b")

def check_sql(sql):
    """Read-only, single statement, known tables only: every table reference after FROM or JOIN is checked, comma lists and
    aliases included (the clause runs to the next keyword), and subqueries are refused. Raises UnsafeSQL otherwise."""
    s = sql.strip().rstrip(";").strip()                       # one trailing semicolon is harmless; any other is refused below
    if not re.match(r"(?i)select\b", s) or FORBIDDEN.search(s):
        raise UnsafeSQL("only a single read-only SELECT is allowed")
    if re.search(r"(?i)`\s*(reflect|java_method|input_file_name|transform|current_user|exec_java)\s*`|\btry_(reflect|java_method)\s*\(", s):
        raise UnsafeSQL("only a single read-only SELECT is allowed")         # the JVM built-ins quoted in backticks, or as try_reflect
    tables = []
    for m in re.finditer(r"(?i)\b(?:from|join)\s+", s):
        rest = s[m.end():]
        end = _CLAUSE_END.search(rest)
        clause = rest[:end.start()] if end else rest
        if "(" in clause or ")" in clause:
            raise UnsafeSQL("subqueries and expressions are not allowed in FROM or JOIN")
        for item in clause.split(","):
            toks = item.strip().split()
            if not toks:
                raise UnsafeSQL("empty table reference")
            tables.append(re.sub(r"(?i)^obs\.", "", toks[0]))   # the first token is the table; what follows is an alias
    bad = [t for t in tables if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", t) or t not in ALLOWED_TABLES]
    if not tables or bad:
        raise UnsafeSQL(f"unknown table(s): {bad or 'none referenced'}")
    return s
