"""The answer that code assembles reads as sentences, not as a form: the accepted results as paragraphs without task labels,
the research expert's code-made rows as plain words, every number, id and citation kept. No model unless a test scripts one."""
import re

from inverse_core.team.expert import Task
from inverse_core.team.plan import Plan
from inverse_core.team.summary import digest
from inverse_core.team.words import answer_in_words, keeps_values, results_in_words, row_in_words

from fakes import crew, events


def mk(i, expert, answer, n_evidence=1):
    return Task(f"T{i}", "g", expert, status="done", result={"answer": answer, "confidence": 0.9, "assumptions": [], "not_checked": [],
                                                              "evidence": [{"type": "sql", "source": "q", "detail": f"{k} rows"} for k in range(n_evidence)]})


# The shapes round 27 produced (docs/evidence/bench/round27-planlane.json), as the experts' accepted answers.
REGISTRY = "P-104. Rows: equipment_id = P-104, baseline_dataset = p104-baseline [Q1]; equipment_id = T-200, baseline_dataset = none [Q1]"
SENSOR = "100. Rows: sampling_hz = 100, sigma = 0.01 [Q1]"
WEIGHT_ROWS = "Rows: mass_kg = 1.0 [Q1]; sigma = 0.01 [Q2]; sigma = 0.1 [Q2]"
WEIGHT = "The weight of P-104 is 9.81 newtons."
MAINTENANCE = ('The maintenance records for P-104 are:\n[{"record_id": "M-002", "date": "2026-10-05", "note": "[text withheld: matched injection pattern]"}, '
               '{"record_id": "M-001", "date": "2026-09-02", "note": "Routine inspection. Mount bolts torqued. Baseline vibration recorded."}]')
MEMORY = {"findings": ["reasoning: " + WEIGHT,                                                                                  # the round-27 memory, as the tool returned it: 'expert: claim', 200 characters each
                       "solver: Found and still standing: research: 0.01. Rows: sigma = 0.01, sampling_hz = 100 [Q1]; research: " + MAINTENANCE[:61],   # an earlier digest, cut
                       "research: 2", "reasoning: 122.625", "research: " + REGISTRY, "research: 400", "research: " + SENSOR, ("research: " + MAINTENANCE)[:200]],
          "refuted": []}


def no_writer(tmp_path):
    return crew(tmp_path, lambda m, msgs: (_ for _ in ()).throw(AssertionError("no model call expected")))


def test_one_result_is_its_answer_in_words(tmp_path):
    ctx, lead = no_writer(tmp_path)
    out = lead.compose(Plan("g", [mk(1, "research", SENSOR)]))
    assert out["answer"] == "The sampling rate is 100 Hz and the noise level is 0.01 [Q1]. [T1.E1]"
    assert set(out["citations"]) == {"T1.E1"} and not events(ctx, "llm")
    assert events(ctx, "compose")[0]["by_code"] is True and events(ctx, "compose")[0]["model"] is None and events(ctx, "compose")[0]["fallback"] is False


def test_two_short_results_are_paragraphs_without_task_labels(tmp_path):
    ctx, lead = no_writer(tmp_path)
    out = lead.compose(Plan("g", [mk(1, "research", WEIGHT_ROWS, 3), mk(2, "reasoning", WEIGHT, 2)]))
    assert out["answer"] == ("The mass is 1.0 kg [Q1]. The noise level is 0.01 [Q2]. The noise level is 0.1 [Q2]. [T1.E1] [T1.E2] [T1.E3]\n\n"
                             "The weight of P-104 is 9.81 newtons. [T2.E1] [T2.E2]")
    assert set(out["citations"]) == {"T1.E1", "T1.E2", "T1.E3", "T2.E1", "T2.E2"} and events(ctx, "compose")[0]["by_code"] is True


