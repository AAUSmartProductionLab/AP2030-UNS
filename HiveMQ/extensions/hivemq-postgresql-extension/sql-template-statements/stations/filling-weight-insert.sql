INSERT INTO filling_weight (
    weight,
    timestamp_utc,
    uuid
)
VALUES (
    CAST(json_extract_path_text(${mqtt-payload-utf8}::json, 'Weight') AS FLOAT),
    CAST(json_extract_path_text(${mqtt-payload-utf8}::json, 'TimeStamp') AS TIMESTAMPTZ),
    json_extract_path_text(${mqtt-payload-utf8}::json, 'Uuid')::UUID
);