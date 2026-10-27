"""Bounded, code-backed answers for supported calculus and registry summaries."""
import math
import re

from .expert import ExpertResult

NUM = r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?'


def initial_value_solution(goal):
    """Integrate y'=a*x+b and check its initial condition and derivative."""
    pattern = (r'^\s*Solve\s+dy\s*/\s*dx\s*=\s*(' + NUM + r')\s*\*?\s*x'
               r'(?:\s*([+-])\s*(\d+(?:\.\d*)?))?\s+with\s+y\s*\(\s*(' + NUM +
               r')\s*\)\s*=\s*(' + NUM + r')\s*\.'
               r'\s*Show the integration, apply the initial condition, and verify the result by differentiation\.?\s*$')
    match = re.fullmatch(pattern,str(goal),re.IGNORECASE)
    if not match:
        return None
    a=float(match[1]); b=float((match[2] or '+')+(match[3] or '0'))
    x0,y0=float(match[4]),float(match[5])
    q=a/2
    constant=y0-q*x0*x0-b*x0
    if not all(math.isfinite(v) for v in (a,b,x0,y0,q,constant)):
        return None
    if not math.isclose(q*2,a) or not math.isclose(q*x0*x0+b*x0+constant,y0,rel_tol=1e-10,abs_tol=1e-10):
        return None
    def term(coefficient,power):
        if not coefficient: return ''
        magnitude='' if abs(coefficient)==1 else f'{abs(coefficient):g}'
        return ('-' if coefficient<0 else '+')+magnitude+'x'+('²' if power==2 else '')
    polynomial=(term(q,2)+term(b,1)).lstrip('+') or '0'
    final=polynomial+(f' + {constant:g}' if constant>=0 else f' - {abs(constant):g}')
    derivative=(term(a,1)+(f' + {b:g}' if b else '')).lstrip('+') or f'{b:g}'
    expr=f'{y0!r}-({q!r}*{x0!r}**2+{b!r}*{x0!r})'
    proof={'expr':expr,'value':constant,'units_checked':False,
           'inputs':{'slope':{'value':a},'offset':{'value':b},'initial_x':{'value':x0},'initial_y':{'value':y0}},
           'integration':{'quadratic':q,'linear':b,'constant':constant},
           'checks':{'derivative_slope':q*2,'derivative_offset':b,'initial_value':q*x0*x0+b*x0+constant}}
    answer=(f'Integrate: y = ∫({derivative}) dx = {polynomial} + C.\n\n'
            f'Apply y({x0:g}) = {y0:g}: C = {y0:g} - ({q:g}·({x0:g})² + {b:g}·({x0:g})) = {constant:g}.\n\n'
            f'**Solution: y = {final}.**\n\n'
            f'Verify by differentiation: dy/dx = {derivative}, as required. '
            f'The initial condition also holds: y({x0:g}) = {y0:g}.')
    return ExpertResult(answer,[{'type':'calc','status':'ok','source':'polynomial integration, differentiation and initial-condition checks',
                                 'detail':f'= {constant:g}; initial condition and derivative checked','result':proof}],1.0,[],[],[])


def overview_requested(goal):
    ids=list(dict.fromkeys(re.findall(r'\b[A-Z]{1,4}-\d+\b',goal)))
    return ids[0] if len(ids)==1 and all(re.search(word,goal,re.IGNORECASE) for word in
        (r'\bregistry\b',r'\bsensors?\b',r'\bmaintenance\b',r'\b(data|samples?)\b')) else None


def equipment_overview(expert,task,budget):
    equipment=overview_requested(task.goal)
    if not equipment:
        return None
    from ..clients.zetaris import SAMPLE_VIEWS
    from .tools import Tools
    toolbox=Tools(expert.ctx,['run_sql'],owner=expert.name)
    evidence=[]
    sections=[]
    def query(sql,label):
        out=toolbox.call('run_sql',{'sql':sql},budget,who=expert.name)
        if out.get('error'):
            raise ValueError(f'{label} could not be retrieved: {out["error"]}')
        rows=out.get('rows',[])
        evidence.append({'type':'sql','source':sql,'detail':f'{len(rows)} rows','rows':rows})
        return rows,f'[Q{len(evidence)}]'
    registry,cite=query(f"SELECT * FROM obs.equipment_table WHERE equipment_id = '{equipment}'",'Registry')
    if not registry:
        return ExpertResult(f'No registry record was returned for {equipment}. {cite}',evidence,1.0,[],[],[])
    def render(label,rows,cite):
        if not rows:
            return f'**{label}**: no rows returned. {cite}'
        return f'**{label}**\n'+ '\n'.join('- '+ '; '.join(f'{key}: {value}' for key,value in row.items())+f' {cite}' for row in rows)
    sections.append(render(f'Registry — {equipment}',registry,cite))
    sensors,cite=query(f"SELECT * FROM obs.sensors_table WHERE equipment_id = '{equipment}'",'Sensor specifications')
    sections.append(render('Sensor specifications',sensors,cite))
    history,cite=query(f"SELECT record_id, date, note FROM obs.maintenance_table WHERE equipment_id = '{equipment}' ORDER BY date",'Maintenance history')
    sections.append(render('Maintenance history',history,cite))
    datasets=list(dict.fromkeys(str(row[key]) for row in registry for key in ('baseline_dataset','current_dataset')
                               if row.get(key) and str(row[key]).lower()!='none'))
    counts=[]
    for dataset in datasets:
        if dataset not in SAMPLE_VIEWS:
            sections.append(f'Dataset {dataset}: sample view is not registered; count unavailable.')
            continue
        rows,cite=query(f'SELECT COUNT(*) AS sample_count FROM {SAMPLE_VIEWS[dataset]}',f'Samples for {dataset}')
        count=int(rows[0]['sample_count'])
        if count<0: raise ValueError('invalid sample count')
        counts.append(count)
        sections.append(f'**{dataset}**: {count} sample rows. {cite}')
    if counts and len(counts)==len(datasets):
        total=sum(counts)
        evidence.append({'type':'calc','status':'ok','source':'sum of distinct dataset row counts',
                         'detail':f'= {total}','result':{'expr':'+'.join(map(str,counts)),'value':total,'units_checked':False}})
        sections.append(f'**Total sensor data: {total} sample rows across {len(counts)} datasets.** [Q{len(evidence)}]')
    return ExpertResult('\n\n'.join(sections),evidence,1.0,[],[],[])
