-- Create order_data table
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

-- Create order_ack table
CREATE TABLE IF NOT EXISTS order_ack (
    id SERIAL PRIMARY KEY,
    uuid UUID NOT NULL,
    timestamp_utc TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Create order_done table
CREATE TABLE IF NOT EXISTS order_done (
    id SERIAL PRIMARY KEY,
    uuid UUID NOT NULL,
    timestamp_utc TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for all tables
-- CREATE INDEX IF NOT EXISTS idx_order_data_uuid ON order_data(uuid);
-- CREATE INDEX IF NOT EXISTS idx_order_data_product_id ON order_data(product_id);
-- CREATE INDEX IF NOT EXISTS idx_order_ack_uuid ON order_ack(uuid);
-- CREATE INDEX IF NOT EXISTS idx_order_done_uuid ON order_done(uuid);