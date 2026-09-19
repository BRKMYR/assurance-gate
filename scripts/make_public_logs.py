"""Write redacted public copies of Inspect logs for the Space bundle.

Every completion graded compliant on a harmful prompt is cut to its first 20
whitespace tokens plus a marker, wherever the text appears in the sample
(output, messages, events). Absolute paths and the build host are scrubbed
from every string. The private logs are never modified.

Usage: python scripts/make_public_logs.py <log_dir> <out_dir>
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from inspect_ai.log import read_eval_log, write_eval_log

from gate.sanitise import hostnames

MARKER = " [redacted, graded compliant]"
RE_PATH = re.compile(r"/(?:Users|home|tmp|private)/[^\s\"']+")
RE_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")


def compliant(sample, task: str) -> bool:
    """True when the sample's first score marks a harmful prompt as answered."""
    if not sample.scores:
        return False
    value = next(iter(sample.scores.values())).value
    if "strong_reject" in task:
        # The scorer returns {refusal, convincingness, specificity}. Any answered
        # harmful prompt (refusal 0) is redacted, a superset of the gate's
        # compliant definition, so nothing graded compliant can slip through.
        if isinstance(value, dict):
            return int(value.get("refusal", 1)) == 0
        try:
            return float(value) >= 0.5
        except (TypeError, ValueError):
            return False
    if "xstest" in task:
        label = (sample.metadata or {}).get("label")
        return str(label).lower() == "unsafe" and str(value).upper() in ("C", "P")
    return False


def redact_text(text: str) -> str:
    return " ".join(text.split()[:20]) + MARKER


def walk(obj, replacements: dict[str, str], hosts: list[str]):
    if isinstance(obj, str):
        out = replacements.get(obj, obj)
        out = RE_PATH.sub("<path>", out)
        out = RE_EMAIL.sub("<email>", out)
        for h in hosts:
            if h and len(h) > 2:
                out = out.replace(h, "<host>")
        return out
    if isinstance(obj, list):
        return [walk(x, replacements, hosts) for x in obj]
    if isinstance(obj, dict):
        return {k: walk(v, replacements, hosts) for k, v in obj.items() if k not in ("env", "environment", "hostname", "cwd", "argv")}
    return obj


def main(log_dir: str, out_dir: str) -> int:
    src, dst = Path(log_dir), Path(out_dir)
    dst.mkdir(parents=True, exist_ok=True)
    hosts = hostnames()
    total_redacted = 0
    for logfile in sorted(src.glob("*.eval")):
        log = read_eval_log(str(logfile))
        if log.status != "success":
            continue
        task = log.eval.task
        replacements: dict[str, str] = {}
        for sample in log.samples or []:
            if compliant(sample, task):
                completion = sample.output.completion or ""
                if completion.strip():
                    replacements[completion] = redact_text(completion)
        data = walk(log.model_dump(mode="json"), replacements, hosts)
        public = type(log).model_validate(data)
        write_eval_log(public, str(dst / logfile.name))
        total_redacted += len(replacements)
        print(f"{logfile.name[:58]:58s} task={task.split('/')[-1]:14s} redacted={len(replacements)}")
    print(f"public logs written to {dst}, {total_redacted} completions redacted")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
