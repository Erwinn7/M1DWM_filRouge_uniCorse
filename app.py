from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_login import (
    LoginManager, UserMixin,
    login_user, login_required, logout_user, current_user
)
from flask import jsonify

from bdd_config import BddObject
from werkzeug.security import generate_password_hash, check_password_hash  # pour vérifier le hash du mot de passe
from datetime import datetime

app = Flask(__name__)
app.secret_key = "secret_key"  # nécessaire pour les sessions

TVA_RATE = 0.2  # 20 % de TVA par défaut
SHIPPING_FEE = 25.0
FREE_SHIPPING_THRESHOLD = 1000.0

# ----- Flask-Login: pour la manipulation des connections utilisateurs -----
login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.init_app(app)

# ----- Helpers globaux -----
def _ensure_cart():
    """Garantit l'existence du panier en session et le retourne."""
    cart = session.get("cart")
    if cart is None:
        cart = {}
        session["cart"] = cart
    return cart


def _to_float(value):
    if value is None:
        return 0.0
    return float(value)


@app.context_processor
def inject_cart_count():
    cart = session.get("cart", {})
    total_items = sum(item.get("quantity", 0) for item in cart.values())
    return {"cart_count": total_items}


# Classe User pour manipuler le user connecté
class User(UserMixin):
    def __init__(self, user_id, user_login, user_password, user_compte_id, user_mail):
        self.id = user_id
        self.username = user_login
        self.password_hash = user_password
        self.compte_id = user_compte_id
        self.mail = user_mail

@login_manager.user_loader
def load_user(user_id):
    conn = BddObject.get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM user WHERE user_id = %s", (user_id,))
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    if row:
        return User(row["user_id"], row["user_login"], row["user_password"], row["user_compte_id"], row["user_mail"])
    return None

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
                "INSERT INTO user (user_login, user_password, user_mail) VALUES (%s, %s,%s)",
                (user_login, hashed, user_mail)
            )
            conn.commit()
            cursor.close()
            # redirige vers la page de login (ou afficher un message)
            return redirect(url_for('login'))
        except Exception as e:
            if conn:
                conn.rollback()
            # log l'erreur côté serveur si besoin
            return render_template("register.html", message="Erreur lors de la création de l'utilisateur.")
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
            user = User(user_row["user_id"], user_row["user_login"], user_row["user_password"], user_row["user_compte_id"], user_row["user_mail"])
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
@login_required
def add_produit():
    """Ajoute un nouveau produit"""
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
        selected_category = request.args.get("category", "").strip()
        search_term = request.args.get("search", "").strip()
        conn = BddObject.get_db_connection()  
        cursor = conn.cursor(dictionary=True)

        base_query = "SELECT * FROM produit"
        where_clauses = []
        params = []

        if selected_category:
            where_clauses.append("type_p = %s")
            params.append(selected_category)

        if search_term:
            where_clauses.append("(designation_p LIKE %s OR type_p LIKE %s)")
            like_value = f"%{search_term}%"
            params.extend([like_value, like_value])

        if where_clauses:
            base_query += " WHERE " + " AND ".join(where_clauses)

        base_query += " ORDER BY date_in DESC"

        cursor.execute(base_query, tuple(params))
        produits = cursor.fetchall()

        cursor.execute("SELECT DISTINCT type_p FROM produit ORDER BY type_p ASC")
        categories = [row["type_p"] for row in cursor.fetchall()]

        cursor.close()
        conn.close()
        return render_template(
            "list_produits.html",
            produits=produits,
            categories=categories,
            selected_category=selected_category,
            search_term=search_term
        ), 200

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
@login_required
def update_produit(id_p):
    """Met à jour les informations d’un produit existant"""
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
@login_required
def delete_produit(id_p):
    """Supprime un produit existant"""
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
@login_required
def add_user():
    """Ajoute un nouvel utilisateur"""
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
def get_users():
    """Retourne tous les utilisateurs"""
    try:
        conn = BddObject.get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT user_id, user_login, user_mail,  user_date_new, user_date_login FROM user ")
        users = cursor.fetchall()

        cursor.close()
        conn.close()
        print(current_user.username)

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


