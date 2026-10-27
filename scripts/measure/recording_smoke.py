"""Check the two recording prompts through the real team with actual registry SQL."""
import argparse
import json
import sys
import tempfile
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'core'))
ODE='Solve dy/dx = 2x with y(0) = 3. Show the integration, apply the initial condition, and verify the result by differentiation.'
OVERVIEW='From the registry, the sensor specifications and the maintenance history, what do we know about P-104, and how much sensor data is there for it?'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file',type=Path)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    if args.env_file:
        from dotenv import load_dotenv
        load_dotenv(args.env_file)
    from inverse_core.budget import Budget
    from inverse_core.clients.zetaris import ZetarisClient
    from inverse_core.ledger import InMemoryLedger
    from inverse_core.team.lanes import Lanes
    from inverse_core.team.lead import Lead
    from inverse_core.team.llmcall import Ctx
    from inverse_core.team.memory import TeamMemory
    from inverse_core.team.registry import Registry
    from inverse_core.trace import Trace
    def no_model(*args):
        raise AssertionError('These supported prompts must not require model inference')
    reports=[]
    with tempfile.TemporaryDirectory(prefix='inverse-recording-smoke-') as temp:
        for name,goal in [('calculus',ODE),('registry',OVERVIEW)]:
            ctx=Ctx(Lanes(factory=no_model),Trace(str(Path(temp)/name)),Budget(max_llm_calls=0),
                    zetaris=ZetarisClient(timeout=15),equipment=['P-104'],root=str(ROOT))
            ctx.registry=Registry(ctx,str(ROOT/'experts'),str(ROOT))
            lead=Lead(ctx,ctx.registry,TeamMemory(InMemoryLedger()))
            started=time.perf_counter()
            plan=lead.plan(goal);lead.run(plan);answer=lead.compose(plan)
            passed=not answer['unfinished'] and bool(answer['citations']) and not answer['unknown_citations']
            if name=='calculus': passed=passed and 'y = x² + 3' in answer['answer'] and 'dy/dx = 2x' in answer['answer']
            else: passed=passed and 'Total sensor data:' in answer['answer'] and len(answer['citations'])>=5
            report={'name':name,'pass':passed,'elapsed_s':round(time.perf_counter()-started,3),
                    'model_calls':ctx.budget.llm_calls,'answer':answer['answer'],'unfinished':answer['unfinished'],
                    'evidence':answer['citations']}
            reports.append(report)
            print(json.dumps(report),flush=True)
    result={'status':'pass' if all(r['pass'] for r in reports) else 'fail','data':'actual connected registry; no invented rows','results':reports}
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    return 0 if result['status']=='pass' else 1


if __name__=='__main__': raise SystemExit(main())
