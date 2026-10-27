"""The answer that code assembles reads as sentences, not as a form: the accepted results as paragraphs without task labels,
the research expert's code-made rows as plain words, every number, id and citation kept. No model unless a test scripts one."""
import re

from inverse_core.team.expert import Task
from inverse_core.team.plan import Plan
from inverse_core.team.words import answer_in_words, keeps_values, results_in_words, row_in_words



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
    digest = "Found and still standing: research: 0.01. Rows: sigma = 0.01, sampling_hz = 100 [Q1]; research: 2. Ruled out: nothing yet."
    assert answer_in_words(digest) == digest
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
