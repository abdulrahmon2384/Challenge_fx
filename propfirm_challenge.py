import sqlite3
import os
import sys

DB = "challenge_terminal.db"

# ----------------- UTILS -----------------
def init_db():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY,
        username TEXT UNIQUE
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS challenges(
        id INTEGER PRIMARY KEY,
        user_id INTEGER,
        name TEXT,
        starting_balance REAL,
        equity REAL,
        highest REAL,
        target REAL,
        trailing_dd REAL,
        daily_dd REAL,
        rr REAL,
        daily_loss_used REAL DEFAULT 0
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS trades(
        id INTEGER PRIMARY KEY,
        challenge_id INTEGER,
        pair TEXT,
        entry REAL,
        sl REAL,
        tp REAL,
        lot REAL,
        risk REAL,
        status TEXT
    )
    """)
    conn.commit()
    conn.close()

def clear():
    os.system('cls' if os.name=='nt' else 'clear')

def pause():
    input("\nPress Enter to continue...")

# ----------------- USER -----------------
def login_or_create_user():
    clear()
    print("=== Trading Challenge Terminal ===\n")
    username = input("Enter your username (or new one to create): ").strip()
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT id FROM users WHERE username=?", (username,))
    row = cur.fetchone()
    if row:
        user_id = row[0]
        print(f"Welcome back, {username}!")
    else:
        cur.execute("INSERT INTO users(username) VALUES(?)", (username,))
        conn.commit()
        user_id = cur.lastrowid
        print(f"User '{username}' created!")
    conn.close()
    pause()
    return user_id, username

# ----------------- CHALLENGE -----------------
def create_challenge(user_id):
    clear()
    print("=== Create New Challenge ===")
    name = input("Challenge Name: ").strip()
    start = float(input("Starting Balance: "))
    target = float(input("Target %: "))
    trailing = float(input("Trailing Drawdown %: "))
    daily = float(input("Daily Drawdown %: "))
    rr = float(input("Reward Ratio (RR): "))

    target_equity = start * (1 + target/100)
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("""
    INSERT INTO challenges(user_id,name,starting_balance,equity,highest,target,trailing_dd,daily_dd,rr)
    VALUES(?,?,?,?,?,?,?,?,?)
    """, (user_id,name,start,start,start,target_equity,trailing/100,daily/100,rr))
    conn.commit()
    conn.close()
    print("Challenge created successfully!")
    pause()
    
    
def list_challenges(user_id):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT id,name,equity,target,daily_loss_used,highest,trailing_dd,daily_dd,rr,starting_balance FROM challenges WHERE user_id=?", (user_id,))
    rows = cur.fetchall()
    conn.close()
    return rows

def select_challenge(user_id):
    challenges = list_challenges(user_id)
    if not challenges:
        print("No challenges found. Create one first.")
        pause()
        return None
    clear()
    print("=== Your Challenges ===")
    for c in challenges:
        print(f"{c[0]}: {c[1]} | Equity: {c[2]:.2f} | Target: {c[3]:.2f}")
    print("B: Back")
    choice = input("Select Challenge ID: ").strip()
    if choice.lower() == 'b':
        return None
    if choice.isdigit():
        cid = int(choice)
        for c in challenges:
            if c[0] == cid:
                return cid
    print("Invalid choice")
    pause()
    return None

def load_challenge_data(challenge_id):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT * FROM challenges WHERE id=?", (challenge_id,))
    row = cur.fetchone()
    conn.close()
    if not row: return None
    return {
        'id': row[0],'user_id': row[1],'name': row[2],
        'starting_balance': row[3],'equity': row[4],'highest': row[5],
        'target': row[6],'trailing_dd': row[7],'daily_dd': row[8],
        'rr': row[9],'daily_loss_used': row[10]
    }

# ----------------- RISK & LOT -----------------
def calculate_next_risk(challenge):
    equity = challenge['equity']
    highest = challenge['highest']
    target = challenge['target']
    trailing = challenge['trailing_dd']
    daily_limit = challenge['daily_dd']
    daily_used = challenge['daily_loss_used']
    rr = challenge['rr']
    floor = highest * (1 - trailing)
    max_dd_risk = equity - floor
    target_risk = (target - equity)/rr
    daily_risk = daily_limit * challenge['starting_balance'] - daily_used
    risk = min(max_dd_risk, target_risk, daily_risk)
    return max(risk,0)

def pip_value(pair):
    if "JPY" in pair:
        return 0.01
    return 0.0001

def calculate_lot(pair, entry, sl, risk, pip_worth=10):
    pip = pip_value(pair)
    stop_pips = abs(entry - sl)/pip
    lot = risk/(stop_pips*pip_worth)
    return round(lot,3)

# ----------------- TRADES -----------------
def open_trade(user_id, challenge_id):
    challenge = load_challenge_data(challenge_id)
    risk = calculate_next_risk(challenge)
    clear()
    print(f"=== Open Trade for Challenge '{challenge['name']}' ===")
    print(f"Next Risk Allowed: {risk:.2f}")
    pair = input("Pair: ").upper()
    entry = float(input("Entry: "))
    sl = float(input("Stop Loss: "))
    tp = float(input("Take Profit: "))
    lot = calculate_lot(pair, entry, sl, risk)
    print(f"Suggested Lot: {lot} | Risk: {risk:.2f}")
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("""
    INSERT INTO trades(challenge_id,pair,entry,sl,tp,lot,risk,status)
    VALUES(?,?,?,?,?,?,?,?)
    """,(challenge_id,pair,entry,sl,tp,lot,risk,"open"))
    conn.commit()
    conn.close()
    pause()

def list_open_trades(challenge_id):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT id,pair,entry,sl,tp,lot,risk,status FROM trades WHERE challenge_id=? AND status='open'", (challenge_id,))
    rows = cur.fetchall()
    conn.close()
    clear()
    print(f"=== Open Trades for Challenge ID {challenge_id} ===")
    if not rows:
        print("No open trades.")
    for r in rows:
        print(f"ID:{r[0]} | {r[1]} Entry:{r[2]} SL:{r[3]} TP:{r[4]} Lot:{r[5]} Risk:{r[6]:.2f} Status:{r[7]}")
    pause()

def update_trade(challenge_id):
    trade_id = int(input("Trade ID to update: "))
    status = input("Status (win/loss/be/custom): ").lower()
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT risk FROM trades WHERE id=? AND challenge_id=?", (trade_id,challenge_id))
    row = cur.fetchone()
    if not row:
        print("Trade not found")
        conn.close()
        pause()
        return
    risk = row[0]
    challenge = load_challenge_data(challenge_id)
    equity = challenge['equity']
    daily_used = challenge['daily_loss_used']
    rr = challenge['rr']
    if status=="win":
        equity += risk*rr
        daily_used = 0
    elif status=="loss":
        equity -= risk
        daily_used += risk
    elif status=="be":
        pass
    if equity>challenge['highest']:
        highest=equity
    else:
        highest=challenge['highest']
    cur.execute("UPDATE challenges SET equity=?, highest=?, daily_loss_used=? WHERE id=?", (equity,highest,daily_used,challenge_id))
    cur.execute("UPDATE trades SET status=? WHERE id=?", (status,trade_id))
    conn.commit()
    conn.close()
    print("Trade updated.")
    pause()

# ----------------- DASHBOARD -----------------
def dashboard(user_id, username):
    while True:
        clear()
        print(f"=== Trading Terminal | User: {username} ===\n")
        challenges = list_challenges(user_id)
        if not challenges:
            print("No challenges created. Create one first.\n")
            print("1. Create Challenge")
            print("2. Logout")
            choice = input("Select: ")
            if choice=="1":
                create_challenge(user_id)
            elif choice=="2":
                return
            continue
        # Pick first challenge as default for dashboard
        challenge = load_challenge_data(challenges[0][0])
        next_risk = calculate_next_risk(challenge)
        conn = sqlite3.connect(DB)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM trades WHERE challenge_id=? AND status='open'", (challenge['id'],))
        open_trades_count = cur.fetchone()[0]
        conn.close()
        # Dashboard summary
        print(f"Challenge: {challenge['name']}")
        print(f"Equity: {challenge['equity']:.2f} | Highest: {challenge['highest']:.2f} | Target: {challenge['target']:.2f}")
        print(f"Daily Loss Used: {challenge['daily_loss_used']:.2f} | Next Risk: {next_risk:.2f}")
        print(f"Open Trades: {open_trades_count}\n")
        # Menu
        print("1. Create Challenge")
        print("2. Select Challenge")
        print("3. Open Trade")
        print("4. List Open Trades")
        print("5. Update Trade Result")
        print("6. Logout")
        choice = input("Select: ").strip()
        if choice=="1":
            create_challenge(user_id)
        elif choice=="2":
            select_challenge(user_id)
        elif choice=="3":
            open_trade(user_id, challenge['id'])
        elif choice=="4":
            list_open_trades(challenge['id'])
        elif choice=="5":
            update_trade(challenge['id'])
        elif choice=="6":
            return
        else:
            print("Invalid choice")
            pause()

# ----------------- MAIN -----------------
def main():
    init_db()
    user_id, username = login_or_create_user()
    dashboard(user_id, username)

if __name__=="__main__":
    main()