def test_three_results_with_a_number_the_writer_invented_are_assembled_by_code(tmp_path):
    ctx, lead = crew(tmp_path, lambda m, msgs: "P-104 weighs 9.81 N [T3.E1] and 32 days passed between its two maintenance records [T2.E1].")
    plan = Plan("Weight of P-104 and its maintenance records", [mk(1, "research", WEIGHT_ROWS, 3), mk(2, "research", MAINTENANCE), mk(3, "reasoning", WEIGHT)])
    out = lead.compose(plan)
    assert events(ctx, "compose_numbers_refused")[0]["numbers"] == ["32"]
    body, note = out["answer"].split("\n\n*(")
    assert body == ("The mass is 1.0 kg [Q1]. The noise level is 0.01 [Q2]. The noise level is 0.1 [Q2]. [T1.E1] [T1.E2] [T1.E3]\n\n"
                    "The maintenance records for P-104 are: For M-002, the date is 2026-10-05 and the note is [text withheld: matched injection pattern]. "
                    "For M-001, the date is 2026-09-02 and the note is Routine inspection. Mount bolts torqued. Baseline vibration recorded. [T2.E1]\n\n"
                    "The weight of P-104 is 9.81 newtons. [T3.E1]")
    assert "*(" + note == "*(The writer added a number no accepted result holds (32); this answer was assembled by code from the accepted results.)*"   # verbatim
    e = events(ctx, "compose")[0]
    assert e["by_code"] is True and e["fallback"] is True and "**T1" not in out["answer"]


def test_three_results_with_the_writer_down_are_assembled_by_code(tmp_path):
    ctx, lead = crew(tmp_path, lambda m, msgs: (_ for _ in ()).throw(RuntimeError("lane down")))
    out = lead.compose(Plan("g", [mk(1, "research", REGISTRY), mk(2, "research", SENSOR), mk(3, "reasoning", WEIGHT)]))
    assert out["answer"] == ("For P-104, the baseline dataset is p104-baseline [Q1]. For T-200, the baseline dataset is none [Q1]. [T1.E1]\n\n"
                             "The sampling rate is 100 Hz and the noise level is 0.01 [Q1]. [T2.E1]\n\n"
                             "The weight of P-104 is 9.81 newtons. [T3.E1]\n\n"
                             "*(The writer model was unavailable, RuntimeError; this summary was assembled by code from the accepted results.)*")
    e = events(ctx, "compose")[0]
    assert e["by_code"] is True and e["fallback"] is True and e["model"] is None


def test_the_writers_own_text_is_untouched(tmp_path):
    written = "P-104 weighs 9.81 N from its 1.0 kg mass [T3.E1] [T1.E1]; its records are dated 2026-09-02 and 2026-10-05 [T2.E1]."
    ctx, lead = crew(tmp_path, lambda m, msgs: written)
    out = lead.compose(Plan("g", [mk(1, "research", WEIGHT_ROWS, 3), mk(2, "research", MAINTENANCE), mk(3, "reasoning", WEIGHT)]))
    assert out["answer"] == written and events(ctx, "compose")[0]["by_code"] is False and events(ctx, "compose")[0]["fallback"] is False


def test_a_failed_task_is_reported_verbatim_after_the_answer_in_words(tmp_path):
    ctx, lead = no_writer(tmp_path)
    failed = Task("T2", "review", "vulnerability", status="failed", feedback="JSONDecodeError: Extra data: line 3 column 1 (char 155)")
    out = lead.compose(Plan("g", [mk(1, "research", SENSOR), failed]))
    assert out["answer"] == ("The sampling rate is 100 Hz and the noise level is 0.01 [Q1]. [T1.E1]"
                             "\n\n**Not completed**\n- T2 (vulnerability) failed: JSONDecodeError: Extra data: line 3 column 1 (char 155)")
    assert out["unfinished"] == [{"task": "T2", "expert": "vulnerability", "status": "failed", "why": "JSONDecodeError: Extra data: line 3 column 1 (char 155)"}]
    assert events(ctx, "compose")[0]["unfinished"] == 1 and events(ctx, "compose")[0]["by_code"] is True


def test_no_accepted_result_is_said_by_code(tmp_path):
    ctx, lead = no_writer(tmp_path)
    out = lead.compose(Plan("g", [Task("T1", "find it", "research", status="rejected", feedback="no rows")]))
    assert out["answer"].startswith("No task produced an accepted result.\n\n**Not completed**\n- T1 (research) rejected: no rows")
    assert events(ctx, "compose")[0]["by_code"] is True and events(ctx, "compose")[0]["fallback"] is True


