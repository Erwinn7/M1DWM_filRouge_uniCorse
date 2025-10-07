from flask import Flask, render_template, request, redirect, url_for
from flask_login import (
    LoginManager, UserMixin,
    login_user, login_required, logout_user
)
from bdd_config import BddObject
from werkzeug.security import generate_password_hash, check_password_hash  # pour vérifier le hash du mot de passe

app = Flask(__name__)
app.secret_key = "secret_key"  # nécessaire pour les sessions

# ----- Flask-Login: pour la manipulation des connections utilisateurs -----
login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.init_app(app)

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

if __name__ == "__main__":
    app.run(debug=True)
