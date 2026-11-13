"""Write an asset's usage.json from an OpenCode session (project-structure.md "Usage tracking").

Plain Python (no Blender). Prices are NEVER guessed: look up the exact model's current official API
pricing (per million tokens) and pass it in. Without rates, a recorded non-zero session cost is used;
with neither, nothing is written (unknown is not zero).

    python3 _lib/usage.py ses_XXXX models/<asset> --model gpt-6.1-sol \
        --input-rate 2 --output-rate 10 --cache-read-rate 0.10 [--cache-write-rate 2.5] \
        [--reasoning-included] [--effort high] [--dry-run]

The session may also be a path to a saved `opencode api get /api/session/<id>` JSON file.
Prints a NOTES.md block (session, counters, rates, formula, result) to paste and complete with the
pricing source URL and lookup date.
"""
import argparse
import json
import os
import subprocess
import sys

FIELDS = ("model", "effort", "input", "output", "cached_input", "spend")


def load_session(ref):
    if os.path.isfile(ref):
        with open(ref) as fh:
            d = json.load(fh)
    else:
        out = subprocess.run(["opencode", "api", "get", f"/api/session/{ref}"], check=True,
                             capture_output=True, text=True).stdout
        d = json.loads(out)
    return d.get("data", d)


def compute(sess, rates=None, reasoning_included=False):
    """-> dict(counters..., spend, formula). rates: dict(input, output, cache_read, cache_write) $/M."""
    t = sess["tokens"]
    c = dict(input=int(t["input"]), output=int(t["output"]), reasoning=int(t.get("reasoning", 0)),
             cache_read=int(t["cache"]["read"]), cache_write=int(t["cache"].get("write", 0)),
             recorded_cost=float(sess.get("cost") or 0))
    billable_out = c["output"] + (0 if reasoning_included else c["reasoning"])
    if rates:
        if c["cache_write"] and rates.get("cache_write") is None:
            raise SystemExit(f"{c['cache_write']} cache-write tokens recorded: pass --cache-write-rate")
        spend = (c["input"] * rates["input"] + c["cache_read"] * rates["cache_read"]
                 + c["cache_write"] * (rates.get("cache_write") or 0) + billable_out * rates["output"]) / 1e6
        formula = (f"({c['input']} x {rates['input']} + {c['cache_read']} x {rates['cache_read']}"
                   f" + {c['cache_write']} x {rates.get('cache_write') or 0}"
                   f" + {billable_out} x {rates['output']}) / 1,000,000")
    elif c["recorded_cost"] > 0:
        spend, formula = c["recorded_cost"], "recorded session API cost"
    else:
        raise SystemExit("no rates given and the recorded cost is 0: look up official pricing and pass "
                         "--input-rate/--output-rate/--cache-read-rate (unknown is not zero; usage.json not written)")
    return dict(c, billable_output=billable_out, spend=round(spend, 6), formula=formula)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("session", help="OpenCode session ID or saved session JSON")
    ap.add_argument("asset_dir", help="the asset folder, e.g. models/<asset> (usage.json is written there)")
    ap.add_argument("--model", required=True,
                    help="name of the AI model that created the asset, e.g. claude-opus-5.5 (session IDs like 'opus' are not exact)")
    ap.add_argument("--effort", help="effort setting (default: the session's model variant)")
    ap.add_argument("--input-rate", type=float)
    ap.add_argument("--output-rate", type=float)
    ap.add_argument("--cache-read-rate", type=float)
    ap.add_argument("--cache-write-rate", type=float)
    ap.add_argument("--reasoning-included", action="store_true",
                    help="output already includes thinking (Claude): do not add tokens.reasoning")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)

    sess = load_session(a.session)
    given = [a.input_rate, a.output_rate, a.cache_read_rate]
    if any(v is not None for v in given) and None in given:
        ap.error("pass all of --input-rate, --output-rate and --cache-read-rate")
    rates = None if given[0] is None else dict(input=a.input_rate, output=a.output_rate,
                                               cache_read=a.cache_read_rate, cache_write=a.cache_write_rate)
    r = compute(sess, rates, a.reasoning_included)
    effort = a.effort or (sess.get("model") or {}).get("variant")
    model = a.model
    out = dict(model=model, effort=effort, input=r["input"], output=r["output"],
               cached_input=r["cache_read"], spend=r["spend"])
    if effort is None:
        raise SystemExit("effort unknown: pass --effort")
    text = json.dumps(out, indent=2) + "\n"
    json.loads(text)
    path = os.path.join(a.asset_dir, "usage.json")
    if not a.dry_run:
        with open(path, "w") as fh:
            fh.write(text)
    sys.stdout.write(text)
    sys.stdout.write(f"""
NOTES.md usage block (add the pricing source URL and lookup date):
- Session: `{sess.get('id', a.session)}` ({(sess.get('model') or {}).get('providerID')}/{(sess.get('model') or {}).get('id')}, variant {effort})
- Counters: input {r['input']}, output {r['output']}, reasoning {r['reasoning']}{' (included in output)' if a.reasoning_included else ' (billed as output)'}, cache read {r['cache_read']}, cache write {r['cache_write']}; recorded cost {r['recorded_cost']}
- Rates ($/M): {rates if rates else 'n/a'}
- spend = {r['formula']} = ${r['spend']:.6f} (API-equivalent estimate, not an invoice)
{'(dry run: ' + path + ' not written)' if a.dry_run else 'Wrote ' + path}
""")
    return 0


if __name__ == "__main__":
    sys.exit(main())
