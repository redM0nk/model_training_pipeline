"""Dataset Curation Console — Flask backend."""
import hmac
import os
import shutil
import subprocess

import yaml
from flask import Flask, Response, jsonify, render_template, request

from dispatcher import Dispatcher
from queue_store import QueueStore
from s3_browser import S3Browser

HERE = os.path.dirname(os.path.abspath(__file__))


def load_conf() -> dict:
    with open(os.path.join(HERE, "app_config.yaml")) as f:
        return yaml.safe_load(f)


def create_app() -> Flask:
    conf = load_conf()
    app = Flask(__name__, template_folder="templates", static_folder="static")

    password = os.environ.get("APP_PASSWORD", "Everestlabs_123!")

    @app.before_request
    def _require_password():
        auth = request.authorization
        if auth and hmac.compare_digest((auth.password or ""), password):
            return None
        return Response(
            "Authentication required.\n",
            401,
            {"WWW-Authenticate": 'Basic realm="Dataset Curation Console"'},
        )

    browser = S3Browser(
        bucket=conf["s3_bucket"],
        root_prefix=conf["s3_root_prefix"],
        videos_subpath=conf["videos_subpath"],
        images_subpath=conf["images_subpath"],
    )
    store = QueueStore(os.path.join(HERE, "state", "queue.json"))
    dispatcher = Dispatcher(store, conf)
    dispatcher.start()

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/api/customers")
    def api_customers():
        return jsonify(browser.list_customers())

    @app.get("/api/locations")
    def api_locations():
        return jsonify(browser.list_locations(request.args["customer"]))

    @app.get("/api/conveyors")
    def api_conveyors():
        return jsonify(browser.list_conveyors(
            request.args["customer"], request.args["location"]))

    @app.get("/api/dates")
    def api_dates():
        entries = browser.list_dates(
            request.args["customer"],
            request.args["location"],
            request.args["conveyor"],
        )
        return jsonify([
            {"date": e.date, "has_videos": e.has_videos,
             "has_images": e.has_images, "ready": e.ready,
             "video_file_count": e.video_file_count,
             "video_total_size": e.video_total_size,
             "image_folder_count": e.image_folder_count}
            for e in entries
        ])

    @app.get("/api/videos")
    def api_videos():
        files = browser.list_video_files(
            request.args["customer"],
            request.args["location"],
            request.args["conveyor"],
            request.args["date"],
        )
        for f in files:
            f["url"] = browser.presign(f["key"])
            f["stream_url"] = "/api/video_stream?key=" + f["key"]
        return jsonify(files)

    @app.get("/api/video_stream")
    def api_video_stream():
        key = request.args.get("key", "")
        if not browser.is_managed_key(key):
            return ("forbidden", 403)
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            return ("ffmpeg not installed on the server", 501)
        url = browser.presign(key, expires=3600, content_type="application/octet-stream")
        cmd = [
            ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin",
            "-i", url,
            "-vf", "scale='min(1280,iw)':-2",
            "-c:v", "libx264", "-preset", "ultrafast", "-tune", "zerolatency",
            "-crf", "28", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k", "-ac", "2",
            "-movflags", "+frag_keyframe+empty_moov+default_base_moof",
            "-f", "mp4", "pipe:1",
        ]
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            bufsize=0,
        )

        def generate():
            try:
                while True:
                    chunk = proc.stdout.read(64 * 1024)
                    if not chunk:
                        break
                    yield chunk
            finally:
                try:
                    proc.stdout.close()
                except Exception:
                    pass
                if proc.poll() is None:
                    proc.terminate()
                    try:
                        proc.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        proc.kill()

        return Response(generate(), mimetype="video/mp4",
                        headers={"Cache-Control": "no-store",
                                 "Accept-Ranges": "none"})

    @app.get("/api/queue")
    def api_queue():
        return jsonify(store.list_jobs())

    @app.post("/api/queue")
    def api_queue_add():
        body = request.get_json(force=True)
        customer = body["customer"]
        location = body["location"]
        conveyor = body["conveyor"]
        dates = body.get("dates") or []

        loc_path = browser.relative_location_path(customer, location, conveyor)
        added = []
        for d in dates:
            j = store.add_job(customer, location, conveyor, d, loc_path)
            added.append(j)
        return jsonify({"added": added})

    @app.post("/api/queue/<job_id>/cancel")
    def api_queue_cancel(job_id: str):
        j = store.cancel(job_id)
        if not j:
            return jsonify({"error": "not pending or not found"}), 404
        return jsonify(j)

    @app.get("/api/tmux/status")
    def api_tmux_status():
        cmd = dispatcher._tmux_pane_command()
        return jsonify({
            "target": conf["tmux_target"],
            "current_command": cmd,
            "idle": cmd in conf["idle_commands"],
        })

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8765")))