def test_every_citation_and_number_present_before_is_present_after():
    """The labelled form the code made until now against the paragraphs: the same [Tn.En], the same [Qn], the same numbers and ids."""
    tasks = [mk(1, "research", REGISTRY), mk(2, "research", SENSOR), mk(3, "research", WEIGHT_ROWS, 3), mk(4, "reasoning", WEIGHT, 2),
             mk(5, "research", MAINTENANCE), mk(6, "research", "400", 2), mk(7, "reasoning", "122.625")]
    before = "\n\n".join(f"**{t.id} ({t.expert})**: {t.result['answer']} " + " ".join(f"[{t.id}.E{i}]" for i in range(1, len(t.result["evidence"]) + 1)) for t in tasks)
    after = results_in_words(tasks)
    assert sorted(re.findall(r"\[T\d+\.E\d+\]", before)) == sorted(re.findall(r"\[T\d+\.E\d+\]", after))
    assert sorted(re.findall(r"\[Q\d+\]", before)) == sorted(re.findall(r"\[Q\d+\]", after))
    for tok in ("P-104", "T-200", "p104-baseline", "none", "100", "0.01", "1.0", "0.1", "9.81", "M-002", "M-001", "2026-10-05", "2026-09-02", "400", "122.625"):
        assert tok in after, tok
    assert keeps_values(before, after) and "**T" not in after and after.split("\n\n")[5] == "400 [T6.E1] [T6.E2]"   # a bare number alone stays as it is
    assert [p.split(" [")[0][:12] for p in after.split("\n\n")][:3] == ["For P-104, t", "The sampling", "The mass is "]   # task order


def test_the_bare_token_in_front_of_the_rows_goes_only_when_the_sentences_hold_it():
    assert answer_in_words(SENSOR) == "The sampling rate is 100 Hz and the noise level is 0.01 [Q1]."
    assert answer_in_words("0.01. Rows: sigma = 0.01, sampling_hz = 100 [Q1]") == "The noise level is 0.01 and the sampling rate is 100 Hz [Q1]."
    assert answer_in_words(REGISTRY) == "For P-104, the baseline dataset is p104-baseline [Q1]. For T-200, the baseline dataset is none [Q1]."
    assert answer_in_words("200. Rows: sampling_hz = 100, sigma = 0.01 [Q1]") == "200. The sampling rate is 100 Hz and the noise level is 0.01 [Q1]."   # 200 is nowhere else
    assert answer_in_words("100. Rows: sampling_hz = 1000 [Q1]") == "100. The sampling rate is 1000 Hz [Q1]."                                       # 100 is not 1000
    assert answer_in_words("The sensor runs at 100 Hz. Rows: sampling_hz = 100, sigma = 0.01 [Q1]") == \
        "The sensor runs at 100 Hz. The sampling rate is 100 Hz and the noise level is 0.01 [Q1]."                                                 # a sentence in front stays


def test_rows_the_code_cannot_read_whole_are_kept_as_they_came():
    cut = "P-104. Rows: equipment_id = P-104, baseline_dataset = p104-baseline [Q1]; equipment_id = T-200, baseline_dat"   # cut at the 320-char cap
    assert answer_in_words(cut) == cut
    nested = 'Records: [{"record_id": "M-002", "extra": {"a": 1}}]'
    assert answer_in_words(nested) == nested
    cut_digest = "Found and still standing: research: 0.01. Rows: sigma = 0.01, sampling_hz = 100 [Q1]; research: 2. Ruled out: nothing yet."   # no closing: not a whole digest
    assert answer_in_words(cut_digest) == cut_digest
    assert answer_in_words("Rows: note = a = b [Q1]") == "Rows: note = a = b [Q1]"
    for plain in ("400", "122.625", WEIGHT, "Reviewed core/inverse_core/team/tools.py: the fixed-rule scan found no pattern hit in 1 file(s), so no weakness is claimed.", ""):
        assert answer_in_words(plain) == plain


