"""Adversarial calculations and the changed-input live failure; no live services."""
import json

import pytest

from inverse_core.team.calculation import calculate, quantities, result_dimension_error
from inverse_core.team.critic import deterministic
from inverse_core.team.expert import Task
from inverse_core.team.plan import Plan
from inverse_core.team.reasoning import safe_eval
from inverse_core.team.verify import unverified_numbers

from fakes import crew, events

GOAL = ('A rectangular cantilever has a 500 N tip load, length 0.3 m, width 0.05 m, '
        'and height 0.02 m in the bending direction. Assume linear elasticity and an ideal fixed support. '
        'Calculate the maximum bending stress. Show the equation and cite engineering references.')
REFERENCE = {"type": "reference", "source": "https://example.org/beam", "detail": "For F=1000 N and L=0.2 m the example gives 75 MPa.",
             "reference": {"chunk_id": "example", "source_id": "beam", "title": "Beam reference", "section": "Bending",
                           "excerpt": "For F=1000 N and L=0.2 m the example gives 75 MPa.", "source_url": "https://example.org/beam", "version": "1", "license": "Apache-2.0"}, "verified": False}


@pytest.mark.parametrize("load,length,width,height,expected", [(500,.3,.05,.02,45), (1000,.2,.04,.02,75), (200,.4,.02,.04,15)])
def test_changed_inputs_use_task_values_not_reference_examples(load,length,width,height,expected):
    context = f'F={load} N, L={length} m, b={width} m, h={height} m. Calculate bending stress.'
    inputs = {name: {"value": value, "unit": unit} for name,value,unit in [('F',load,'N'),('L',length,'m'),('b',width,'m'),('h',height,'m')]}
    result = calculate('6*F*L/(b*h**2)', inputs, 'MPa', context)
    assert result['value'] == pytest.approx(expected) and result['unit']=='MPa'
    assert result['units_checked'] and result['library_version']=='0.25'


def test_raw_literal_formula_checks_units_and_caret_power():
    result = calculate('6*500*0.3/(0.05*0.02^2)', unit='MPa', context=GOAL)
    assert result['value']==pytest.approx(45)
    assert safe_eval('2^3') == 8
    assert safe_eval('2**3') == 8


def test_scalar_example_answer_cannot_replace_using_the_question_inputs():
    assert calculate('2+3',context='Calculate 2 plus 3.')['value']==5
    for copied in ['75','5']:
        with pytest.raises(ValueError,match='none of'):
            calculate(copied,context='Calculate 2 plus 3.')
    assert calculate('5',context='Evaluate 5.')['value']==5


def test_ordinary_prose_in_and_equipment_ids_are_not_units_or_quantities():
    values = quantities('P-104 in newtons has mass_kg = 1.0; acceleration 9.81 m/s^2 in newtons.')
    assert len(values)==2 and all(float(q.magnitude)!=104 for _,_,q in values)
    result=calculate('1.0*9.81', context='mass_kg = 1.0; g=9.81 m/s^2. Calculate weight in newtons.')
    assert result['value']==pytest.approx(9.81) and result_dimension_error(result,'Calculate weight') is None


def test_reference_input_substitution_and_missing_dimensions_fail():
    with pytest.raises(ValueError, match='not supported'):
        calculate('F*L', {'F':{'value':1000,'unit':'N'}, 'L':{'value':.3,'unit':'m'}}, context=GOAL)
    with pytest.raises(ValueError, match='not supported'):
        calculate('6*F*L/(b*h**2)', {'F':{'value':500,'unit':'N'},'L':{'value':.3,'unit':'m'},'b':{'value':.05,'unit':'m'},'h':{'value':.02,'unit':'m'}}, 'MPa', 'A 500 N tip load. Calculate stress; no dimensions are given.')
    with pytest.raises(ValueError, match='none of'):
        calculate('75', context=GOAL)
    force=calculate('500', context=GOAL)
    assert result_dimension_error(force, GOAL)


