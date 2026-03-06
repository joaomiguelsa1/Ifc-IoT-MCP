SELECT 
    COUNT(*) as total,
    SUM(CASE WHEN value >= 10 AND value <= 35 
        THEN 1 ELSE 0 END) as validas,
    MIN(value) as temp_min,
    MAX(value) as temp_max,
    ROUND(AVG(value), 2) as temp_media
FROM sensor_readings
WHERE sensor_type = 'temperature'
  AND source = 'MOCK_AUTO';