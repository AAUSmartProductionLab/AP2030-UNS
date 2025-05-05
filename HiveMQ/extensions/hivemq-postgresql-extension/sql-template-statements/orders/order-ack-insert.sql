INSERT INTO order_ack (
    uuid,
    timestamp_utc
)
VALUES (
    CAST(json_extract_path_text(${mqtt-payload-utf8}::json, 'UUID') AS UUID),
    NOW()
);