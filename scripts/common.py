"""Small shared manifest/approval helpers. No creative generation or network."""
from pathlib import Path
import datetime, hashlib, json, math, uuid
import comfy_config

SKILL = Path(__file__).resolve().parents[1]

def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))

def save(path, data):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf8')
        tmp.replace(path)
    finally:
        tmp.unlink(missing_ok=True)

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def stamp():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

def need(ok, message):
    if not ok: raise ValueError(message)

def locate(project, path):
    p = Path(path).expanduser()
    return p.resolve() if p.is_absolute() else (Path(project) / p).resolve()

def load_film(project):
    f = read(Path(project) / 'film.json'); need(isinstance(f, dict), 'film.json must be an object')
    need(isinstance(f.get('title'), str) and f['title'].strip(), 'Missing title')
    need(isinstance(f.get('segments'), list) and f['segments'], 'Missing segments')
    for key in ['segments', 'assets', 'characters']:
        rows = f.get(key, []); need(isinstance(rows, list), key + ' must be an array')
        ids = [r.get('id') for r in rows]
        need(all(isinstance(i, str) and i and all(c.isalnum() or c in '_-' for c in i) for i in ids), 'Use simple IDs in ' + key)
        need(len(ids) == len(set(ids)), 'Duplicate IDs in ' + key)
    assets = {a['id']: a for a in f.get('assets', [])}; seen = set()
    for s in f['segments']:
        t = s.get('edit_seconds')
        need(isinstance(t, (int, float)) and not isinstance(t, bool) and math.isfinite(t) and t > 0,
             'edit_seconds must be positive and finite: ' + s['id'])
        prev = s.get('continuity_from'); need(not prev or prev in seen, 'continuity_from must be an earlier segment')
        refs = s.get('references', []); need(isinstance(refs, list), 'references must be an array'); labels = []
        for ref in refs:
            need(ref.get('asset_id') in assets, 'Unknown reference asset in ' + s['id'])
            need(isinstance(ref.get('label'), str), 'Missing reference label'); labels.append(ref['label'])
        need(len(labels) == len(set(labels)), 'Duplicate reference labels in ' + s['id']); seen.add(s['id'])
    return f

def settings(project, film):
    return comfy_config.resolve_settings(project, film.get('comfy', {}), skill_root=SKILL)

