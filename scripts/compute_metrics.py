#!/usr/bin/env python3
"""Compute platform-specific CSV metrics; undefined ratios are null."""
import argparse
import csv
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import re
import sys


def read_inputs(sources):
    rows = []
    for file_index, source in enumerate(sources, start=1):
        with source.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            fields = reader.fieldnames or []
            common = {"row_id", "platform", "period", "post_id", "likes", "comments", "clicks", "spend_cny"}
            if len(fields) != len(set(fields)) or not common.issubset(fields):
                raise ValueError(f"Missing or duplicate common headers in {source}")
            variants = [("impressions", "saves"), ("views", "shares")]
            available = [(denom, extra) for denom, extra in variants if {denom, extra}.issubset(fields)]
            if len(available) != 1:
                raise ValueError(f"Ambiguous or missing exposure/interaction headers in {source}")
            denominator, extra = available[0]
            label = source.name
            if sum(p.name == source.name for p in sources) > 1:
                label = f"input{file_index}-{source.name}"
            for raw in reader:
                if None in raw or any(value is None for value in raw.values()):
                    raise ValueError(f"Malformed CSV row ending at {source}:{reader.line_num}")
                rows.append({"raw": raw, "source_id": f"{raw['row_id']}@{label}:{reader.line_num}",
                             "row_number": reader.line_num, "denominator_name": denominator,
                             "extra": extra})
    return rows


def ratio(numerator, denominator):
    return float(numerator / denominator) if denominator else None


