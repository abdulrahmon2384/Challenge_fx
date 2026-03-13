import os
import sys
import mysql.connector
from urllib.parse import urlparse
from dotenv import load_dotenv

# Try to import rich
try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.prompt import Prompt, FloatPrompt, IntPrompt
    from rich.align import Align
    from rich import box
except ImportError:
    print("Error: 'rich' library is required.")
    print("Please run: pip install -r requirements.txt")
    sys.exit(1)

# Load environment variables
load_dotenv()

console = Console()

# Database Connection Helper
def get_db_connection():
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        console.print("[bold red]Error:[/bold red] DATABASE_URL not found in .env file.")
        sys.exit(1)
        
    try:
        # Parse the URL manually
        # Expected format: mysql://user:password@host:port/database
        # Or standard SQLAlchemy format
        url = urlparse(db_url)
        
        # Extract components
        # Note: url.path returns '/database', so we slice [1:]
        conn = mysql.connector.connect(
            user=url.username,
            password=url.password,
            host=url.hostname,
            port=url.port if url.port else 3306,
            database=url.path[1:]
        )
        return conn
    except Exception as e:
        console.print(f"[bold red]Error connecting to database:[/bold red] {e}")
        console.print(f"[yellow]Ensure your DATABASE_URL is correct: {db_url}[/yellow]")
        sys.exit(1)

# ----------------- UTILS -----------------
def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Users Table (MySQL Syntax: AUTO_INCREMENT instead of SERIAL)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INT AUTO_INCREMENT PRIMARY KEY,
        username VARCHAR(255) UNIQUE
    );
    """)
    
    # Challenges Table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS challenges (
        id INT AUTO_INCREMENT PRIMARY KEY,
        user_id INT,
        name VARCHAR(255),
        starting_balance REAL,
        equity REAL,
        highest REAL,
        target REAL,
        trailing_dd REAL,
        daily_dd REAL,
        rr REAL,
        daily_loss_used REAL DEFAULT 0,
        type VARCHAR(50) DEFAULT 'prop'
    );
    """)
    
    # Trades Table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS trades (
        id INT AUTO_INCREMENT PRIMARY KEY,
        challenge_id INT,
        pair VARCHAR(50),
        entry REAL,
        sl REAL,
        tp REAL,
        lot REAL,
        risk REAL,
        status VARCHAR(50)
    );
    """)
    
    conn.commit()
    cur.close()
    conn.close()

def clear():
    console.clear()

def pause():
    console.input("\n[dim]Press Enter to continue...[/dim]")

# ----------------- USER -----------------
def login_or_create_user():
    clear()
    console.print(Panel(Align.center("[bold cyan]Trading Challenge Terminal[/bold cyan]\n[dim]Advanced Risk Management System[/dim]"), box=box.ROUNDED, style="blue"))
    
    username = Prompt.ask("[bold green]Enter your username[/bold green] (or new one to create)").strip()
    
    conn = get_db_connection()
    cur = conn.cursor()
    # MySQL uses %s for placeholders
    cur.execute("SELECT id FROM users WHERE username=%s", (username,))
    row = cur.fetchone()
    
    if row:
        user_id = row[0]
        console.print(f"\n[bold green]Welcome back, {username}![/bold green]")
    else:
        # MySQL: No RETURNING id
        cur.execute("INSERT INTO users(username) VALUES(%s)", (username,))
        user_id = cur.lastrowid
        conn.commit()
        console.print(f"\n[bold green]User '{username}' created![/bold green]")
    
    cur.close()
    conn.close()
    pause()
    return user_id, username

# ----------------- CHALLENGE -----------------
def create_challenge(user_id):
    clear()
    console.print(Panel("[bold]Create New Account[/bold]", style="cyan"))
    
    ctype = Prompt.ask("Account Type", choices=["Prop Firm", "Live Trading"], default="Prop Firm")
    name = Prompt.ask("Account Name").strip()
    start = FloatPrompt.ask("Starting Balance")
    
    if ctype == "Prop Firm":
        target_pct = FloatPrompt.ask("Target %")
        trailing = FloatPrompt.ask("Trailing Drawdown %")
        daily = FloatPrompt.ask("Daily Drawdown %")
        rr = FloatPrompt.ask("Reward Ratio (RR)")
        target_equity = start * (1 + target_pct/100)
        c_type_val = 'prop'
        trailing_val = trailing/100
        daily_val = daily/100
    else:
        target_equity = 0
        trailing_val = 0
        daily_val = 0
        rr = 0
        c_type_val = 'live'

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
    INSERT INTO challenges(user_id,name,starting_balance,equity,highest,target,trailing_dd,daily_dd,rr,type)
    VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """, (user_id,name,start,start,start,target_equity,trailing_val,daily_val,rr,c_type_val))
    conn.commit()
    cur.close()
    conn.close()
    console.print("\n[bold green]Account created successfully![/bold green]")
    pause()
    
