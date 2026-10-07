import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'hotel_reservation_secret_key_2026')
    MYSQL_HOST = os.environ.get('MYSQL_HOST', 'localhost')
    MYSQL_USER = os.environ.get('MYSQL_USER', 'root')
    MYSQL_PASSWORD = os.environ.get('MYSQL_PASSWORD', '')
    MYSQL_DB = os.environ.get('MYSQL_DB', 'hotel_db')
    MYSQL_PORT = int(os.environ.get('MYSQL_PORT', 3306))
