# Enrich model eval — summary

brand-examples nudge: **off** (off = model only; on = DB brand index in play)

catalog hint: **off** (on = the brand's catalog is in the pass-B prompt)

classifier: **jev** (jev = Jev decides category/subtype, Haiku the rest; llm = Haiku's pass A for every row)

Score = passing cases / total (clusters: groups converged + canonical-matched).

| model | api_model | time s | in tok | out tok | of which reasoning | cost $ | categorization | common_error | gold_dispensary | identity_cluster | gold_dispensary | gold_dispensary | gold_dispensary | identity_cluster | variant_fix | note |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| haiku-or | anthropic/claude-haiku-4.5 | 71 | 29,283 | 5,211 | 0 | 0.0857 | 10/12 | 7/7 | 55/56 | 4/6 (4 conv) | 44/48 | 105/108 | 49/50 | 4/5 (4 conv) | 9/10 |  |
| luna | openai/gpt-6-luna | 57 | 24,524 | 4,598 | 1,391 | 0.0357 | 10/12 | 7/7 | 56/56 | 4/6 (4 conv) | 45/48 | 106/108 | 49/50 | 4/5 (4 conv) | 9/10 |  |
