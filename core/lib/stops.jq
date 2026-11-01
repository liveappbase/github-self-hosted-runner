# core/lib/stops.jq — the STOP table (PLAN D7), the ONE copy: status.jq prints each STOP's properties from it, keep.jq
# reads "a newer release proceeds alone?" from it (core/README.md, "KEEP" and "The programs' outputs").

# STOP -> [candidate closed?, version rejected?, a newer release proceeds alone?]; null = the plan's "—". SHIM REFUSED
# is D6's ("STOP with the shim's reason"): D7 has no row for it, so its properties are this table's own.
def table: {
  "check failed": [true, false, true],
  "ROLLED BACK": [true, true, true],
  "PINNED RUNNER RETIRED": [true, true, true],
  "JOBS FAIL ON THE NEW IMAGE": [false, false, false],
  "ROLLBACK FAILED": [false, null, false],
  "CI DISABLED": [false, null, false],
  "POOL DOWN": [false, null, false],
  "HAND CHANGE": [null, false, false],
  "recipe changed": [null, false, false],
  "NO BASELINE": [null, false, false],
  "NO EVIDENCE": [false, false, false],
  "NO IDLE": [false, false, false],
  "untested jq": [null, false, false],
  "SHIM REFUSED": [false, false, false]
};

# a STOP's row, or null for a STOP this core does not know (its properties are never guessed)
def props($name): table[$name] // null;

# a newer release proceeds alone past this STOP: true only when its row says so (an unknown STOP: false)
def newer_proceeds($name): (props($name) // [null, null, false])[2] == true;
