from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_login import (
    LoginManager, UserMixin,
    login_user, login_required, logout_user, current_user
)
from flask import jsonify

from bdd_config import BddObject
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

app = Flask(__name__)
app.secret_key = "secret_key"

login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.init_app(app)

# Classe User pour manipuler le user connecté
class User(UserMixin):
    def __init__(self, user_id, user_login, user_password, user_compte_id, user_mail, user_role="user"):
        self.id = user_id
        self.username = user_login
        self.password_hash = user_password
        self.compte_id = user_compte_id
        self.mail = user_mail
        self.role = user_role

@login_manager.user_loader
def load_user(user_id):
    conn = BddObject.get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM user WHERE user_id = %s", (user_id,))
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    if row:
        return User(row["user_id"], row["user_login"], row["user_password"], row["user_compte_id"], row["user_mail"], row.get("user_role", "user"))
    return None

# Décorateur pour vérifier si l'utilisateur est admin
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash("Vous devez être connecté", "danger")
            return redirect(url_for("login"))
        if current_user.role != "admin":
            flash("❌ Accès refusé. Seuls les administrateurs peuvent accéder à cette ressource.", "danger")
            return redirect(url_for("home"))
        return f(*args, **kwargs)
    return decorated_function

#route principale
@app.route("/")
@login_required # nécessite une connexion
def home():
    return render_template("home.html")


#route pour enregistrer un utilisateur
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        user_login = request.form["user_login"].strip()
        user_password = request.form["user_password"]
        user_mail = request.form.get("user_mail", "").strip()

        # contrôles simples côté serveur
        if len(user_login) < 3 or len(user_password) < 6:
            return render_template("register.html", message="Login trop court ou mot de passe insuffisant (>=6)")

        hashed = generate_password_hash(user_password)

        conn = None
        try:
            conn = BddObject.get_db_connection()
            cursor = conn.cursor()
            #requete pour vérifier si le login existe déjà
            cursor.execute("SELECT user_id FROM user WHERE user_login = %s", (user_login,))
            if cursor.fetchone():
                cursor.close()
                if conn:
                    conn.rollback()
                return render_template("register.html", message="Nom d'utilisateur déjà utilisé.")
            
            cursor.execute(
                "INSERT INTO user (user_login, user_password, user_mail, user_date_new) VALUES (%s, %s, %s, NOW())",
                (user_login, hashed, user_mail)
            )
            conn.commit()
            cursor.close()
            # redirige vers la page de login (ou afficher un message)
            return redirect(url_for('login'))
        except Exception as e:
            if conn:
                conn.rollback()
            # Affiche l'erreur réelle pour déboguer
            print(f"Erreur inscription : {str(e)}")
            error_msg = f"Erreur : {str(e)}"
            return render_template("register.html", message=error_msg)
        finally:
            if conn:
                conn.close()
    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        userLogin = request.form["user_login"]
        userPassword = request.form["user_password"]

        conn = BddObject.get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM user WHERE user_login = %s", (userLogin,)) 
        user_row = cursor.fetchone()
        cursor.close()
        conn.close()

        if user_row and check_password_hash(user_row["user_password"], userPassword):
            user = User(user_row["user_id"], user_row["user_login"], user_row["user_password"], user_row["user_compte_id"], user_row["user_mail"], user_row.get("user_role", "user"))
            login_user(user)
            return redirect(url_for("home"))
        else:
            return render_template("login.html", message="Identifiants invalides.")

    return render_template("login.html")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))

####GESTION DES PRODUITS####    

@app.route("/produits/add", methods=["GET", "POST"])
@admin_required
def add_produit():
    """Ajoute un nouveau produit (admin uniquement)"""
    if request.method == "POST":
        type_p = request.form["type_p"]
        designation_p = request.form["designation_p"]
        prix_ht = request.form["prix_ht"]
        stock_p = request.form["stock_p"]

        try:
            conn = BddObject.get_db_connection()
            cursor = conn.cursor()

            cursor.execute("""
                INSERT INTO produit (type_p, designation_p, prix_ht, stock_p, date_in)
                VALUES (%s, %s, %s, %s, NOW())
            """, (type_p, designation_p, prix_ht, stock_p))

            conn.commit()
            cursor.close()
            conn.close()

            return redirect(url_for("get_produits"))

        except Exception as e:
            flash("Erreur lors de l'ajout du produit", "danger")
            return render_template("add_produit.html", message=str(e)), 500

    return render_template("add_produit.html")



