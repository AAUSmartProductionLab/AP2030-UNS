INSERT INTO stoppering_state (
    state,
    timestamp_utc,
    process_queue
)
VALUES (
    json_extract_path_text(${mqtt-payload-utf8}::json, 'State'),
    CAST(json_extract_path_text(${mqtt-payload-utf8}::json, 'TimeStamp') AS TIMESTAMPTZ),
    json_extract_path_text(${mqtt-payload-utf8}::json, 'ProcessQueue')::JSONB
);