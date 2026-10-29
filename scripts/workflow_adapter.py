"""Pure, profile-bound H3 workflow adaptation. No network, model loading or GPU."""
from __future__ import annotations

import copy
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re


def _need(ok, message):
    if not ok:
        raise ValueError(message)


def load_builtin_profile():
    path = Path(__file__).resolve().parents[1] / 'profiles' / 'h3-ref2va.json'
    return json.loads(path.read_text('utf-8-sig'))


def graph_digest(graph):
    """Identity of the imported API graph, including its metadata and parameters."""
    return hashlib.sha256(json.dumps(graph, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':')).encode('utf-8')).hexdigest()


def _link(value):
    return (isinstance(value, list) and len(value) == 2 and isinstance(value[0], str)
            and isinstance(value[1], int) and not isinstance(value[1], bool))


def _integer(value, minimum=0):
    return isinstance(value, int) and not isinstance(value, bool) and value >= minimum


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _graph_errors(graph):
    if not isinstance(graph, dict) or not graph:
        return ['workflow: expected a nonempty API-format node dictionary']
    if isinstance(graph.get('nodes'), list):
        return ['workflow: visual UI JSON is not API-format JSON; export the API workflow']
    errors = []
    for node_id, node in graph.items():
        if (not isinstance(node_id, str) or not isinstance(node, dict)
                or not isinstance(node.get('class_type'), str) or not isinstance(node.get('inputs'), dict)):
            errors.append('workflow: invalid API node ' + str(node_id))
            continue
        for key, value in node['inputs'].items():
            if _link(value) and value[0] not in graph:
                errors.append('workflow: unresolved link ' + node_id + '.' + str(key))
    return errors


def _ancestors(graph, node_id):
    found = set()
    pending = [node_id]
    while pending:
        current = pending.pop()
        if current in found or current not in graph:
            continue
        found.add(current)
        pending.extend(v[0] for v in graph[current].get('inputs', {}).values() if _link(v))
    return found


def _value_binding(graph, node_id, name):
    """Follow a plain primitive, but do not guess how to rewrite arbitrary links."""
    if node_id not in graph or name not in graph[node_id]['inputs']:
        return None, None
    value = graph[node_id]['inputs'][name]
    if not _link(value):
        return {'node': node_id, 'input': name}, value
    source = graph.get(value[0], {})
    if source.get('class_type') in ('PrimitiveStringMultiline', 'PrimitiveString', 'PrimitiveInt', 'PrimitiveFloat'):
        choices = [key for key in ('value', 'text', 'string') if key in source.get('inputs', {})]
        if len(choices) == 1 and not _link(source['inputs'][choices[0]]):
            return {'node': value[0], 'input': choices[0]}, source['inputs'][choices[0]]
    return None, None


def _frame_binding(graph, target, limits):
    binding, _ = _value_binding(graph, target, 'length')
    if binding is not None:
        return binding
    value = graph[target]['inputs'].get('length')
    if not _link(value):
        return None
    math_node = graph.get(value[0], {})
    if math_node.get('class_type') != 'ComfyMathExpression':
        return None
    # One known H3 formula: seconds -> rounded frame count -> the 5+17n grid.
    # Parse no code and evaluate no expression supplied by a workflow.
    lower, step, fps = limits['frame_min'], limits['frame_step'], limits['fps']
    base = f'max({lower},round(a*{fps:g}))'
    expected = f'{base}+({lower}-({base}%{step}))%{step}'
    expression = re.sub(r'\s+', '', str(math_node.get('inputs', {}).get('expression', '')))
    if expression != expected:
        return None
    binding, _ = _value_binding(graph, value[0], 'values.a')
    if binding is not None:
        return {**binding, 'unit': 'seconds'}
    return None