@pytest.mark.parametrize('expr', ['1e309', 'exp(1000)', '(-1)**.5', '10**1000', '1/0', '__import__("os").getcwd()', '(1).__class__', '[1,2][0]', 'x'*1201])
def test_scalar_calculator_rejects_nonfinite_unbounded_or_executable_input(expr):
    with pytest.raises((ValueError,OverflowError,ZeroDivisionError)):
        safe_eval(expr)


@pytest.mark.parametrize('expr', ['F.__class__', '__import__("os")', 'F[0]', 'F**101'])
def test_unit_calculator_cannot_execute_arbitrary_python(expr):
    with pytest.raises(ValueError):
        calculate(expr, {'F':{'value':500,'unit':'N'}}, context=GOAL)


def test_conversion_rounding_signs_and_local_percentage_binding():
    pressure=[{'value':10,'unit':'Pa'}]
    assert unverified_numbers('Stress is 10 MPa.',pressure)==['10']
    assert unverified_numbers('Pressure is 0.00001 MPa.',pressure)==[]
    assert unverified_numbers('Force is -6 N.',[{'value':6,'unit':'N'}])==['-6']
    assert unverified_numbers('Force is 6 N.',[{'value':-6,'unit':'N'}])==['6']
    assert unverified_numbers('Force is 122.6 N.',[{'value':122.625,'unit':'N'}])==[]
    assert '981' in unverified_numbers('Force is 981 N; confidence is 40 percent.',[9.81,.4])
    assert unverified_numbers('Damping increased 40 percent.',[.4])==[]


def test_signed_force_and_unit_conversion_are_computed_with_task_inputs():
    force=calculate('2 * -3',unit='N',context='mass 2 kg and acceleration -3 m/s^2. Calculate force.')
    assert force['value']==-6 and force['units_checked']
    length=calculate('d',{'d':{'value':1000,'unit':'mm'}},'m','Convert 1000 mm to metres.')
    assert length['value']==1 and length['unit']=='m'
    temperature=calculate('T',{'T':{'value':20,'unit':'degC'}},'K','Convert 20 degrees Celsius to kelvin.')
    assert temperature['value']==pytest.approx(293.15)


def test_confidence_and_library_versions_never_ground_a_numerical_answer():
    assert unverified_numbers('The result is 0.25.',[{'value':6,'library_version':'0.25'}])==['0.25']
    assert unverified_numbers('The result is 0.9.',[{'value':6,'confidence':.9}])==['0.9']


def test_reference_numbers_hashes_and_failed_expression_inputs_are_not_proof():
    evidence=[REFERENCE,{'type':'calc','source':'step 1:75*1000','detail':'not computable: unsupported expression','status':'error'}]
    assert unverified_numbers('75',evidence)==['75']
    assert unverified_numbers('12345',[{'source_url':'https://example.org/12345','content_hash':'12345','value':1}])==['12345']
    result={'answer':'75','confidence':.9,'task_goal':GOAL,'evidence':evidence}
    assert deterministic(result)[0]=='revise'
    result['evidence']=[REFERENCE]
    assert 'successful calculation' in deterministic(result)[1]


def test_successful_calculation_overrides_a_copied_model_answer_and_retains_citations(tmp_path):
    reply={'steps':[{'claim':'nominal beam stress','calc':'6*F*L/(b*h**2)','inputs':{'F':{'value':500,'unit':'N'},'L':{'value':.3,'unit':'m'},'b':{'value':.05,'unit':'m'},'h':{'value':.02,'unit':'m'}},'unit':'MPa','expect':45}], 'answer':'75','confidence':.9}
    def script(model,messages):
        if messages[0]['content'].startswith('You are an adversarial reviewer'):
            return json.dumps({'verdict':'accept','problems':[]})
        assert messages[1]['content'].rfind('AUTHORITATIVE TASK') > messages[1]['content'].find('75 MPa')
        return json.dumps(reply)
    ctx,lead=crew(tmp_path,script)
    # Preserve explicit supplied references while executing the real review/composition path.
    task=Task('T1',GOAL,'reasoning',references=[REFERENCE])
    lead._execute(task)
    assert task.status=='done' and task.result['validation_errors']==[]
    assert '45 MPa' in task.result['answer'] and not task.result['answer'].startswith('75')
    assert lead.memory.findings()==[]
    answer=lead.compose(Plan(GOAL,[task]))
    assert '45 MPa' in answer['answer'] and answer['citations'] and answer['references']


