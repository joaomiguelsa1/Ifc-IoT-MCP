SELECT 
    COUNT(*) as total,
    SUM(CASE WHEN value >= 20 AND value <= 26 
        THEN 1 ELSE 0 END) as conformes,
    SUM(CASE WHEN value < 20 OR value > 26 
        THEN 1 ELSE 0 END) as nao_conformes,
    ROUND(100.0 * SUM(CASE WHEN value >= 20 AND value <= 26 
        THEN 1 ELSE 0 END) / COUNT(*), 2) as percentagem
FROM sensor_readings
WHERE sensor_type = 'temperature'
  AND source = 'MOCK_AUTO';