def _native_audio(graph, output_id):
    """Recognize a selected output's native H3 decoder/sampler connection."""
    output = graph.get(output_id, {})
    cls = output.get('class_type')
    holder = output_id
    if cls == 'SaveVideo':
        video_link = output.get('inputs', {}).get('video')
        if not _link(video_link) or graph.get(video_link[0], {}).get('class_type') != 'CreateVideo':
            return None, None, None, ['audio: SaveVideo requires a directly mapped CreateVideo source']
        holder = video_link[0]
    elif cls != 'VHS_VideoCombine':
        return None, None, None, ['output: this adapter supports VHS_VideoCombine or SaveVideo/CreateVideo']
    inputs = graph[holder]['inputs']
    audio_link = inputs.get('audio')
    if not _link(audio_link) or graph.get(audio_link[0], {}).get('class_type') != 'VAEDecodeAudio':
        return holder, None, None, ['audio: selected output must use native VAEDecodeAudio, not silence or an external mix']
    samples = graph[audio_link[0]]['inputs'].get('samples')
    if not _link(samples):
        return holder, None, None, ['audio: native audio decoder must be connected to its generation sampler']
    image_link = inputs.get('images')
    if not _link(image_link) or samples[0] not in _ancestors(graph, image_link[0]):
        return holder, None, None, ['audio: audio and video must come from the same generation sampler']
    links = [
        {'node': audio_link[0], 'input': 'samples', 'source': samples},
        {'node': holder, 'input': 'audio', 'source': audio_link},
    ]
    return holder, samples[0], links, []


def _reference_slots(graph, target, refs):
    """Read existing media inputs without creating ports, loaders or connections."""
    slots = {'image': [], 'audio': []}
    errors = []
    node = graph.get(target, {})
    for kind, label in [('image', 'Picture'), ('audio', 'Audio')]:
        prefix = refs.get(kind + '_prefix', '')
        if not prefix:
            errors.append('references: configure ' + kind + '_prefix')
            continue
        matched = []
        for socket, value in node.get('inputs', {}).items():
            if not socket.startswith(prefix):
                continue
            suffix = socket[len(prefix):]
            if not suffix.isdigit():
                continue
            matched.append((int(suffix), socket, value))
        matched.sort()
        if not refs.get('dynamic') and [item[0] for item in matched] != list(range(len(matched))):
            errors.append('references: existing ' + kind + ' ports must be consecutive from zero')
        for index, socket, value in matched:
            loader = graph.get(value[0], {}) if _link(value) else {}
            if (not _link(value) or value[1] != 0
                    or loader.get('class_type') != refs.get(kind + '_loader')
                    or kind not in loader.get('inputs', {}) or _link(loader['inputs'][kind])):
                if not refs.get('dynamic'):
                    errors.append('references: ' + socket + ' needs an explicit existing '
                                  + str(refs.get(kind + '_loader')) + '.' + kind + ' filename input')
                continue
            slots[kind].append({'node': value[0], 'input': kind, 'socket': socket,
                                'label': label + ' ' + str(index + 1)})
    if not refs.get('dynamic') and not slots['image']:
        errors.append('references: the uploaded API has no usable existing image reference slot; provide a matching API instead of adding nodes')
    return slots, errors


def _reference_kind(name, refs):
    for kind in ('image', 'audio'):
        prefix = refs.get(kind + '_prefix')
        if isinstance(prefix, str) and name.startswith(prefix) and name[len(prefix):].isdigit():
            return kind
    return None


def _uses(graph, node_id):
    return [(consumer, name) for consumer, node in graph.items()
            for name, value in node['inputs'].items() if _link(value) and value[0] == node_id]


def _dedicated_reference_loaders(graph, refs):
    """Only direct input loaders with no use outside the selected reference ports."""
    target = refs['target']; result = {}
    for name, value in graph[target]['inputs'].items():
        kind = _reference_kind(name, refs)
        if not kind or not _link(value) or value[1] != 0:
            continue
        node_id = value[0]; node = graph.get(node_id, {})
        if (node.get('class_type') != refs[kind + '_loader']
                or kind not in node.get('inputs', {}) or _link(node['inputs'][kind])):
            continue
        if all(consumer == target and _reference_kind(socket, refs) == kind
               for consumer, socket in _uses(graph, node_id)):
            result[node_id] = kind
    return result


