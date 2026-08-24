# Enrich model eval — summary

brand-examples nudge: **off** (off = model only; on = DB brand index in play)

Score = passing cases / total (clusters: groups converged + canonical-matched).

| model | api_model | time s | in tok | out tok | cost $ | gold_dispensary | note |
|---|---|---|---|---|---|---|---|
| haiku | claude-haiku-4-5-20251001 | 26 | 27,345 | 6,048 | 0.0461 | 105/108 |  |
| deepseek | deepseek/deepseek-v4-flash | 1 | 0 | 0 | 0.0000 | 11/108 | no tokens — bad slug? |
