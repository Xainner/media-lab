"""Which ComfyUI files a Media Lab job may delete. Plain Python so the runtime tests can load it.

A job's references are uploaded to input/ as job_<id>_<name> and its graphs save under
output/media_lab/. Only those, and ComfyUI's temp previews, are ever removable; any other path,
absolute path or escape through '..' or a symlink is refused.
"""
from __future__ import annotations

import os
import re

JOB_INPUT = re.compile(r"job_[0-9a-f]{8,32}_[^/\\]+")


def _real(path: str) -> str:
    return os.path.realpath(path)


def _inside(root: str, path: str) -> bool:
    root = _real(root)
    return path != root and os.path.commonpath([root, path]) == root


def allowed(roots: dict, kind: str, path: str) -> bool:
    """path must already be resolved with realpath."""
    if kind == "input" and roots.get("input"):
        return os.path.dirname(path) == _real(roots["input"]) and bool(JOB_INPUT.fullmatch(os.path.basename(path)))
    if kind == "output" and roots.get("output"):
        return _inside(os.path.join(roots["output"], "media_lab"), path)
    if kind == "temp" and roots.get("temp"):
        return _inside(roots["temp"], path)
    return False


def removable(roots: dict, kind: str, relative: str) -> list[str]:
    """The file itself plus same-stem siblings (Video Combine writes a .png next to each video)."""
    root = roots.get(kind)
    if not root or not isinstance(relative, str) or not relative or os.path.isabs(relative):
        return []
    path = _real(os.path.join(root, relative))
    if not allowed(roots, kind, path):
        return []
    folder, name = os.path.split(path)
    stem = os.path.splitext(name)[0]
    try:
        names = os.listdir(folder)
    except OSError:
        return []
    found = []
    for other in names:
        candidate = os.path.join(folder, other)
        if (other == name or other.startswith(stem + ".")) and os.path.isfile(candidate) \
                and not os.path.islink(candidate) and allowed(roots, kind, _real(candidate)):
            found.append(candidate)
    return found


def sweep(roots: dict, older_than: float, now: float) -> list[str]:
    """Job leftovers older than older_than seconds: input/job_* and everything under output/media_lab."""
    cutoff, found = now - older_than, []
    folder = roots.get("input")
    if folder and os.path.isdir(folder):
        for name in os.listdir(folder):
            path = os.path.join(folder, name)
            if JOB_INPUT.fullmatch(name) and os.path.isfile(path) and not os.path.islink(path) \
                    and os.path.getmtime(path) < cutoff:
                found.append(path)
    media = os.path.join(roots.get("output") or "", "media_lab")
    if roots.get("output") and os.path.isdir(media):
        for base, _dirs, files in os.walk(media, followlinks=False):
            for name in files:
                path = os.path.join(base, name)
                if not os.path.islink(path) and os.path.getmtime(path) < cutoff and allowed(roots, "output", _real(path)):
                    found.append(path)
    return found