def _semantic_bindings(graph, profile):
    """Find the only literal inputs that the selected H3/output semantics permit."""
    target = profile.get('references', {}).get('target')
    output_id = profile.get('output', {}).get('node')
    limits = profile.get('limits', {})
    expected = {key: None for key in ('prompt', 'seed', 'frames', 'width', 'height', 'fps', 'filename_prefix')}
    expected['preview_frames'] = []
    if target not in graph:
        return expected
    expected['prompt'], _ = _value_binding(graph, target, 'prompt')
    try:
        expected['frames'] = _frame_binding(graph, target, limits)
    except (KeyError, TypeError, ValueError):
        pass
    for key in ('width', 'height'):
        if not _link(graph[target]['inputs'].get(key)):
            expected[key], _ = _value_binding(graph, target, key)
    holder, sampler, _, _ = _native_audio(graph, output_id)
    if sampler:
        expected['seed'], _ = _value_binding(graph, sampler, 'seed')
    if holder:
        key = 'frame_rate' if graph[holder]['class_type'] == 'VHS_VideoCombine' else 'fps'
        expected['fps'], _ = _value_binding(graph, holder, key)
    expected['filename_prefix'], _ = _value_binding(graph, output_id, 'filename_prefix')
    for node_id in _ancestors(graph, output_id):
        node = graph[node_id]
        if node.get('class_type') == 'ModelPreviewOverrideKJ' and 'preview_frames' in node['inputs']:
            binding, _ = _value_binding(graph, node_id, 'preview_frames')
            if binding:
                expected['preview_frames'].append(binding)
    expected['preview_frames'].sort(key=lambda item: (item['node'], item['input']))
    return expected


def _binding_paths(profile):
    paths = set()
    bindings = profile.get('bindings', {})
    for key in ('prompt', 'seed', 'frames', 'width', 'height', 'fps', 'filename_prefix'):
        binding = bindings.get(key)
        if isinstance(binding, dict):
            paths.add((binding['node'], binding['input']))
    for binding in bindings.get('preview_frames', []):
        paths.add((binding['node'], binding['input']))
    for kind in ('image', 'audio'):
        for slot in profile.get('references', {}).get('slots', {}).get(kind, []):
            paths.add((slot['node'], slot['input']))
    return paths


def assert_input_only_changes(original, submitted, profile):
    """Lock the generation backbone; permit only declared task and media-input changes."""
    problems = validate_profile(profile, original, check_source=True)
    _need(not problems, 'Cannot verify original API: ' + '; '.join(problems))
    _need(isinstance(submitted, dict), 'Submitted workflow must be an API graph')
    problems = _graph_errors(submitted)
    _need(not problems, 'Submitted workflow is invalid: ' + '; '.join(problems))
    refs = profile['references']; dynamic = refs.get('dynamic', False)
    target = refs['target']
    removable = _dedicated_reference_loaders(original, refs) if dynamic else {}
    removed = set(original) - set(submitted)
    added = set(submitted) - set(original)
    _need(removed <= set(removable), 'Generation-backbone or shared nodes cannot be removed: ' + ', '.join(sorted(removed - set(removable))))
    if not dynamic:
        _need(not removed and not added, 'Workflow structure changed: nodes cannot be added or removed')
    else:
        slots, errors = _reference_slots(submitted, target, {**refs, 'dynamic': False})
        _need(not errors, 'Invalid submitted media references: ' + '; '.join(errors))
        _need(1 <= len(slots['image']) <= refs['max_images'] and len(slots['audio']) <= refs['max_audio'],
              'Submitted reference counts exceed model limits')
        assigned = {slot['node']: kind for kind, values in slots.items() for slot in values}
        for node_id in added:
            kind = assigned.get(node_id); node = submitted[node_id]
            _need(kind is not None and node_id.startswith('STUDIO_REF_' + kind.upper() + '_'),
                  'Only task-bound STUDIO_REF image/audio input loaders may be added: ' + node_id)
            _need(set(node) == {'class_type', 'inputs'} and node['class_type'] == refs[kind + '_loader']
                  and set(node['inputs']) == {kind}, 'Unexpected added input-loader structure: ' + node_id)
            _server_name(node['inputs'][kind], kind)
            _need(all(consumer == target and _reference_kind(socket, refs) == kind
                      for consumer, socket in _uses(submitted, node_id)), 'New input loader feeds an unrelated graph branch: ' + node_id)
    allowed = _binding_paths(profile)
    if dynamic:
        # Shared input loaders belong to another branch as well; keep their entire
        # node unchanged and use a separate task loader for the new reference.
        allowed -= {(slot['node'], slot['input']) for values in refs.get('slots', {}).values() for slot in values}
        allowed |= {(node_id, kind) for node_id, kind in removable.items()}
    for node_id, before in original.items():
        if node_id in removed:
            continue
        after = submitted[node_id]
        _need(isinstance(after, dict) and set(after) == set(before), 'Workflow node fields changed: ' + node_id)
        for key in before:
            if key != 'inputs':
                _need(after[key] == before[key], 'Workflow node type/metadata changed: ' + node_id + '.' + key)
        old_inputs, new_inputs = before['inputs'], after.get('inputs')
        _need(isinstance(new_inputs, dict), 'Workflow inputs are invalid: ' + node_id)
        ignored = ({name for name in set(old_inputs) | set(new_inputs) if _reference_kind(name, refs)}
                   if dynamic and node_id == target else set())
        _need(set(new_inputs) - ignored == set(old_inputs) - ignored, 'Generation-backbone input ports changed: ' + node_id)
        for name, old_value in old_inputs.items():
            if name in ignored:
                continue
            new_value = new_inputs[name]
            if old_value == new_value:
                continue
            _need(not _link(old_value) and not _link(new_value),
                  'Workflow connection changed: ' + node_id + '.' + name)
            _need((node_id, name) in allowed, 'Undeclared workflow parameter changed: ' + node_id + '.' + name)
    return True