def list_challenges(user_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id,name,equity,target,daily_loss_used,highest,trailing_dd,daily_dd,rr,starting_balance,type FROM challenges WHERE user_id=%s", (user_id,))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows

def select_challenge(user_id):
    challenges = list_challenges(user_id)
    if not challenges:
        console.print("[yellow]No accounts found. Create one first.[/yellow]")
        pause()
        return None
    clear()
    
    table = Table(title="Your Accounts", box=box.SIMPLE)
    table.add_column("ID", justify="center", style="cyan", no_wrap=True)
    table.add_column("Name", style="magenta")
    table.add_column("Type", style="yellow")
    table.add_column("Equity", justify="right", style="green")
    
    for c in challenges:
        c_type = c[10] if len(c) > 10 else 'prop'
        table.add_row(str(c[0]), c[1], c_type.upper(), f"{c[2]:.2f}")
        
    console.print(table)
    console.print("\n[dim]Enter 'B' to go back[/dim]")
    
    choice = Prompt.ask("Select ID").strip()
    if choice.lower() == 'b':
        return None
    if choice.isdigit():
        cid = int(choice)
        for c in challenges:
            if c[0] == cid:
                return cid
    console.print("[red]Invalid choice[/red]")
    pause()
    return None

def load_challenge_data(challenge_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM challenges WHERE id=%s", (challenge_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    if not row: return None
    
    c_type = row[11] if len(row) > 11 else 'prop'
    
    return {
        'id': row[0],'user_id': row[1],'name': row[2],
        'starting_balance': row[3],'equity': row[4],'highest': row[5],
        'target': row[6],'trailing_dd': row[7],'daily_dd': row[8],
        'rr': row[9],'daily_loss_used': row[10], 'type': c_type
    }

# ----------------- RISK & LOT -----------------
def calculate_next_risk(challenge):
    conn = get_db_connection()
    cur = conn.cursor()
    # Handle NULL sum result (MySQL returns None if no rows match)
    cur.execute("SELECT SUM(risk) FROM trades WHERE challenge_id=%s AND status='open'", (challenge['id'],))
    result = cur.fetchone()
    total_open_risk = float(result[0]) if result and result[0] is not None else 0.0
    cur.close()
    conn.close()
    
    equity = challenge['equity']
    
    if challenge['type'] == 'live':
        if equity < 10:
            risk = equity * 0.02
        elif equity < 110:
            risk = 5.0
        else:
            steps = int(equity / 110)
            risk = 10 * (2 ** (steps - 1))
        return max(risk, 0), total_open_risk

    else:
        highest = challenge['highest']
        target = challenge['target']
        trailing = challenge['trailing_dd']
        daily_limit = challenge['daily_dd']
        daily_used = challenge['daily_loss_used']
        rr = challenge['rr']
        
        floor = highest * (1 - trailing)
        max_dd_risk = equity - floor
        target_risk = (target - equity)/rr
        daily_allowance = daily_limit * challenge['starting_balance']
        daily_risk = daily_allowance - daily_used - total_open_risk
        
        risk = min(max_dd_risk, target_risk, daily_risk)
        return max(risk,0), total_open_risk

def calculate_lot(pair, entry, sl, risk):
    pair = pair.upper()
    delta_price = abs(entry - sl)
    
    if delta_price == 0: return 0
    
    if "XAU" in pair:
        lot = risk / (delta_price * 100)
    elif pair.endswith("USD"):
        lot = risk / (delta_price * 100000)
    elif pair.startswith("USD"):
        lot = (risk * entry) / (delta_price * 100000)
    else:
        lot = risk / (delta_price * 100000)

    return round(lot, 2)

# ----------------- TRADES -----------------
def open_trade(user_id, challenge_id):
    challenge = load_challenge_data(challenge_id)
    risk, _ = calculate_next_risk(challenge)
    
    clear()
    console.print(Panel(f"[bold]Open Trade for '{challenge['name']}'[/bold]", style="blue"))
    
    label = "Suggested Risk" if challenge['type'] == 'live' else "Next Risk Allowed"
    console.print(f"{label}: [bold green]{risk:.2f}[/bold green]")
    
    if risk <= 0:
        msg = "Your daily limit is reached." if challenge['type'] == 'prop' else "Insufficient balance."
        console.print(Panel(f"\n[bold red]No available risk.[/bold red]\n[yellow]{msg}[/yellow]", style="red"))
        pause()
        return

    common_pairs = ["GBPUSD", "EURUSD", "AUDUSD", "XAUUSD", "USDCAD", "USDNZD", "Custom"]
    pair_choice = Prompt.ask("Select Pair", choices=common_pairs, default="GBPUSD")
    pair = Prompt.ask("Enter Custom Pair Symbol").upper() if pair_choice == "Custom" else pair_choice

    entry = FloatPrompt.ask("Entry Price")
    sl = FloatPrompt.ask("Stop Loss")
    tp = FloatPrompt.ask("Take Profit")
    
    lot = calculate_lot(pair, entry, sl, risk)
    
    console.print(Panel(f"Suggested Lot: [bold cyan]{lot}[/bold cyan] | Risk: [bold red]{risk:.2f}[/bold red]", style="white"))
    
    if Prompt.ask("Confirm Trade?", choices=["y", "n"], default="y") == "y":
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
        INSERT INTO trades(challenge_id,pair,entry,sl,tp,lot,risk,status)
        VALUES(%s,%s,%s,%s,%s,%s,%s,%s)
        """,(challenge_id,pair,entry,sl,tp,lot,risk,"open"))
        conn.commit()
        cur.close()
        conn.close()
        console.print("[green]Trade Opened![/green]")
    else:
        console.print("[yellow]Trade Cancelled[/yellow]")
    pause()

def list_open_trades(challenge_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id,pair,entry,sl,tp,lot,risk,status FROM trades WHERE challenge_id=%s AND status='open'", (challenge_id,))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    
    clear()
    if not rows:
        console.print(Panel("[yellow]No open trades.[/yellow]", title=f"Trades for Challenge ID {challenge_id}"))
    else:
        table = Table(title=f"Open Trades - ID {challenge_id}", box=box.ROUNDED)
        table.add_column("ID", style="cyan", justify="center")
        table.add_column("Pair", style="bold white")
        table.add_column("Entry", justify="right")
        table.add_column("SL", justify="right", style="red")
        table.add_column("TP", justify="right", style="green")
        table.add_column("Lot", justify="center")
        table.add_column("Risk", justify="right", style="bold red")

        for r in rows:
            table.add_row(str(r[0]), r[1], str(r[2]), str(r[3]), str(r[4]), str(r[5]), f"{r[6]:.2f}")
        
        console.print(table)
    pause()

def view_trade_history(challenge_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id,pair,lot,risk,status FROM trades WHERE challenge_id=%s AND status!='open' ORDER BY id DESC", (challenge_id,))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    
    clear()
    if not rows:
        console.print(Panel("[yellow]No closed trades found.[/yellow]", title=f"History for Challenge ID {challenge_id}"))
    else:
        table = Table(title=f"Trade History - ID {challenge_id}", box=box.SIMPLE)
        table.add_column("ID", style="dim", justify="center")
        table.add_column("Pair", style="bold white")
        table.add_column("Lot", justify="center")
        table.add_column("Risk", justify="right")
        table.add_column("Result", justify="center")

        for r in rows:
            status_style = "green" if r[4] == "win" else "red"
            if r[4] == "be": status_style = "yellow"
            table.add_row(str(r[0]), r[1], str(r[2]), f"{r[3]:.2f}", f"[{status_style}]{r[4].upper()}[/{status_style}]")
        
        console.print(table)
    pause()

def update_trade(challenge_id):
    trade_id = IntPrompt.ask("Trade ID to update")
    status = Prompt.ask("Status", choices=["win", "loss", "be"], default="win")
    
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT risk FROM trades WHERE id=%s AND challenge_id=%s", (trade_id,challenge_id))
    row = cur.fetchone()
    
    if not row:
        console.print("[red]Trade not found[/red]")
        cur.close()
        conn.close()
        pause()
        return
        
    risk = row[0]
    challenge = load_challenge_data(challenge_id)
    equity = challenge['equity']
    daily_used = challenge['daily_loss_used']
    rr = challenge['rr']
    
    if status=="win":
        if challenge['type'] == 'prop':
            equity += risk * rr
        else:
            if rr == 0:
                pnl = FloatPrompt.ask("Profit Amount")
                equity += pnl
            else:
                equity += risk * rr
        daily_used = 0 
    elif status=="loss":
        equity -= risk
        daily_used += risk
    elif status=="be":
        pass
        
    highest = max(equity, challenge['highest'])
        
    cur.execute("UPDATE challenges SET equity=%s, highest=%s, daily_loss_used=%s WHERE id=%s", (equity,highest,daily_used,challenge_id))
    cur.execute("UPDATE trades SET status=%s WHERE id=%s", (status,trade_id))
    conn.commit()
    cur.close()
    conn.close()
    console.print(f"[green]Trade updated to {status.upper()}[/green]")
    pause()

def account_dashboard(user_id, challenge_id):
    while True:
        clear()
        challenge = load_challenge_data(challenge_id)
        if not challenge:
            console.print("[red]Error loading account data.[/red]")
            pause()
            return

        next_risk, open_risk = calculate_next_risk(challenge)
        
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM trades WHERE challenge_id=%s AND status='open'", (challenge['id'],))
        open_trades_count = cur.fetchone()[0]
        cur.close()
        conn.close()
        
        equity = challenge['equity']
        start_bal = challenge['starting_balance']
        equity_color = "green" if equity >= start_bal else "red"
        
        growth_pct = ((equity - start_bal) / start_bal) * 100 if start_bal > 0 else 0.0
        growth_color = "green" if growth_pct >= 0 else "red"
        growth_str = f"[{growth_color}]{growth_pct:+.2f}%[/{growth_color}]"

        grid = Table.grid(expand=True)
        grid.add_column(justify="center", ratio=1)
        grid.add_column(justify="center", ratio=1)
        grid.add_column(justify="center", ratio=1)
        
        grid.add_row(
            Panel(f"[{equity_color}]{equity:.2f}[/{equity_color}]", title="Current Equity", style="bold"),
            Panel(growth_str, title="Total Growth", style="bold"),
            Panel(f"[magenta]{open_trades_count}[/magenta]", title="Open Trades", style="bold")
        )

        if challenge['type'] == 'live':
            grid.add_row(
                Panel(f"[blue]{challenge['highest']:.2f}[/blue]", title="High Watermark", style="bold"),
                Panel(f"[bold cyan]{next_risk:.2f}[/bold cyan]", title="SUGGESTED RISK", style="bold white", border_style="cyan"),
                Panel("[dim]N/A[/dim]", title="Daily Limit", style="dim")
            )
            subtitle_text = "Live Trading Strategy"
        else:
            grid.add_row(
                Panel(f"[red]{challenge['daily_loss_used']:.2f}[/red]", title="Daily Loss Used", style="bold"),
                Panel(f"[bold green]{next_risk:.2f}[/bold green]", title="NEXT RISK ALLOWED", style="bold white", border_style="green"),
                Panel(f"[gold1]{challenge['target']:.2f}[/gold1]", title="Profit Target", style="bold")
            )
            subtitle_text = "Prop Firm Risk Assistant"
        
        main_panel = Panel(
            Align.center(grid),
            title=f"[bold cyan]Account: {challenge['name']} ({challenge['type'].upper()})[/bold cyan]",
            subtitle=f"[dim]{subtitle_text}[/dim]",
            box=box.HEAVY,
            padding=(1, 2)
        )
        console.print(main_panel)
        
        console.print(Panel(
            "[1] Open Trade          [2] List Open Trades\n"
            "[3] Trade History       [4] Update Trade Result\n"
            "[5] Back to Main Menu",
            title="Account Actions",
            border_style="blue",
            box=box.ROUNDED
        ))
        
        choice = Prompt.ask("Select Option", choices=["1", "2", "3", "4", "5"])
        
        if choice=="1":
            open_trade(user_id, challenge['id'])
        elif choice=="2":
            list_open_trades(challenge['id'])
        elif choice=="3":
            view_trade_history(challenge['id'])
        elif choice=="4":
            update_trade(challenge['id'])
        elif choice=="5":
            return

def main_menu(user_id, username):
    while True:
        clear()
        console.print(Panel(
            Align.center(f"[bold]Welcome, {username}![/bold]\nSelect an option to manage your trading accounts."),
            title="Main Menu",
            box=box.DOUBLE,
            style="magenta"
        ))
        
        console.print("[1] Add Account")
        console.print("[2] Select Existing Account")
        console.print("[3] Logout")
        
        choice = Prompt.ask("\nSelect Option", choices=["1", "2", "3"])
        
        if choice == "1":
            create_challenge(user_id)
        elif choice == "2":
            cid = select_challenge(user_id)
            if cid:
                account_dashboard(user_id, cid)
        elif choice == "3":
            return

def main():
    init_db()
    user_id, username = login_or_create_user()
    main_menu(user_id, username)

if __name__=="__main__":
    main()
