"""
llm_match_products.py — Use Claude to resolve ambiguous listing→product matches.

For each unmatched listing that has at least one candidate above --min-score,
asks Claude whether the listing is the same product as any candidate. Confirmed
matches are linked; unconfirmed are left for manual review in the UI.

Usage:
    python scripts/llm_match_products.py [--min-score 0.4] [--top-n 5] [--dry-run]

    ANTHROPIC_API_KEY must be set in the environment or .env.
    DATABASE_URL must be set in the environment or .env.
"""

import argparse
import os
import sys
import time
import json
from datetime import datetime, timezone

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    print("psycopg2-binary required: pip install psycopg2-binary", file=sys.stderr)
    sys.exit(1)

try:
    import anthropic
except ImportError:
    print("anthropic required: pip install anthropic", file=sys.stderr)
    sys.exit(1)


SYSTEM_PROMPT = """\
You are helping deduplicate a cannabis product catalog. You will be given a scraped
listing and a list of candidate products already in the database.

Your job: decide whether the scraped listing is the SAME product as any candidate.
"Same product" means a customer buying either one gets the exact same item —
same strain/flavor, same brand, same size/weight, same format.

Different strains, flavors, or colors are NOT the same product, even if names are similar.
Different weights/sizes are NOT the same product.

Respond with JSON only — no explanation outside the JSON:
{"match": <1-based index of the matching candidate, or null if no match>, "reason": "<one sentence>"}
"""

def load_env(project_root: str) -> None:
    env_path = os.path.join(project_root, ".env")
    if not os.path.isfile(env_path):
        return
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            if key not in os.environ:
                os.environ[key] = val


def parse_args():
    p = argparse.ArgumentParser(description="LLM-assisted listing→product matching")
    p.add_argument("--min-score", type=float, default=0.4,
                   help="Min similarity score for a candidate to be sent to Claude (default: 0.4)")
    p.add_argument("--top-n", type=int, default=5,
                   help="Max candidates per listing to show Claude (default: 5)")
    p.add_argument("--model", default="claude-haiku-4-5-20251001",
                   help="Claude model to use (default: claude-haiku-4-5-20251001)")
    p.add_argument("--delay", type=float, default=0.3,
                   help="Seconds between API calls (default: 0.3)")
    p.add_argument("--dry-run", action="store_true",
                   help="Print decisions without writing to DB")
    return p.parse_args()


def build_prompt(listing: dict, candidates: list[dict]) -> str:
    lines = [
        "SCRAPED LISTING:",
        f"  Name:     {listing['scraped_name']}",
        f"  Brand:    {listing['scraped_brand'] or '(none)'}",
        f"  Variant:  {listing['variant'] or '(none)'}",
        f"  Category: {listing['scraped_category'] or '(none)'}",
        "",
        "CANDIDATES:",
    ]
    for i, c in enumerate(candidates, 1):
        p = c["product"]
        lines.append(
            f"  {i}. \"{p.name}\"  brand={p.brand or '(none)'}  "
            f"variant={p.variant or '(none)'}  category={p.category}  "
            f"score={c['score']:.3f}"
        )
    return "\n".join(lines)


