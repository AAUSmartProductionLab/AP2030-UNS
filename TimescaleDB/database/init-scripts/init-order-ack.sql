CREATE TABLE IF NOT EXISTS order_ack (
    id SERIAL PRIMARY KEY,
    uuid UUID NOT NULL,
    timestamp_utc TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Create index for faster lookups
CREATE INDEX IF NOT EXISTS idx_uuid_data_uuid ON uuid_data(uuid);