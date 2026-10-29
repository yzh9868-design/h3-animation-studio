"""Portable connection and workflow registry. No generation, imports or model installs."""
from __future__ import annotations

import copy
import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import re
import urllib.error
import urllib.parse
import urllib.request
import uuid

import workflow_adapter as adapter

SKILL = Path(__file__).resolve().parents[1]
EXECUTION_FIELDS = ('schema_version', 'mode', 'adapter', 'bindings', 'references', 'output',
                    'audio', 'limits', 'defaults', 'source_graph_sha256')
HTTP_APIS = [
    {'method': 'GET', 'path': '/system_stats', 'purpose': 'Runtime, system memory and GPU information'},
    {'method': 'GET', 'path': '/object_info', 'purpose': 'Node schemas and available option/model names'},
    {'method': 'GET', 'path': '/object_info/{node_class}', 'purpose': 'One node schema'},
    {'method': 'POST', 'path': '/upload/image', 'purpose': 'Upload an input reference; mutates server storage'},
    {'method': 'POST', 'path': '/prompt', 'purpose': 'Submit an authorized workflow for execution'},
    {'method': 'GET', 'path': '/queue', 'purpose': 'Inspect pending and running tasks'},
    {'method': 'GET', 'path': '/history/{prompt_id}', 'purpose': 'Inspect execution status and outputs'},
    {'method': 'GET', 'path': '/view', 'purpose': 'Download an input or output media file'},
    {'method': 'WS', 'path': '/ws', 'purpose': 'Optional real-time progress; runner currently polls history'},
]


def read(path):
    value = json.loads(Path(path).read_text('utf-8-sig'))
    if not isinstance(value, dict):
        raise ValueError('Expected a JSON object: ' + str(path))
    return value


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', 'utf-8')
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _hash(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':')).encode()).hexdigest()


def _file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _path(base, value):
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (Path(base) / path).resolve()


def validate_url(value):
    if not isinstance(value, str):
        raise ValueError('ComfyUI URL must be text')
    parsed = urllib.parse.urlsplit(value)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('Use an HTTP(S) ComfyUI URL without embedded credentials')
    if parsed.query or parsed.fragment:
        raise ValueError('ComfyUI base URL cannot contain query parameters or fragments')
    try:
        parsed.port
    except ValueError:
        raise ValueError('ComfyUI URL contains an invalid port') from None
    return value.rstrip('/')