def infer_profile(graph, profile_id='imported', workflow=None):
    """Infer only unambiguous H3 bindings. Report unresolved choices as issues."""
    base = load_builtin_profile()
    profile = {
        'schema_version': 1, 'id': profile_id, 'name': profile_id,
        'mode': 'Ref2VA', 'adapter': 'h3_ref2va', 'workflow': workflow,
        'bindings': {key: None for key in ('prompt', 'seed', 'frames', 'width', 'height', 'fps', 'filename_prefix')},
        'references': copy.deepcopy(base['references']), 'output': {'node': None, 'require_audio': True},
        'audio': {'native_links': []}, 'limits': copy.deepcopy(base['limits']),
        'defaults': {'width': None, 'height': None, 'seed': None}, 'issues': [],
        'source_graph_sha256': graph_digest(graph),
    }
    profile['bindings']['preview_frames'] = []
    profile['references']['target'] = None
    profile['references']['slots'] = {'image': [], 'audio': []}
    profile['references']['dynamic'] = True
    profile['references']['max_images'] = 9
    profile['references']['max_audio'] = 3
    graph_errors = _graph_errors(graph)
    if graph_errors:
        profile['adapter'] = 'unsupported'
        profile['mode'] = 'unknown'
        profile['issues'] = graph_errors
        return profile
    h3_nodes = [key for key, node in graph.items() if node['class_type'] == 'MiniMaxH3ReferenceToVideo']
    outputs = [key for key, node in graph.items()
               if node['class_type'] in ('VHS_VideoCombine', 'SaveVideo')
               and node['inputs'].get('save_output', True) is not False]
    if len(h3_nodes) == 1:
        h3 = h3_nodes[0]
        profile['references']['target'] = h3
        profile['references']['slots'], _ = _reference_slots(graph, h3, profile['references'])
        binding, _ = _value_binding(graph, h3, 'prompt')
        profile['bindings']['prompt'] = binding
        for key in ('width', 'height'):
            value = graph[h3]['inputs'].get(key)
            if not _link(value):
                profile['bindings'][key], profile['defaults'][key] = _value_binding(graph, h3, key)
        if len(outputs) == 1:
            output = outputs[0]
            profile['output']['node'] = output
            holder, sampler, links, _ = _native_audio(graph, output)
            if links:
                profile['audio']['native_links'] = links
            if sampler:
                profile['bindings']['seed'], profile['defaults']['seed'] = _value_binding(graph, sampler, 'seed')
            if holder:
                fps_key = 'frame_rate' if graph[holder]['class_type'] == 'VHS_VideoCombine' else 'fps'
                profile['bindings']['fps'], fps = _value_binding(graph, holder, fps_key)
                if _number(fps) and fps > 0:
                    profile['limits']['fps'] = fps
                profile['bindings']['filename_prefix'], _ = _value_binding(graph, output, 'filename_prefix')
            for key, node in graph.items():
                if 'preview_frames' in node['inputs'] and key in _ancestors(graph, output):
                    binding, _ = _value_binding(graph, key, 'preview_frames')
                    if binding:
                        profile['bindings']['preview_frames'].append(binding)
        profile['bindings']['frames'] = _frame_binding(graph, h3, profile['limits'])
    elif not h3_nodes:
        profile['adapter'] = 'unsupported'
        profile['mode'] = 'unknown'
    profile['issues'] = validate_profile(profile, graph)
    return profile


