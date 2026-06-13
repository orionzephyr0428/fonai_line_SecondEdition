import mysql.connector
from config import MYSQL_HOST, MYSQL_PORT, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DATABASE

def get_connection():
    return mysql.connector.connect(
        host=MYSQL_HOST,     
        port=MYSQL_PORT,      
        user=MYSQL_USER,    
        password=MYSQL_PASSWORD,
        database=MYSQL_DATABASE,
    )