def _header_environment(value):
    if not isinstance(value, dict):
        raise ValueError('headers_env must map HTTP header names to environment-variable names')
    for header, variable in value.items():
        if not isinstance(header, str) or not re.fullmatch(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+", header):
            raise ValueError('Invalid authentication header name')
        if not isinstance(variable, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', variable):
            raise ValueError('Store an environment-variable name, never a credential value, in headers_env')
    return dict(value)


def runtime_auth_headers(cfg):
    headers = {}
    for header, variable in _header_environment(cfg.get('headers_env', {})).items():
        value = os.environ.get(variable)
        if not value:
            raise ValueError('Required authentication environment variable is unset: ' + variable)
        if '\n' in value or '\r' in value:
            raise ValueError('Authentication environment variable contains an invalid line break: ' + variable)
        headers[header] = value
    return headers


def _api_graph(graph):
    if not isinstance(graph, dict):
        raise ValueError('Expected an API-format JSON object')
    if isinstance(graph.get('nodes'), list):
        raise ValueError('This is a visual/UI workflow. Export the ComfyUI workflow in API format first.')
    if isinstance(graph.get('prompt'), dict):
        graph = graph['prompt']
    if not graph or not all(isinstance(key, str) and isinstance(node, dict)
                            and isinstance(node.get('class_type'), str)
                            and isinstance(node.get('inputs'), dict) for key, node in graph.items()):
        raise ValueError('Expected an API-format node dictionary with class_type and inputs')
    return graph


def load_graph(path):
    return _api_graph(read(path))


def _profile_file(root, selected, base):
    if not isinstance(selected, str) or not selected.strip():
        raise ValueError('A workflow profile ID or JSON path is required')
    if selected.lower().endswith('.json') or '/' in selected or '\\' in selected:
        path = _path(base, selected)
    else:
        if not re.fullmatch(r'[A-Za-z0-9_-]+', selected):
            raise ValueError('Use a simple workflow profile ID')
        path = root / 'local/profiles' / (selected + '.json')
        if not path.is_file():
            path = root / 'profiles' / (selected + '.json')
    if not path.is_file():
        raise ValueError('Workflow profile not found: ' + str(path))
    return path


def resolve_settings(project, film_comfy=None, skill_root=None):
    """Resolve defaults < local config < project config < explicit film.comfy.

    Incomplete profiles remain inspectable drafts; execution validates their issues.
    Secrets are resolved only by runtime_auth_headers and never stored in settings.
    """
    root = Path(skill_root or SKILL).resolve()
    project = Path(project).resolve()
    explicit = dict(film_comfy or {})
    local_path = root / 'local/comfy.json'
    layers = [(read(local_path), local_path.parent)] if local_path.is_file() else []
    if explicit.get('config'):
        config_path = _path(project, explicit['config'])
        layers.append((read(config_path), config_path.parent))
    layers.append((explicit, project))
    merged = {'base_url': 'http://127.0.0.1:8188', 'ffmpeg': 'ffmpeg', 'ffprobe': 'ffprobe',
              'timeout_seconds': 120, 'headers_env': {}}
    selected, selected_base = 'h3-ref2va', root
    workflow_path = None
    infer = False
    for layer, base in layers:
        if 'headers' in layer or 'api_key' in layer or 'token' in layer:
            raise ValueError('Keep credentials in environment variables and configure headers_env')
        merged.update({k: v for k, v in layer.items() if k not in ('config', 'profile', 'workflow', 'workflow_profile')})
        if 'profile' in layer:
            selected, selected_base = layer['profile'], base
            infer = False
            workflow_path = None
        if 'workflow' in layer:
            workflow_path = _path(base, layer['workflow'])
            infer = 'profile' not in layer
    if workflow_path is not None and infer:
        graph = load_graph(workflow_path)
        profile = adapter.infer_profile(graph, profile_id='project-workflow', workflow=str(workflow_path))
    else:
        profile_file = _profile_file(root, selected, selected_base)
        profile = read(profile_file)
        if workflow_path is None:
            if not profile.get('workflow'):
                raise ValueError('Profile does not specify its API workflow file: ' + str(profile_file))
            workflow_path = _path(profile_file.parent, profile['workflow'])
        graph = load_graph(workflow_path)
    execution = {key: copy.deepcopy(profile[key]) for key in EXECUTION_FIELDS if key in profile}
    defaults = execution.setdefault('defaults', {})
    for key in ('width', 'height', 'seed'):
        if key in merged:
            defaults[key] = merged[key]
    if 'fps' in merged:
        execution.setdefault('limits', {})['fps'] = merged['fps']
    issues = adapter.validate_profile(execution, graph)
    execution['issues'] = list(issues)
    cfg = dict(merged)
    cfg['base_url'] = validate_url(cfg['base_url'])
    _header_environment(cfg.get('headers_env', {}))
    if not isinstance(cfg['timeout_seconds'], (int, float)) or isinstance(cfg['timeout_seconds'], bool) or not math.isfinite(cfg['timeout_seconds']) or cfg['timeout_seconds'] <= 0:
        raise ValueError('timeout_seconds must be positive')
    cfg.update(width=defaults.get('width'), height=defaults.get('height'), seed=defaults.get('seed'),
               fps=execution.get('limits', {}).get('fps'), workflow=str(workflow_path), workflow_profile=execution)
    return cfg


def configure(root, *, url=None, profile=None, timeout=None, headers_env=None, width=None, height=None):
    root = Path(root).resolve()
    path = root / 'local/comfy.json'
    cfg = read(path) if path.is_file() else {}
    if url is not None:
        cfg['base_url'] = validate_url(url)
    if profile is not None:
        _profile_file(root, profile, root)
        cfg['profile'] = profile
    if timeout is not None:
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError('timeout must be positive')
        cfg['timeout_seconds'] = timeout
    if headers_env is not None:
        cfg['headers_env'] = _header_environment(headers_env)
    for key, value in [('width', width), ('height', height)]:
        if value is not None:
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise ValueError('Expected a positive integer for ' + key)
            cfg[key] = value
    cfg.setdefault('base_url', 'http://127.0.0.1:8188')
    cfg.setdefault('profile', 'h3-ref2va')
    save(path, cfg)
    return {'status': 'configured', 'config': str(path), 'settings': cfg,
            'network_requests': 0, 'gpu_submission': False}


def _merge(target, patch):
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _merge(target[key], value)
        else:
            target[key] = copy.deepcopy(value)
    return target


def import_workflow(root, path, name, mapping=None, replace=False):
    root = Path(root).resolve()
    if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9_-]+', name):
        raise ValueError('Use a simple workflow name containing letters, numbers, _ or -')
    if (root / 'profiles' / (name + '.json')).exists():
        raise ValueError('Name conflicts with a bundled profile; choose another name')
    destination = root / 'local/workflows' / (name + '.json')
    profile_path = root / 'local/profiles' / (name + '.json')
    if not replace and (destination.exists() or profile_path.exists()):
        raise ValueError('Workflow name already exists; use --replace explicitly or choose another name')
    source_bytes = Path(path).read_bytes()
    graph = _api_graph(json.loads(source_bytes.decode('utf-8-sig')))
    if Path(path).resolve() == destination.resolve():
        raise ValueError('Import source must differ from its registered copy; the source file is kept unchanged')
    profile = adapter.infer_profile(graph, profile_id=name, workflow='../workflows/' + name + '.json')
    if mapping is not None:
        patch = read(mapping) if not isinstance(mapping, dict) else mapping
        profile = _merge(profile, patch)
    profile['id'] = name
    profile['workflow'] = '../workflows/' + name + '.json'
    # Mapping describes inputs; it cannot redefine which uploaded graph is trusted.
    profile['source_graph_sha256'] = adapter.graph_digest(graph)
    profile['issues'] = adapter.validate_profile(profile, graph)
    # Retain the uploaded document byte-for-byte, including wrappers and metadata.
    # Only the separate profile is generated; the source API is never rewritten.
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        temporary.write_bytes(source_bytes)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    save(profile_path, profile)
    return {'status': 'imported' if not profile['issues'] else 'needs_configuration',
            'profile': name, 'profile_file': str(profile_path), 'workflow': str(destination),
            'issues': profile['issues'], 'network_requests': 0, 'gpu_submission': False}


def _fingerprint(cfg):
    return _hash({'profile': cfg['workflow_profile'], 'workflow_sha256': _file_hash(cfg['workflow']),
                  'base_url': cfg['base_url'], 'headers_env': cfg.get('headers_env', {})})


def _check_path(root, identity):
    return Path(root) / 'local/checks' / (_hash(identity)[:24] + '.json')


def list_workflows(root):
    root = Path(root).resolve()
    rows = []
    for directory in (root / 'profiles', root / 'local/profiles'):
        for path in sorted(directory.glob('*.json')) if directory.is_dir() else []:
            identity = path.stem
            try:
                profile = read(path)
                cfg = resolve_settings(root, {'profile': str(path)}, root)
                status = 'needs_configuration' if cfg['workflow_profile']['issues'] else 'offline_ready'
                checked = _check_path(root, identity)
                if checked.is_file() and not cfg['workflow_profile']['issues']:
                    check = read(checked)
                    if check.get('fingerprint') == _fingerprint(cfg) and check.get('online'):
                        status = check['status']
                refs = cfg['workflow_profile'].get('references', {})
                slots = refs.get('slots', {})
                original_slots = {kind: (len(slots[kind]) if isinstance(slots.get(kind), list) else None)
                                  for kind in ('image', 'audio')}
                if refs.get('dynamic') is True:
                    required_media = {'mode': 'dynamic',
                                      'image': {'min': 1, 'max': refs.get('max_images')},
                                      'audio': {'min': 0, 'max': refs.get('max_audio')}}
                else:
                    required_media = {'mode': 'fixed', **original_slots}
                rows.append({'id': identity, 'name': profile.get('name', identity), 'mode': profile.get('mode'),
                             'adapter': profile.get('adapter'), 'status': status, 'profile_file': str(path),
                             'workflow': cfg['workflow'], 'references': cfg['workflow_profile'].get('references', {}),
                             'required_media': required_media, 'original_media_slots': original_slots,
                             'source_graph_sha256': cfg['workflow_profile'].get('source_graph_sha256'),
                             'output': cfg['workflow_profile'].get('output', {}),
                             'limits': cfg['workflow_profile'].get('limits', {}),
                             'issues': cfg['workflow_profile']['issues'], 'generation_verified': False})
            except (ValueError, OSError, KeyError) as error:
                rows.append({'id': identity, 'status': 'needs_configuration', 'issues': [str(error)],
                             'generation_verified': False})
    return {'workflows': rows, 'network_requests': 0, 'gpu_submission': False,
            'note': 'Node availability and schema compatibility do not prove generation quality.'}


def doctor(root, profile=None, online=False):
    root = Path(root).resolve()
    explicit = {'profile': profile} if profile else {}
    cfg = resolve_settings(root, explicit, root)
    graph = load_graph(cfg['workflow'])
    issues = list(cfg['workflow_profile']['issues'])
    requests = 0
    system = None
    status = 'needs_configuration' if issues else 'offline_ready'
    if online:
        try:
            headers = runtime_auth_headers(cfg)
            def get(route):
                nonlocal requests
                requests += 1
                request = urllib.request.Request(cfg['base_url'] + route, headers=headers, method='GET')
                with urllib.request.urlopen(request, timeout=cfg['timeout_seconds']) as response:
                    return json.loads(response.read().decode('utf-8-sig'))
            stats = get('/system_stats')
            node_info = get('/object_info')
            if not issues:
                # Compile only a local compatibility preview. Dynamic media ports
                # may change in the input layer; no upload or execution occurs.
                active_profile = cfg['workflow_profile']
                limits = active_profile['limits']
                plan = adapter.source_plan({'edit_seconds': limits['min_seconds']}, profile=active_profile)
                refs = active_profile['references']
                if refs.get('dynamic') is True:
                    image_count = 1
                    audio_count = 1 if refs.get('max_audio', 0) > 0 else 0
                else:
                    image_count = len(refs['slots']['image'])
                    audio_count = len(refs['slots']['audio'])
                image_refs = [f'pending_image_{index + 1}.png' for index in range(image_count)]
                audio_refs = [f'pending_audio_{index + 1}.wav' for index in range(audio_count)]
                preview, _ = adapter.compile_graph(graph, 'Configuration compatibility check.', image_refs, audio_refs,
                                                   frames=plan['source_frames'], width=cfg['width'], height=cfg['height'],
                                                   seed=cfg['seed'], prefix='h3_animation_studio/configuration_check',
                                                   profile=active_profile)
                adapter.validate_live_graph(preview, node_info, profile=active_profile)
            system = {'os': stats.get('system', {}).get('os'),
                      'comfyui_version': stats.get('system', {}).get('comfyui_version'),
                      'devices': [{k: device.get(k) for k in ('name', 'type', 'vram_total')}
                                  for device in stats.get('devices', [])]}
            status = 'schema_compatible' if not issues else 'needs_configuration'
        except (ValueError, KeyError, OSError, urllib.error.URLError) as error:
            issues.append(str(error))
            status = 'needs_configuration'
    selected = profile
    if not selected:
        local = root / 'local/comfy.json'
        selected = read(local).get('profile', 'h3-ref2va') if local.is_file() else 'h3-ref2va'
    identity = Path(selected).stem if str(selected).lower().endswith('.json') else str(selected)
    result = {'profile': identity, 'status': status, 'online': online, 'issues': issues,
              'workflow': cfg['workflow'], 'fingerprint': _fingerprint(cfg),
              'checked_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'network_requests': requests, 'gpu_submission': False, 'generation_verified': False}
    if system is not None:
        result['system'] = system
    save(_check_path(root, identity), result)
    return result
