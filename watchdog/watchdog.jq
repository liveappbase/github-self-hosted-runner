# watchdog/watchdog.jq — the rules of the weekly runner watchdog (PLAN D8); watchdog/run does the gh calls and runs it.
# It must run under every jq of core/TESTED_JQ with the area watchdog, jq-1.6 included: every `if` has its `else`.
#
#   jq -n -r -f watchdog.jq --arg step pick|rules --argjson now EPOCH --arg release V --slurpfile cfg F
#      --slurpfile releases F --slurpfile jobs F [--slurpfile logs F]
# cfg: {"hosts": {"hz": LINE, "studio": LINE}, "families": [{"name", "host", "labels": [...]}]}; releases: GitHub's
# release list of actions/runner; jobs: one array of job objects (the jobs on main of the last 14 days); logs: {"JOB
# ID": the head of its log}; release: the newest release (releases/latest), whose version names the topics.
#   step pick:  the job ids whose logs the rules read (per label: its newest job, and its newest job older than 8 days)
#   step rules: the output lines, every `clear` before every `open`

def DAY: 86400;
def vnum: split(".") | map(tonumber);
def dashed: gsub("\\."; "-");
def day: strftime("%Y-%m-%d");

def cfg: $ARGS.named.cfg[0];
def alljobs: $ARGS.named.jobs[0];
def labels: [cfg.families[] | .name as $f | .host as $h | .labels[] | {label: ., family: $f, host: $h}];

def measured($now):
  labels[] as $L
  | ([alljobs[] | select(.status == "completed" and .runner_name != null and .started_at != null
                         and any(.labels[]?; . == $L.label))] | sort_by(.started_at)) as $js
  | $L + {jobs: $js, newest: ($js | last),
          old: ([$js[] | select((.started_at | fromdateiso8601) < $now - 8 * DAY)] | last)};

def version_of($job):
  if $job == null then null
  else (($ARGS.named.logs[0] // {})[$job.id | tostring] // "") as $t
       | (($t | capture("Current runner version: '(?<v>[0-9]+\\.[0-9]+\\.[0-9]+)'") | .v) // null)
  end;

def counted: .conclusion == "success" or .conclusion == "failure" or .conclusion == "timed_out";
def failure: .conclusion == "failure" or .conclusion == "timed_out";

def rules($now; $release):
  ([$ARGS.named.releases[0][] | select(.draft != true and .prerelease != true and (.tag_name | test("^v[0-9]+\\.[0-9]+\\.[0-9]+$")))
    | {v: .tag_name[1:], at: (.published_at | fromdateiso8601)}] | sort_by(.v | vnum)) as $rels
  | ([$rels[] | select(.at <= $now - 7 * DAY)] | last) as $r7
  # every release in the list read that the newest supersedes: an ask of an old release never holds a slot, also after
  # missed weekly runs (Codex r1 F9)
  | ([$rels[] | select((.v | vnum) < ($release | vnum))] | map(.v)) as $before
  | [measured($now)
     | . as $m
     | version_of($m.newest) as $vnew | version_of($m.old) as $vold
     | ([$m.jobs[] | select(counted and (.completed_at | fromdateiso8601) > $now - 7 * DAY)]) as $last
     | ([$m.jobs[] | select(counted and (.completed_at | fromdateiso8601) > $now - 14 * DAY
                            and (.completed_at | fromdateiso8601) <= $now - 7 * DAY)]) as $prev
     | ([$last[] | select(failure)] | length) as $f1 | ($last | length) as $n1
     | ([$prev[] | select(failure)] | length) as $f0 | ($prev | length) as $n0
     | $m + {vnew: $vnew, vold: $vold, f1: $f1, n1: $n1, f0: $f0, n0: $n0,
             nm: (if $m.newest == null then "no job on main in 14 days"
                  elif $vnew == null then "its newest job log names no runner version"
                  elif $m.old == null then "no job older than 8 days, so no FAILING reading"
                  elif $vold == null then "its job of 8 days ago names no runner version"
                  else null end),
             stale: ($vnew != null and $r7 != null and (($vnew | vnum) < ($r7.v | vnum))),
             failing: ($vnew != null and $vold != null and $vnew != $vold and $f1 >= 3 and $n1 > 0
                       and ($f1 / $n1) >= 2 * (if $n0 > 0 then $f0 / $n0 else 0 end))}] as $ls
  | (cfg.hosts) as $hosts
  | ([$ls[] | select(.nm != null) | "\(.label) (\(.family)): \(.nm)"]) as $nm
  | (if ($nm | length) > 0 then " Not measured: " + ($nm | join("; ")) + "." else "" end) as $nmtext
  | ([$ls[] | select(.stale)]) as $stale
  | ([$ls[] | select(.failing)]) as $failing
  | ($release | dashed) as $R
  | ([$before[] | dashed | "clear runner-stale-\(.)", "clear runner-failing-\(.)", "clear runner-watchdog-could-not-run-\(.)"]
     + ["clear runner-watchdog-could-not-run", "clear runner-watchdog-could-not-run-\($R)"]
     + (if ($stale | length) == 0 then ["clear runner-stale-\($R)"] else [] end)
     + (if ($failing | length) == 0 then ["clear runner-failing-\($R)"] else [] end)) as $clears
  | ([if ($stale | length) > 0 then
        "open runner-stale-\($R) Update the runner images: "
        + ([$stale[] | "\(.label) (\(.family)) runs runner \(.vnew) on its newest job on main, older than runner \($r7.v) (out since \($r7.at | day))"] | join("; "))
        + ". GitHub retires old runner versions, and then no job starts on them. "
        + ([$stale | unique_by(.family)[] | "For \(.family): run `\($hosts[.host]) runner-updater status` and follow the line of its STOP."] | join(" "))
        + $nmtext
      else empty end,
      if ($failing | length) > 0 then
        "open runner-failing-\($R) Jobs fail more often since the runner image changed: "
        + ([$failing[] | "\(.label) (\(.family)) runs runner \(.vnew) (8 days ago: runner \(.vold)); \(.f1) of \(.n1) jobs failed in the last 7 days, \(.f0) of \(.n0) in the 7 days before"] | join("; "))
        + ". "
        + ([$failing | unique_by(.family)[] | "To go back to the previous image of \(.family): `\($hosts[.host]) runner-updater back \(.family)`; `\($hosts[.host]) runner-updater status` shows the date until which back works."] | join(" "))
        + $nmtext
      else empty end]) as $opens
  | ($clears + $opens)[];

($ARGS.named.now // error("watchdog.jq: --argjson now is required")) as $now
| if $ARGS.named.step == "pick" then
    [measured($now) | .newest.id, .old.id] | map(select(. != null)) | unique | .[]
  elif $ARGS.named.step == "rules" then
    rules($now; ($ARGS.named.release // error("watchdog.jq: --arg release is required")))
  else error("watchdog.jq: --arg step must be pick or rules") end
