import mysql.connector

class BddObject:

    # ----- Connexion MySQL -----
    @staticmethod
    def get_db_connection():
        return mysql.connector.connect(
            host="localhost",
            user="root",  # Changez par vos identifiants
            password="",  # Changez par votre mot de passe
            database="2025_M1"
        )