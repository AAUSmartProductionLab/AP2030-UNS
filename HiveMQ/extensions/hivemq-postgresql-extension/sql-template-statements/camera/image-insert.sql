INSERT INTO qc_image (uuid, timestamp_utc, image_base64, image_format)
VALUES (
    CAST(json_extract_path_text(${mqtt-payload-utf8}::json, 'Uuid') AS UUID),
    CAST(json_extract_path_text(${mqtt-payload-utf8}::json, 'TimeStamp') AS TIMESTAMPTZ),
    (${mqtt-payload-utf8}::JSONB ->> 'Image'),
    (${mqtt-payload-utf8}::JSONB ->> 'Format')
);