def _digest(data):
    return hashlib.sha256(json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf8')).hexdigest()

def review_digest(project, film):
    """Full-package identity for presentation and safe legacy migration only."""
    try:
        cfg = settings(project, film)
    except (ValueError, OSError, KeyError) as error:
        cfg = {'configuration_error': str(error), 'requested_configuration': film.get('comfy', {})}
    wf = Path(cfg['workflow']) if cfg.get('workflow') else None
    media = []
    for a in film.get('assets', []):
        p = locate(project, a.get('path', '__missing__'))
        media.append(dict(id=a['id'], path=str(p), sha256=sha(p) if p.is_file() else 'MISSING'))
    return _digest(dict(film=film, settings=cfg, workflow_sha256=sha(wf) if wf and wf.is_file() else 'MISSING', media=media))

def selected_segments(film, segment_ids=None):
    by_id = {s['id']: s for s in film['segments']}
    ids = list(by_id) if segment_ids is None else list(segment_ids)
    need(ids and len(ids) == len(set(ids)) and set(ids) <= set(by_id), 'Unknown/duplicate approved segment IDs')
    return [by_id[sid] for sid in ids]

def segment_digest(project, film, segment):
    """Bind actual segment inputs and declared upstream definitions, never unrelated shots."""
    by_id = {s['id']: s for s in film['segments']}; assets = {a['id']: a for a in film.get('assets', [])}
    cfg = settings(project, film); wf = Path(cfg['workflow']); memo = {}; active = set()
    def visit(sid):
        need(sid in by_id and sid not in active, 'Invalid continuity dependency: ' + sid)
        if sid in memo: return memo[sid]
        active.add(sid); s = by_id[sid]; media = []
        for ref in s.get('references', []):
            a = assets.get(ref.get('asset_id')); need(a is not None, 'Unknown reference asset in ' + sid)
            p = locate(project, a.get('path', '__missing__'))
            media.append(dict(reference=ref, asset=a, resolved_path=str(p), sha256=sha(p) if p.is_file() else 'MISSING'))
        previous = s.get('continuity_from')
        data = dict(segment=s, media=media, settings=cfg,
                    mode=s.get('mode', film.get('mode', film.get('h3_mode', 'Ref2VA'))),
                    audio_mode=film.get('audio_mode', 'h3_native'),
                    workflow_sha256=sha(wf) if wf.is_file() else 'MISSING',
                    continuity_digest=visit(previous) if previous else None)
        memo[sid] = _digest(data); active.remove(sid)
        return memo[sid]
    return visit(segment if isinstance(segment, str) else segment['id'])

def ready_errors(project, film, segment_ids=None):
    errors = []; chosen = selected_segments(film, segment_ids)
    if segment_ids is None and not film.get('script', '').strip(): errors.append('Missing complete script')
    if film.get('audio_mode', 'h3_native') != 'h3_native': errors.append('Built-in executor requires H3 native audio')
    needed_assets = {r['asset_id'] for s in chosen for r in s.get('references', [])}
    for a in film.get('assets', []):
        if segment_ids is not None and a['id'] not in needed_assets: continue
        if a.get('kind') not in ('image', 'video', 'audio'): errors.append('Unknown asset kind: ' + a['id'])
        if not a.get('path') or not locate(project, a['path']).is_file(): errors.append('Missing actual asset: ' + a['id'])
    for s in chosen:
        for key in ('prompt_zh', 'prompt_en'):
            if not isinstance(s.get(key), str) or not s[key].strip(): errors.append('Missing ' + key + ': ' + s['id'])
        if not s.get('shots'): errors.append('Missing storyboard shots: ' + s['id'])
        if s.get('mode', 'Ref2VA') == 'Ref2VA' and not s.get('references'): errors.append('Missing references: ' + s['id'])
    total = film.get('duration_seconds')
    if segment_ids is None and total is not None and abs(sum(s['edit_seconds'] for s in film['segments']) - total) > .001:
        errors.append('Segment durations differ from target')
    try:
        cfg = settings(project, film)
        if not cfg.get('workflow') or not Path(cfg['workflow']).is_file():
            errors.append('Missing execution workflow')
        issues = cfg.get('configuration_issues', cfg.get('workflow_profile', {}).get('issues', []))
        errors.extend('ComfyUI configuration: ' + str(issue) for issue in issues)
    except (ValueError, OSError, KeyError) as error:
        errors.append('ComfyUI configuration: ' + str(error))
    return errors

def authorization_record(project, film, segment_id, evidence, kind, manifest=None, legacy_digest=None):
    need(isinstance(evidence, str) and evidence.strip(), 'Record the actual user confirmation; do not invent consent')
    record = dict(segment_digest=segment_digest(project, film, segment_id), authorization_id=uuid.uuid4().hex,
                  authorization_type=kind, user_confirmation=evidence, confirmed_at=stamp())
    if manifest:
        record.update(review_digest=manifest['review_digest'], html_sha256=manifest['html_sha256'])
    if legacy_digest: record['legacy_review_digest'] = legacy_digest
    return record

def load_approval(project, film, *, allow_stale_legacy=False):
    path = Path(project) / 'approval.json'
    need(path.is_file(), 'User confirmation of the complete HTML package is required')
    a = read(path)
    if a.get('version') == 2:
        need(isinstance(a.get('records'), dict), 'Invalid segment approval records')
        return a
    need(isinstance(a.get('user_confirmation'), str) and a['user_confirmation'].strip(), 'Missing actual user confirmation evidence')
    report = Path(project) / 'review/index.html'
    valid = a.get('review_digest') == review_digest(project, film) and report.is_file() and sha(report) == a.get('html_sha256')
    if not valid:
        need(allow_stale_legacy, 'Legacy approval is stale; restore its approved version before migration, or explicitly authorize only the repaired segment')
        return dict(version=2, records={}, segment_ids=[], initial_approval=a, suspended_legacy_approval=a)
    ids = [s['id'] for s in selected_segments(film, a.get('segment_ids'))]
    records = {sid: authorization_record(project, film, sid, a['user_confirmation'], 'legacy', a, a['review_digest']) for sid in ids}
    migrated = dict(version=2, records=records, segment_ids=ids, initial_approval=a,
                    user_confirmation=a['user_confirmation'], migrated_at=stamp())
    save(path, migrated)
    return migrated

def require_approval(project, film, segment_ids=None):
    errors = ready_errors(project, film, segment_ids)
    need(not errors, 'Project not ready: ' + '; '.join(errors))
    a = load_approval(project, film)
    for segment in selected_segments(film, segment_ids):
        sid = segment['id']; record = a['records'].get(sid)
        need(isinstance(record, dict) and isinstance(record.get('user_confirmation'), str)
             and record['user_confirmation'].strip(), 'User did not approve this segment: ' + sid)
        need(record.get('segment_digest') == segment_digest(project, film, sid),
             'Approval is stale for ' + sid + '; record the explicit local repair request')
    return a
