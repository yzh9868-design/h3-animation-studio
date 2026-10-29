"""Approved H3 Ref2VA execution. Stdlib only; no old director-engine dependency.

inspect is offline. prepare uploads but does not generate. Only submit --execute
posts GPU work. collect uses frozen jobs, even when later approval is invalid.
"""
from __future__ import annotations

import argparse
import contextlib
import copy
import datetime as dt
from fractions import Fraction
import hashlib
import json
import math
import mimetypes
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import uuid

import common
import comfy_config
import workflow_adapter as adapter

# Compatibility aliases; actual execution uses the selected profile's limits.
_DEFAULT_LIMITS = adapter.load_builtin_profile()['limits']
FPS = _DEFAULT_LIMITS['fps']
FRAME_MIN = _DEFAULT_LIMITS['frame_min']
FRAME_STEP = _DEFAULT_LIMITS['frame_step']
FRAME_MAX = _DEFAULT_LIMITS['frame_max']


def require(ok, message):
    if not ok:
        raise ValueError(message)


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def sha(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def read(path):
    return json.loads(Path(path).read_text("utf-8-sig"))


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", "utf-8")
        os.replace(temp, path)
    finally:
        if temp.exists():
            temp.unlink()


def project_path(project, relative):
    require(isinstance(relative, str) and relative.strip(), "A project-relative path is required")
    path = Path(relative)
    require(not path.is_absolute() and not re.match(r"^[A-Za-z]:", relative),
            "Use a project-relative path: " + relative)
    result = (project / path).resolve()
    require(result.is_relative_to(project), "Path escapes the project: " + relative)
    return result


def source_plan(segment, profile=None):
    return adapter.source_plan(segment, profile)


def server_name(value, kind):
    require(isinstance(value, str) and value and "\\" not in value and ":" not in value
            and all(ord(c) >= 32 for c in value), "Unsafe uploaded reference filename")
    path = PurePosixPath(value)
    require(not path.is_absolute() and ".." not in path.parts and not value.endswith("/"),
            "Reference must use a server-relative filename")
    allowed = {".png", ".jpg", ".jpeg", ".webp"} if kind == "image" else {".wav", ".mp3", ".flac", ".ogg", ".m4a"}
    require(path.suffix.lower() in allowed, "Unsupported " + kind + " reference")
    return value


def compile_graph(template, prompt, images, audios, *, frames, width, height, seed, prefix, profile=None):
    return adapter.compile_graph(template, prompt, images, audios, frames=frames, width=width,
                                 height=height, seed=seed, prefix=prefix, profile=profile)


class Client:
    def __init__(self, settings):
        self.base = settings["base_url"].rstrip("/")
        url = urllib.parse.urlsplit(self.base)
        require(url.scheme in ("http", "https") and bool(url.netloc) and not url.username,
                "base_url must be an HTTP(S) endpoint without embedded credentials")
        self.timeout = settings.get("timeout_seconds", 120)
        self.auth_headers = comfy_config.runtime_auth_headers(settings)

    def request(self, route, payload=None, headers=None):
        method = "GET" if payload is None else "POST"
        headers = {**self.auth_headers, **(headers or {})}
        if isinstance(payload, dict):
            payload = json.dumps(payload).encode("utf-8")
            headers = {"Content-Type": "application/json", **(headers or {})}
        req = urllib.request.Request(self.base + route, data=payload, headers=headers or {}, method=method)
        with urllib.request.urlopen(req, timeout=self.timeout) as response:
            return response.read()

    def json(self, route, payload=None):
        return json.loads(self.request(route, payload).decode("utf-8-sig"))

    def upload(self, path):
        path = Path(path)
        content = path.read_bytes()
        checksum = hashlib.sha256(content).hexdigest()
        filename = "studio_" + checksum[:24] + path.suffix.lower()
        boundary = "studio_" + uuid.uuid4().hex
        mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        body = (f'--{boundary}\r\nContent-Disposition: form-data; name="image"; filename="{filename}"\r\n'
                f'Content-Type: {mime}\r\n\r\n').encode() + content
        for key, value in [("type", "input"), ("overwrite", "false")]:
            body += (f'\r\n--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}').encode()
        body += f"\r\n--{boundary}--\r\n".encode()
        result = json.loads(self.request("/upload/image", body, {"Content-Type": "multipart/form-data; boundary=" + boundary}))
        require(result.get("name") and result.get("type", "input") == "input", "Upload did not return an input filename")
        subfolder = result.get("subfolder", "")
        uploaded = "/".join(x for x in (subfolder.strip("/"), result["name"]) if x)
        query = urllib.parse.urlencode({"filename": result["name"], "subfolder": subfolder, "type": "input"})
        require(hashlib.sha256(self.request("/view?" + query)).hexdigest() == checksum,
                "Uploaded reference bytes differ from the approved local asset")
        return uploaded


def validate_live_graph(graph, info, profile=None):
    return adapter.validate_live_graph(graph, info, profile)


def run(command, **kwargs):
    return subprocess.run(command, check=True, capture_output=True, **kwargs)


def probe(path, cfg):
    return json.loads(run([cfg["ffprobe"], "-v", "error", "-count_frames", "-show_streams",
                           "-show_format", "-of", "json", str(path)]).stdout)


def video_details(info):
    video = next((s for s in info["streams"] if s["codec_type"] == "video"), None)
    audio = next((s for s in info["streams"] if s["codec_type"] == "audio"), None)
    require(video is not None and audio is not None, "Generated MP4 must contain video and native audio; no silent replacement")
    fps = float(Fraction(video.get("avg_frame_rate") or video["r_frame_rate"]))
    count = int(video.get("nb_read_frames") or video.get("nb_frames") or 0)
    return video, audio, fps, count


def edited_endpoint(source, frame, edit_frames, cfg):
    index = edit_frames - 1
    vf = f"select=eq(n\\,{index})"
    run([cfg["ffmpeg"], "-v", "error", "-y", "-i", str(source), "-vf", vf,
         "-frames:v", "1", "-pix_fmt", "rgb24", str(frame)])
    source_pixels = run([cfg["ffmpeg"], "-v", "error", "-i", str(source), "-vf", vf,
                         "-frames:v", "1", "-pix_fmt", "rgb24", "-f", "rawvideo", "pipe:1"]).stdout
    frame_pixels = run([cfg["ffmpeg"], "-v", "error", "-i", str(frame), "-frames:v", "1",
                        "-pix_fmt", "rgb24", "-f", "rawvideo", "pipe:1"]).stdout
    require(source_pixels and source_pixels == frame_pixels, "Edited endpoint pixels do not match the selected source")
    return {"source": str(source), "source_sha256": sha(source), "source_frame_index": index,
            "edit_out_seconds": edit_frames / cfg.get("fps", FPS), "frame": str(frame), "frame_sha256": sha(frame),
            "rgb_sha256": hashlib.sha256(source_pixels).hexdigest(), "pixel_binding": True,
            "media_review": "not_performed", "human_review": "pending"}


def state_path(project):
    return project / "execution" / "state.json"


def load_state(project):
    path = state_path(project)
    return read(path) if path.exists() else {"version": 1, "jobs": {}, "prepared_archive": []}


@contextlib.contextmanager
def locked(project):
    home = project / "execution"
    home.mkdir(parents=True, exist_ok=True)
    lock = home / ".cli.lock"
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise ValueError("Another CLI action holds execution/.cli.lock. If interrupted, inspect the owner and state before removing a stale lock.")
    try:
        os.write(fd, json.dumps({"pid": os.getpid(), "created_at": now()}).encode())
        os.close(fd)
        yield
    finally:
        lock.unlink(missing_ok=True)


def approved(project, segment_id=None):
    film = common.load_film(project)
    approval = common.require_approval(project, film, [segment_id] if segment_id else None)
    cfg = common.settings(project, film)
    profile = cfg['workflow_profile']
    require(profile.get('adapter') == 'h3_ref2va', 'This workflow is registered but has no executable H3 Ref2VA adapter')
    require(cfg['fps'] == profile['limits']['fps'], 'Configured fps differs from the selected workflow profile')
    mode = film.get("mode", film.get("h3_mode", "Ref2VA"))
    require(isinstance(mode, str) and mode.lower() == "ref2va", "Built-in execution is Ref2VA only; supply a matching workflow for the approved mode, never silently switch")
    current = common.segment_digest(project, film, segment_id) if segment_id else common.review_digest(project, film)
    return film, approval, cfg, current


def get_segment(film, segment_id):
    require(isinstance(segment_id, str) and segment_id
            and all(c.isalnum() or c in "_-" for c in segment_id), "Safe segment ID required")
    matches = [s for s in film["segments"] if s["id"] == segment_id]
    require(len(matches) == 1, "Unknown or duplicate segment ID")
    return matches[0]


def approved_segment(film, approval, segment):
    allowed = approval.get("segment_ids")
    require(isinstance(allowed, list) and segment["id"] in allowed,
            "User did not approve this segment: " + segment["id"])
    mode = segment.get("mode", film.get("mode", film.get("h3_mode", "Ref2VA")))
    require(isinstance(mode, str) and mode.lower() == "ref2va", "This segment needs a workflow for its approved H3 mode; built-in execution is Ref2VA only")


def references(project, film, segment):
    assets = {a["id"]: a for a in film["assets"]}
    grouped = {"image": {}, "audio": {}}
    for ref in segment["references"]:
        match = re.fullmatch(r"(Picture|Audio)\s*([1-9])", ref["label"], re.I)
        require(match is not None, "Use explicit Picture N or Audio N reference labels")
        kind = "image" if match[1].lower() == "picture" else "audio"
        index = int(match[2]);require(index not in grouped[kind], "Duplicate reference label")
        asset = assets[ref["asset_id"]]
        # User-provided inputs may be outside the project. common's approval
        # digest already includes their resolved absolute paths and bytes.
        # Generated outputs remain confined by project_path.
        path = common.locate(project, asset["path"])
        require(path.is_file(), "Missing reference: " + asset["id"])
        server_name(path.name, kind)
        grouped[kind][index] = {"asset_id": asset["id"], "label": ("Picture " if kind == "image" else "Audio ") + str(index),
                                "kind": kind, "local_path": str(path), "sha256": sha(path)}
    for kind, values in grouped.items():
        require(sorted(values) == list(range(1, len(values) + 1)), "Reference numbering must be consecutive from 1")
    return [grouped[kind][i] for kind in ("image", "audio") for i in sorted(grouped[kind])]


def continuity_label(segment, refs):
    expected = "Picture " + str(sum(r["kind"] == "image" for r in refs) + 1)
    label = segment.get("continuity_picture", expected)
    require(label == expected, "continuity_picture must match the next image input port: " + expected)
    return label


def validate_prompt_references(prompt, refs):
    expected = {r["label"] for r in refs}
    declared = {kind.title() + " " + str(int(number)) for kind, number in
                re.findall(r"\b(Picture|Audio|Video)\s*(\d+)\b", prompt, re.I)}
    require(declared == expected,
            "Prompt/input reference labels differ. Missing in prompt: " + str(sorted(expected - declared))
            + "; not provided: " + str(sorted(declared - expected)))


def job_matches(project, film, approval, job):
    sid = job["segment_id"]
    require(job["segment"] == get_segment(film, sid), "Current segment changed after its selected take: " + sid)
    current = common.segment_digest(project, film, sid)
    record = approval.get("records", {}).get(sid, {})
    if job.get("segment_digest"):
        require(job["segment_digest"] == current, "Selected take belongs to older inputs: " + sid)
        if record.get("authorization_type") == "repair":
            require(job.get("authorization_id") == record.get("authorization_id"),
                    "A newly requested repair has not produced the selected take yet: " + sid)
    else:
        require(record.get("segment_digest") == current and record.get("legacy_review_digest") == job.get("review_digest"),
                "Legacy take was not bound by a valid approval migration: " + sid)


def validate_continuity(project, film, approval, state, job):
    """Check the selected upstream take as well as bytes of its bound endpoint."""
    previous_id = job["segment"].get("continuity_from")
    if not previous_id:
        return
    previous = state["jobs"].get(previous_id)
    require(previous and previous["status"] == "downloaded", "Collect the selected continuity predecessor: " + previous_id)
    job_matches(project, film, approval, previous)
    endpoint = previous["endpoint"]
    require(sha(endpoint["source"]) == endpoint["source_sha256"]
            and sha(endpoint["frame"]) == endpoint["frame_sha256"], "Selected continuity endpoint changed")
    refs = [r for r in job["references"] if r.get("continuity_from") == previous_id]
    require(len(refs) == 1, "Frozen job lacks its declared actual endpoint reference")
    ref = refs[0]
    require(ref.get("source_sha256") == endpoint["source_sha256"]
            and ref.get("source_frame_index") == endpoint["source_frame_index"]
            and ref.get("sha256") == endpoint["frame_sha256"]
            and ref.get("local_path") == endpoint["frame"], "Continuity predecessor take was replaced; prepare this dependent segment again")
    if ref.get("predecessor_job_token"):
        require(ref["predecessor_job_token"] == previous["job_token"], "Continuity predecessor take was replaced")
    validate_continuity(project, film, approval, state, previous)


def prepare(project, segment_id, replace_prepared=False, new_take=False):
    with locked(project):
        film, approval, cfg, current = approved(project, segment_id)
        segment = get_segment(film, segment_id);approved_segment(film, approval, segment);plan = source_plan(segment, cfg["workflow_profile"])
        authority = approval["records"][segment_id]
        state = load_state(project);old = state["jobs"].get(segment_id)
        require(not (replace_prepared and new_take), "Use either --replace-prepared or --new-take")
        if old:
            if new_take:
                require(old["status"] in ("downloaded", "failed", "prepare_failed"),
                        "A new take cannot replace an in-flight or uncertain job; collect or resolve it first")
                require(authority.get("authorization_type") == "repair"
                        and authority.get("authorization_id") != old.get("authorization_id"),
                        "A new take requires a new explicit local repair authorization")
            else:
                require(replace_prepared and old["status"] in ("prepared", "prepare_failed"),
                        "Job already exists; use --replace-prepared for drafts or --new-take after an explicit repair request")
            state["prepared_archive"].append(old)
        else:
            require(not new_take, "No previous take exists; prepare this segment normally")
        refs = references(project, film, segment)
        previous_id = segment.get("continuity_from")
        if previous_id:
            require(previous_id != segment_id, "A segment cannot continue itself")
            previous = state["jobs"].get(previous_id)
            require(previous and previous["status"] == "downloaded", "Collect only the declared continuity predecessor first: " + previous_id)
            job_matches(project, film, approval, previous)
            validate_continuity(project, film, approval, state, previous)
            endpoint = previous["endpoint"]
            require(sha(endpoint["source"]) == endpoint["source_sha256"]
                    and sha(endpoint["frame"]) == endpoint["frame_sha256"], "Actual selected endpoint changed")
            label = continuity_label(segment, refs)
            refs.append({"asset_id": None, "label": label, "kind": "image",
                         "local_path": endpoint["frame"], "sha256": endpoint["frame_sha256"],
                         "role": "actual_edited_last_frame", "continuity_from": previous_id,
                         "source_frame_index": endpoint["source_frame_index"], "source_sha256": endpoint["source_sha256"],
                         "predecessor_job_token": previous["job_token"]})
        validate_prompt_references(segment["prompt_en"], refs)
        token = uuid.uuid4().hex
        jobdir = project / "execution" / "jobs" / (segment_id + "_" + token)
        jobdir.mkdir(parents=True)
        job = {"segment_id": segment_id, "job_token": token, "status": "preparing", "prepared_at": now(),
               "review_digest": common.review_digest(project, film), "segment_digest": current,
               "authorization_id": authority["authorization_id"], "approval_evidence": authority["user_confirmation"], "segment": copy.deepcopy(segment),
               "settings": copy.deepcopy(cfg), "job_directory": str(jobdir), "references": refs, **plan,
               "media_review": "not_performed", "human_review": "pending"}
        state["jobs"][segment_id] = job;save(state_path(project), state)
        try:
            template = comfy_config.load_graph(cfg["workflow"])
            source_path = jobdir / 'source_workflow.json'
            save(source_path, template)
            job.update(source_workflow=str(source_path), source_workflow_sha256=sha(source_path),
                       source_graph_digest=adapter.graph_digest(template))
            save(state_path(project), state)
            preview, _ = compile_graph(template, segment["prompt_en"],
                                       [f"pending_{i}.png" for i, r in enumerate(refs) if r["kind"] == "image"],
                                       [f"pending_{i}.wav" for i, r in enumerate(refs) if r["kind"] == "audio"],
                                       frames=plan["source_frames"], width=cfg["width"], height=cfg["height"],
                                       seed=cfg["seed"], prefix="h3_animation_studio/preflight", profile=cfg["workflow_profile"])
            client = Client(cfg)
            info = client.json("/object_info")  # Only read schema after offline input checks.
            validate_live_graph(preview, info, cfg["workflow_profile"])
            for ref in refs:
                latest_film, latest_approval, _, latest = approved(project, segment_id)
                approved_segment(latest_film, latest_approval, get_segment(latest_film, segment_id))
                require(latest == current and latest_approval["records"][segment_id]["authorization_id"] == authority["authorization_id"]
                        and sha(ref["local_path"]) == ref["sha256"], "Approval/reference changed during preparation")
                ref["server_reference"] = client.upload(ref["local_path"])
            images = [r["server_reference"] for r in sorted(refs, key=lambda r: r["label"]) if r["kind"] == "image"]
            audios = [r["server_reference"] for r in sorted(refs, key=lambda r: r["label"]) if r["kind"] == "audio"]
            graph, bindings = compile_graph(template, segment["prompt_en"], images, audios,
                                             frames=plan["source_frames"], width=cfg["width"], height=cfg["height"],
                                             seed=cfg["seed"], prefix="h3_animation_studio/" + segment_id + "_" + token, profile=cfg["workflow_profile"])
            validate_live_graph(graph, info, cfg["workflow_profile"])
            latest_film, latest_approval, _, latest = approved(project, segment_id)
            approved_segment(latest_film, latest_approval, get_segment(latest_film, segment_id))
            require(latest == current and latest_approval["records"][segment_id]["authorization_id"] == authority["authorization_id"], "Approval changed during preparation")
            validate_continuity(project, latest_film, latest_approval, load_state(project), job)
            graph_path = jobdir / "api_graph.json";save(graph_path, graph)
            job.update(status="prepared", graph=str(graph_path), graph_sha256=sha(graph_path),
                       graph_content_sha256=digest(graph), reference_bindings=bindings,
                       live_schema_sha256=digest({c: info[c] for c in {n["class_type"] for n in graph.values()}}))
            save(state_path(project), state)
        except Exception as error:
            job.update(status="prepare_failed", error=str(error));save(state_path(project), state)
            raise
        return job


def submit(project, segment_id, execute=False):
    require(execute, "Actual GPU submission requires --execute after HTML approval")
    with locked(project):
        film, approval, _, current = approved(project, segment_id)
        approved_segment(film, approval, get_segment(film, segment_id))
        state = load_state(project);job = state["jobs"][segment_id]
        require(job["status"] == "prepared", "Only a prepared, never-submitted job can submit; uncertain/failed jobs are not retried")
        job_matches(project, film, approval, job)
        authority = approval["records"][segment_id]
        if job.get("authorization_id"):
            require(job["authorization_id"] == authority.get("authorization_id"), "Prepared job belongs to an older authorization; prepare it again")
        require(sha(job["graph"]) == job["graph_sha256"], "Prepared graph changed")
        require(job.get('source_workflow') and job.get('source_workflow_sha256'),
                'Prepared task has no immutable source-workflow snapshot; prepare this authorized take again')
        require(sha(job['source_workflow']) == job['source_workflow_sha256'],
                'The frozen uploaded-workflow snapshot changed')
        original = read(job['source_workflow'])
        require(adapter.graph_digest(original) == job['source_graph_digest'], 'Source workflow identity changed')
        submitted_graph = read(job['graph'])
        adapter.assert_input_only_changes(original, submitted_graph, job['settings']['workflow_profile'])
        for ref in job["references"]:
            require(sha(ref["local_path"]) == ref["sha256"], "Reference changed after approval/preparation")
        validate_continuity(project, film, approval, state, job)
        job.update(status="submission_uncertain", submission_started_at=now(),
                   requested_prompt_id=str(uuid.uuid4()), client_id=str(uuid.uuid4()))
        save(state_path(project), state)  # Written before POST: an interrupted call must not resubmit.
        payload = {"prompt": submitted_graph, "client_id": job["client_id"],
                   "prompt_id": job["requested_prompt_id"],
                   "extra_data": {"h3_animation_studio": {"job_token": job["job_token"],
                                  "review_digest": job["review_digest"], "segment_digest": current}}}
        try:
            result = Client(job["settings"]).json("/prompt", payload)
            require(isinstance(result.get("prompt_id"), str) and result["prompt_id"], "Submission did not return prompt_id")
        except Exception as error:
            job["submission_error"] = str(error);save(state_path(project), state)
            raise ValueError("Submission outcome uncertain; inspect queue/history, never submit again. " + str(error)) from error
        job.update(status="submitted", prompt_id=result["prompt_id"], submitted_at=job["submission_started_at"], accepted_at=now())
        save(state_path(project), state)
        return job


def output_videos(value):
    if isinstance(value, dict):
        if str(value.get("filename", "")).lower().endswith(".mp4"):
            yield value
        for child in value.values():
            yield from output_videos(child)
    elif isinstance(value, list):
        for child in value:
            yield from output_videos(child)


def collect(project, segment_id, prompt_id=None):
    # Deliberately no common.load_film / require_approval here: old accepted
    # work remains collectible after the user changes or deletes the new draft.
    with locked(project):
        state = load_state(project);job = state["jobs"][segment_id]
        if job["status"] == "downloaded":
            require(sha(job["source"]) == job["source_sha256"], "Collected source changed")
            return job
        require(job["status"] in ("submitted", "submission_uncertain", "collection_error", "failed"), "No submitted job to collect")
        known = job.get("prompt_id")
        require(not (known and prompt_id and known != prompt_id), "A known prompt_id cannot be replaced by a different job")
        pid = prompt_id or known or job.get("requested_prompt_id")
        require(pid, "Known history prompt_id required")
        client = Client(job["settings"])
        history = client.json("/history/" + urllib.parse.quote(pid, safe=""))
        item = history.get(pid)
        if not item:
            return {"segment_id": segment_id, "status": job["status"], "prompt_id": pid,
                    "collection": "no history yet; query status --remote; do not resubmit"}
        if not known:
            graph = next((x for x in item.get("prompt", []) if isinstance(x, dict) and digest(x) == job["graph_content_sha256"]), None)
            require(graph is not None and digest(graph) == job["graph_content_sha256"],
                    "Uncertain submission must match the exact frozen graph before binding a history ID")
            job["prompt_id"] = pid
        save(Path(job["job_directory"]) / "history.json", item)
        status = item.get("status", {})
        if status.get("status_str") == "error":
            job.update(status="failed", failure_recorded_at=now());save(state_path(project), state)
            raise ValueError("Remote GPU job failed. Evidence saved; no automatic retry")
        if not status.get("completed") and status.get("status_str") != "success":
            return {"segment_id": segment_id, "status": "running", "prompt_id": pid}
        try:
            profile = job['settings'].get('workflow_profile')
            if not profile:
                profile = adapter.infer_profile(read(job['graph']), profile_id='legacy-frozen')
            output_id = str(profile['output']['node'])
            require(output_id in item.get('outputs', {}), 'Configured output node is missing from task history: ' + output_id)
            videos = list(output_videos(item['outputs'][output_id]))
            unique = {json.dumps(v, sort_keys=True): v for v in videos}
            require(len(unique) == 1, "Expected exactly one MP4 from the configured output node; inspect saved history")
            chosen = next(iter(unique.values()))
            query = urllib.parse.urlencode({k: chosen[k] for k in ("filename", "subfolder", "type") if k in chosen})
            source = Path(job["job_directory"]) / "source.mp4"
            temp = source.with_suffix(".download")
            temp.write_bytes(client.request("/view?" + query));os.replace(temp, source)
            info = probe(source, job["settings"])
            video, audio, fps, frames = video_details(info)
            require(abs(fps - job["settings"].get("fps", FPS)) < 1e-6 and frames == job["source_frames"], "Actual source fps/frames differ from the approved source plan")
            require(int(video["width"]) == job["settings"]["width"] and int(video["height"]) == job["settings"]["height"], "Actual source dimensions differ")
            require(float(audio.get("duration") or info["format"]["duration"]) + 0.001 >= job["edit_seconds"], "Native audio is shorter than the edit; no padding or external replacement")
            frame = Path(job["job_directory"]) / "edited_last_frame.png"
            endpoint = edited_endpoint(source, frame, job["edit_frames"], job["settings"])
            save(Path(job["job_directory"]) / "endpoint.json", endpoint)
            job.update(status="downloaded", downloaded_at=now(), source=str(source), source_sha256=sha(source),
                       endpoint=endpoint, actual_probe=info, actual_frames=frames, actual_fps=fps)
            job.pop("collection_error", None);save(state_path(project), state)
        except Exception as error:
            job.update(status="collection_error", collection_error=str(error));save(state_path(project), state)
            raise
        return job


def status(project, remote=False):
    state = load_state(project);rows=[]
    for sid, job in state["jobs"].items():
        row = {k: job.get(k) for k in ("status", "prompt_id", "prepared_at", "submitted_at", "downloaded_at", "source")}
        row["segment_id"] = sid
        if remote and job["status"] in ("submitted", "submission_uncertain", "collection_error"):
            client = Client(job["settings"]);pid = job.get("prompt_id") or job.get("requested_prompt_id")
            row["history"] = client.json("/history/" + urllib.parse.quote(pid, safe=""))
            row["queue"] = client.json("/queue")
        rows.append(row)
    return {"jobs": rows, "media_review": "not_performed", "human_review": "pending"}


def assemble(project, output="output/film.mp4", overwrite=False):
    with locked(project):
        film, approval, cfg, current = approved(project)
        state = load_state(project);selected=[]
        fps = cfg["fps"]
        for segment in film["segments"]:
            approved_segment(film, approval, segment)
            job = state["jobs"].get(segment["id"])
            require(job and job["status"] == "downloaded", "Collect segment first: " + segment["id"])
            job_matches(project, film, approval, job)
            validate_continuity(project, film, approval, state, job)
            require(sha(job["source"]) == job["source_sha256"], "Selected source changed")
            for ref in job["references"]:
                require(sha(ref["local_path"]) == ref["sha256"], "Reference provenance changed")
            selected.append(job)
        dest = project_path(project, output)
        require(dest.suffix.lower() == ".mp4" and (overwrite or not dest.exists()), "Use a new output MP4 or explicitly pass --overwrite")
        require(dest not in [Path(j["source"]) for j in selected], "Output cannot overwrite source")
        dest.parent.mkdir(parents=True, exist_ok=True)
        total_frames = sum(j["edit_frames"] for j in selected);seconds=total_frames/fps
        with tempfile.TemporaryDirectory(prefix="assembly_", dir=project/"execution") as temp:
            temp=Path(temp)
            for index, job in enumerate(selected):
                vf = f"trim=start=0:end={job['edit_seconds']},setpts=PTS-STARTPTS,fps={fps},scale={cfg['width']}:{cfg['height']}:force_original_aspect_ratio=decrease,pad={cfg['width']}:{cfg['height']}:(ow-iw)/2:(oh-ih)/2,setsar=1,format=yuv420p"
                af = f"atrim=start=0:end={job['edit_seconds']},asetpts=PTS-STARTPTS,aresample=48000,aformat=channel_layouts=stereo"
                run([cfg["ffmpeg"],"-v","error","-y","-i",job["source"],"-map","0:v:0","-map","0:a:0","-vf",vf,"-af",af,"-frames:v",str(job["edit_frames"]),"-t",str(job["edit_seconds"]),"-c:v","libx264","-crf","18","-c:a","aac","-b:a","192k",str(temp/f"{index:04d}.mp4")])
            (temp/"concat.txt").write_text("".join(f"file '{i:04d}.mp4'\n" for i in range(len(selected))),"utf-8")
            result=temp/"final.mp4"
            run([cfg["ffmpeg"],"-v","error","-y","-f","concat","-safe","1","-i","concat.txt","-map","0:v:0","-map","0:a:0","-c:v","copy","-c:a","aac","-t",str(seconds),"-movflags","+faststart",str(result)],cwd=temp)
            info=probe(result,cfg);_,_,actual_fps,count=video_details(info)
            require(count==total_frames and abs(actual_fps-fps)<1e-6 and abs(float(info["format"]["duration"])-seconds)<=0.15,"Final frame count/fps/duration mismatch")
            run([cfg["ffmpeg"],"-v","error","-i",str(result),"-f","null","-"])
            latest_film,latest_approval,_,latest=approved(project)
            for segment in latest_film["segments"]:
                approved_segment(latest_film,latest_approval,segment)
            require(latest==current,"Review changed during assembly; output not published")
            require(overwrite or not dest.exists(),"Output appeared during assembly; not overwritten")
            os.replace(result,dest)
        report={"status":"technical_checks_passed","output":str(dest),"sha256":sha(dest),"assembled_at":now(),
                "review_digest":current,"frames":total_frames,"fps":fps,"duration_seconds":seconds,
                "audio_strategy":"native H3 audio retained per segment; no TTS or external soundtrack",
                "segments":[{"segment_id":j["segment_id"],"source":j["source"],"source_sha256":j["source_sha256"],"edit_seconds":j["edit_seconds"]} for j in selected],
                "technical_probe":info,"media_review":"not_performed","human_review":"pending"}
        save(dest.with_suffix(".assembly.json"),report);return report


def inspect_project(project):
    film = common.load_film(project); cfg = common.settings(project, film)
    template = comfy_config.load_graph(cfg['workflow']); profile = cfg['workflow_profile']
    issues = adapter.validate_profile(profile, template)
    plans = []
    for segment in film['segments']:
        mode = segment.get('mode', film.get('mode', film.get('h3_mode', profile.get('mode', 'Ref2VA'))))
        row = {'id': segment['id'], 'continuity_from': segment.get('continuity_from'), 'mode': mode,
               'built_in_execution_supported': profile.get('adapter') == 'h3_ref2va' and str(mode).lower() == 'ref2va'}
        try:
            row.update(source_plan(segment, profile))
            if segment.get('continuity_from'):
                refs = [{'kind': 'image' if r['label'].startswith('Picture') else 'audio'} for r in segment.get('references', [])]
                row['continuity_picture'] = continuity_label(segment, refs)
        except ValueError as error:
            row['planning_error'] = str(error)
        plans.append(row)
    return {'network_requests': 0, 'gpu_submission': False, 'mode': profile.get('mode'),
            'workflow': cfg['workflow'], 'workflow_sha256': sha(cfg['workflow']),
            'bindings': profile.get('bindings'), 'output': profile.get('output'),
            'limits': profile.get('limits'), 'configuration_issues': issues,
            'planning_ready': not issues and not any('planning_error' in row for row in plans),
            'segments': plans, 'audio': 'H3 native audio; user-supplied reference audio optional'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action",choices=["inspect","prepare","submit","collect","status","assemble"])
    parser.add_argument("--project",required=True);parser.add_argument("--segment")
    parser.add_argument("--replace-prepared",action="store_true")
    parser.add_argument("--new-take",action="store_true",help="Archive a completed/failed take only after a new explicit repair authorization")
    parser.add_argument("--execute",action="store_true");parser.add_argument("--remote",action="store_true")
    parser.add_argument("--prompt-id",help="Recover an uncertain accepted job only after exact frozen-graph matching")
    parser.add_argument("--output",default="output/film.mp4");parser.add_argument("--overwrite",action="store_true")
    args=parser.parse_args();project=Path(args.project).resolve();require(project.is_dir(),"Project directory required")
    if args.action=="inspect":result=inspect_project(project)
    elif args.action=="prepare":result=prepare(project,args.segment,args.replace_prepared,args.new_take)
    elif args.action=="submit":result=submit(project,args.segment,args.execute)
    elif args.action=="collect":result=collect(project,args.segment,args.prompt_id)
    elif args.action=="status":result=status(project,args.remote)
    else:result=assemble(project,args.output,args.overwrite)
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=="__main__":
    try:
        main()
    except (ValueError,KeyError,OSError,subprocess.CalledProcessError,urllib.error.URLError) as error:
        raise SystemExit(str(error))
