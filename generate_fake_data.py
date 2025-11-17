
"""
generate_fake_data.py

Génère des données factices pour les tables `produit` et `user` décrites dans le dump SQL fourni.

Usage examples:
  - Générer un fichier SQL:
      python generate_fake_data.py --mode sql --out fake_data.sql --n-produits 200 --n-users 50

  - Insérer directement dans une base MySQL:
      python generate_fake_data.py --mode db --db-host localhost --db-user root --db-pass secret \
          --db-name 2025_M1 --n-produits 200 --n-users 50

Options:
  --start-user-id INT   : user_id initial (par défaut 8 pour rester cohérent avec ton dump)
  --include-plain       : inclure mot de passe en clair dans le rapport (utile pour tests) (False par défaut)
"""

import argparse
import base64
import hashlib
import os
import random
import sys
from datetime import datetime, timedelta

from faker import Faker

# Optional DB insert
try:
    import mysql.connector
except Exception:
    mysql = None

fake = Faker("fr_FR")


def scrypt_like_hash(password: str):
    """
    Tente d'utiliser hashlib.scrypt avec paramètres allégés pour éviter l'erreur 'memory limit exceeded'.
    Si scrypt échoue pour raison mémoire, on revient sur pbkdf2_hmac comme fallback.
    Retourne une chaîne lisible du type:
      scrypt:<n>:<r>:<p>$<salt_b64>$<hexhash>
    ou
      pbkdf2:<iterations>$<salt_b64>$<hexhash>
    """
    salt = os.urandom(16)

    # Paramètres allégés initialement
    n = 2 ** 14  # 16384
    r = 8
    p = 1
    dklen = 64

    try:
        key = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=n, r=r, p=p, dklen=dklen)
        salt_b64 = base64.b64encode(salt).decode("ascii").rstrip("=")
        return f"scrypt:{n}:{r}:{p}${salt_b64}${key.hex()}"
    except (ValueError, MemoryError) as e:
        # Fallback pbkdf2_hmac — beaucoup moins gourmand
        iterations = 100_000
        key2 = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations, dklen=dklen)
        salt_b64 = base64.b64encode(salt).decode("ascii").rstrip("=")
        return f"pbkdf2:{iterations}${salt_b64}${key2.hex()}"


def gen_produit_row():
    types = ["Électronique", "Alimentation", "Hygiène", "Papeterie", "Meuble", "Vêtement", "Jouet", "Accessoire"]
    type_p = random.choice(types)
    designation_p = fake.sentence(nb_words=random.randint(2, 6)).rstrip(".")
    prix_ht = round(random.uniform(1.0, 1500.0), 2)
    # date_in entre 2023-01-01 et aujourd'hui
    start = datetime(2023, 1, 1)
    dt = start + timedelta(days=random.randint(0, (datetime.now() - start).days))
    date_in = dt.date()
    timeS_in = dt + timedelta(hours=random.randint(0, 23), minutes=random.randint(0, 59), seconds=random.randint(0, 59))
    stock_p = random.randint(0, 500)
    return {
        "type_p": type_p,
        "designation_p": designation_p,
        "prix_ht": f"{prix_ht:.2f}",
        "date_in": date_in.isoformat(),
        "timeS_in": timeS_in.strftime("%Y-%m-%d %H:%M:%S"),
        "stock_p": stock_p,
    }


def gen_user_row(user_id, possible_compte_ids, include_plain=False):
    user_login = fake.user_name()
    plain_pass = fake.password(length=random.randint(8, 14))
    user_password = scrypt_like_hash(plain_pass)
    # user_compte_id peut être NULL ou pointer vers une valeur aléatoire existante (différente de self)
    user_compte_id = None
    if possible_compte_ids and random.random() < 0.4:
        # choisir un id différent du user_id (éviter self-referencement)
        choices = [uid for uid in possible_compte_ids if uid != user_id]
        if choices:
            user_compte_id = random.choice(choices)
    user_mail = fake.safe_email()
    # dates entre 2023-01-01 et maintenant
    start = datetime(2023, 1, 1)
    created = start + timedelta(days=random.randint(0, (datetime.now() - start).days),
                                hours=random.randint(0, 23),
                                minutes=random.randint(0, 59),
                                seconds=random.randint(0, 59))
    # last login after creation, up to now
    last_login = created + timedelta(days=random.randint(0, max(0, (datetime.now() - created).days)),
                                     hours=random.randint(0, 23),
                                     minutes=random.randint(0, 59),
                                     seconds=random.randint(0, 59))
    row = {
        "user_id": user_id,
        "user_login": user_login,
        "user_password": user_password,
        "user_compte_id": user_compte_id,
        "user_mail": user_mail,
        "user_date_new": created.strftime("%Y-%m-%d %H:%M:%S"),
        "user_date_login": last_login.strftime("%Y-%m-%d %H:%M:%S"),
    }
    if include_plain:
        row["plain_password"] = plain_pass
    return row


def escape_sql(s: str):
    # simple SQL escaping pour chaîne (UTF-8)
    return s.replace("\\", "\\\\").replace("'", "''")


