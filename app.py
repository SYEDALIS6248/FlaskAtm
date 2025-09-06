import os
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv
load_dotenv()

# ---------------- App & Database Configuration ---------------- #

app = Flask(__name__)
app.secret_key = "your_super_secret_key" # Change this for production

# Get the DATABASE_URL from environment variables
db_url = os.environ.get('DATABASE_URL')
if not db_url:
    # If DATABASE_URL is not found, use this local one as a fallback
    db_url = "postgresql://postgres:your_password@localhost/atm_db"
    print("WARNING: DATABASE_URL not found. Using local fallback.")

# Heroku/Render use 'postgres://' but SQLAlchemy needs 'postgresql://'
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# ---------------- Database Models ---------------- #

class User(db.Model):
    __tablename__ = 'users'
    user_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    card_number = db.Column(db.String(16), unique=True, nullable=False)
    pin = db.Column(db.String(4), nullable=False)
    balance = db.Column(db.Float, nullable=False, default=0.0)
    transactions = db.relationship('Transaction', backref='user', lazy=True)

class Transaction(db.Model):
    __tablename__ = 'transactions'
    txn_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=False)
    txn_type = db.Column(db.String(20), nullable=False)
    amount = db.Column(db.Float, nullable=False, default=0.0)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

# ---------------- Routes ---------------- #

@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        card = request.form["card_number"]
        pin = request.form["pin"]

        user = User.query.filter_by(card_number=card, pin=pin).first()

        if user:
            session.clear()
            session["user_id"] = user.user_id
            flash(f"Welcome {user.name}!", "success")
            return redirect(url_for("dashboard"))
        else:
            flash("Invalid card number or PIN", "error")

    # Renders login.html
    return render_template("login.html")

@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect(url_for("login"))

    user = User.query.get(session["user_id"])
    # Renders dashboard.html
    return render_template("dashboard.html", user=user)

@app.route("/withdraw", methods=["GET", "POST"])
def withdraw():
    if "user_id" not in session: return redirect(url_for("login"))

    user = User.query.get(session["user_id"])
    if request.method == "POST":
        amount = float(request.form["amount"])
        pin = request.form["pin"]

        if user.pin != pin:
            flash("Invalid PIN", "error")
        elif user.balance >= amount:
            user.balance -= amount
            new_txn = Transaction(user_id=user.user_id, txn_type='withdraw', amount=amount)
            db.session.add(new_txn)
            db.session.commit()

            session['last_transaction_id'] = new_txn.txn_id
            flash(f"Withdrawn ₹{amount:.2f}. Please take your cash.", "success")
            return redirect(url_for("receipt"))
        else:
            flash("Insufficient balance", "error")

    # Renders withdraw.html
    return render_template("withdraw.html")

@app.route("/deposit", methods=["GET", "POST"])
def deposit():
    if "user_id" not in session: return redirect(url_for("login"))
    
    user = User.query.get(session["user_id"])
    if request.method == "POST":
        amount = float(request.form["amount"])
        pin = request.form["pin"]

        if user.pin != pin:
            flash("Invalid PIN", "error")
        else:
            user.balance += amount
            new_txn = Transaction(user_id=user.user_id, txn_type='deposit', amount=amount)
            db.session.add(new_txn)
            db.session.commit()

            session['last_transaction_id'] = new_txn.txn_id
            flash(f"Deposited ₹{amount:.2f}. Your new balance is ₹{user.balance:.2f}", "success")
            return redirect(url_for("receipt"))

    # Renders deposit.html
    return render_template("deposit.html")

@app.route("/transactions", methods=["GET", "POST"])
def transactions():
    if "user_id" not in session: return redirect(url_for("login"))

    user = User.query.get(session["user_id"])
    user_transactions = None
    if request.method == "POST":
        pin = request.form["pin"]
        if user.pin == pin:
            # Fetch the last 10 transactions
            user_transactions = Transaction.query.filter_by(user_id=session["user_id"]).order_by(Transaction.timestamp.desc()).limit(10).all()
        else:
            flash("Invalid PIN", "error")

    # Renders transactions.html
    return render_template("transactions.html", transactions=user_transactions)

@app.route("/balance", methods=["GET", "POST"])
def balance():
    if "user_id" not in session: return redirect(url_for("login"))

    user = User.query.get(session["user_id"])
    current_balance = None
    if request.method == "POST":
        pin = request.form["pin"]
        if user.pin == pin:
            current_balance = user.balance
        else:
            flash("Invalid PIN", "error")
            
    # Renders balance.html
    return render_template("balance.html", balance=current_balance)

@app.route("/receipt")
def receipt():
    if "user_id" not in session or "last_transaction_id" not in session:
        flash("No recent transaction found.", "error")
        return redirect(url_for("dashboard"))

    user = User.query.get(session['user_id'])
    last_txn = Transaction.query.get(session['last_transaction_id'])

    receipt_data = {
        "timestamp": last_txn.timestamp,
        "card_last_4": user.card_number[-4:],
        "txn_type": last_txn.txn_type,
        "amount": last_txn.amount,
        "new_balance": user.balance
    }
    # Renders receipt.html
    return render_template("receipt.html", receipt=receipt_data)

@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out", "info")
    return redirect(url_for("login"))

# ---------------- Main Execution ---------------- #

if __name__ == "__main__":
    with app.app_context():
        # This is the magic line right here!
        db.create_all()
    app.run(debug=True)