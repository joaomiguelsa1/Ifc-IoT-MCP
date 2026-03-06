SELECT 
    ifc_filename,
    space_name,
    COUNT(DISTINCT sensor_type) as num_tipos
FROM sensor_readings
GROUP BY ifc_filename, space_name
ORDER BY ifc_filename, num_tipos DESC;