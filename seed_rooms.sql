USE hotel_db;
TRUNCATE TABLE rooms;
INSERT INTO rooms (room_number, room_type, price_per_night, capacity, facilities, status) VALUES
('101', 'Standard Room', 350000.00, 2, 'AC, TV 32 Inch, Free Wi-Fi, Shower Air Hangat, Double Bed', 'available'),
('102', 'Standard Room', 350000.00, 2, 'AC, TV 32 Inch, Free Wi-Fi, Shower Air Hangat, Twin Bed', 'available'),
('201', 'Deluxe Room', 550000.00, 3, 'AC, Smart TV 43 Inch, Free Wi-Fi, Water Heater, Queen Bed, Balkon Kota, Mini Refrigerator', 'available'),
('202', 'Deluxe Room', 550000.00, 3, 'AC, Smart TV 43 Inch, Free Wi-Fi, Water Heater, King Bed, Balkon Kota, Coffee Maker', 'available'),
('301', 'Executive Suite', 950000.00, 4, 'AC, Smart TV 55 Inch, Free High-Speed Wi-Fi, Bathtub, King Bed, Ruang Tamu Separasi, Mini Bar, Free Breakfast', 'available'),
('302', 'Executive Suite', 950000.00, 4, 'AC, Smart TV 55 Inch, Free High-Speed Wi-Fi, Bathtub, King Bed, Ruang Tamu Separasi, Mini Bar, Mountain View', 'maintenance');
