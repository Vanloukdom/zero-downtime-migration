-- EXPAND : on ajoute sans rien casser. Colonnes nullables = ALTER instantané,
-- aucune réécriture de table, l'ancienne version continue de fonctionner.
ALTER TABLE customers ADD COLUMN IF NOT EXISTS first_name TEXT;
ALTER TABLE customers ADD COLUMN IF NOT EXISTS last_name  TEXT;

-- Pendant la transition, v1 (écrit full_name) et v2 (écrit first/last) cohabitent.
-- Ce trigger garde les deux représentations synchronisées, quelle que soit la version qui écrit.
CREATE OR REPLACE FUNCTION sync_customer_names() RETURNS trigger AS $$
DECLARE
    first_part TEXT;
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.first_name IS NULL AND NEW.full_name IS NOT NULL THEN
            first_part := split_part(NEW.full_name, ' ', 1);           -- écrit par v1
            NEW.first_name := first_part;
            NEW.last_name  := NULLIF(substr(NEW.full_name, length(first_part) + 2), '');
        ELSIF NEW.full_name IS NULL THEN                               -- écrit par contract
            NEW.full_name := trim(concat_ws(' ', NEW.first_name, NEW.last_name));
        END IF;
        RETURN NEW;
    END IF;

    IF NEW.full_name IS DISTINCT FROM OLD.full_name
       AND NEW.first_name IS NOT DISTINCT FROM OLD.first_name
       AND NEW.last_name  IS NOT DISTINCT FROM OLD.last_name THEN
        -- v1 a modifié full_name → on recalcule first/last
        first_part := split_part(NEW.full_name, ' ', 1);
        NEW.first_name := first_part;
        NEW.last_name  := NULLIF(substr(NEW.full_name, length(first_part) + 2), '');
    ELSIF NEW.full_name IS NOT DISTINCT FROM OLD.full_name
          AND (NEW.first_name IS DISTINCT FROM OLD.first_name
               OR NEW.last_name IS DISTINCT FROM OLD.last_name) THEN
        -- v2 a modifié first/last → on recalcule full_name
        NEW.full_name := trim(concat_ws(' ', NEW.first_name, NEW.last_name));
    ELSIF NEW.first_name IS NULL AND NEW.full_name IS NOT NULL THEN
        -- backfill d'une ligne historique
        first_part := split_part(NEW.full_name, ' ', 1);
        NEW.first_name := first_part;
        NEW.last_name  := NULLIF(substr(NEW.full_name, length(first_part) + 2), '');
    END IF;
    RETURN NEW;
END $$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS customers_sync_names ON customers;
CREATE TRIGGER customers_sync_names BEFORE INSERT OR UPDATE ON customers
    FOR EACH ROW EXECUTE FUNCTION sync_customer_names();
