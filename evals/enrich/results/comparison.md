# Enrich model comparison

Models: haiku, deepseek


## identity_cluster — identity_clusters.json

_Each case is a GROUP of real-world listings of the SAME physical product, worded differently across dispensaries (naming, size notation, ALLCAPS, format words). After enrichment every member must land on the SAME identity tuple (the fields in expect_same), and match `canonical` if given. Brand is held constant so this isolates what enrichment controls (category, subtype, strain, variant). This is the cross-dispensary 'same product → same key' test._

| group | canonical | haiku | deepseek |
|---|---|---|---|
| clust-blue-dream-eighth | category=flower, subtype=flower, strain=Blue Dream, variant=3.5g | ✓ converged + canonical | ✓ converged + canonical |
| clust-gelato-cart | category=vaporizers, subtype=cart, strain=Gelato, variant=0.5g | ✓ converged + canonical | ✓ converged + canonical |
| clust-watermelon-gummy | category=edible, subtype=gummy, strain=Watermelon, variant=100mg | ✗ split: strain=[Watermelon|Watermelon Lemonade] | ✓ converged + canonical |
| clust-gmo-preroll | category=preroll, subtype=single, strain=GMO, variant=1g | ~ converged, off-canonical (strain) | ~ converged, off-canonical (strain) |
| clust-ruby-elderberry-sage | category=edible, subtype=gummy, strain=Elderberry Sage, product_line=Night Cap, variant=100mg | ✗ split: product_line=[|Night Cap|Nightcap] | ✗ split: product_line=[|Night Cap|Nightcap] |