def _binding_errors(binding, graph, name, *, optional=False):
    if binding is None:
        return [] if optional else ['bindings: configure ' + name]
    if (not isinstance(binding, dict) or not isinstance(binding.get('node'), str)
            or not isinstance(binding.get('input'), str)):
        return ['bindings: invalid ' + name]
    node = graph.get(binding['node'])
    if not node or binding['input'] not in node.get('inputs', {}):
        return ['bindings: missing node/input for ' + name]
    if _link(node['inputs'][binding['input']]):
        return ['bindings: ' + name + ' must target a literal input, not overwrite a graph link']
    return []


def validate_profile(profile, graph, *, check_source=True):
    """Recompute issues from current fields; cached inference issues are not gates."""
    errors = _graph_errors(graph)
    if errors:
        return errors
    if not isinstance(profile, dict) or profile.get('schema_version') != 1:
        return ['profile: schema_version must be 1']
    if check_source and profile.get('source_graph_sha256') != graph_digest(graph):
        errors.append('source: uploaded API fingerprint is missing or changed; reimport the user-authorized source instead of rewriting it')
    if profile.get('adapter') != 'h3_ref2va' or str(profile.get('mode', '')).lower() != 'ref2va':
        return ['adapter: only H3 Ref2VA native audiovisual execution is implemented']
    bindings = profile.get('bindings', {})
    if not isinstance(bindings, dict):
        return ['bindings: expected an object']
    for key in ('prompt', 'seed', 'frames', 'fps', 'filename_prefix'):
        errors.extend(_binding_errors(bindings.get(key), graph, key))
    frame_binding = bindings.get('frames')
    if isinstance(frame_binding, dict) and frame_binding.get('unit', 'frames') not in ('frames', 'seconds'):
        errors.append('bindings: frames unit must be frames or seconds')
    for key in ('width', 'height'):
        errors.extend(_binding_errors(bindings.get(key), graph, key, optional=True))
    previews = bindings.get('preview_frames', [])
    if not isinstance(previews, list):
        errors.append('bindings: preview_frames must be a list')
    else:
        for binding in previews:
            errors.extend(_binding_errors(binding, graph, 'preview_frames'))
    refs = profile.get('references', {})
    target = refs.get('target') if isinstance(refs, dict) else None
    if graph.get(target, {}).get('class_type') != 'MiniMaxH3ReferenceToVideo':
        errors.append('references: configure one MiniMaxH3ReferenceToVideo target')
    elif any(key not in graph[target]['inputs'] for key in ('prompt', 'length', 'width', 'height')):
        errors.append('references: H3 target lacks expected prompt/length/width/height inputs')
    if not isinstance(refs, dict):
        return errors + ['references: expected an object']
    for key in ('image_prefix', 'audio_prefix', 'image_loader', 'audio_loader'):
        if not isinstance(refs.get(key), str) or not refs[key]:
            errors.append('references: configure ' + key)
    if refs.get('image_loader') != 'LoadImage' or refs.get('audio_loader') != 'LoadAudio':
        errors.append('references: dynamic material adaptation uses only LoadImage and LoadAudio input nodes')
    if not _integer(refs.get('max_images'), 1) or not _integer(refs.get('max_audio')):
        errors.append('references: invalid image/audio limits')
    slots, slot_errors = _reference_slots(graph, target, refs)
    errors.extend(slot_errors)
    if (check_source or not refs.get('dynamic')) and refs.get('slots') != slots:
        errors.append('references: configured media slots must match the uploaded API existing loaders and connections exactly')
    output = profile.get('output', {})
    output_id = output.get('node') if isinstance(output, dict) else None
    if output_id not in graph:
        errors.append('output: configure one output node (multiple or missing output candidates require an explicit mapping)')
    else:
        holder, _, actual_links, audio_errors = _native_audio(graph, output_id)
        errors.extend(audio_errors)
        declared_links = profile.get('audio', {}).get('native_links', [])
        if not actual_links or declared_links != actual_links:
            errors.append('audio: configure the selected output native decoder/sampler links')
        if output.get('require_audio') is not True:
            errors.append('audio: this H3 adapter requires native audio output')
        if holder and target and target not in _ancestors(graph, holder):
            errors.append('references: selected H3 target does not feed the selected output')
        if graph[output_id]['inputs'].get('pingpong') or graph[output_id]['inputs'].get('loop_count', 0):
            errors.append('output: looping/pingpong is not supported by the source-frame collection contract')
        if graph[output_id]['inputs'].get('trim_to_audio'):
            errors.append('output: trim_to_audio changes planned frame counts; configure a frame-preserving output')
    limits = profile.get('limits', {})
    if not isinstance(limits, dict):
        return errors + ['limits: expected an object']
    for key in ('frame_min', 'frame_step', 'frame_max', 'dimension_multiple', 'max_dimension'):
        if not _integer(limits.get(key), 1):
            errors.append('limits: configure positive integer ' + key)
    for key in ('fps', 'min_seconds', 'max_seconds'):
        if not _number(limits.get(key)) or limits[key] <= 0:
            errors.append('limits: configure positive ' + key)
    if all(_number(limits.get(key)) for key in ('min_seconds', 'max_seconds')) and limits['min_seconds'] > limits['max_seconds']:
        errors.append('limits: min_seconds exceeds max_seconds')
    defaults = profile.get('defaults', {})
    if not isinstance(defaults, dict):
        return errors + ['defaults: expected an object']
    multiple, maximum = limits.get('dimension_multiple'), limits.get('max_dimension')
    if not all(_integer(defaults.get(key), 1) for key in ('width', 'height')):
        errors.append('dimensions: expected width/height must be configured (linked inputs are preserved)')
    elif _integer(multiple, 1) and _integer(maximum, 1):
        if any(defaults[key] % multiple or defaults[key] > maximum for key in ('width', 'height')):
            errors.append('dimensions: expected width/height must respect profile bounds and alignment')
    if not _integer(defaults.get('seed')):
        errors.append('defaults: configure a nonnegative integer seed')
    expected = _semantic_bindings(graph, profile)
    for key in ('prompt', 'seed', 'frames', 'width', 'height', 'fps', 'filename_prefix'):
        binding = bindings.get(key)
        if binding != expected[key]:
            errors.append('bindings: ' + key + ' does not match its existing semantic input; model/LoRA/optimization parameters cannot be rebound as task inputs')
    if isinstance(previews, list) and any(binding not in expected['preview_frames'] for binding in previews):
        errors.append('bindings: preview_frames must use existing preview inputs')
    return errors