# ---------- ROUTE GET : récupérer la liste de tous les produits ----------
@app.route("/produits", methods=["GET"])
@login_required
def get_produits():
    """Retourne tous les produits sous forme JSON"""
    try:
        conn = BddObject.get_db_connection()  
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM produit")
        produits = cursor.fetchall()
        cursor.close()
        conn.close()
        return render_template("list_produits.html", produits=produits), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
    # ---------- ROUTE GET : récupérer un seul produit par son id ----------
@app.route("/produits/<int:id_p>", methods=["GET"])
@login_required
def get_produit(id_p):
    """Retourne un produit spécifique"""
    try:
        conn = BddObject.get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM produit WHERE id_p = %s DESC", (id_p,))
        produit = cursor.fetchone()

        cursor.close()
        conn.close()

        if not produit:
            return jsonify({"message": f"Aucun produit trouvé avec id_p={id_p}"}), 404

        return jsonify(produit), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

    

    # ---------- ROUTE : mettre à jour un produit ----------

#afficher le formulaire de modification
@app.route("/produit/edit/<int:id_p>", methods=["GET"])
@login_required
def edit_produit(id_p):
    """Affiche le formulaire de modification pour un produit donné"""
    conn = BddObject.get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM produit WHERE id_p = %s", (id_p,))
    produit = cursor.fetchone()

    cursor.close()
    conn.close()

    if not produit:
        return "Produit introuvable", 404

    return render_template("edit_produit.html", produit=produit)


@app.route("/produits/update/<int:id_p>", methods=["POST"])
@admin_required
def update_produit(id_p):
    """Met à jour les informations d’un produit existant (admin uniquement)"""
    try:
        type_p = request.form["type_p"]
        designation_p = request.form["designation_p"]
        prix_ht = request.form["prix_ht"]
        stock_p = request.form["stock_p"]

        conn = BddObject.get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE produit
            SET type_p=%s, designation_p=%s, prix_ht=%s, stock_p=%s
            WHERE id_p=%s
        """, (type_p, designation_p, prix_ht, stock_p, id_p))

        conn.commit()
        cursor.close()
        conn.close()

        return redirect(url_for("get_produits"))

    except Exception as e:
        return f"Erreur : {str(e)}", 500
    



#supprimer un produit
@app.route("/produits/delete/<int:id_p>", methods=["DELETE"])
@admin_required
def delete_produit(id_p):
    """Supprime un produit existant (admin uniquement)"""
    try:
        conn = BddObject.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM produit WHERE id_p = %s", (id_p,))
        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({"success": True, "message": "Produit supprimé avec succès"}), 200
    except Exception as e:
        print(f"Erreur lors de la suppression : {e}")
        return jsonify({"success": False, "error": str(e)}), 500     



####GESTION DES UTILISATEURS####

#ajouter un utilisateur
@app.route("/users/add", methods=["GET", "POST"])
@admin_required
def add_user():
    """Ajoute un nouvel utilisateur (admin uniquement)"""
    try:
        conn = BddObject.get_db_connection()
        cursor = conn.cursor(dictionary=True)

        if request.method == "POST":
            user_login = request.form["user_login"]
            user_mail = request.form["user_mail"]
            user_password = request.form["user_password"]

            # Vérifier si login ou mail existe déjà
            cursor.execute("SELECT * FROM user WHERE user_login = %s OR user_mail = %s", (user_login, user_mail))
            existing_user = cursor.fetchone()
            if existing_user:
                flash("Ce login ou cet email est déjà utilisé", "danger")
                return redirect(url_for("add_user"))

            # Hash du mot de passe
            hashed_password = generate_password_hash(user_password)

            # Insertion du nouvel utilisateur
            cursor.execute("""
                INSERT INTO user (user_login, user_mail, user_password, user_date_new)
                VALUES (%s, %s, %s, %s)
            """, (user_login, user_mail, hashed_password, datetime.now()))

            conn.commit()
            cursor.close()
            conn.close()

            flash("Nouvel utilisateur ajouté avec succès", "success")
            return redirect(url_for("get_users"))

        cursor.close()
        conn.close()
        return render_template("add_user.html")

    except Exception as e:
        print(f"Erreur lors de l'ajout de l'utilisateur : {e}")
        flash("Erreur lors de l’ajout de l’utilisateur", "danger")
        return redirect(url_for("get_users"))

    

# ---------- ROUTE GET : récupérer tous les utilisateurs ----------
@app.route("/users", methods=["GET"])
@admin_required
def get_users():
    """Retourne tous les utilisateurs (admin uniquement)"""
    try:
        conn = BddObject.get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT user_id, user_login, user_mail, user_date_new, user_date_login FROM user")
        users = cursor.fetchall()

        cursor.close()
        conn.close()

        return render_template("users.html", users=users)
    except Exception as e:
        print(f"Erreur récupération utilisateurs : {e}")
        return render_template("users.html", users=[])


# ---------- ROUTE GET : récupérer un seul utilisateur par son id ----------
@app.route("/users/<int:user_id>", methods=["GET"])
def get_user_by_id(user_id):
    """Retourne un utilisateur précis selon son ID"""
    try:
        conn = BddObject.get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT user_id, user_login, user_mail, user_compte_id, user_date_new, user_date_login 
            FROM user WHERE user_id = %s
        """, (user_id,))
        user = cursor.fetchone()

        cursor.close()
        conn.close()

        if not user:
            return jsonify({"message": f"Aucun utilisateur trouvé avec user_id={user_id}"}), 404

        return jsonify(user), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------- ROUTE GET : rechercher un utilisateur par login ----------
