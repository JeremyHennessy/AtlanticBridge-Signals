"""Analyse consented pilot feedback without inventing users, savings or paid demand.

Input is private operator-supplied data. Browser page time is never research time.
Existing source/review metrics are reused per reviewer, preserving their denominators.
"""
from __future__ import annotations
from collections import defaultdict
from datetime import date
import math
from statistics import median
from .commercial_validation import review_metrics

def _text(value, name):
    if not isinstance(value,str) or not value.strip() or len(value)>500:raise ValueError('Invalid '+name)
    return value

def _seconds(value):
    if type(value) not in (int,float) or not math.isfinite(value) or value<0:raise ValueError('Active research time must be finite and non-negative')
    return value

def analyse(data:dict)->dict:
    if not isinstance(data,dict) or data.get('schema_version')!=1:raise ValueError('Unsupported pilot schema')
    for field in ('participants','reviews','paired_research_tasks','purchase_feedback'):
        if not isinstance(data.get(field),list) or len(data[field])>10000:raise ValueError('Invalid bounded '+field)
    participants={}
    for p in data['participants']:
        pid=_text(p.get('reviewer'),'reviewer')
        if pid in participants:raise ValueError('Duplicate pilot participant')
        for flag in ('consented','independent_user'):
            if type(p.get(flag)) is not bool:raise ValueError('Participation flags must be explicit')
        _text(p.get('role'),'role');date.fromisoformat(p['recorded_date'])
        if p['consented'] and not p.get('consent_record'):raise ValueError('Consent requires an operator-held record reference')
        participants[pid]=p
    groups=defaultdict(list);seen=set();unverified=0
    for r in data['reviews']:
        who=_text(r.get('reviewer'),'reviewer');key=(who,_text(r.get('alert_id'),'alert id'))
        if key in seen:raise ValueError('Duplicate reviewer/alert observation')
        seen.add(key)
        # Also validate excluded submissions rather than silently counting invalid inputs.
        review_metrics([r])
        p=participants.get(who)
        if not p or not p['consented'] or not p['independent_user']:unverified+=1;continue
        groups[who].append(r)
    by_reviewer={k:review_metrics(v) for k,v in groups.items()}
    # Existing elapsed-page metrics are disclosed, not relabelled as active research time.
    for values in by_reviewer.values():
        values['mean_elapsed_page_view_seconds']=values.pop('mean_review_seconds')
        values['elapsed_time_may_include_idle']=True
    tasks=[];taskkeys=set()
    for t in data['paired_research_tasks']:
        who=_text(t.get('reviewer'),'reviewer');task=_text(t.get('task_id'),'task id');key=(who,task)
        if key in taskkeys:raise ValueError('Duplicate paired task')
        taskkeys.add(key)
        if who not in groups:raise ValueError('Paired task requires an independently consented reviewer with feedback')
        if t.get('timing_basis')!='MANUALLY_TIMED_ACTIVE_RESEARCH':raise ValueError('Page elapsed time cannot establish research savings')
        if t.get('order') not in ('BASELINE_FIRST','TOOL_FIRST'):raise ValueError('Counterbalance order must be recorded')
        if t.get('baseline_method') not in ('MANUAL_RESEARCH','ANNOUNCEMENTS_ONLY','CIPO_ONLY'):raise ValueError('Specify the comparison method')
        _text(t.get('timing_record'),'timing record')
        baseline=_seconds(t.get('baseline_seconds'));tool=_seconds(t.get('tool_seconds'))
        tasks.append({'reviewer':who,'task_id':task,'baseline_method':t['baseline_method'],'seconds_saved':baseline-tool,'order':t['order']})
    purchase=[];buyerkeys=set()
    for row in data['purchase_feedback']:
        who=_text(row.get('reviewer'),'reviewer')
        if who in buyerkeys:raise ValueError('Duplicate purchase feedback')
        buyerkeys.add(who)
        p=participants.get(who)
        if not p or not p['consented'] or not p['independent_user']:raise ValueError('Purchase feedback needs an independent consented participant')
        if type(row.get('willing_to_pay')) not in (bool,type(None)):raise ValueError('Willingness to pay is boolean or unknown')
        if type(row.get('payment_verified')) is not bool:raise ValueError('Actual payment must be explicit')
        if row['payment_verified'] and not row.get('operator_payment_record'):raise ValueError('A stated willingness is not a verified payment')
        purchase.append(row)
    independent=[p for p in participants.values() if p['consented'] and p['independent_user']]
    unique_alerts={r['alert_id'] for rows in groups.values() for r in rows}
    return {'schema_version':1,'independent_consented_participants':len(independent),'participants_with_reviews':len(groups),
            'submitted_review_observations':sum(map(len,groups.values())),'unique_reviewed_alerts':len(unique_alerts),
            'excluded_unverified_reviewer_submissions':unverified,'per_reviewer':by_reviewer,
            'paired_active_research_tasks':len(tasks),'paired_task_results':tasks,
            'median_active_seconds_saved':median(t['seconds_saved'] for t in tasks) if tasks else None,
            'willingness_assessed':sum(r['willing_to_pay'] is not None for r in purchase),
            'willing_to_pay_statements':sum(r['willing_to_pay'] is True for r in purchase),
            'verified_paying_participants':sum(r['payment_verified'] for r in purchase),
            'commercial_viability_proven':False,'predictive_validation_complete':False,'expansion_score_publication_allowed':False}