def source_plan(segment, profile=None):
    limits = (profile if profile is not None else load_builtin_profile())['limits']
    fps = limits['fps']
    _need(_number(fps) and fps > 0, 'Profile fps must be positive')
    seconds = segment.get('edit_seconds')
    _need(_number(seconds) and seconds > 0, 'edit_seconds must be positive and finite')
    edit_frames = round(seconds * fps)
    _need(edit_frames > 0 and abs(seconds * fps - edit_frames) < 1e-5,
          f'edit_seconds must lie on the {fps:g}-fps edit grid')
    lower, step, upper = (limits[key] for key in ('frame_min', 'frame_step', 'frame_max'))
    _need(all(_integer(value, 1) for value in (lower, step, upper)), 'Profile frame bounds must be positive integers')
    frames = segment.get('source_frames')
    if frames is None:
        needed = max(edit_frames, math.ceil(limits['min_seconds'] * fps))
        frames = lower + step * max(0, math.ceil((needed - lower) / step))
    _need(_integer(frames, 1) and lower <= frames <= upper and (frames - lower) % step == 0,
          f'source_frames must be {lower}..{upper} and congruent to {lower} modulo {step} for this profile')
    _need(frames >= edit_frames, 'Source cannot be shorter than the approved edit window')
    max_on_grid = lower + step * math.floor((min(upper, limits['max_seconds'] * fps) - lower) / step)
    _need(limits['min_seconds'] <= frames / fps <= limits['max_seconds'],
          f"Planned source must be {limits['min_seconds']:g}..{limits['max_seconds']:g} seconds. "
          f'On this grid the maximum is {max_on_grid} frames / {max_on_grid / fps:g} seconds; split or adjust the segment before approval')
    return {'fps': fps, 'source_frames': frames, 'source_seconds': frames / fps,
            'edit_frames': edit_frames, 'edit_seconds': float(seconds),
            'discarded_tail_seconds': (frames - edit_frames) / fps}


