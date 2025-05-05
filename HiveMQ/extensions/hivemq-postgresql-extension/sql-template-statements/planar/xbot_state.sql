SELECT insert_xbot_state(
    ${mqtt-topic},
    CAST(json_extract_path_text(${mqtt-payload-utf8}::json, 'StationId') AS INTEGER),
    json_extract_path_text(${mqtt-payload-utf8}::json, 'State'),
    CAST(json_extract_path_text(${mqtt-payload-utf8}::json, 'TimeStamp') AS TIMESTAMP),
    NULLIF(json_extract_path_text(${mqtt-payload-utf8}::json, 'CommandUuid'), 'null')::UUID
);