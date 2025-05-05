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
CREATE INDEX IF NOT EXISTS idx_order_data_uuid ON order_data(uuid);
CREATE INDEX IF NOT EXISTS idx_order_data_product_id ON order_data(product_id);
CREATE INDEX IF NOT EXISTS idx_order_ack_uuid ON order_ack(uuid);
CREATE INDEX IF NOT EXISTS idx_order_done_uuid ON order_done(uuid);


-- Now use a DO block to create multiple Xbot tables
DO $$
DECLARE
    i INTEGER;
    table_name TEXT;
BEGIN
    -- Loop to create tables for Xbot1 through Xbot5
    FOR i IN 1..10 LOOP
        table_name := 'xbot' || i || '_state';
        
        EXECUTE format('
            CREATE TABLE IF NOT EXISTS %I (
                id SERIAL PRIMARY KEY,
                station_id INTEGER,
                state VARCHAR(50),
                timestamp TIMESTAMP,
                command_uuid UUID,
                received_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )', table_name);
            
        -- Create index for each table
        EXECUTE format('
            CREATE INDEX IF NOT EXISTS idx_%I_timestamp ON %I(timestamp)
        ', table_name, table_name);
    END LOOP;
END
$$;

CREATE OR REPLACE FUNCTION insert_xbot_state(
    topic TEXT,
    station_id INTEGER,
    state TEXT,
    timestamp_value TIMESTAMP,
    command_uuid UUID
) RETURNS VOID AS $$
DECLARE
    xbot_id TEXT;
    table_name TEXT;
BEGIN
    -- Extract Xbot ID from topic
    xbot_id := substring(topic FROM 'NN/Nybrovej/InnoLab/Planar/([^/]+)/DATA/State');
    
    -- Convert to lowercase and remove any non-alphanumeric characters for safety
    table_name := lower(regexp_replace(xbot_id, '[^a-zA-Z0-9]', '', 'g')) || '_state';
    
    -- Execute dynamic SQL to insert into the appropriate table
    EXECUTE format('
        INSERT INTO %I (
            station_id,
            state,
            timestamp,
            command_uuid,
            timestamp_utc
        ) VALUES ($1, $2, $3, $4, NOW())',
        table_name)
    USING station_id, state, timestamp_value, command_uuid;
END;
$$ LANGUAGE plpgsql;