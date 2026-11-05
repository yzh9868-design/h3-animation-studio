"""Run an already-authorized H3 scope without serializing independent units.

Default: offline inspection only. --execute may prepare/submit each ready unit
once, then collect its frozen ID. --recover can only collect existing jobs.
This helper never grants approval, creates new takes or retries GPU generation.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import time

import common
import comfy_run as run

ACTIVE = ('submitted', 'submission_uncertain', 'collection_error')


def inspect_scope(project, segment_ids=None):
    film = common.load_film(project)
    chosen = common.selected_segments(film, segment_ids)
    ids = [s['id'] for s in chosen]
    inspection = run.inspect_project(project)
    plans = [p for p in inspection['segments'] if p['id'] in ids]
    errors = list(inspection.get('configuration_issues', []))
    if set(ids) == {s['id'] for s in film['segments']}:
        errors.extend(common.ready_errors(project, film))
    errors.extend(p['id'] + ': ' + p['planning_error'] for p in plans if p.get('planning_error'))
    state = run.load_state(project)
    for segment in chosen:
        sid = segment['id']
        try:
            actual, approval, _, _ = run.approved(project, sid, migrate_legacy=False)
            run.approved_segment(actual, approval, segment)
            refs = run.references(project, actual, segment)
            previous = segment.get('continuity_from')
            if previous:
                refs.append(dict(label=run.continuity_label(segment, refs), kind='image'))
                if previous not in ids:
                    upstream = state['jobs'].get(previous)
                    common.need(upstream and upstream['status'] == 'downloaded',
                                'Collect the predecessor outside this scope first: ' + previous)
                    run.job_matches(project, actual, approval, upstream)
                    run.validate_continuity(project, actual, approval, state, upstream)
            run.validate_prompt_references(segment['prompt_en'], refs)
            if sid in state['jobs']:
                run.job_matches(project, actual, approval, state['jobs'][sid])
        except (ValueError, KeyError, OSError) as error:
            errors.append(sid + ': ' + str(error))
    return film, ids, dict(phase='offline_ready' if not errors else 'not_ready',
        segment_ids=ids, plans=plans, errors=errors, network_requests=0, gpu_submission=False)


def run_batch(project, segment_ids=None, *, execute=False, recover=False,
              poll_seconds=20, wait_seconds=10800, assemble=None):
    project = Path(project).resolve()
    common.need(not (execute and recover), 'Choose --execute or --recover')
    common.need(1 <= poll_seconds <= 60 and wait_seconds > 0,
                'Use 1–60 second polling and a positive timeout')
    if recover:
        state = run.load_state(project)
        ids = list(state['jobs']) if segment_ids is None else list(segment_ids)
        common.need(ids and len(ids) == len(set(ids)) and set(ids) <= set(state['jobs']),
                    '--recover requires existing, unique segment IDs; it never prepares missing tasks')
        film = None  # Recovery reads frozen jobs, even if the current draft changed.
    else:
        film, ids, plan = inspect_scope(project, segment_ids)
        if plan['errors'] or not execute:
            return plan
    if assemble:
        current = common.load_film(project)
        common.need(set(ids) == {s['id'] for s in current['segments']},
                    '--assemble requires the complete film scope, not a partial batch')
    segments = {s['id']: s for s in film['segments']} if film else {}
    blocked, reads, observed = {}, {}, {}
    deadline = time.monotonic() + wait_seconds
    previous_snapshot = None

    def snapshot(phase):
        nonlocal previous_snapshot
        jobs = run.load_state(project)['jobs']
        rows = []
        for sid in ids:
            job = jobs.get(sid, {})
            row = dict(segment_id=sid, status=job.get('status', 'not_prepared'),
                       prompt_id=job.get('prompt_id') or job.get('requested_prompt_id'))
            if sid in observed:
                row['observed_status'] = observed[sid]
            if sid in blocked:
                row['error'] = blocked[sid]
            dep = segments.get(sid, {}).get('continuity_from')
            if not job and dep:
                row['waiting_for'] = dep
            rows.append(row)
        result = dict(phase=phase, segment_ids=ids, jobs=rows,
                      automatic_gpu_retry=False, errors=dict(blocked))
        signature = json.dumps(result, sort_keys=True, ensure_ascii=False)
        result['updated_at'] = common.stamp()
        common.save(project / 'execution/batch-status.json', result)
        if signature != previous_snapshot:
            print(json.dumps(result, ensure_ascii=False), flush=True)
            previous_snapshot = signature
        return result

    while time.monotonic() < deadline:
        # Queue every independent/ready unit before any collection in this pass.
        if execute:
            for sid in ids:
                if sid in blocked:
                    continue
                jobs = run.load_state(project)['jobs']
                job = jobs.get(sid)
                if not job:
                    dep = segments[sid].get('continuity_from')
                    if dep and jobs.get(dep, {}).get('status') != 'downloaded':
                        continue
                    try:
                        job = run.prepare(project, sid)
                        snapshot('queuing')
                    except Exception as error:
                        blocked[sid] = str(error)
                        continue
                if job['status'] == 'prepared':
                    try:
                        run.submit(project, sid, execute=True)
                    except Exception as error:
                        # submit persists uncertainty before POST. Only collect that ID.
                        latest = run.load_state(project)['jobs'].get(sid, {})
                        if latest.get('status') != 'submission_uncertain':
                            blocked[sid] = str(error)
                    snapshot('queuing')
                elif job['status'] not in ACTIVE + ('downloaded',):
                    blocked[sid] = job.get('error') or (
                        'Resolve existing ' + job['status'] + ' take explicitly; no automatic replacement')
        for sid in ids:
            if sid in blocked:
                continue
            job = run.load_state(project)['jobs'].get(sid)
            if not job:
                continue
            if job['status'] == 'downloaded':
                continue
            if job['status'] not in ACTIVE:
                blocked[sid] = job.get('error') or ('Cannot collect status ' + job['status'])
                continue
            if not (job.get('prompt_id') or job.get('requested_prompt_id')):
                blocked[sid] = 'Missing frozen prompt ID; inspect the existing task without resubmitting'
                continue
            try:
                result = run.collect(project, sid)
                observed[sid] = result['status']
                reads[sid] = 0
                snapshot('collecting')
            except Exception as error:
                reads[sid] = reads.get(sid, 0) + 1
                latest = run.load_state(project)['jobs'][sid]
                if latest['status'] == 'failed' or reads[sid] >= 3:
                    blocked[sid] = str(error)
        jobs = run.load_state(project)['jobs']
        if all(jobs.get(sid, {}).get('status') == 'downloaded' for sid in ids):
            result = snapshot('complete')
            if assemble:
                result['assembly'] = run.assemble(project, output=assemble)
                common.save(project / 'execution/batch-status.json', result)
            return result
        for sid in ids:
            dep = segments.get(sid, {}).get('continuity_from')
            if sid not in jobs and dep and (dep in blocked or jobs.get(dep, {}).get('status') in ('failed', 'prepare_failed')):
                blocked[sid] = 'Predecessor needs attention: ' + dep
        possible = any(sid not in blocked and (
            jobs.get(sid, {}).get('status') in ACTIVE or
            (execute and sid not in jobs and (not segments[sid].get('continuity_from') or
             jobs.get(segments[sid]['continuity_from'], {}).get('status') == 'downloaded')))
            for sid in ids)
        if not possible:
            return snapshot('needs_attention')
        snapshot('collecting')
        time.sleep(poll_seconds)
    return snapshot('waiting_timeout')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--segments', nargs='+', help='Exact authorized scope; default entire film')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--execute', action='store_true')
    mode.add_argument('--recover', action='store_true')
    parser.add_argument('--poll-seconds', type=int, default=20)
    parser.add_argument('--wait-seconds', type=int, default=10800)
    parser.add_argument('--assemble', metavar='PROJECT_RELATIVE_MP4')
    args = parser.parse_args()
    try:
        result = run_batch(args.project, args.segments, execute=args.execute, recover=args.recover,
            poll_seconds=args.poll_seconds, wait_seconds=args.wait_seconds, assemble=args.assemble)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result['phase'] in ('offline_ready', 'complete') else 1
    except (ValueError, KeyError, OSError) as error:
        print(json.dumps(dict(phase='needs_attention', error=str(error), automatic_gpu_retry=False), ensure_ascii=False))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
