import pytest

from fakes import crew, events

ODE='Solve dy/dx = 2x with y(0) = 3. Show the integration, apply the initial condition, and verify the result by differentiation.'
OVERVIEW='From the registry, the sensor specifications and the maintenance history, what do we know about P-104, and how much sensor data is there for it?'


def test_initial_value_prompt_is_integrated_and_checked_without_inference(tmp_path):
    ctx,lead=crew(tmp_path,lambda m,msgs:pytest.fail('no model needed'))
    plan=lead.plan(ODE); lead.run(plan); result=lead.compose(plan)
    assert 'y = x² + 3' in result['answer'] and 'dy/dx = 2x' in result['answer']
    assert 'C = 3' in result['answer'] and not result['unfinished'] and not events(ctx,'llm')
    proof=next(iter(result['citations'].values()))['result']
    assert proof['checks']['derivative_slope']==2 and proof['checks']['initial_value']==3


def test_registry_overview_counts_actual_rows_and_cites_every_source(tmp_path):
    ctx,lead=crew(tmp_path,lambda m,msgs:pytest.fail('no model needed'))
    def sql(statement,limit=2000):
        if 'equipment_table' in statement:
            return [{'equipment_id':'P-104','mass_kg':1,'baseline_dataset':'p104-baseline','current_dataset':'p104-current'}]
        if 'sensors_table' in statement:
            return [{'sensor_id':'P104-DISP-1','quantity':'x','unit':'m','sigma':.01,'sampling_hz':100}]
        if 'maintenance_table' in statement:
            return [{'record_id':'M-001','date':'2026-09-02','note':'Inspected'}]
        return [{'sample_count':123 if 'baseline' in statement else 456}]
    ctx.zetaris.sql=sql
    plan=lead.plan(OVERVIEW); lead.run(plan); result=lead.compose(plan)
    assert not result['unfinished'],[(t.feedback,t.result) for t in plan.tasks]
    assert '579 sample rows' in result['answer'] and 'sampling_hz: 100' in result['answer']
    assert 'Inspected' in result['answer'] and len(result['citations'])==6 and not events(ctx,'llm')


def test_failed_registry_request_never_substitutes_invented_data(tmp_path):
    ctx,lead=crew(tmp_path,lambda m,msgs:pytest.fail('no model needed'))
    ctx.zetaris.sql=lambda *a,**k:(_ for _ in ()).throw(RuntimeError('database unavailable'))
    plan=lead.plan(OVERVIEW);lead.run(plan);result=lead.compose(plan)
    assert result['unfinished'] and not result['citations'] and 'database unavailable' in result['answer']
