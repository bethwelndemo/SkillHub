import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'skillhub-secret-change-in-production')
    MYSQL_HOST = os.environ.get('MYSQL_HOST', 'localhost')
    MYSQL_USER = os.environ.get('MYSQL_USER', 'root')
    MYSQL_PASSWORD = os.environ.get('MYSQL_PASSWORD', 'your_password')
    MYSQL_DB = os.environ.get('MYSQL_DB', 'skillhub')
    MYSQL_CURSORCLASS = 'DictCursor'
    UPLOAD_FOLDER = 'static/images/uploads'
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024