def _server_name(value, kind):
    _need(isinstance(value, str) and value and '\\' not in value and ':' not in value
          and all(ord(c) >= 32 for c in value), 'Unsafe uploaded reference filename')
    path = PurePosixPath(value)
    _need(not path.is_absolute() and '..' not in path.parts and not value.endswith('/'), 'Reference must use a server-relative filename')
    allowed = {'.png', '.jpg', '.jpeg', '.webp'} if kind == 'image' else {'.wav', '.mp3', '.flac', '.ogg', '.m4a'}
    _need(path.suffix.lower() in allowed, 'Unsupported ' + kind + ' reference')
    return value


def _set_binding(graph, binding, value):
    if binding is not None:
        graph[binding['node']]['inputs'][binding['input']] = value


def compile_graph(template, prompt, images, audios, *, frames, width, height, seed, prefix, profile=None):
    """Bind task inputs and media references while preserving the generation backbone."""
    selected = copy.deepcopy(profile if profile is not None else infer_profile(template))
    selected.setdefault('defaults', {}).update(width=width, height=height, seed=seed)
    problems = validate_profile(selected, template)
    _need(not problems, 'Workflow profile is not executable: ' + '; '.join(problems))
    _need(isinstance(prompt, str) and prompt.strip(), 'Approved English H3 prompt is required')
    refs = selected['references']
    _need(1 <= len(images) <= refs['max_images'] and len(audios) <= refs['max_audio'], 'Reference image/audio count exceeds profile limits')
    slots = refs['slots']
    if not refs.get('dynamic'):
        for kind, values in [('image', images), ('audio', audios)]:
            _need(len(values) == len(slots[kind]), 'Reference input count differs from the explicitly fixed-slot profile')
    source_plan({'edit_seconds': 1 / selected['limits']['fps'], 'source_frames': frames}, selected)
    _need(isinstance(prefix, str) and prefix and ':' not in prefix and '\\' not in prefix
          and not PurePosixPath(prefix).is_absolute() and '..' not in PurePosixPath(prefix).parts, 'Output prefix must be server relative')
    graph = copy.deepcopy(template)
    bindings = selected['bindings']
    for key, value in [('prompt', prompt), ('seed', seed), ('frames', frames), ('width', width), ('height', height),
                       ('fps', selected['limits']['fps']), ('filename_prefix', prefix)]:
        binding = bindings.get(key)
        if key == 'frames' and binding.get('unit') == 'seconds':
            value = frames / selected['limits']['fps']
        _set_binding(graph, binding, value)
    for binding in bindings.get('preview_frames', []):
        _set_binding(graph, binding, frames)
    injected = []
    if refs.get('dynamic'):
        target = graph[refs['target']]['inputs']
        reusable = _dedicated_reference_loaders(template, refs)
        for socket in list(target):
            if _reference_kind(socket, refs):
                del target[socket]
        reused = set()
        for kind, values in [('image', images), ('audio', audios)]:
            available = sorted(node_id for node_id, loader_kind in reusable.items() if loader_kind == kind)
            for index, value in enumerate(values):
                value = _server_name(value, kind)
                if available:
                    node_id = available.pop(0)
                    graph[node_id]['inputs'][kind] = value
                    reused.add(node_id)
                else:
                    node_id = f'STUDIO_REF_{kind.upper()}_{index}'
                    while node_id in graph:
                        node_id += '_'
                    graph[node_id] = {'class_type': refs[kind + '_loader'], 'inputs': {kind: value}}
                socket = refs[kind + '_prefix'] + str(index)
                target[socket] = [node_id, 0]
                injected.append({'label': ('Picture ' if kind == 'image' else 'Audio ') + str(index + 1),
                                 'kind': kind, 'server_reference': value, 'node': node_id,
                                 'input': kind, 'socket': socket})
        for node_id in reusable:
            if node_id not in reused and not _uses(graph, node_id):
                del graph[node_id]
    else:
        updated = {}
        for kind, values in [('image', images), ('audio', audios)]:
            for value, slot in zip(values, slots[kind]):
                value = _server_name(value, kind)
                key = (slot['node'], slot['input'])
                _need(key not in updated or updated[key] == value,
                      'A shared existing loader cannot receive conflicting reference filenames')
                updated[key] = value
                graph[slot['node']]['inputs'][slot['input']] = value
                injected.append({'label': slot['label'], 'kind': kind, 'server_reference': value,
                                 'node': slot['node'], 'input': slot['input'], 'socket': slot['socket']})
    assert_input_only_changes(template, graph, selected)
    problems = validate_profile(selected, graph, check_source=False)
    _need(not problems, 'Compiled graph failed profile checks: ' + '; '.join(problems))
    return graph, injected