def generate_sql_insert_statements(n_produits, n_users, out_file, start_user_id=8, include_plain=False):
    produits = [gen_produit_row() for _ in range(n_produits)]

    # Générer users avec user_id explicites (pour pouvoir référencer user_compte_id)
    users = []
    user_ids = list(range(start_user_id, start_user_id + n_users))
    for uid in user_ids:
        users.append(gen_user_row(uid, possible_compte_ids=user_ids, include_plain=include_plain))

    with open(out_file, "w", encoding="utf-8") as f:
        f.write("-- Generated by generate_fake_data.py\n")
        f.write("START TRANSACTION;\n")
        f.write("SET time_zone = \"+00:00\";\n\n")

        # produit inserts (sans id pour laisser auto_increment gérer)
        for p in produits:
            f.write(
                "INSERT INTO `produit` (`type_p`,`designation_p`,`prix_ht`,`date_in`,`timeS_in`,`stock_p`) VALUES "
                f"('{escape_sql(p['type_p'])}','{escape_sql(p['designation_p'])}',{p['prix_ht']},'{p['date_in']}','{p['timeS_in']}',{p['stock_p']});\n"
            )
        f.write("\n")

        # user inserts (avec user_id explicite pour être sûr des références)
        for u in users:
            comp = "NULL" if u["user_compte_id"] is None else str(u["user_compte_id"])
            f.write(
                "INSERT INTO `user` (`user_id`,`user_login`,`user_password`,`user_compte_id`,`user_mail`,`user_date_new`,`user_date_login`) VALUES "
                f"({u['user_id']},'{escape_sql(u['user_login'])}','{escape_sql(u['user_password'])}',{comp},'{escape_sql(u['user_mail'])}','{u['user_date_new']}','{u['user_date_login']}');\n"
            )
        f.write("\nCOMMIT;\n")
    print(f"Fichier SQL écrit : {out_file}")
    if include_plain:
        print("ATTENTION : le fichier contient des mots de passe en clair dans la sortie du script (option --include-plain). Ne pas partager.")


def insert_direct_db(n_produits, n_users, db_host, db_user, db_pass, db_name, db_port=3306, start_user_id=8, include_plain=False):
    if mysql is None:
        raise RuntimeError("mysql-connector-python introuvable. Installe-le (pip install mysql-connector-python) pour utiliser le mode db.")
    cnx = mysql.connector.connect(host=db_host, user=db_user, password=db_pass, database=db_name, port=db_port)
    cur = cnx.cursor()
    try:
        # Insert produits
        for _ in range(n_produits):
            p = gen_produit_row()
            cur.execute(
                "INSERT INTO produit (type_p, designation_p, prix_ht, date_in, timeS_in, stock_p) VALUES (%s,%s,%s,%s,%s,%s)",
                (p["type_p"], p["designation_p"], p["prix_ht"], p["date_in"], p["timeS_in"], p["stock_p"]),
            )
        cnx.commit()

        # Insert users with explicit user_id (attention : possible conflit si user_id existe déjà)
        user_ids = list(range(start_user_id, start_user_id + n_users))
        for uid in user_ids:
            u = gen_user_row(uid, possible_compte_ids=user_ids, include_plain=include_plain)
            cur.execute(
                "INSERT INTO user (user_id, user_login, user_password, user_compte_id, user_mail, user_date_new, user_date_login) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (u["user_id"], u["user_login"], u["user_password"], u["user_compte_id"], u["user_mail"], u["user_date_new"], u["user_date_login"]),
            )
        cnx.commit()
        print(f"Inséré {n_produits} produits et {n_users} users dans la base {db_name}@{db_host}")
        if include_plain:
            print("ATTENTION : mots de passe en clair générés en mémoire (option --include-plain).")
    finally:
        cur.close()
        cnx.close()


def main():
    parser = argparse.ArgumentParser(description="Générateur de données factices pour 2025_M1 (version modifiée)")
    parser.add_argument("--mode", choices=["sql", "db"], default="sql", help="Mode: 'sql' (fichier) ou 'db' (insertion directe)")
    parser.add_argument("--out", default="fake_data.sql", help="Chemin du fichier SQL en mode sql")
    parser.add_argument("--n-produits", type=int, default=100, help="Nombre de produits à générer")
    parser.add_argument("--n-users", type=int, default=50, help="Nombre de users à générer")
    parser.add_argument("--start-user-id", type=int, default=8, help="Valeur user_id de départ (par défaut 8)")
    parser.add_argument("--include-plain", action="store_true", help="Inclure les mots de passe en clair dans la sortie (utile pour tests)")

    # DB params
    parser.add_argument("--db-host", default="localhost")
    parser.add_argument("--db-user", default="root")
    parser.add_argument("--db-pass", default="")
    parser.add_argument("--db-name", default="2025_M1")
    parser.add_argument("--db-port", type=int, default=3306)

    args = parser.parse_args()

    if args.mode == "sql":
        generate_sql_insert_statements(args.n_produits, args.n_users, args.out, start_user_id=args.start_user_id, include_plain=args.include_plain)
    else:
        insert_direct_db(args.n_produits, args.n_users, args.db_host, args.db_user, args.db_pass, args.db_name, db_port=args.db_port, start_user_id=args.start_user_id, include_plain=args.include_plain)


if __name__ == "__main__":
    main()