#### GESTION DU PANIER ####

@app.route("/cart")
@login_required
def view_cart():
    cart = session.get("cart", {})
    cart_items = []
    total = 0.0

    for product_id, data in cart.items():
        line_total = data["prix_ht"] * data["quantity"]
        total += line_total
        cart_items.append({
            "id_p": int(product_id),
            "designation": data["designation"],
            "prix_ht": data["prix_ht"],
            "quantity": data["quantity"],
            "line_total": line_total,
        })

    total_tva = total * TVA_RATE
    total_ttc = total + total_tva
    shipping_cost = 0.0 if total >= FREE_SHIPPING_THRESHOLD else SHIPPING_FEE
    grand_total = total_ttc + shipping_cost

    return render_template(
        "cart.html",
        cart_items=cart_items,
        total_ht=total,
        total_tva=total_tva,
        total_ttc=total_ttc,
        tva_rate=int(TVA_RATE * 100),
        shipping_cost=shipping_cost,
        free_shipping_threshold=FREE_SHIPPING_THRESHOLD,
        grand_total=grand_total,
    )


@app.route("/cart/add/<int:id_p>", methods=["POST"])
@login_required
def add_to_cart(id_p):
    try:
        quantity = int(request.form.get("quantity", 1))
        if quantity < 1:
            quantity = 1
    except (TypeError, ValueError):
        quantity = 1

    conn = BddObject.get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id_p, designation_p, prix_ht, stock_p FROM produit WHERE id_p = %s", (id_p,))
    produit = cursor.fetchone()
    cursor.close()
    conn.close()

    if not produit:
        flash("Produit introuvable.", "danger")
        return redirect(url_for("get_produits"))

    stock_dispo = produit.get("stock_p")
    try:
        stock_dispo = int(stock_dispo) if stock_dispo is not None else None
    except (TypeError, ValueError):
        stock_dispo = None

    cart = _ensure_cart()
    cart_item = cart.get(str(id_p), {
        "designation": produit["designation_p"],
        "prix_ht": _to_float(produit["prix_ht"]),
        "quantity": 0,
    })

    nouvelle_quantite = cart_item["quantity"] + quantity

    if stock_dispo is not None and nouvelle_quantite > stock_dispo:
        nouvelle_quantite = stock_dispo

    if nouvelle_quantite == cart_item["quantity"]:
        flash("Stock insuffisant pour ajouter davantage de ce produit.", "warning")
        return redirect(url_for("get_produits"))

    cart_item["quantity"] = nouvelle_quantite
    cart[str(id_p)] = cart_item
    session["cart"] = cart
    session.modified = True

    flash("Produit ajouté au panier.", "success")
    return redirect(url_for("view_cart"))


@app.route("/cart/remove/<int:id_p>", methods=["POST"])
@login_required
def remove_from_cart(id_p):
    cart = session.get("cart", {})
    if str(id_p) in cart:
        cart.pop(str(id_p))
        session["cart"] = cart
        session.modified = True
        flash("Produit retiré du panier.", "info")
    return redirect(url_for("view_cart"))


@app.route("/cart/clear", methods=["POST"])
@login_required
def clear_cart():
    session.pop("cart", None)
    flash("Panier vidé.", "info")
    return redirect(url_for("view_cart"))


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
@login_required
def delete_user(user_id):
    """Supprime un utilisateur existant"""
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
@login_required
def edit_user(user_id):
    """Affiche et met à jour les informations d’un utilisateur"""
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
            flash("❌ Utilisateur introuvable", "danger")
            return redirect(url_for("get_users"))

        return render_template("edit_user.html", user=user)

    except Exception as e:
        print(f"Erreur lors de la modification : {e}")
        flash("❌ Erreur lors de la mise à jour de l’utilisateur", "danger")
        return redirect(url_for("get_users"))



if __name__ == "__main__":
    app.run(debug=True)

    
