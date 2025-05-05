CREATE TABLE IF NOT EXISTS order_data (
    id SERIAL PRIMARY KEY,
    uuid UUID NOT NULL,
    product_id VARCHAR(50) NOT NULL,
    format VARCHAR(50) NOT NULL,
    units INTEGER NOT NULL,
    ipcw INTEGER NOT NULL,
    ipci INTEGER NOT NULL,
    qc_samples INTEGER NOT NULL,
    timestamp_utc TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_order_uuid ON order_data(uuid);
CREATE INDEX IF NOT EXISTS idx_order_product_id ON order_data(product_id);