@app.route("/users/search", methods=["GET"])
def search_user_by_login():
    """Recherche un utilisateur par son login (partiel ou complet)"""
    try:
        login = request.args.get("login", "").strip()

        if not login:
            return jsonify({"message": "Veuillez fournir un paramètre ?login=..."}), 400

        conn = BddObject.get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT user_id, user_login, user_mail, user_compte_id, user_date_new, user_date_login
            FROM user WHERE user_login LIKE %s
        """, (f"%{login}%",))
        users = cursor.fetchall()

        cursor.close()
        conn.close()

        if not users:
            return jsonify({"message": f"Aucun utilisateur trouvé pour '{login}'"}), 404

        return jsonify(users), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


#supprimer un utilisateur
@app.route("/users/delete/<int:user_id>", methods=["POST"])
@admin_required
def delete_user(user_id):
    """Supprime un utilisateur existant (admin uniquement)"""
    try:
        conn = BddObject.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM user WHERE user_id = %s", (user_id,))
        conn.commit()
        cursor.close()
        conn.close()

        flash("🗑️ Utilisateur supprimé avec succès", "success")
    except Exception as e:
        print(f"Erreur lors de la suppression de l'utilisateur : {e}")
        flash("❌ Erreur lors de la suppression", "danger")

    return redirect(url_for("get_users"))

# modifier un utilisateur
@app.route("/users/edit/<int:user_id>", methods=["GET", "POST"])
@admin_required
def edit_user(user_id):
    """Affiche et met à jour les informations d’un utilisateur (admin uniquement)"""
    try:
        conn = BddObject.get_db_connection()
        cursor = conn.cursor(dictionary=True)

        if request.method == "POST":
            user_login = request.form["user_login"]
            user_mail = request.form["user_mail"]

            # Mise à jour du user
            cursor.execute("""
                UPDATE user 
                SET user_login = %s, user_mail = %s
                WHERE user_id = %s
            """, (user_login, user_mail, user_id))

            conn.commit()
            cursor.close()
            conn.close()

            flash("✅ Utilisateur modifié avec succès", "success")
            return redirect(url_for("get_users"))

        # Récupération des infos utilisateur
        cursor.execute("""
            SELECT user_id, user_login, user_mail, user_date_new, user_date_login 
            FROM user 
            WHERE user_id = %s
        """, (user_id,))
        user = cursor.fetchone()

        cursor.close()
        conn.close()

        if not user:
            flash("Utilisateur introuvable", "danger")
            return redirect(url_for("get_users"))

        return render_template("edit_user.html", user=user)

    except Exception as e:
        print(f"Erreur lors de la modification : {e}")
        flash("Erreur lors de la mise à jour de l’utilisateur", "danger")
        return redirect(url_for("get_users"))

@app.route('/produits/recherche', methods=['GET'])
@login_required
def rechercher_produits():
    search_query = request.args.get('search', '')

    # obtenir la connexion via BddObject
    conn = BddObject.get_db_connection()
    cursor = conn.cursor(dictionary=True)

    if search_query:
        cursor.execute("SELECT * FROM produit WHERE designation_p LIKE %s", ('%' + search_query + '%',))
    else:
        cursor.execute("SELECT * FROM produit")

    produits = cursor.fetchall()
    cursor.close()
    conn.close()

    return render_template('list_produits.html', produits=produits, query=search_query)



if __name__ == "__main__":
    app.run(debug=True)


