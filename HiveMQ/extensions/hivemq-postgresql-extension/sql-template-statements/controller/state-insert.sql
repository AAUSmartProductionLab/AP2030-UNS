INSERT INTO controller_state (
    state,
    timestamp_utc
)
VALUES (
    json_extract_path_text(${mqtt-payload-utf8}::json, 'State'),
    CAST(json_extract_path_text(${mqtt-payload-utf8}::json, 'TimeStamp') AS TIMESTAMPTZ)
);