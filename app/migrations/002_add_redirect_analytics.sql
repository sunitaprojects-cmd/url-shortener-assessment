ALTER TABLE url_mappings
    ADD COLUMN IF NOT EXISTS redirect_count BIGINT;

UPDATE url_mappings
SET redirect_count = 0
WHERE redirect_count IS NULL;

ALTER TABLE url_mappings
    ALTER COLUMN redirect_count SET DEFAULT 0,
    ALTER COLUMN redirect_count SET NOT NULL;

ALTER TABLE url_mappings
    ADD COLUMN IF NOT EXISTS last_accessed_at TIMESTAMPTZ;

ALTER TABLE url_mappings
    ALTER COLUMN last_accessed_at DROP DEFAULT,
    ALTER COLUMN last_accessed_at DROP NOT NULL;
