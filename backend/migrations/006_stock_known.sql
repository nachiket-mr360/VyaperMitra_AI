PRAGMA foreign_keys = ON;

-- Additive. Does not rewrite current_stock.
-- DEFAULT 1 keeps counted balances. Rows with 0 qty and no movements are not counted.
ALTER TABLE products ADD COLUMN stock_known INTEGER NOT NULL DEFAULT 1 CHECK (stock_known IN (0, 1));

UPDATE products
SET stock_known = 0
WHERE current_stock = 0
  AND NOT EXISTS (
      SELECT 1 FROM stock_movements m WHERE m.product_id = products.id
  );
