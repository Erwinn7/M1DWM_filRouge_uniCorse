import mysql.connector

class BddObject:

    # ----- Connexion MySQL -----
    @staticmethod
    def get_db_connection():
        return mysql.connector.connect(
            host="localhost",
<<<<<<< HEAD
            user="root",  # Changez par vos identifiants
            password="",  # Changez par votre mot de passe
=======
            user="root",
            password="",
>>>>>>> 0c0191bf78210d55c581bc5514266287ec3d45de
            database="2025_M1"
        )