# model_training_pipeline

## Video Readiness Dashboard (`app/`)

A small web app that browses the S3 production tree, shows which recording
dates are ready for frame extraction (videos uploaded but no extracted images
yet), and queues `extract_frames_for_labeling_v2.py` runs against tmux on the
host machine.

### Layout it expects in S3

```
s3://<bucket>/<root>/<customer>/<location>/<conveyor>/1/Videos/<YYYY-MM-DD>/...
s3://<bucket>/<root>/<customer>/<location>/<conveyor>/1/Images/Original/RGB/<YYYY-MM-DD>/...
```

Defaults: `bucket=emain`, `root=Data/Modeling/Fact/Production/`. Configurable
in `app/app_config.yaml`.

A date is **ready** if it appears under `Videos/` but not under
`Images/Original/RGB/`.

### Running

The app must run on the same host as the target tmux session (e.g.
`auto-ml-1`) because it dispatches via `tmux send-keys`.

```bash
cd app
./run.sh             # serves on http://0.0.0.0:8765
```

If a tmux session named `1` doesn't exist yet, create it first:

```bash
tmux new -s 1 -d
```

### How queueing works

1. User picks customer → location → conveyor → checks recording dates.
2. Clicking **Queue selected** posts to `/api/queue`; jobs land in
   `app/state/queue.json` as `pending`.
3. A background dispatcher thread polls the configured tmux pane
   (`tmux_target` in `app_config.yaml`, default `1:0.0`).
4. When the pane is idle (its `pane_current_command` is a shell), the
   dispatcher:
   - writes a per-job YAML in `per_job_config_dir/` whose
     `locations_to_monitor` is scoped to just the queued conveyor;
   - sends:
     `cd <wd> && python data_collection/extract_frames_for_labeling_v2.py
     --path_to_config <per-job-yaml> --recording_date <date> && touch <marker>`
   - watches for the marker to mark the job `done` (or `failed` if the pane
     goes idle without producing the marker).

Jobs run one at a time, in order. The Queue table updates every 5s.

### Notes

- AWS credentials are picked up from the standard boto3 chain
  (env, `~/.aws/credentials`, instance profile, etc.).
- Cancelling a job is only possible while it's `pending`. A `running` job
  has already been sent to tmux and would need to be killed in the pane.
- Set `tmux_target` to the actual session/window/pane index for your setup;
  tmux indexing depends on `base-index` in `~/.tmux.conf`.