def test_live_failure_replay_never_finishes_or_enters_memory(tmp_path):
    reply={'steps':[{'claim':'stress','calc':'75 * 1000 * 0.3 / (0.04 * 0.02^3)','expect':75}], 'answer':'75','confidence':.9}
    def script(model,messages):
        assert not messages[0]['content'].startswith('You are an adversarial reviewer'), 'failed arithmetic must be blocked before a model can approve it'
        return json.dumps(reply)
    ctx,lead=crew(tmp_path,script)
    task=Task('T1',GOAL,'reasoning',references=[REFERENCE])
    lead._execute(task)
    assert task.status!='done' and task.result['validation_errors']
    result=lead.compose(Plan(GOAL,[task]))
    assert not result['citations'] and result['unfinished'] and lead.memory.findings()==[]
    assert 'No task produced an accepted result' in result['answer']


def test_algebra_answer_cannot_replace_computed_root_with_a_task_input(tmp_path):
    def script(model,messages):
        if messages[0]['content'].startswith('You are an adversarial reviewer'):
            return json.dumps({'verdict':'accept','problems':[]})
        return json.dumps({'steps':[{'claim':'isolate x','calc':'(11-3)/2','expect':4}], 'answer':'x = 3','confidence':.9})
    ctx,lead=crew(tmp_path,script)
    task=Task('T1','Solve 2*x + 3 = 11 for x.','reasoning')
    lead._execute(task)
    assert task.status=='done' and task.result['answer'].startswith('Calculated result: 4.')
    assert 'x = 3' not in task.result['answer']


def test_configurable_solver_corrects_copied_reference_answer(tmp_path):
    def script(model,messages):
        if messages[0]['content'].startswith('You are an adversarial reviewer'):
            return json.dumps({'verdict':'accept','problems':[]})
        if 'tool_result' not in messages[-1]['content']:
            return json.dumps({'tool':'calc','args':{'expr':'6*500*0.3/(0.05*0.02**2)','unit':'MPa'}})
        return json.dumps({'answer':'The maximum stress is 75 MPa.','confidence':.9})
    ctx,lead=crew(tmp_path,script)
    task=Task('T1',GOAL,'solver',references=[REFERENCE])
    lead._execute(task)
    assert task.status=='done' and task.result['answer'].startswith('Calculated result: 45 MPa.')
    assert lead.memory.findings()==[] and not task.result['validation_errors']


def test_dimensionless_named_inputs_do_not_strip_physical_units():
    assert calculate('f',{'f':{'value':.064,'unit':''}},context='The friction factor is 0.064.')['value']==.064
    with pytest.raises(ValueError,match='not supported'):
        calculate('F',{'F':{'value':500,'unit':''}},context='Force is 500 N.')


@pytest.mark.parametrize('equation,root',[('2*x + 3 = 11',4),('3x - 7 = 8',5),('2*(x+1) = x-4',-6),('x/2+1 = 4',6)])
def test_supported_linear_equations_are_checked_without_model_calls(tmp_path,equation,root):
    ctx,lead=crew(tmp_path,lambda m,msgs:pytest.fail('simple linear equations need no model'))
    plan=lead.plan(f'Solve {equation} for x. Show the arithmetic.')
    lead.run(plan)
    answer=lead.compose(plan)
    proof=next(iter(answer['citations'].values()))['result']
    assert proof['value']==root and proof['substitution']['left']==proof['substitution']['right']
    assert not answer['unfinished'] and not events(ctx,'llm')


