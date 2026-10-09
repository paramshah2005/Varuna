import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit
from backend.api.handler import handler
from backend.api.storage import get_store


class LocalHandler(BaseHTTPRequestHandler):
    def handle_request(self):
        path = urlsplit(self.path)
        if path.path == "/api/health":
            result = dict(
                statusCode=200,
                body=json.dumps(dict(mode="local development", ready=True)),
            )
        else:
            length = int(self.headers.get("Content-Length", "0"))
            if length > 150000:
                self.send_error(413)
                return
            event = dict(
                rawPath=path.path,
                headers=dict(self.headers),
                body=self.rfile.read(length).decode() if length else None,
                queryStringParameters={
                    k: v[0] for k, v in parse_qs(path.query).items()
                },
                requestContext=dict(
                    http=dict(method=self.command),
                    authorizer=dict(jwt=dict(claims=dict(sub="local-operator"))),
                ),
            )
            result = handler(event)
        self.send_response(result["statusCode"])
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(result["body"].encode())

    do_GET = handle_request
    do_POST = handle_request

    def log_message(self, format, *args):
        pass


def main():
    store = get_store()
    from backend.workflows.jobs import local_start, local_apply

    for row in store.db.execute(
        "SELECT body FROM records WHERE sk='META' AND pk LIKE 'RUN#%'"
    ).fetchall():
        run = json.loads(row[0])
        if run["status"] in {
            "queued",
            "simulating",
            "baseline_complete",
            "investigating",
            "plan_ready",
            "job_retrying",
        }:
            threading.Thread(
                target=local_start, args=(run["run_id"], store), daemon=True
            ).start()
        elif run["status"] in {"applying", "verified"}:
            threading.Thread(
                target=local_apply, args=(run["run_id"], store), daemon=True
            ).start()
    port = int(os.getenv("AQUA_LOCAL_API_PORT", "8000"))
    print(f"AquaAgent local development API: http://127.0.0.1:{port}/api", flush=True)
    ThreadingHTTPServer(("127.0.0.1", port), LocalHandler).serve_forever()


if __name__ == "__main__":
    main()