def ask_claude(client: anthropic.Anthropic, model: str, prompt: str) -> tuple[dict, int, int]:
    """Returns (result_dict, input_tokens, output_tokens)."""
    msg = client.messages.create(
        model=model,
        max_tokens=150,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = msg.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw), msg.usage.input_tokens, msg.usage.output_tokens


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def main():
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    load_env(project_root)

    args = parse_args()

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("Error: ANTHROPIC_API_KEY not set", file=sys.stderr)
        sys.exit(1)

    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("Error: DATABASE_URL not set", file=sys.stderr)
        sys.exit(1)

    conn = psycopg2.connect(db_url)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("SELECT alias, canonical_brand FROM brand_aliases")
    brand_aliases: dict[str, str] = {r["alias"]: r["canonical_brand"] for r in cur.fetchall()}
    print(f"  {len(brand_aliases)} brand aliases loaded")

    cur.execute("SELECT id, name, brand, variant, category FROM products")
    products = cur.fetchall()
    print(f"  {len(products)} existing products loaded")

    cur.execute("""
        SELECT l.id, l.scraped_name, l.scraped_brand, l.variant,
               l.scraped_category, d.slug
        FROM listings l
        JOIN dispensaries d ON d.id = l.dispensary_id
        WHERE l.product_id IS NULL
          AND l.scraped_name IS NOT NULL
    """)
    unmatched = cur.fetchall()
    print(f"  {len(unmatched)} unmatched listings\n")

    sys.path.insert(0, os.path.join(project_root, "services"))
    from matching import score_candidates

    class _Row:
        def __init__(self, r):
            self.id       = r["id"]
            self.name     = r["name"]
            self.brand    = r["brand"]
            self.variant  = r["variant"]
            self.category = r["category"]

    product_objs = [_Row(p) for p in products]
    client = anthropic.Anthropic(api_key=api_key)

    auto_matched    = 0
    no_candidate    = 0
    llm_no_match    = 0
    parse_errors    = 0
    total_in_tok    = 0
    total_out_tok   = 0
    now = utcnow()

    for listing in unmatched:
        scraped_name     = (listing["scraped_name"]     or "").strip()
        scraped_brand    = (listing["scraped_brand"]    or "").strip()
        variant          = (listing["variant"]          or "").strip()
        scraped_category = (listing["scraped_category"] or "").strip()

        candidates = score_candidates(
            scraped_name=scraped_name,
            scraped_brand=scraped_brand,
            scraped_variant=variant,
            scraped_category="",  # match UI behavior: brand+variant pool, no category filter
            products=product_objs,
            brand_aliases=brand_aliases,
            top_n=args.top_n,
        )

        candidates = [c for c in candidates if c["score"] >= args.min_score]

        if not candidates:
            no_candidate += 1
            continue

        prompt = build_prompt(listing, candidates)
        label = f"name={scraped_name!r}  brand={scraped_brand or '?'}  variant={variant or '-'}"
        print(f"  ? {label}  [{len(candidates)} candidate(s)]", end="", flush=True)

        try:
            result, in_tok, out_tok = ask_claude(client, args.model, prompt)
        except Exception as e:
            print(f"  ERROR: {e}")
            parse_errors += 1
            time.sleep(args.delay)
            continue

        total_in_tok  += in_tok
        total_out_tok += out_tok

        match_idx = result.get("match")
        reason    = result.get("reason", "")

        if match_idx is None:
            llm_no_match += 1
            print(f"\r  NO MATCH  {label}  — {reason}  [{in_tok}in/{out_tok}out]")
        else:
            try:
                chosen = candidates[int(match_idx) - 1]
            except (IndexError, TypeError, ValueError):
                print(f"\r  BAD IDX  {label}  got match={match_idx!r}")
                parse_errors += 1
                time.sleep(args.delay)
                continue

            product_id = str(chosen["product"].id)
            print(f"\r  {'[DRY] ' if args.dry_run else ''}MATCH  {label}  "
                  f"→ \"{chosen['product'].name}\"  [{reason}]  [{in_tok}in/{out_tok}out]")

            if not args.dry_run:
                cur.execute(
                    "UPDATE listings SET product_id = %s, updated_at = %s WHERE id = %s",
                    (product_id, now, str(listing["id"])),
                )

            auto_matched += 1

        time.sleep(args.delay)

    if not args.dry_run:
        conn.commit()
    conn.close()

    print(f"\n{'[DRY RUN] ' if args.dry_run else ''}Done.")
    print(f"  Matched        : {auto_matched}")
    print(f"  No match (LLM) : {llm_no_match}")
    print(f"  No candidates  : {no_candidate}")
    print(f"  Errors         : {parse_errors}")
    api_calls = auto_matched + llm_no_match + parse_errors
    if api_calls:
        print(f"  Tokens         : {total_in_tok} in / {total_out_tok} out  ({api_calls} calls, ~{total_in_tok//api_calls} in/call avg)")


if __name__ == "__main__":
    main()
