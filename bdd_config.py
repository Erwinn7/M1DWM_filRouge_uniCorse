import mysql.connector

class BddObject :

    # ----- Connexion MySQL -----
    def get_db_connection():
        return mysql.connector.connect(
            host="localhost",
            user="root",
            password="",
            database="2025_M1"
        )