def compute(sources, period=None):
    rows = read_inputs(sources)
    selected = []
    excluded = []
    for row in rows:
        if period is not None and row["raw"]["period"] != period:
            excluded.append({"source_id": row["source_id"], "row_id": row["raw"]["row_id"],
                             "period": row["raw"]["period"], "reason": "outside_requested_period"})
        else:
            selected.append(row)
    seen, unique, duplicates = {}, [], []
    for row in selected:
        signature = tuple(sorted(row["raw"].items()))
        if signature in seen:
            duplicates.append({"kept_source_id": seen[signature]["source_id"],
                               "duplicate_source_id": row["source_id"]})
        else:
            seen[signature] = row
            unique.append(row)
    groups = {}
    for row in unique:
        raw = row["raw"]
        groups.setdefault((raw["platform"], raw["period"], raw["row_id"]), []).append(row)
    conflicts, conflict_keys = [], set()
    for key, group in groups.items():
        if len(group) > 1:
            conflicts.append({"platform": key[0], "period": key[1], "row_id": key[2],
                              "source_ids": [r["source_id"] for r in group],
                              "rows": [{"source_id": r["source_id"], "values": r["raw"]} for r in group]})
            conflict_keys.add(key)
    issues, post_rows, buckets = [], [], {}
    for row in unique:
        raw = row["raw"]
        if (raw["platform"], raw["period"], raw["row_id"]) in conflict_keys:
            continue
        valid, values = True, {}
        for field in (row["denominator_name"], "likes", "comments", row["extra"], "clicks", "spend_cny"):
            try:
                value = Decimal(raw[field].strip())
                if not value.is_finite() or value < 0 or (field != "spend_cny" and value != value.to_integral_value()):
                    raise InvalidOperation
                values[field] = value
            except InvalidOperation:
                valid = False
                issues.append({"source_id": row["source_id"], "row_id": raw["row_id"],
                               "row_number": row["row_number"], "code": "invalid_number", "field": field,
                               "value": raw[field]})
        if not raw["row_id"].strip() or not raw["platform"].strip():
            valid = False
            issues.append({"source_id": row["source_id"], "row_id": raw["row_id"],
                           "row_number": row["row_number"], "code": "missing_identity"})
        if not valid:
            continue
        denominator = values[row["denominator_name"]]
        interactions = values["likes"] + values["comments"] + values[row["extra"]]
        clicks, spend = values["clicks"], values["spend_cny"]
        definition = "likes+comments+" + row["extra"]
        metrics = {"platform": raw["platform"], "period": raw["period"], "denominator_name": row["denominator_name"],
                   "denominator": int(denominator), "interaction_definition": definition,
                   "interactions": int(interactions), "clicks": int(clicks), "spend_cny": float(spend),
                   "engagement_rate": ratio(interactions, denominator), "ctr": ratio(clicks, denominator),
                   "cpc": ratio(spend, clicks)}
        post_rows.append({"row_id": raw["row_id"], "source_id": row["source_id"],
                          "period": raw["period"], "post_id": raw["post_id"], **metrics})
        if denominator == 0 or clicks == 0:
            issues.append({"source_id": row["source_id"], "row_id": raw["row_id"],
                           "row_number": row["row_number"], "code": "zero_denominator",
                           "fields": (["engagement_rate", "ctr"] if denominator == 0 else []) + (["cpc"] if clicks == 0 else [])})
        # A platform with two different definitions remains two separate buckets.
        key = (raw["platform"], raw["period"], row["denominator_name"], definition)
        bucket = buckets.setdefault(key, {"platform": raw["platform"], "period": raw["period"], "denominator_name": row["denominator_name"],
                                           "interaction_definition": definition, "denominator": Decimal(0),
                                           "interactions": Decimal(0), "clicks": Decimal(0), "spend_cny": Decimal(0),
                                           "source_ids": []})
        for field, value in [("denominator", denominator), ("interactions", interactions), ("clicks", clicks), ("spend_cny", spend)]:
            bucket[field] += value
        bucket["source_ids"].append(row["source_id"])
    platforms, total_clicks, total_spend = [], Decimal(0), Decimal(0)
    for bucket in buckets.values():
        total_clicks += bucket["clicks"]
        total_spend += bucket["spend_cny"]
        platform = dict(bucket)
        platform.update(engagement_rate=ratio(bucket["interactions"], bucket["denominator"]),
                        ctr=ratio(bucket["clicks"], bucket["denominator"]), cpc=ratio(bucket["spend_cny"], bucket["clicks"]))
        for field in ("denominator", "interactions", "clicks"):
            platform[field] = int(bucket[field])
        platform["spend_cny"] = float(bucket["spend_cny"])
        platforms.append(platform)
    return {"skill": "social-metrics-report", "source_ids": [r["source_id"] for r in rows],
            "platforms": platforms, "post_rows": post_rows,
            "data_quality": {"input_rows": len(rows), "included_input_rows": len(selected),
                             "unique_rows": len(unique), "excluded_rows": excluded,
                             "exact_duplicates": duplicates, "conflicts": conflicts, "issues": issues},
            "combined_financials": {"clicks": int(total_clicks), "spend_cny": float(total_spend),
                                    "cpc": ratio(total_spend, total_clicks)}}


def write_outputs(sources, out, result):
    targets = [out / name for name in ("result.json", "metrics.csv")]
    input_paths = {source.resolve() for source in sources}
    for target in targets:
        if target.resolve() in input_paths or target.exists() or target.is_symlink():
            raise ValueError(f"Refusing to overwrite source or existing output: {target}")
    out.mkdir(parents=True, exist_ok=True)
    fields = ["platform", "period", "denominator_name", "denominator", "interaction_definition", "interactions", "clicks",
              "spend_cny", "engagement_rate", "ctr", "cpc", "source_ids"]
    with targets[1].open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for platform in result["platforms"]:
            writer.writerow({**platform, "source_ids": ";".join(platform["source_ids"])})
    with targets[0].open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, action="append", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--period", help="Include only this YYYY-MM; otherwise keep periods in separate buckets")
    args = parser.parse_args()
    try:
        if args.period and (not re.fullmatch(r"\d{4}-\d{2}", args.period) or not 1 <= int(args.period[-2:]) <= 12):
            raise ValueError("--period must use YYYY-MM with a valid month")
        result = compute(args.input, args.period)
        write_outputs(args.input, args.out, result)
    except (OSError, ValueError, UnicodeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    print(args.out.resolve() / "result.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
