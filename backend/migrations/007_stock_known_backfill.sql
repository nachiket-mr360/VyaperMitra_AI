-- Idempotent. For shops that already applied 006 before the unknown-stock UPDATE.
-- Does not change current_stock, sales, or movements.
UPDATE products
SET stock_known = 0
WHERE stock_known = 1
  AND current_stock = 0
  AND NOT EXISTS (
      SELECT 1 FROM stock_movements m WHERE m.product_id = products.id
  );
