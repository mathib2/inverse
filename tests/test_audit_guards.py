"""Guards tightened by the 27 Oct audit: placeholders, the SQL guard's JVM built-ins, the web tools' reach."""
import pytest


def test_a_goal_with_less_than_and_greater_than_is_not_a_copied_placeholder():
    """'(t < 1) ... (t >= 3)' matched the placeholder pattern '<[^>]*>', so every plan for such a goal was refused."""
    from inverse_core.team.plan import PLACEHOLDER
    assert not PLACEHOLDER.search("Compare the largest |x| for t < 1 with the largest for t >= 3")
    assert not PLACEHOLDER.search("sensors with sigma <= 0.01 and sampling_hz >= 100")
    assert PLACEHOLDER.search("<one self-contained instruction, written by you for THIS goal>")
    assert PLACEHOLDER.search("Do <a name from the list> now")


def test_backtick_quoted_and_try_jvm_builtins_are_refused():
    from inverse_core.team.sql_guard import UnsafeSQL, check_sql
    for sql in ("SELECT `reflect`('java.lang.Runtime', 'getRuntime') FROM obs.equipment_table",
                "SELECT try_reflect('java.lang.System', 'getenv') FROM obs.equipment_table",
                "SELECT `java_method`('x', 'y') FROM obs.equipment_table"):
        with pytest.raises(UnsafeSQL):
            check_sql(sql)
    check_sql("SELECT equipment_id, mass_kg FROM obs.equipment_table")


def test_the_web_tools_never_read_the_tailnet():
    from inverse_core.team.tools import _private
    assert _private("<tailnet-ip>") and _private("<tailnet-ip>") and _private("127.0.0.1") and _private("<lan-ip>")
    assert not _private("8.8.8.8")
