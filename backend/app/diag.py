from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.bundle import build_bundle, bundle_json_bytes, bundle_zip_bytes


def main() -> None:
    parser = argparse.ArgumentParser(description="SonicStream local diagnostic export")
    parser.add_argument("command", choices=["bundle"])
    parser.add_argument("--job-id")
    parser.add_argument("--since")
    parser.add_argument("--until")
    parser.add_argument("--out", default="diagnostic-bundle.json")
    parser.add_argument("--zip", action="store_true")
    args = parser.parse_args()
    if not args.job_id and not args.since:
        raise SystemExit("job-id or since is required")
    bundle = build_bundle(job_id=args.job_id, since=args.since, until=args.until)
    out = Path(args.out)
    if args.zip:
        out.write_bytes(bundle_zip_bytes(bundle))
    else:
        out.write_bytes(bundle_json_bytes(bundle))
    print(json.dumps({"wrote": str(out.resolve()), "events": bundle["manifest"]["event_count"], "incomplete": bundle["manifest"]["incomplete"]}))


if __name__ == "__main__":
    main()
