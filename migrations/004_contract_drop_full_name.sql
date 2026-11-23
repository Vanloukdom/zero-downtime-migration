-- CONTRACT : à appliquer UNIQUEMENT quand plus aucun pod v1 ne tourne
-- (plusieurs releases après l'expand). C'est la seule étape irréversible.
DROP TRIGGER IF EXISTS customers_sync_names ON customers;
DROP FUNCTION IF EXISTS sync_customer_names();
ALTER TABLE customers ALTER COLUMN first_name SET NOT NULL;
ALTER TABLE customers DROP COLUMN IF EXISTS full_name;
