"""Bounded engineering checks; --live explicitly opts into real model calls.

Live runs use a temporary reference index, fresh in-memory memory and temporary
traces. They do not alter H-MEM or run/deploy the web application.
"""
import argparse
import json
import math
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'core'))

from inverse_core.team.calculation import calculate, quantity

CASES=[
    {"name":"beam","goal":"A rectangular cantilever has a 500 N tip load, length 0.3 m, width 0.05 m, and height 0.02 m in the bending direction. Assume linear elasticity and an ideal fixed support. Calculate the maximum bending stress. Show the equation and cite engineering references.",
     "expr":"6*500*0.3/(0.05*0.02**2)","unit":"MPa","expected":45},
    {"name":"algebra","goal":"Solve 2*x + 3 = 11 for x. Show the arithmetic.","expr":"(11-3)/2","expected":4},
    {"name":"signed_force","goal":"A mass is 2 kg and acceleration is -3 m/s^2. Calculate force in newtons.","expr":"2 * -3","unit":"N","expected":-6},
    {"name":"thermal","goal":"Mass m=2 kg, specific heat cp=4180 J/(kg*K), and temperature increase dT=50 K. Calculate sensible heat in joules with constant specific heat and no phase change.",
     "expr":"m*cp*dT","inputs":{"m":{"value":2,"unit":"kg"},"cp":{"value":4180,"unit":"J/(kg*K)"},"dT":{"value":50,"unit":"K"}},"unit":"J","expected":418000},
    {"name":"fluid","goal":"A fully developed laminar pipe has Darcy friction factor f=0.064, length L=10 m, diameter D=0.01 m, density rho=1000 kg/m^3, and mean speed v=0.1 m/s. Calculate pressure drop using Darcy-Weisbach; neglect fittings and elevation change.",
     "expr":"f*(L/D)*(rho*v**2/2)","inputs":{"f":{"value":.064,"unit":""},"L":{"value":10,"unit":"m"},"D":{"value":.01,"unit":"m"},"rho":{"value":1000,"unit":"kg/m^3"},"v":{"value":.1,"unit":"m/s"}},"unit":"Pa","expected":320},
    {"name":"missing_inputs","goal":"Calculate bending stress in a cantilever with a 500 N tip load. Its length and cross-section have not been provided. Do not assume those dimensions.","abstain":True},
]


def offline(case):
    if case.get('abstain'):
        try: calculate('75',unit='MPa',context=case['goal'])
        except ValueError: return {'name':case['name'],'pass':True,'abstained':True}
        return {'name':case['name'],'pass':False}
    out=calculate(case['expr'],case.get('inputs'),case.get('unit'),case['goal'])
    return {'name':case['name'],'pass':math.isclose(out['value'],case['expected'],rel_tol=1e-8,abs_tol=1e-9),'value':out['value'],'unit':out.get('unit','')}


def live(case,temp):
    from inverse_core.budget import Budget
    from inverse_core.ledger import InMemoryLedger
    from inverse_core.team.critic import Critic
    from inverse_core.team.lanes import Lanes
    from inverse_core.team.lead import Lead
    from inverse_core.team.llmcall import Ctx
    from inverse_core.team.memory import TeamMemory
    from inverse_core.team.registry import Registry
    from inverse_core.trace import Trace

    ctx=Ctx(Lanes(),Trace(str(temp/case['name'])),Budget(max_llm_calls=12,max_seconds=180),root=str(ROOT))
    ctx.registry=Registry(ctx,str(ROOT/'experts'),str(ROOT))
    lead=Lead(ctx,ctx.registry,TeamMemory(InMemoryLedger()),Critic(ctx),max_attempts=2)
    start=time.perf_counter()
    plan=lead.plan(case['goal'])
    lead.run(plan,parallel=1)
    answer=lead.compose(plan)
    computed=[e for e in answer['citations'].values() if e.get('type')=='calc' and e.get('status')=='ok' and e.get('result')]
    values=[]
    for item in computed:
        out=item['result']
        try:
            value=float(quantity(out['value'],out.get('unit','')).to(case.get('unit','')).magnitude)
            values.append(value)
        except (ValueError,TypeError): pass
    if case.get('abstain'):
        passed=not computed and (bool(answer['unfinished']) or any(word in answer['answer'].lower() for word in ('missing','need','required','cannot','not provided')))
    else:
        passed=any(math.isclose(value,case['expected'],rel_tol=1e-6,abs_tol=1e-9) for value in values) and not answer['unknown_citations']
    assert lead.memory.findings()==[] or not any(e.get('type')=='reference' for t in plan.tasks for e in (t.result or{}).get('evidence',[]))
    return {'name':case['name'],'pass':passed,'answer':answer['answer'],'values_in_requested_unit':values,
            'tasks':[(t.id,t.expert,t.status,t.attempts) for t in plan.tasks],
            'elapsed_s':round(time.perf_counter()-start,2),'model_calls':ctx.budget.llm_calls,
            'models':answer['models_used'],'unfinished':answer['unfinished'],
            'calculation_attempts':[e for e in ctx.trace.events if e['kind']=='calculation_steps'],
            'tool_attempts':[e for e in ctx.trace.events if e['kind']=='tool'] if not passed else []}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live',action='store_true')
    parser.add_argument('--only',help='Comma-separated case names')
    parser.add_argument('--env-file',type=Path)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    if args.env_file:
        from dotenv import load_dotenv
        load_dotenv(args.env_file)
    selected=set(args.only.split(',')) if args.only else {c['name'] for c in CASES}
    if selected-{c['name'] for c in CASES}: parser.error('unknown case name')
    with tempfile.TemporaryDirectory(prefix='inverse-calculation-eval-') as temporary:
        temp=Path(temporary)
        if args.live:
            from inverse_core.knowledge import rebuild
            os.environ['INVERSE_ENGINEERING_ENABLED']='1'
            os.environ['INVERSE_ENGINEERING_DB']=str(temp/'knowledge.sqlite3')
            os.environ['INVERSE_EXPERTS_LOCAL']=str(temp/'experts.local')
            rebuild(ROOT/'data/engineering/sources.json',ROOT/'data/engineering',temp/'knowledge.sqlite3')
        results=[]
        for case in CASES:
            if case['name'] not in selected: continue
            try: result=live(case,temp) if args.live else offline(case)
            except Exception as e: result={'name':case['name'],'pass':False,'error':f'{type(e).__name__}: {e}'}
            results.append(result)
            print(json.dumps(result,ensure_ascii=True),flush=True)
        report={'mode':'live model' if args.live else 'deterministic calculator','passed':sum(r['pass'] for r in results),'cases':len(results),'results':results}
        if args.output:
            args.output.parent.mkdir(parents=True,exist_ok=True)
            args.output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
        return 0 if all(r['pass'] for r in results) else 1


if __name__=='__main__': raise SystemExit(main())
