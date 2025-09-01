from flask import Flask, render_template, request, redirect, url_for, flash, session, g
import sqlite3
import os
from datetime import datetime

app = Flask(__name__)
app.secret_key = "supersecretkey"
DATABASE = "bank.db"

# ---------------- Database Helper ---------------- #
def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def init_db():
    if os.path.exists(DATABASE):
        return # Database already exists
    with app.app_context():
        db = get_db()
        with app.open_resource('schema.sql', mode='r') as f:
            db.cursor().executescript(f.read())
        db.commit()
        print("✅ Database initialized and populated with sample data.")
        # Create schema and sample data
        db.executescript("""
            DROP TABLE IF EXISTS users;
            DROP TABLE IF EXISTS transactions;

            CREATE TABLE users (
                user_id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                card_number TEXT UNIQUE NOT NULL,
                pin TEXT NOT NULL,
                balance REAL DEFAULT 0.0
            );

            CREATE TABLE transactions (
                txn_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                txn_type TEXT NOT NULL,
                amount REAL DEFAULT 0.0,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            );

            INSERT INTO users (name, card_number, pin, balance) VALUES
            ('John Doe', '1111222233334444', '1234', 5432.10),
            ('Jane Smith', '9999888877776666', '5678', 10500.75);
        """)
        db.commit()

def init_db_on_startup():
    init_db()

# ---------------- Routes ---------------- #
@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        card = request.form["card_number"]
        pin = request.form["pin"]

        db = get_db()
        user = db.execute("SELECT * FROM users WHERE card_number=? AND pin=?", (card, pin)).fetchone()
        
        if user:
            session.clear()
            session["user_id"] = user["user_id"]
            flash(f"Welcome {user['name']}!", "success")
            return redirect(url_for("dashboard"))
        else:
            flash("Invalid card number or PIN", "error")

    return render_template("login.html")

@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect(url_for("login"))

    db = get_db()
    user = db.execute("SELECT * FROM users WHERE user_id=?", (session["user_id"],)).fetchone()
    
    return render_template("dashboard.html", user=user)

@app.route("/withdraw", methods=["GET", "POST"])
def withdraw():
    if "user_id" not in session: return redirect(url_for("login"))
    
    if request.method == "POST":
        amount = float(request.form["amount"])
        pin = request.form["pin"]
        db = get_db()
        user = db.execute("SELECT * FROM users WHERE user_id=?", (session["user_id"],)).fetchone()

        if user["pin"] != pin:
            flash("Invalid PIN", "error")
            return render_template("withdraw.html")

        if user["balance"] >= amount:
            new_balance = user["balance"] - amount
            db.execute("UPDATE users SET balance=? WHERE user_id=?", (new_balance, user["user_id"]))
            db.execute("INSERT INTO transactions (user_id, txn_type, amount) VALUES (?, 'withdraw', ?)", (user["user_id"], amount))
            db.commit()

            txn_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
            session['last_transaction_id'] = txn_id
            
            flash(f"Withdrawn ₹{amount}. Please take your cash.", "success")
            return redirect(url_for("receipt"))
        else:
            flash("Insufficient balance", "error")
            return render_template("withdraw.html")

    return render_template("withdraw.html")

@app.route("/deposit", methods=["GET", "POST"])
def deposit():
    if "user_id" not in session: return redirect(url_for("login"))

    if request.method == "POST":
        amount = float(request.form["amount"])
        pin = request.form["pin"]
        db = get_db()
        user = db.execute("SELECT * FROM users WHERE user_id=?", (session["user_id"],)).fetchone()

        if user["pin"] != pin:
            flash("Invalid PIN", "error")
            return render_template("deposit.html")

        new_balance = user["balance"] + amount
        db.execute("UPDATE users SET balance=? WHERE user_id=?", (new_balance, user["user_id"]))
        db.execute("INSERT INTO transactions (user_id, txn_type, amount) VALUES (?, 'deposit', ?)", (user["user_id"], amount))
        db.commit()
        
        txn_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        session['last_transaction_id'] = txn_id

        flash(f"Deposited ₹{amount}. Your new balance is ₹{new_balance}", "success")
        return redirect(url_for("receipt"))

    return render_template("deposit.html")

@app.route("/transactions", methods=["GET", "POST"])
def transactions():
    if "user_id" not in session: return redirect(url_for("login"))
    
    if request.method == "POST":
        pin = request.form["pin"]
        db = get_db()
        user = db.execute("SELECT * FROM users WHERE user_id=?", (session["user_id"],)).fetchone()
        
        if user["pin"] == pin:
            transactions = db.execute(
                "SELECT * FROM transactions WHERE user_id=? ORDER BY timestamp DESC LIMIT 10",
                (session["user_id"],)
            ).fetchall()
            # Convert string timestamps to datetime objects
            processed_transactions = []
            for txn in transactions:
                txn_dict = dict(txn)
                txn_dict['timestamp'] = datetime.strptime(txn['timestamp'], '%Y-%m-%d %H:%M:%S')
                processed_transactions.append(txn_dict)
            return render_template("transactions.html", transactions=processed_transactions)
        else:
            flash("Invalid PIN", "error")
            return render_template("transactions.html", transactions=None)

    return render_template("transactions.html", transactions=None)


@app.route("/balance", methods=["GET", "POST"])
def balance():
    if "user_id" not in session: return redirect(url_for("login"))

    if request.method == "POST":
        pin = request.form["pin"]
        db = get_db()
        user = db.execute("SELECT * FROM users WHERE user_id=?", (session["user_id"],)).fetchone()
        if user["pin"] == pin:
            return render_template("balance.html", balance=user['balance'])
        else:
            flash("Invalid PIN", "error")
            return render_template("balance.html", balance=None)
            
    return render_template("balance.html", balance=None)

@app.route("/receipt")
def receipt():
    if "user_id" not in session: return redirect(url_for("login"))
    if "last_transaction_id" not in session:
        flash("No recent transaction found to print.", "error")
        return redirect(url_for("dashboard"))

    db = get_db()
    user = db.execute("SELECT * FROM users WHERE user_id=?", (session['user_id'],)).fetchone()
    last_txn = db.execute(
        "SELECT * FROM transactions WHERE txn_id=?",
        (session['last_transaction_id'],)
    ).fetchone()

    receipt_data = {
        "timestamp": datetime.strptime(last_txn['timestamp'], '%Y-%m-%d %H:%M:%S'),
        "card_last_4": user['card_number'][-4:],
        "txn_type": last_txn['txn_type'],
        "amount": last_txn['amount'],
        "new_balance": user['balance']
    }
    return render_template("receipt.html", receipt=receipt_data)

@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out", "info")
    return redirect(url_for("login"))

# ---------------- Run ---------------- #
if __name__ == "__main__":
    init_db_on_startup()
    app.run(debug=True)

