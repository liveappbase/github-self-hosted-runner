# core/lib/logfmt.jq — runscaler's log text into records. Shared by the core's programs (core/README.md, "The log").
#
# The format is charm log v2's text formatter (runscaler's default `log-format = "text"`), one Write per record:
#   YYYY-MM-DD HH:MM:SS LEVEL [SET: ]MESSAGE key=value key="quoted \"value\""
#   a multi-line value as a line "  key=" and then one line "  │ TEXT" per value line; after it, more keys on a line
#   " key=value", or another "  key=" (a blank line may come between)
# Lines of other programs (a Docker pull writes "…: Pulling from …", "Digest: …") are no record and end the record
# before them; continuation lines with no record before them (the tail of an earlier interval's record) are ignored.
#
# tokenize: the log text -> {"records": [RECORD], "carry": TEXT}. RECORD = {"t", "lvl", "set" (null for a global
# record), "msg", "attrs" (top-level keys only; quoted values unquoted, multi-line values joined with "\n"), "text" (the
# record's lines as written)}. carry = the last record, from its header on: a record is complete only when a following
# record header is read, so the last one is always held, also when the text ends with a newline (with no header in
# the text: a partial last line). The caller prepends it to the next interval's text. tokenize_final reads every
# record and holds nothing (r1.jq: a held record once the log has been quiet for SETTLE, and P's text at the updater's
# own restart); when the text ends in a partial line that belongs to a record, that record has "partial": true. A
# partial last line that starts with a space belongs to the record before it: it is a continuation line cut short
# ("  ", "  err", "  " and a cut "│", " nam": a short write that ended at the start of a key, value or attribute line).
# A partial last line of another shape (a cut header, another program's line) leaves the record before it whole.

def _hdr_re: "^[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2} (DEBU|INFO|WARN|ERRO|FATA) ";
def _key_re: "[A-Za-z_][A-Za-z0-9_.-]*";

# runscaler's messages the core reads, matched EXACTLY: the message, then the end or " key=" (so "Runner started
# (cold)", a Tart debug line, is not "Runner started")
def known_messages: [
  "Failed to start runner, will retry",
  "Runner exited before job completion; removing stale capacity",
  "Runner removed",
  "Runner started",
  "VM exited unexpectedly"
];

def _kind:
  if test(_hdr_re) then "h"
  elif startswith("  │") then "v"
  elif test("^  " + _key_re + "=$") then "k"
  elif test("^ " + _key_re + "=") then "a"
  elif . == "" then "e"
  else "f" end;

def _unquote:
  if length >= 2 and startswith("\"") and endswith("\"") then .[1:-1] | gsub("\\\\\""; "\"") else . end;

def _attrs:
  [match("(?<k>" + _key_re + ")=(?<v>\"(?:[^\"\\\\]|\\\\.)*\"|[^ ]*)"; "g")
   | {(.captures[0].string): (.captures[1].string | _unquote)}] | add // {};

def _split_message:
  . as $r
  | ([known_messages[] | . as $m
      | select($r == $m or (($r | startswith($m + " ")) and ($r[($m | length):] | test("^ " + _key_re + "="))))]
     | .[0]) as $k
  | if $k != null then {msg: $k, attrs: $r[($k | length):]}
    else $r | capture("^(?<msg>.*?)(?<attrs>( " + _key_re + "=.*)?)$") end;

def _header:
  capture("^(?<t>[0-9-]{10} [0-9:]{8}) (?<lvl>[A-Z]{4}) (?<rest>.*)$") as $h
  | (($h.rest | capture("^(?<set>[A-Za-z0-9][A-Za-z0-9._-]*): (?<r>.*)$")) // {set: null, r: $h.rest}) as $p
  | ($p.r | _split_message) as $m
  | {t: $h.t, lvl: $h.lvl, set: $p.set, msg: $m.msg, attrs: ($m.attrs | _attrs), text: .};

def _tokenize($final):
  . as $text
  | ($text | endswith("\n")) as $complete
  | ($text | split("\n")) as $all
  | (if $complete then $all[:-1] else $all end) as $ls
  | [$ls[] | _kind] as $kinds0
  # tokenize_final of a text that ends in a partial line that starts with a space: a continuation line cut short, of
  # the record before it ("c"), not another program's line (Codex r3 F1, Opus r3 F2)
  | (if $final and ($complete | not) and ($kinds0 | length) > 0 and $kinds0[-1] == "f" and ($ls[-1] | startswith(" "))
     then $kinds0[:-1] + ["c"] else $kinds0 end) as $kinds
  | ([range(0; $kinds | length) | select($kinds[.] == "h")] | last) as $last_h
  | (if ($ls | length) == 0 then 0
     elif $final then ($ls | length)
     # the last record is not complete until a following record header is read: a value line, a "  key=" line or
     # more " key=value" may still come, also when the text ends with a newline (Codex r1 F1)
     elif $last_h != null then $last_h
     # no header: only a partial last line may be the start of one
     elif ($complete | not) then (($ls | length) - 1)
     else ($ls | length) end) as $cut
  | {records:
      (reduce range(0; $cut) as $i ({recs: [], cur: null, key: null};
         $ls[$i] as $l | $kinds[$i] as $k
         | if $k == "h" then (if .cur != null then .recs += [.cur] else . end) | .cur = ($l | _header) | .key = null
           elif .cur == null then .
           elif $k == "k" then ($l | ltrimstr("  ") | rtrimstr("=")) as $key
             | .key = $key | .cur.attrs[$key] = [] | .cur.text += "\n" + $l
           elif $k == "v" then
             (if .key != null then .key as $key | .cur.attrs[$key] += [$l | sub("^  │ ?"; "")] else . end)
             | .cur.text += "\n" + $l
           elif $k == "a" then .cur.attrs += ($l | _attrs) | .key = null | .cur.text += "\n" + $l
           elif $k == "e" then .
           elif $k == "c" then .cur.text += "\n" + $l
           else .recs += [.cur] | .cur = null | .key = null end)
       # tokenize_final of a text that ends in a partial line: the record that line belongs to is `partial` (r1.jq reads
       # it only as a proof of life). A line of another program ended the record before it (.cur is null then)
       | (if $final and ($complete | not) and .cur != null then .cur.partial = true else . end)
       | (if .cur != null then .recs + [.cur] else .recs end)
       | map(.attrs |= with_entries(if (.value | type) == "array" then .value |= join("\n") else . end))),
     carry: (if $cut < ($ls | length) then ($ls[$cut:] | join("\n")) + (if $complete then "\n" else "" end)
             else "" end)};

def tokenize: _tokenize(false);
def tokenize_final: _tokenize(true);
