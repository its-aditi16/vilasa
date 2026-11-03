"""Turn the India Post 'All India Pincode Directory' CSV into Vilasa's per-PIN village file.

1. Download the CSV from data.gov.in ("All India Pincode Directory") into data/raw/
2. python scripts/build_keyterms.py data/raw/<file>.csv --district Tumakuru --district Tumkur
3. Restart the app. The demo banner disappears once real data is loaded.
"""

import argparse
import sys

import _path  # noqa: F401
from vilasa.config import ROOT
from vilasa.pincodes import PinDirectory


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv", help="India Post directory CSV")
    ap.add_argument("--district", action="append", default=[], help="District name as written in the CSV (repeatable). Tumakuru is often 'TUMKUR'.")
    ap.add_argument("--state", action="append", default=[], help="Filter by state instead (repeatable)")
    ap.add_argument("--out", default=str(ROOT / "data" / "pincodes_tumakuru.json"))
    args = ap.parse_args()
    if not args.district and not args.state:
        sys.exit("Give at least one --district or --state, e.g. --district Tumakuru --district Tumkur")

    d = PinDirectory.from_india_post_csv(args.csv, districts=args.district, states=args.state)
    if not d.pins:
        sys.exit("No rows matched. Check the district spelling in the CSV (try --district TUMKUR).")
    d.save(args.out)
    n_villages = sum(len(p.villages) for p in d.pins.values())
    print(f"Wrote {args.out}: {len(d.pins)} PIN codes, {n_villages} post-office/village names.")
    sample = next(iter(d.pins.values()))
    print(f"Example {sample.pin}: {', '.join(sample.villages[:8])}")
    print(f"Keyterms for {sample.pin}: {len(d.keyterms(sample.pin, 'kn-IN'))} (limit 200)")


if __name__ == "__main__":
    main()