def test_a_row_is_one_sentence_in_the_schemas_words():
    assert row_in_words({"sensor_id": "T200-DISP-1", "equipment_id": "T-200", "quantity": "x", "unit": "m", "sigma": 0.1, "sampling_hz": 100}, "[Q1]") == \
        "For T200-DISP-1, the equipment is T-200, the quantity is x, the unit is m, the noise level is 0.1 and the sampling rate is 100 Hz [Q1]."
    assert row_in_words({"equipment_id": "P-104"}, "[Q1]") == "Equipment P-104 [Q1]."
    assert row_in_words({"count(*)": 400}) == "The count is 400."
    assert row_in_words({"mass_kg": None}) == "The mass is none."                                                  # a missing value is said plainly, no unit
    assert row_in_words({"record_id": "M-001", "note": "Mount bolts torqued."}) == "For M-001, the note is Mount bolts torqued."
    assert answer_in_words(MAINTENANCE) == ("The maintenance records for P-104 are: For M-002, the date is 2026-10-05 and the note is [text withheld: matched injection pattern]. "
                                            "For M-001, the date is 2026-09-02 and the note is Routine inspection. Mount bolts torqued. Baseline vibration recorded.")


def test_a_memory_digest_is_a_list_of_findings_in_words(tmp_path):
    """The summary case's answer is the summary Ada reads out of the memory by code (team/summary.py): one plain sentence per
    finding under "What the crew found", newest first, each once, the earlier digest among round 27's findings never said again;
    what was ruled out the same way. It is already in words, so the final answer keeps it as it is, with its citations added
    by code: every value and citation the reviewer saw is in the answer."""
    text = digest(MEMORY)
    assert text == ("What the crew found:\n"
                    "- Scout found that the maintenance records for P-104 are: the record M-002 has the date 2026-10-05 and the note [text withheld: matched injection pattern]; "
                    "the record M-001 has the date 2026-09-02 (cut off).\n"                                                       # cut by the memory tool: its whole records, the cut marked
                    "- Scout found that the sampling rate is 100 Hz and the noise level is 0.01 [Q1].\n"
                    "- Scout answered 400.\n"
                    "- Scout found that the machine P-104 has the baseline dataset p104-baseline [Q1]; the machine T-200 has no baseline dataset [Q1].\n"
                    "- Euler answered 122.625.\n"
                    "- Scout answered 2.\n"
                    "- Euler found that the weight of P-104 is 9.81 newtons.\n\n"                                                 # the earlier digest is not a finding: its parts are, each said once
                    "What was ruled out: nothing yet.\n\n"
                    "Nothing is marked unchecked.")
    words = answer_in_words(text)
    assert words == text and keeps_values(text, words) and "Found and still standing" not in words
    for tok in ("9.81", "0.01", "100", "2026-10-05", "2", "122.625", "P-104", "p104-baseline", "T-200", "400", "M-001", "2026-09-02"):
        assert tok in words, tok
    ruled = digest({"findings": ["research: " + SENSOR], "refuted": ["reasoning: The weight of P-104 is 10.0 newtons.", "research: 2"]})
    assert answer_in_words(ruled) == ruled == ("What the crew found:\n- Scout found that the sampling rate is 100 Hz and the noise level is 0.01 [Q1].\n\n"
                                               "What was ruled out:\n- Euler said the weight of P-104 is 10.0 newtons; it was refuted.\n- Scout said 2; it was refuted.\n\n"
                                               "Nothing is marked unchecked.")
    assert answer_in_words(digest({})) == "What the crew found: nothing yet.\n\nWhat was ruled out: nothing yet.\n\nNothing is marked unchecked."
    old = "Found and still standing: research: 400; reasoning: 122.625. Ruled out: nothing yet. Still unchecked: nothing else is recorded in the shared memory."
    assert answer_in_words(old) == ("Found and still standing:\n- 400 (research).\n- 122.625 (reasoning).\n\nRuled out: nothing yet.\n\n"
                                    "Still unchecked: nothing else is recorded in the shared memory.")                             # the shape before summary.py, as a saved mission may hold it
    ctx, lead = no_writer(tmp_path)                                                                                             # the summary mission: one solver task, composed by code
    out = lead.compose(Plan("Summarize what the crew has found and ruled out so far.", [mk(1, "solver", text)]))
    assert out["answer"] == words + " [T1.E1]" and set(out["citations"]) == {"T1.E1"} and events(ctx, "compose")[0]["by_code"] is True


