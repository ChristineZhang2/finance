import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    user_id = session["user_id"]

    # Query the database for the user's stocks
    stocks = db.execute(
        "SELECT symbol, SUM(shares) as total_shares FROM transactions WHERE user_id = ? GROUP BY symbol HAVING total_shares > 0", user_id)

    # Initialize the variables for totals
    total_value = 0
    portfolio = []

    # Get the current price for each stock and calculate the total value
    for stock in stocks:
        quote = lookup(stock['symbol'])
        if quote is None:
            return apology("Unable to fetch stock data", 500)

        stock_value = quote['price'] * stock['total_shares']
        total_value += stock_value

        portfolio.append({
            'symbol': stock['symbol'],
            'name': quote['name'],
            'shares': stock['total_shares'],
            'price': usd(quote['price']),
            'value': usd(stock_value)
        })

    # Get user's updated balance
    cash = db.execute("SELECT cash FROM users WHERE id = ?", user_id)[0]['cash']
    total_value += cash

    return render_template("index.html",
                           portfolio=portfolio,
                           cash=usd(cash),
                           total=usd(total_value))


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "POST":
        symbol = request.form.get("symbol").upper()
        shares = request.form.get("shares")

        # Make sure the symbol was submitted
        if not symbol:
            return apology("You must provide a symbol", 400)

        # Make sure the the number of shares was submitted
        if not shares:
            return apology("You must provide number of shares", 400)

        # Make sure the number of shares is a positive number
        try:
            shares = int(shares)
            if shares <= 0:
                return apology("The number of shares must be a positive integer", 400)
        except ValueError:
            return apology("The number of shares must be a positive integer", 400)

        # Look up the stock
        stock = lookup(symbol)
        if stock is None:
            return apology("invalid symbol", 400)

        # Calculate the total cost
        cost = shares * stock["price"]

        # Check if the user has enough money
        user_id = session["user_id"]
        user_cash = db.execute("SELECT cash FROM users WHERE id = ?", user_id)[0]["cash"]

        if user_cash < cost:
            return apology("not enough cash", 400)

        # Update user's money
        db.execute("UPDATE users SET cash = cash - ? WHERE id = ?", cost, user_id)

        # Record the purchase into database
        db.execute("INSERT INTO transactions (user_id, symbol, shares, price, type) VALUES (?, ?, ?, ?, ?)",
                   user_id, symbol, shares, stock["price"], "buy")

        # Redirect user to home page
        flash(f"Bought {shares} shares of {symbol} for {usd(cost)}!")
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    user_id = session["user_id"]

    # Query all transactions from the user
    transactions = db.execute("""
                              SELECT symbol, shares, price, type, timestamp
                              FROM transactions
                              WHERE user_id = ?
                              ORDER BY timestamp DESC""", user_id)
    # Format the data for display
    for transaction in transactions:
        transaction["price"] = usd(transaction["price"])
        transaction["timestamp"] = transaction["timestamp"]

    return render_template("history.html", transactions=transactions)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute(
            "SELECT * FROM users WHERE username = ?", request.form.get("username")
        )

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(
            rows[0]["hash"], request.form.get("password")
        ):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "POST":
        symbol = request.form.get("symbol").upper()
        if not symbol:
            return apology("You must provide a stock symbol", 400)

        stock_data = lookup(symbol)
        if stock_data is None:
            return apology("Invalid Stock Symbol", 400)

        return render_template("quoted.html", stock={
            'name': stock_data['name'],
            'symbol': stock_data['symbol'],
            'price': usd(stock_data['price'])
        })
    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    # if user reached route using POST
    if request.method == "POST":
        # make sure username was submitted
        if not request.form.get("username"):
            return apology("You must provide your username", 400)

        # make sure pasword was submitted
        elif not request.form.get("password"):
            return apology("You must provide your password", 400)

        # get confirmation that the password was submitted
        elif request.form.get("password") != request.form.get("confirmation"):
            return apology("Sorry, but your passwords do not match", 400)

        # look for username in database
        username = request.form.get("username")

        # make sure the username doesn't exist already and then insert
        try:
            db.execute("INSERT INTO users (username, hash) VALUES (?, ?)",
                       username,
                       generate_password_hash(request.form.get("password")))
        except ValueError:
            return apology("This username already exists")

        # Query the database for the newly inserted user
        rows = db.execute("SELECT * FROM users WHERE username = ?", username)

        # Store which user logged in
        session["user_id"] = rows[0]["id"]

        # redirect the user to the home page
        return redirect("/")

    # If the User reached route via the get
    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    user_id = session["user_id"]

    # if the method is POST
    if request.method == "POST":
        symbol = request.form.get("symbol")
        shares = request.form.get("shares")

        # make sure the symbol was submitted
        if not symbol:
            return apology("You must provide a symbol", 400)
        # make sure number of shares is submitted
        if not shares:
            return apology("You must provide a number of shares", 400)
        # Make sure the number of shares is a positive number
        try:
            shares = int(shares)
            if shares <= 0:
                return apology("The number of shares must be a positive integer", 400)
        except ValueError:
            return apology("number of shares must be a positive integer", 400)
        # Query the database for the user's stocks
        stocks = db.execute(
            "SELECT symbol, SUM(shares) as total_shares FROM transactions WHERE user_id = ? GROUP BY symbol HAVING total_shares > 0", user_id)

        # Check if the user owns the stock
        user_shares = next((item for item in stocks if item["symbol"] == symbol), None)
        if not user_shares:
            return apology("Sorry, but you don't own this stock", 400)

        # Check if the user has enough shares to sell
        if shares > user_shares["total_shares"]:
            return apology("Sorry, but you don't have enough shares", 400)

        # Get the current stock price
        quote = lookup(symbol)
        if quote is None:
            return apology("Sorry, we're unable to retrieve the stock price", 500)

        # Calculate the total sale value
        sale_value = shares * quote["price"]

        # Update the user's cash
        db.execute("UPDATE users SET cash = cash + ? WHERE id = ?", sale_value, user_id)

        # Record the Sale transaction
        db.execute("INSERT INTO transactions (user_id, symbol, shares, price, type) VALUES (?,?,?,?,?)",
                   user_id, symbol, shares, quote["price"], "sell")
        flash(f"Sold {shares} shares of {symbol} for {usd(sale_value)}!")
        return redirect("/")

    else:
        # Get the user's stocks for select menu
        stocks = db.execute(
            "SELECT symbol, SUM(shares) as total_shares FROM transactions WHERE user_id = ? GROUP BY symbol HAVING total_shares > 0", user_id)
        return render_template("sell.html", stocks=stocks)

# PERSONAL TOUCH: add cash


@app.route("/add_cash", methods=["GET", "POST"])
@login_required
def add_cash():
    """Add cash to the user's account"""
    if request.method == "POST":
        amount = request.form.get("amount")

        # Validate the input
        try:
            amount = float(amount)
            if amount <= 0:
                return apology("Sorry, but the amount must be positive", 400)
        except ValueError:
            return apology("Invalid amount", 400)

        # Update the user's cash in the database
        user_id = session["user_id"]
        db.execute("UPDATE users SET cash = cash + ? WHERE id = ?", amount, user_id)

        # Flash a success message
        flash(f"Successfully added {usd(amount)} to your account!")

        # Redirect to home page
        return redirect("/")

    else:
        return render_template("add_cash.html")
