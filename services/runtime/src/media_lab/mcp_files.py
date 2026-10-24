"""Temporary per-file transfer links so MCP agents move real files over plain HTTP.

An LLM cannot practically emit megabytes of base64 as tool arguments, and it rarely
holds the MCP bearer token its client uses. A token holder therefore asks for short-lived,
single-purpose links: one upload link per incoming file (consumed by the first successful
upload) and download links scoped to one owned artifact. Links store only a hash, belong
to the minting token and stop working when it is revoked, expires or loses its scope.
"""
import json
import secrets
import shutil
import subprocess
import tempfile
import time
import uuid
from pathlib import Path

import anyio
from fastapi import HTTPException, UploadFile
from PIL import Image, UnidentifiedImageError
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse

from .security import digest
from .tenancy import NotOwned, ResourceLimit

UPLOAD_TTL = 2 * 3600
DOWNLOAD_TTL = 3600
MAX_LINKS_PER_CALL = 50
MAX_PENDING_UPLOADS = 200
MAX_LIVE_DOWNLOADS = 1000
MEDIA_MAX_BYTES = 500 * 1024 * 1024
LEASE_SECONDS = 15 * 60
IMAGE_TYPES = {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp"}
WEBM_CODECS = {"vp8", "vp9", "av1", "opus", "vorbis"}
AUDIO_FORMATS = {"wav": "audio/wav", "flac": "audio/flac", "mp3": "audio/mpeg", "ogg": "audio/ogg"}


class TransferError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status, self.message = status, message


class McpFiles:
    def __init__(self, accounts, origin, artifacts, routes):
        self.accounts, self.origin, self.artifacts, self.routes = accounts, origin, artifacts, routes
        self.spool = Path(artifacts.root).parent / "incoming"
        # Partial uploads live in per-request temporary folders; drop any a crash left behind.
        for stale in self.spool.glob('*') if self.spool.is_dir() else []:
            if stale.stat().st_mtime < time.time() - 86400:
                shutil.rmtree(stale, ignore_errors=True)
        with accounts.db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS mcp_transfers(
                    id TEXT PRIMARY KEY, secret_hash TEXT UNIQUE NOT NULL,
                    owner_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    token_id TEXT NOT NULL REFERENCES mcp_tokens(id) ON DELETE CASCADE,
                    direction TEXT NOT NULL, name TEXT NOT NULL, session_id TEXT,
                    uri TEXT, sha256 TEXT, state TEXT NOT NULL, error TEXT, result TEXT,
                    created_at REAL NOT NULL, expires_at REAL NOT NULL, leased_at REAL);
                CREATE INDEX IF NOT EXISTS mcp_transfer_owner ON mcp_transfers(owner_id, direction, expires_at);
            """)

    # ---- link minting (called from authorized MCP tools) ----

    def _mint(self, db, identity, direction, name, ttl, **values):
        secret = ('rvl_up_' if direction == 'upload' else 'rvl_dl_') + secrets.token_urlsafe(32)
        tid, now = uuid.uuid4().hex, time.time()
        db.execute('INSERT INTO mcp_transfers(id,secret_hash,owner_id,token_id,direction,name,session_id,uri,sha256,state,created_at,expires_at) '
                   'VALUES(?,?,?,?,?,?,?,?,?,?,?,?)', (tid, digest(secret), identity['owner_id'], identity['id'], direction, name,
                   values.get('session_id'), values.get('uri'), values.get('sha256'), 'pending' if direction == 'upload' else 'ready', now, now + ttl))
        return tid, self.origin + '/mcp/files/' + secret

    def create_uploads(self, identity, names, session_id):
        now = time.time()
        with self.accounts.db() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('DELETE FROM mcp_transfers WHERE expires_at<?', (now - 86400,))
            pending = db.execute("SELECT COUNT(*) FROM mcp_transfers WHERE owner_id=? AND direction='upload' AND state='pending' AND expires_at>?",
                                 (identity['owner_id'], now)).fetchone()[0]
            if pending + len(names) > MAX_PENDING_UPLOADS:
                raise ResourceLimit(f'At most {MAX_PENDING_UPLOADS} unused upload links per account; use or let them expire')
            slots = []
            for name in names:
                tid, url = self._mint(db, identity, 'upload', name, UPLOAD_TTL, session_id=session_id)
                slots.append({'id': tid, 'name': name, 'url': url})
        return {'expires_at': now + UPLOAD_TTL, 'expires_in_seconds': UPLOAD_TTL, 'uploads': slots}

    def create_downloads(self, identity, references):
        now, links = time.time(), []
        with self.accounts.db() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('DELETE FROM mcp_transfers WHERE expires_at<?', (now - 86400,))
            live = db.execute("SELECT COUNT(*) FROM mcp_transfers WHERE owner_id=? AND direction='download' AND expires_at>?",
                              (identity['owner_id'], now)).fetchone()[0]
            if live + len(references) > MAX_LIVE_DOWNLOADS:
                raise ResourceLimit('Too many live download links; wait for older ones to expire')
            for reference, path in references:
                _, url = self._mint(db, identity, 'download', path.name, DOWNLOAD_TTL, uri=reference['uri'], sha256=reference['sha256'])
                links.append({'reference': reference, 'url': url, 'filename': path.name, 'bytes': path.stat().st_size, 'sha256': reference['sha256'],
                              'content_type': guess_type(path)})
        return {'expires_at': now + DOWNLOAD_TTL, 'expires_in_seconds': DOWNLOAD_TTL, 'links': links}

    def upload_status(self, identity, ids):
        marks = ','.join('?' * len(ids))
        with self.accounts.db() as db:
            rows = {r['id']: r for r in db.execute(f"SELECT * FROM mcp_transfers WHERE owner_id=? AND direction='upload' AND id IN ({marks})",
                                                   (identity['owner_id'], *ids))}
        items, now = [], time.time()
        for tid in ids:
            row = rows.get(tid)
            if not row:
                items.append({'id': tid, 'status': 'unknown'})
                continue
            status = row['state']
            if status in ('pending', 'uploading') and row['expires_at'] <= now:
                status = 'expired'
            item = {'id': tid, 'name': row['name'], 'status': status, 'expires_at': row['expires_at']}
            if row['result']:
                item.update(json.loads(row['result']))
            if row['error'] and status != 'completed':
                item['last_error'] = row['error']
            items.append(item)
        return {'uploads': items}

    # ---- HTTP side (self-authenticating link, no bearer) ----

    def grant(self, secret):
        """Return the live transfer and its owner, or None. Re-checks the minting token every time."""
        if not secret.startswith(('rvl_up_', 'rvl_dl_')) or len(secret) > 128:
            return None
        now = time.time()
        with self.accounts.db() as db:
            row = db.execute('SELECT x.*, t.scopes FROM mcp_transfers x JOIN mcp_tokens t ON t.id=x.token_id '
                             'JOIN mcp_accounts m ON m.owner_id=x.owner_id JOIN users u ON u.id=x.owner_id '
                             'WHERE x.secret_hash=? AND x.expires_at>? AND t.revoked_at IS NULL AND t.expires_at>? '
                             'AND m.enabled=1 AND u.enabled=1', (digest(secret), now, now)).fetchone()
        if not row:
            return None
        row = dict(row)
        needed = 'create' if row['direction'] == 'upload' else 'read'
        return row if needed in json.loads(row['scopes']) else None

    async def serve(self, grant, scope, receive, send):
        request = Request(scope, receive)

        async def reply(status, message):
            return await JSONResponse({'detail': message}, status, headers={'Cache-Control': 'no-store'})(scope, receive, send)
        if grant['direction'] == 'download':
            if request.method not in {'GET', 'HEAD'}:
                return await reply(405, 'Use GET or HEAD to download')
            try:
                path = await anyio.to_thread.run_sync(self.artifacts.resolve, grant['uri'], grant['sha256'])
            except (ValueError, NotOwned, FileNotFoundError):
                return await reply(404, 'Resource unavailable')
            return await FileResponse(path, filename=path.name, media_type=guess_type(path),
                                      headers={'X-Content-SHA256': grant['sha256']})(scope, receive, send)
        if request.method not in {'PUT', 'POST'}:
            return await reply(405, 'Upload with PUT (raw file bytes) or POST (multipart, one file field)')
        if grant['state'] == 'completed':
            return await reply(409, 'This upload link was already used; its reference is available with get_uploads')
        if not self._lease(grant['id']):
            return await reply(409, 'Another upload to this link is in progress')
        try:
            result = await self._receive(grant, request)
        except TransferError as exc:
            self._release(grant['id'], exc.message)
            return await reply(exc.status, exc.message)
        except ResourceLimit:
            self._release(grant['id'], 'Account storage quota reached')
            return await reply(413, 'Account storage quota reached')
        except Exception:
            self._release(grant['id'], 'The upload could not be stored')
            return await reply(500, 'The upload could not be stored; the link stays usable until it expires')
        with self.accounts.db() as db:
            db.execute("UPDATE mcp_transfers SET state='completed', result=?, error=NULL, uri=?, sha256=? WHERE id=?",
                       (json.dumps(result), result['reference']['uri'], result['reference']['sha256'], grant['id']))
        return await JSONResponse({'ok': True, 'id': grant['id'], 'name': grant['name'], **result},
                                  headers={'Cache-Control': 'no-store'})(scope, receive, send)

    def _lease(self, tid):
        now = time.time()
        with self.accounts.db() as db:
            return db.execute("UPDATE mcp_transfers SET state='uploading', leased_at=? WHERE id=? AND "
                              "(state='pending' OR (state='uploading' AND leased_at<?))", (now, tid, now - LEASE_SECONDS)).rowcount == 1

    def _release(self, tid, error):
        with self.accounts.db() as db:
            db.execute("UPDATE mcp_transfers SET state='pending', leased_at=NULL, error=? WHERE id=? AND state='uploading'", (error[:300], tid))

    async def _receive(self, grant, request):
        declared = request.headers.get('content-length')
        if declared and (not declared.isdigit() or int(declared) > MEDIA_MAX_BYTES + 1024 * 1024):
            raise TransferError(413, 'File exceeds 500 MiB')
        self.spool.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=self.spool) as directory:
            raw = Path(directory) / 'raw'
            await self._spool(request, raw)
            kind, path, content_type, info = await anyio.to_thread.run_sync(prepare, raw, self.artifacts.max_pixels)
            route = '/v1/uploads' if kind == 'image' else '/v1/media/uploads'
            if kind == 'image' and path.stat().st_size > self.artifacts.max_bytes:
                raise TransferError(413, f'Images are limited to {self.artifacts.max_bytes // (1024 * 1024)} MiB')
            endpoint = self.routes().get(('POST', route))
            if endpoint is None:
                raise TransferError(503, 'Uploads are unavailable on this server')
            with path.open('rb') as handle:
                file = UploadFile(handle, filename=grant['name'], headers={'content-type': content_type})
                try:
                    stored = (await endpoint(file=file, session_id=grant['session_id'] or 'direct'))['data']
                except HTTPException as exc:
                    raise TransferError(422, 'The file was rejected: ' + str(exc.detail)) from None
                except NotOwned:
                    raise TransferError(404, 'The session does not belong to your account') from None
        reference = {'uri': stored['uri'], 'sha256': stored['sha256']}
        details = {k: stored[k] for k in ('width', 'height', 'has_alpha', 'size') if k in stored}
        return {'reference': reference, 'kind': kind, 'content_type': stored.get('content_type', content_type), **info, **details}

    async def _spool(self, request, target):
        size = 0
        content_type = request.headers.get('content-type', '')
        with target.open('wb') as out:
            if content_type.startswith('multipart/form-data'):
                async def counted():
                    nonlocal size
                    async for chunk in request.stream():
                        size += len(chunk)
                        if size > MEDIA_MAX_BYTES + 1024 * 1024:
                            raise TransferError(413, 'File exceeds 500 MiB')
                        yield chunk
                from starlette.formparsers import MultiPartParser
                try:
                    form = await MultiPartParser(request.headers, counted(), max_files=1, max_fields=10).parse()
                except TransferError:
                    raise
                except Exception:
                    raise TransferError(400, 'Invalid multipart body; send exactly one file field') from None
                files = [value for _, value in form.multi_items() if hasattr(value, 'read')]
                if len(files) != 1:
                    raise TransferError(400, 'Send exactly one file field (curl -F "file=@./name.ext" <url>)')
                written = 0
                while chunk := await files[0].read(1024 * 1024):
                    written += len(chunk)
                    out.write(chunk)
                await form.close()
                size = written
            else:
                async for chunk in request.stream():
                    size += len(chunk)
                    if size > MEDIA_MAX_BYTES:
                        raise TransferError(413, 'File exceeds 500 MiB')
                    out.write(chunk)
        if not size:
            raise TransferError(400, 'The request body is empty; send the file bytes (curl -T ./name.ext <url>)')
        if size > MEDIA_MAX_BYTES:
            raise TransferError(413, 'File exceeds 500 MiB')


def guess_type(path):
    from .artifacts import MEDIA_TYPES
    by_extension = {extension: mime for mime, extension in MEDIA_TYPES.items()}
    by_extension.update(png='image/png', jpg='image/jpeg', jpeg='image/jpeg', webp='image/webp', wav='audio/wav')
    return by_extension.get(path.suffix.lstrip('.').lower(), 'application/octet-stream')


def prepare(raw, max_pixels):
    """Detect the real type from the bytes and normalize uncommon containers.

    Returns (kind, path, content_type, info). Images other than PNG/JPEG/WebP become PNG;
    audio outside WAV/FLAC/MP3/Ogg becomes FLAC; video outside MP4/MKV/WebM is remuxed to MKV.
    """
    try:
        with Image.open(raw) as image:
            if image.width * image.height > max_pixels:
                raise TransferError(413, f'Image exceeds {max_pixels} pixels')
            if image.format in IMAGE_TYPES:
                return 'image', raw, IMAGE_TYPES[image.format], {}
            image.seek(0)
            image.load()
            converted = raw.with_name('converted.png')
            frame = image.convert('RGBA' if 'A' in image.getbands() or 'transparency' in image.info else 'RGB')
            frame.save(converted, 'PNG')
            return 'image', converted, 'image/png', {'converted_from': image.format}
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
        if isinstance(exc, Image.DecompressionBombError):
            raise TransferError(413, f'Image exceeds {max_pixels} pixels') from None
    probe = ffprobe(raw)
    if probe is None:
        raise TransferError(415, 'Unsupported file: send an image (PNG, JPEG, WebP, GIF, BMP, TIFF…), audio or video')
    streams = probe.get('streams', [])
    names = probe.get('format', {}).get('format_name', '').split(',')
    formats, primary = set(names), names[0]
    duration = float(probe.get('format', {}).get('duration') or 0)
    video = [s for s in streams if s.get('codec_type') == 'video' and not (s.get('disposition') or {}).get('attached_pic')]
    audio = [s for s in streams if s.get('codec_type') == 'audio']
    if video:
        info = {'seconds': round(duration, 3), 'width': video[0].get('width'), 'height': video[0].get('height'), 'has_audio': bool(audio)}
        codecs = {s.get('codec_name') for s in video + audio}
        if 'webm' in formats and codecs <= WEBM_CODECS:
            return 'video', raw, 'video/webm', info
        if 'matroska' in formats:
            return 'video', raw, 'video/x-matroska', info
        if 'mp4' in formats or 'mov' in formats:
            return 'video', raw, 'video/mp4', info
        remuxed = raw.with_name('remuxed.mkv')
        if not ffmpeg(['-i', str(raw), '-map', '0:v:0', '-map', '0:a?', '-c', 'copy', str(remuxed)]):
            raise TransferError(415, 'This video container could not be read; send MP4, MKV or WebM')
        return 'video', remuxed, 'video/x-matroska', {**info, 'converted_from': primary}
    if audio:
        info = {'seconds': round(duration, 3)}
        for name, mime in AUDIO_FORMATS.items():
            if name in formats:
                if name == 'ogg' and audio[0].get('codec_name') == 'opus':
                    mime = 'audio/opus'
                return 'audio', raw, mime, info
        converted = raw.with_name('converted.flac')
        if not ffmpeg(['-i', str(raw), '-map', '0:a:0', '-vn', '-c:a', 'flac', str(converted)]):
            raise TransferError(415, 'This audio could not be decoded; send WAV, FLAC, MP3 or Ogg/Opus')
        return 'audio', converted, 'audio/flac', {**info, 'converted_from': primary}
    raise TransferError(415, 'Unsupported file: no image, audio or video stream found')


def ffprobe(path):
    try:
        result = subprocess.run(['ffprobe', '-v', 'error', '-show_entries',
                                 'format=format_name,duration:stream=codec_type,codec_name,width,height:stream_disposition=attached_pic',
                                 '-of', 'json', str(path)], capture_output=True, text=True, timeout=60, check=True)
        return json.loads(result.stdout)
    except (subprocess.SubprocessError, OSError, ValueError):
        return None


def ffmpeg(arguments):
    try:
        subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-y', *arguments], capture_output=True, timeout=600, check=True)
        return True
    except (subprocess.SubprocessError, OSError):
        return False
