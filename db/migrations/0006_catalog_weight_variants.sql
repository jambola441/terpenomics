-- Bootstrap catalog entries in weight-measured categories show the package total
-- alone: "3.5g", not "7pk 3.5g" (catalog_bootstrap.py: the subtype already says
-- pack). New proposals are written that way. This relabels the entries pushed before,
-- which a re-push leaves alone because it never rewrites an entry's identity fields.
--
-- Only the label changes, never the size, and matching compares sizes as numbers
-- (sizes.same_size). Only labels of exactly that shape are touched, so a variant a
-- person typed in is left as it is. The weight categories are taxonomy.py's.
-- Idempotent.
UPDATE brand_catalog_entries
SET variant = regexp_replace(variant, '^[0-9]+pk\s+', '')
WHERE source = 'listings_bootstrap'
  AND category IN ('flower', 'preroll', 'vaporizers', 'concentrate')
  AND variant ~ '^[0-9]+pk\s+[0-9.]+(g|mg)$';
