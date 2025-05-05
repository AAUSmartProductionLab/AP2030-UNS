INSERT INTO order_data (
    uuid,
    product_id,
    format,
    units,
    ipcw,
    ipci,
    qc_samples,
    timestamp_utc
)
VALUES (
    CAST(json_extract_path_text(${mqtt-payload-utf8}::json, 'UUID') AS UUID),
    json_extract_path_text(${mqtt-payload-utf8}::json, 'ProductId'),
    json_extract_path_text(${mqtt-payload-utf8}::json, 'Format'),
    CAST(json_extract_path_text(${mqtt-payload-utf8}::json, 'Units') AS INTEGER),
    CAST(json_extract_path_text(${mqtt-payload-utf8}::json, 'IPCw') AS INTEGER),
    CAST(json_extract_path_text(${mqtt-payload-utf8}::json, 'IPCi') AS INTEGER),
    CAST(json_extract_path_text(${mqtt-payload-utf8}::json, 'QC-samples') AS INTEGER),
    NOW()
);