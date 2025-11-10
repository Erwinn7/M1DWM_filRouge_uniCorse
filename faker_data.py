from faker import Faker
import random
from bdd_config import BddObject

# Créer une instance Faker en français
fake = Faker('fr_FR')

# Connexion à la base de données
conn = BddObject.get_db_connection()
cursor = conn.cursor()

# Liste de types de produits possibles
types_produits = ['Informatique', 'Électronique', 'Vêtements', 'Alimentation', 'Maison', 'Beauté', 'Sport']

# Nombre de produits à insérer
nombre_produits = 30

for _ in range(nombre_produits):
    type_p = random.choice(types_produits)
    designation_p = fake.catch_phrase()  # un nom de produit aléatoire
    prix_ht = round(random.uniform(5.0, 1500.0), 2)
    stock_p = random.randint(1, 200)

    cursor.execute("""
        INSERT INTO produit (type_p, designation_p, prix_ht, stock_p, date_in)
        VALUES (%s, %s, %s, %s, CURDATE())
    """, (type_p, designation_p, prix_ht, stock_p))

# Validation et fermeture
conn.commit()
cursor.close()
conn.close()

print(f"{nombre_produits} produits ont été ajoutés avec succès ✅")