def test_a_count_column_is_a_count_and_a_unit_follows_only_a_number():
    """'Rows: n = 2 [Q1]' is the most common count shape in the saved evidence (SELECT COUNT(*) AS n, the dialect's own example)."""
    assert answer_in_words("2. Rows: n = 2 [Q1]; equipment_id = P-104 [Q2]") == "The count is 2 [Q1]. Equipment P-104 [Q2]."
    assert answer_in_words("2 sensors. Rows: n = 2 [Q1]; sensor_id = P104-DISP-1 [Q2]") == "2 sensors. The count is 2 [Q1]. Sensor P104-DISP-1 [Q2]."
    assert row_in_words({"n_samples": 400}, "[Q1]") == "The number of samples is 400 [Q1]."
    assert row_in_words({"count": 3}) == "The count is 3." and row_in_words({"total": 5}) == "The total is 5."
    assert row_in_words({"sampling_hz": "unknown"}) == "The sampling rate is unknown." and row_in_words({"mass_kg": "1e-3"}) == "The mass is 1e-3 kg."


def test_an_aggregate_is_said_over_its_column_and_a_null_id_is_not_the_subject():
    """min(date) and avg(mass_kg) are in the saved evidence: the function in a word, the column in the schema's words, its unit kept."""
    assert answer_in_words("Rows: avg(mass_kg) = 1.0 [Q1]") == "The average mass is 1.0 kg [Q1]."
    assert row_in_words({"min(date)": "2026-09-02", "max(date)": "2026-10-05"}) == "The earliest date is 2026-09-02 and the latest date is 2026-10-05."
    assert row_in_words({"sum(n)": 5}) == "The total count is 5." and row_in_words({"max(sigma)": 0.1}) == "The largest noise level is 0.1."
    assert row_in_words({"stddev(mass_kg)": 0.2}) == "The stddev of mass is 0.2 kg." and row_in_words({"count(1)": 3}) == "The count is 3."
    assert row_in_words({"equipment_id": None, "mass_kg": 1.0}, "[Q1]") == "The equipment is none and the mass is 1.0 kg [Q1]."   # 'For none, ...' is not a subject
    assert row_in_words({"equipment_id": None, "sensor_id": "S-1", "sigma": 0.1}) == "For S-1, the equipment is none and the noise level is 0.1."


def test_a_pasted_array_keeps_its_numbers_as_written_and_what_follows_it():
    assert answer_in_words('Records: [{"record_id": "S-1", "sigma": 0.10, "note": "x0.10y"}]') == "Records: For S-1, the noise level is 0.10 and the note is x0.10y."
    assert answer_in_words('Records: [{"record_id": "S-1", "sigma": 1e-6, "n": 1000}]') == "Records: For S-1, the noise level is 1e-6 and the count is 1000."   # never 1e-06 or 1000.0
    assert answer_in_words('Records: [{"record_id": "M-1", "date": "2026-09-02"}].') == "Records: For M-1, the date is 2026-09-02."                        # no double stop
    assert answer_in_words('Records: [{"record_id": "M-1", "date": "2026-09-02"}] [Q1]') == "Records: For M-1, the date is 2026-09-02. [Q1]"
    assert answer_in_words('Records: [{"record_id": "M-1", "date": "2026-09-02"}]. Both are recent.') == "Records: For M-1, the date is 2026-09-02. Both are recent."
    for kept in ('Records: [{"record_id": "M-1", "date": "2026-09-02"}] and more text.', 'Records: [{"record_id": "M-1", "done": true}]'):   # a sentence that goes on, a bool
        assert answer_in_words(kept) == kept


def test_keeps_values_checks_whole_tokens():
    assert keeps_values("100 [Q1]", "The rate is 100 Hz [Q1].") and keeps_values("**T1 (research)**: 400 [T1.E1]", "400 [T1.E1]")
    for before, after in (("100", "1000"), ("[Q1]", "Q1 here"), ("0.01", "10.01"), ("1.0", "1.05"), ("P-104", "P-1045")):
        assert not keeps_values(before, after), (before, after)
