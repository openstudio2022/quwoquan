"""Loopback-only 同源 HTTP 服务。"""
from __future__ import annotations
import json, mimetypes, sys, time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse
from .service import WorkbenchError, WorkbenchService

class WorkbenchHandler(SimpleHTTPRequestHandler):
    service: WorkbenchService
    static_root: Path
    chunk_size = 64 * 1024
    def __init__(self, *args, **kwargs): super().__init__(*args, directory=str(self.static_root), **kwargs)
    def _timing(self): return (time.perf_counter() - getattr(self, "_started", time.perf_counter())) * 1000
    def _headers(self): self.send_header("Server-Timing", f'app;dur={self._timing():.3f}')
    def _json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode(); self.send_response(status); self.send_header("Content-Type", "application/json; charset=utf-8"); self.send_header("Content-Length", str(len(body))); self._headers(); self.end_headers()
        try: self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError): pass
    @staticmethod
    def _filters(query):
        mapping = {x: x for x in ("contentFormIds", "sources", "tagRefs", "versions", "reviewStates", "poolStates", "captureCoverages", "semanticParseCoverages", "revisions", "captureMethods", "dialectVersions", "semanticFingerprints", "lossSeverities", "carrierMismatches", "modelBatches", "reviewGates")}; filters = {d: query[s] for s, d in mapping.items() if query.get(s)}
        for name in ("query", "tagMatch", "sort", "readToken"):
            if query.get(name): filters[name] = query[name][-1]
        for name in ("page", "pageSize"):
            if query.get(name):
                try: filters[name] = int(query[name][-1])
                except ValueError as exc: raise WorkbenchError("CONTENT_WORKBENCH.REQUEST_INVALID", f"{name} must be an integer") from exc
        return filters
    def _error(self, exc): self._json(exc.status, {"error": {"code": exc.code, "message": str(exc)}})
    def _finish_log(self, operation, status):
        print(json.dumps({"component": "content_workbench", "operation": operation, "status": status, "durationMs": round(self._timing(), 3)}, ensure_ascii=False), file=sys.stderr, flush=True)
    def _static_get(self, parsed):
        decoded = unquote(parsed.path)
        if ".." in Path(decoded).parts:
            self.send_error(404, "File not found")
            return
        target = Path(self.translate_path(parsed.path))
        if target.exists() or Path(decoded).suffix:
            return super().do_GET()
        original = self.path
        try:
            self.path = "/index.html"
            return super().do_GET()
        finally:
            self.path = original
    def do_GET(self):
        self._started = time.perf_counter(); parsed = urlparse(self.path); operation = parsed.path
        try:
            filters = self._filters(parse_qs(parsed.query))
            if parsed.path == "/api/overview": self._json(200, self.service.overview(filters))
            elif parsed.path == "/api/facets": self._json(200, self.service.facets(filters))
            elif parsed.path == "/api/items": self._json(200, self.service.query(filters))
            elif parsed.path.startswith("/api/items/") and "/sources/" in parsed.path and "/evidence/" in parsed.path:
                parts = parsed.path.split("/")
                if len(parts) != 9: raise WorkbenchError("CONTENT_WORKBENCH.NOT_FOUND", "API route not found", 404)
                self._json(200, self.service.source_evidence(unquote(parts[3]), unquote(parts[4]), unquote(parts[6]), unquote(parts[8]), filters.get("readToken")))
            elif parsed.path.startswith("/api/items/"):
                parts = parsed.path.split("/")
                if len(parts) != 5: raise WorkbenchError("CONTENT_WORKBENCH.NOT_FOUND", "API route not found", 404)
                self._json(200, self.service.detail(unquote(parts[3]), unquote(parts[4]), filters))
            elif parsed.path.startswith("/api/media/"):
                parts = parsed.path.split("/")
                if len(parts) < 6: raise WorkbenchError("CONTENT_WORKBENCH.NOT_FOUND", "API route not found", 404)
                self._media(self.service.media_path(unquote(parts[3]), unquote(parts[4]), unquote("/".join(parts[5:])), filters.get("readToken")))
            elif parsed.path.startswith("/api/"): raise WorkbenchError("CONTENT_WORKBENCH.NOT_FOUND", "API route not found", 404)
            else: return self._static_get(parsed)
            self._finish_log(operation, 200)
        except WorkbenchError as exc: self._error(exc); self._finish_log(operation, exc.status)
        except (IndexError, KeyError, ValueError) as exc: self._error(WorkbenchError("CONTENT_WORKBENCH.REQUEST_INVALID", str(exc))); self._finish_log(operation, 400)
    def _media(self, path):
        if not path.is_file(): raise WorkbenchError("CONTENT_WORKBENCH.NOT_FOUND", "media not found", 404)
        size = path.stat().st_size; start, end, status = 0, size - 1, 200; header = self.headers.get("Range")
        if header:
            try:
                unit, value = header.split("=", 1); lower, upper = value.split("-", 1); start, end = int(lower or 0), int(upper or end)
                if unit != "bytes" or start < 0 or end < start or end >= size: raise ValueError
            except ValueError as exc: raise WorkbenchError("CONTENT_WORKBENCH.RANGE_INVALID", "invalid byte range", 416) from exc
            status = 206
        self.send_response(status); self.send_header("Content-Type", mimetypes.guess_type(path.name)[0] or "application/octet-stream"); self.send_header("Accept-Ranges", "bytes"); self.send_header("Content-Length", str(end - start + 1))
        if status == 206: self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self._headers(); self.end_headers(); remaining = end - start + 1
        try:
            with path.open("rb") as handle:
                handle.seek(start)
                while remaining:
                    chunk = handle.read(min(self.chunk_size, remaining))
                    if not chunk: break
                    self.wfile.write(chunk); remaining -= len(chunk)
        except (BrokenPipeError, ConnectionResetError): pass
    def do_POST(self):
        self._started = time.perf_counter(); operation = urlparse(self.path).path
        try:
            length = int(self.headers.get("Content-Length", "0")); data = json.loads(self.rfile.read(length) or b"{}")
            if operation == "/api/reviews": payload = self.service.save_review(data)
            elif operation == "/api/candidates": payload = self.service.register_candidate(data)
            elif operation == "/api/refresh": payload = self.service.refresh()
            else: raise WorkbenchError("CONTENT_WORKBENCH.NOT_FOUND", "API route not found", 404)
            self._json(200, payload); self._finish_log(operation, 200)
        except WorkbenchError as exc: self._error(exc); self._finish_log(operation, exc.status)
        except (ValueError, json.JSONDecodeError) as exc: self._error(WorkbenchError("CONTENT_WORKBENCH.REQUEST_INVALID", str(exc))); self._finish_log(operation, 400)
    def log_message(self, format, *args): pass

def serve(service, static_root, host="127.0.0.1", port=0):
    if host not in {"127.0.0.1", "::1", "localhost"}: raise WorkbenchError("CONTENT_WORKBENCH.NON_LOOPBACK", "only loopback bind is allowed")
    static_root = static_root.expanduser().resolve(strict=True)
    handler = type("ConfiguredWorkbenchHandler", (WorkbenchHandler,), {"service": service, "static_root": static_root})
    return ThreadingHTTPServer((host, port), handler)
