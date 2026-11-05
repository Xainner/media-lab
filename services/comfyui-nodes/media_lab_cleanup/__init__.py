"""Media Lab cleanup: delete the copies a runtime job left inside ComfyUI.

In-house route, no nodes. The runtime uploads each job's references to input/ and its graphs
save under output/media_lab/; the studio keeps its own copy of every result, so these are only
working files. When a job ends the runtime posts the files it touched here, and while a worker
is idle it asks for a sweep of leftovers older than a day. rules.py decides what is removable.
"""
import os
import time

from aiohttp import web

import folder_paths
from server import PromptServer

from .rules import removable, sweep

NODE_CLASS_MAPPINGS = {}
NODE_DISPLAY_NAME_MAPPINGS = {}


def _roots():
    return {"input": folder_paths.get_input_directory(), "output": folder_paths.get_output_directory(),
            "temp": folder_paths.get_temp_directory()}


@PromptServer.instance.routes.post("/media_lab/cleanup")
async def cleanup(request):
    try:
        body = await request.json()
    except ValueError:
        return web.json_response({"error": "invalid JSON"}, status=400)
    roots, targets = _roots(), set()
    for item in body.get("files") or []:
        if isinstance(item, dict):
            targets.update(removable(roots, item.get("type", ""), item.get("path", "")))
    older_than = body.get("older_than")
    if isinstance(older_than, (int, float)) and older_than >= 3600:
        targets.update(sweep(roots, float(older_than), time.time()))
    removed = 0
    for path in targets:
        try:
            os.unlink(path)
            removed += 1
        except FileNotFoundError:
            pass
    return web.json_response({"removed": removed})