@pytest.mark.parametrize('goal',['Solve x*x=4 for x','Solve x/(x-1)=2 for x','Solve x=x for x',
    'Solve x=1 for x and calculate heat','Solve __import__("os")=x for x','Solve 1e999*x=3 for x'])
def test_unsupported_or_ambiguous_equations_stay_on_normal_expert_path(goal):
    from inverse_core.team.calculation import linear_solution
    assert linear_solution(goal) is None


def test_accepted_reference_example_is_not_a_substitute_for_failed_computation(tmp_path):
    ctx,lead=crew(tmp_path,lambda m,msgs:'{}')
    source=Task('T1','Find beam references','research',status='done',result={
        'answer':'Worked example: 75 MPa.','reference_only':True,'evidence':[REFERENCE],
        'confidence':.6,'assumptions':[],'not_checked':[]})
    failed=Task('T2',GOAL,'reasoning',['T1'],status='failed',feedback='missing required dimensions')
    result=lead.compose(Plan(GOAL,[source,failed]))
    assert 'Worked example: 75 MPa' not in result['answer'] and result['unfinished']


def test_final_writer_cannot_replace_typed_result_with_reference_example(tmp_path):
    ctx,lead=crew(tmp_path,lambda m,msgs:pytest.fail('typed results must be composed by code'))
    common={'confidence':.9,'assumptions':[],'not_checked':[]}
    source=Task('T1','Find references','research',status='done',result=common | {
        'answer':'Worked example: 75 MPa.','reference_only':True,'evidence':[REFERENCE]})
    computation=calculate('6*500*0.3/(0.05*0.02**2)',unit='MPa',context=GOAL)
    calculated=Task('T2',GOAL,'reasoning',['T1'],status='done',result=common | {
        'answer':'Calculated result: 45 MPa.','evidence':[REFERENCE,{'type':'calc','status':'ok','source':'stress calculation','result':computation,'detail':'= 45 MPa'}]})
    other=Task('T3','Check assumptions','reasoning',status='done',result=common | {
        'answer':'Linear elasticity assumed.','evidence':[{'type':'step','source':'assumption','detail':'Linear elasticity assumed.'}]})
    result=lead.compose(Plan(GOAL,[source,calculated,other]))
    assert '45 MPa' in result['answer'] and '75 MPa' not in result['answer']
    assert result['references'] and result['citations'] and not events(ctx,'llm')


def test_writer_unknown_citation_is_replaced_by_real_accepted_evidence(tmp_path):
    ctx,lead=crew(tmp_path,lambda m,msgs:'The result is 6 [T99.E99].')
    tasks=[Task(f'T{i}','Calculate product','reasoning',status='done',result={
        'answer':'The product is 6.','evidence':[{'type':'calc','source':'2*3','detail':'= 6'}],
        'confidence':.9,'assumptions':[],'not_checked':[]}) for i in range(1,4)]
    result=lead.compose(Plan('Calculate a product',tasks))
    assert '[T99.E99]' not in result['answer'] and not result['unknown_citations']
    assert len(result['citations'])==3 and events(ctx,'compose_citations_refused')


@pytest.mark.parametrize('failure',['exception','unreadable','unsubstantiated_reject'])
def test_reviewer_failure_never_completes_or_writes_findings(tmp_path,failure):
    def script(model,messages):
        if messages[0]['content'].startswith('You are the Reasoning expert'):
            return json.dumps({'steps':[{'claim':'product','calc':'2*3','expect':6}],'answer':'The product is 6.','confidence':.9})
        if failure=='exception': raise RuntimeError('review lane unavailable')
        return 'not json' if failure=='unreadable' else json.dumps({'verdict':'reject','problems':[]})
    ctx,lead=crew(tmp_path,script)
    lead.critic.code_first=False
    task=Task('T1','Calculate 2 times 3','reasoning')
    lead._execute(task)
    assert task.status!='done' and lead.memory.findings()==[]
    final=lead.compose(Plan('Calculate 2 times 3',[task]))
    assert final['unfinished'] and not final['citations']
