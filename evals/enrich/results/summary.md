# Enrich model eval — summary

brand-examples nudge: **on** (off = model only; on = DB brand index in play)

Score = passing cases / total (clusters: groups converged + canonical-matched).

| model | api_model | time s | in tok | out tok | cost $ | identity_cluster | note |
|---|---|---|---|---|---|---|---|
| haiku | claude-haiku-4-5-20251001 | 9 | 4,861 | 1,123 | 0.0084 | 2/5 (3 conv) |  |
| deepseek | deepseek/deepseek-v4-flash | 45 | 5,501 | 2,937 | 0.0010 | 3/5 (4 conv) |  |
