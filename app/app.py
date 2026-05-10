"""Video readiness dashboard — Flask backend."""
import os

import yaml
from flask import Flask, jsonify, render_template, request

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
             "image_file_count": e.image_file_count,
             "image_total_size": e.image_total_size}
            for e in entries
        ])

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