def validate_live_graph(graph, info, profile=None):
    """Check node/schema availability without asserting generation effect quality."""
    selected = profile if profile is not None else infer_profile(graph)
    problems = validate_profile(selected, graph, check_source=False)
    _need(not problems, 'Workflow profile is not executable: ' + '; '.join(problems))
    for node in graph.values():
        cls = node['class_type']
        _need(cls in info, 'ComfyUI does not expose required node ' + cls)
        spec = info[cls].get('input', {})
        fields = {**spec.get('required', {}), **spec.get('optional', {})}
        for key, value in node['inputs'].items():
            rule = fields.get(key)
            if not rule or _link(value):
                continue
            options = rule[0]
            if isinstance(options, list) and not (cls in (selected['references']['image_loader'], selected['references']['audio_loader']) and key in ('image', 'audio')):
                _need(value in options, f'Unavailable model/option: {cls}.{key}={value}')
            if _number(value) and len(rule) > 1 and isinstance(rule[1], dict):
                bounds = rule[1]
                _need(bounds.get('min', -math.inf) <= value <= bounds.get('max', math.inf), f'Live node range rejected {cls}.{key}')
                if options == 'INT' and bounds.get('step', 1) > 1:
                    _need((value - bounds.get('min', 0)) % bounds['step'] == 0, f'Live node grid rejected {cls}.{key}')
    target_cls = graph[selected['references']['target']]['class_type']
    frame_binding = selected['bindings']['frames']
    # When a primitive carries length, check its bounds above and still validate
    # the H3 node's semantic length grid, not a hardcoded numeric node id.
    length_rule = info.get(target_cls, {}).get('input', {}).get('required', {}).get('length')
    if not length_rule or len(length_rule) < 2 or not isinstance(length_rule[1], dict):
        raise ValueError('Live H3 node lacks its length schema')
    bounds = length_rule[1]
    limits = selected['limits']
    _need(bounds.get('min') == limits['frame_min'] and bounds.get('step', 1) == limits['frame_step'],
          'Live length grid differs from this workflow profile; adapt the profile before generation')
    _need(limits['frame_max'] <= bounds.get('max', math.inf), 'Profile frame_max exceeds the live H3 node limit')
