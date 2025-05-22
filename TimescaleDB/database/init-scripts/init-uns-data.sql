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

CREATE TABLE IF NOT EXISTS filling_state (
    state VARCHAR(255) NOT NULL,
    timestamp_utc TIMESTAMPTZ NOT NULL,
    process_queue JSONB NOT NULL
);

CREATE TABLE IF NOT EXISTS stoppering_state (
    state VARCHAR(255) NOT NULL,
    timestamp_utc TIMESTAMPTZ NOT NULL,
    process_queue JSONB NOT NULL
);

CREATE TABLE IF NOT EXISTS load_state (
    state VARCHAR(255) NOT NULL,
    timestamp_utc TIMESTAMPTZ NOT NULL,
    process_queue JSONB NOT NULL
);

CREATE TABLE IF NOT EXISTS unload_state (
    state VARCHAR(255) NOT NULL,
    timestamp_utc TIMESTAMPTZ NOT NULL,
    process_queue JSONB NOT NULL
);

CREATE TABLE IF NOT EXISTS camera_state (
    state VARCHAR(255) NOT NULL,
    timestamp_utc TIMESTAMPTZ NOT NULL,
    process_queue JSONB NOT NULL
);

CREATE TABLE IF NOT EXISTS planar_state (
    id SERIAL PRIMARY KEY,
    state VARCHAR(255) NOT NULL,
    timestamp_utc TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS configured_stations_log (
    log_id SERIAL PRIMARY KEY,
    configuration_id INTEGER NOT NULL, -- New column
    station_id INTEGER NOT NULL,
    name VARCHAR(255) NOT NULL,
    approach_pos_x REAL,
    approach_pos_y REAL,
    approach_pos_z REAL,
    process_pos_x REAL,
    process_pos_y REAL,
    process_pos_z REAL,
    config_received_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE SEQUENCE IF NOT EXISTS limit_configuration_id_seq START 1;
CREATE SEQUENCE IF NOT EXISTS station_configuration_id_seq START 1;

CREATE OR REPLACE FUNCTION log_station_configurations(payload JSONB)
RETURNS VOID AS $$
DECLARE
    station_data JSONB;
    next_config_id INTEGER;
BEGIN
    -- Get the next configuration ID from the sequence
    SELECT nextval('station_configuration_id_seq') INTO next_config_id;

    FOR station_data IN SELECT * FROM jsonb_array_elements(payload->'Stations')
    LOOP
        INSERT INTO configured_stations_log (
            configuration_id, -- Include the new ID
            station_id,
            name,
            approach_pos_x,
            approach_pos_y,
            approach_pos_z,
            process_pos_x,
            process_pos_y,
            process_pos_z
        )
        VALUES (
            next_config_id, -- Use the same ID for all stations in this batch
            (station_data->>'StationId')::INTEGER,
            station_data->>'Name',
            (station_data->'Approach Position'->>0)::REAL, -- JSON arrays are 0-indexed
            (station_data->'Approach Position'->>1)::REAL,
            (station_data->'Approach Position'->>2)::REAL,
            (station_data->'Process Position'->>0)::REAL,
            (station_data->'Process Position'->>1)::REAL,
            (station_data->'Process Position'->>2)::REAL
        );
    END LOOP;
END;
$$ LANGUAGE plpgsql;

-- Create table for configured limits log
CREATE TABLE IF NOT EXISTS configured_limits_log (
    log_id SERIAL PRIMARY KEY,
    configuration_id INTEGER NOT NULL,
    max_speed_x REAL,
    max_speed_y REAL,
    max_speed_rz REAL,
    max_accel_x REAL,
    max_accel_y REAL,
    max_accel_rz REAL,
    config_received_at TIMESTAMPTZ DEFAULT NOW()
);

-- Function to log planar limits
CREATE OR REPLACE FUNCTION log_planar_limits(payload JSONB)
RETURNS VOID AS $$
DECLARE
    next_config_id INTEGER;
BEGIN
    -- Get the next configuration ID from the sequence
    SELECT nextval('limit_configuration_id_seq') INTO next_config_id;

    INSERT INTO configured_limits_log (
        configuration_id,
        max_speed_x,
        max_speed_y,
        max_speed_rz,
        max_accel_x,
        max_accel_y,
        max_accel_rz
    )
    VALUES (
        next_config_id,
        (payload->>'maxSpeedX')::REAL,
        (payload->>'maxSpeedY')::REAL,
        (payload->>'maxSpeedRz')::REAL,
        (payload->>'maxAccelX')::REAL,
        (payload->>'maxAccelY')::REAL,
        (payload->>'maxAccelRz')::REAL
    );
END;
$$ LANGUAGE plpgsql;

-- Create indexes for all tables
CREATE INDEX IF NOT EXISTS idx_order_data_uuid ON order_data(uuid);
CREATE INDEX IF NOT EXISTS idx_order_data_product_id ON order_data(product_id);
CREATE INDEX IF NOT EXISTS idx_order_ack_uuid ON order_ack(uuid);
CREATE INDEX IF NOT EXISTS idx_order_done_uuid ON order_done(uuid);
CREATE INDEX IF NOT EXISTS idx_planar_state_timestamp_utc ON planar_state(timestamp_utc);
CREATE INDEX IF NOT EXISTS idx_configured_stations_log_config_id ON configured_stations_log(configuration_id);
CREATE INDEX IF NOT EXISTS idx_configured_stations_log_received_at ON configured_stations_log(config_received_at);
CREATE INDEX IF NOT EXISTS idx_configured_limits_log_config_id ON configured_limits_log(configuration_id);
CREATE INDEX IF NOT EXISTS idx_configured_limits_log_received_at ON configured_limits_log(config_received_at);



-- Now use a DO block to create multiple Xbot tables
DO $$
DECLARE
    i INTEGER;
    table_name TEXT;
BEGIN
    -- Loop to create tables for Xbot1 through Xbot10
    FOR i IN 1..10 LOOP
        table_name := 'xbot' || i || '_state';
        
        EXECUTE format('
            CREATE TABLE IF NOT EXISTS %I (
                id SERIAL PRIMARY KEY,
                station_id INTEGER,
                state VARCHAR(50),
                timestamp_utc TIMESTAMP NOT NULL,
                uuid UUID
            )', table_name);
            
        -- Create index for each table
        EXECUTE format('
            CREATE INDEX IF NOT EXISTS idx_%I_timestamp_utc ON %I(timestamp_utc)
        ', table_name, table_name);
    END LOOP;
END
$$;

-- This function can insert data from a given topic into the appropriate Xbot state table
CREATE OR REPLACE FUNCTION insert_xbot_state(
    topic TEXT,
    station_id INTEGER,
    state TEXT,
    timestamp_value TIMESTAMP,
    uuid UUID
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
            timestamp_utc,
            uuid
        ) VALUES ($1, $2, $3, $4)',
        table_name)
    USING station_id, state, timestamp_value, uuid;
END;
$$ LANGUAGE plpgsql;