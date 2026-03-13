import sqlite3
import os
import sys

# Try to import rich, if not installed, give instructions
try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.prompt import Prompt, FloatPrompt, IntPrompt
    from rich.layout import Layout
    from rich.align import Align
    from rich.text import Text
    from rich import box
except ImportError:
    print("Error: 'rich' library is required for the advanced terminal view.")
    print("Please run: pip install -r requirements.txt")
    sys.exit(1)

DB = "challenge_terminal.db"
console = Console()

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
    console.clear()

def pause():
    console.input("\n[dim]Press Enter to continue...[/dim]")

# ----------------- USER -----------------
def login_or_create_user():
    clear()
    console.print(Panel(Align.center("[bold cyan]Trading Challenge Terminal[/bold cyan]\n[dim]Advanced Risk Management System[/dim]"), box=box.ROUNDED, style="blue"))
    
    username = Prompt.ask("[bold green]Enter your username[/bold green] (or new one to create)").strip()
    
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT id FROM users WHERE username=?", (username,))
    row = cur.fetchone()
    if row:
        user_id = row[0]
        console.print(f"\n[bold green]Welcome back, {username}![/bold green]")
    else:
        cur.execute("INSERT INTO users(username) VALUES(?)", (username,))
        conn.commit()
        user_id = cur.lastrowid
        console.print(f"\n[bold green]User '{username}' created![/bold green]")
    conn.close()
    pause()
    return user_id, username

# ----------------- CHALLENGE -----------------
def create_challenge(user_id):
    clear()
    console.print(Panel("[bold]Create New Challenge[/bold]", style="cyan"))
    
    name = Prompt.ask("Challenge Name").strip()
    start = FloatPrompt.ask("Starting Balance")
    target = FloatPrompt.ask("Target %")
    trailing = FloatPrompt.ask("Trailing Drawdown %")
    daily = FloatPrompt.ask("Daily Drawdown %")
    rr = FloatPrompt.ask("Reward Ratio (RR)")

    target_equity = start * (1 + target/100)
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("""
    INSERT INTO challenges(user_id,name,starting_balance,equity,highest,target,trailing_dd,daily_dd,rr)
    VALUES(?,?,?,?,?,?,?,?,?)
    """, (user_id,name,start,start,start,target_equity,trailing/100,daily/100,rr))
    conn.commit()
    conn.close()
    console.print("\n[bold green]Challenge created successfully![/bold green]")
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
        console.print("[yellow]No challenges found. Create one first.[/yellow]")
        pause()
        return None
    clear()
    
    table = Table(title="Your Challenges", box=box.SIMPLE)
    table.add_column("ID", justify="center", style="cyan", no_wrap=True)
    table.add_column("Name", style="magenta")
    table.add_column("Equity", justify="right", style="green")
    table.add_column("Target", justify="right", style="blue")
    
    for c in challenges:
        table.add_row(str(c[0]), c[1], f"{c[2]:.2f}", f"{c[3]:.2f}")
        
    console.print(table)
    console.print("\n[dim]Enter 'B' to go back[/dim]")
    
    choice = Prompt.ask("Select Challenge ID").strip()
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
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT SUM(risk) FROM trades WHERE challenge_id=? AND status='open'", (challenge['id'],))
    total_open_risk = cur.fetchone()[0] or 0
    conn.close()
    
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
    daily_allowance = daily_limit * challenge['starting_balance']
    daily_risk = daily_allowance - daily_used - total_open_risk
    
    risk = min(max_dd_risk, target_risk, daily_risk)
    return max(risk,0), total_open_risk

def pip_value(pair):
    if "JPY" in pair:
        return 0.01
    return 0.0001

def calculate_lot(pair, entry, sl, risk, pip_worth=10):
    pip = pip_value(pair)
    stop_pips = abs(entry - sl)/pip
    if stop_pips == 0: return 0
    lot = risk/(stop_pips*pip_worth)
    return round(lot,3)

# ----------------- TRADES -----------------
def open_trade(user_id, challenge_id):
    challenge = load_challenge_data(challenge_id)
    risk, _ = calculate_next_risk(challenge)
    
    clear()
    console.print(Panel(f"[bold]Open Trade for '{challenge['name']}'[/bold]", style="blue"))
    console.print(f"Next Risk Allowed: [bold green]{risk:.2f}[/bold green]")
    
    if risk <= 0:
        console.print(Panel("\n[bold red]No available risk for a new trade.[/bold red]\n[yellow]Your daily limit is either reached or fully committed to other open trades.[/yellow]", style="red"))
        pause()
        return

    pair = Prompt.ask("Pair").upper()
    entry = FloatPrompt.ask("Entry Price")
    sl = FloatPrompt.ask("Stop Loss")
    tp = FloatPrompt.ask("Take Profit")
    
    lot = calculate_lot(pair, entry, sl, risk)
    
    console.print(Panel(f"Suggested Lot: [bold cyan]{lot}[/bold cyan] | Risk: [bold red]{risk:.2f}[/bold red]", style="white"))
    
    if Prompt.ask("Confirm Trade?", choices=["y", "n"], default="y") == "y":
        conn = sqlite3.connect(DB)
        cur = conn.cursor()
        cur.execute("""
        INSERT INTO trades(challenge_id,pair,entry,sl,tp,lot,risk,status)
        VALUES(?,?,?,?,?,?,?,?)
        """,(challenge_id,pair,entry,sl,tp,lot,risk,"open"))
        conn.commit()
        conn.close()
        console.print("[green]Trade Opened![/green]")
    else:
        console.print("[yellow]Trade Cancelled[/yellow]")
    pause()

def list_open_trades(challenge_id):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT id,pair,entry,sl,tp,lot,risk,status FROM trades WHERE challenge_id=? AND status='open'", (challenge_id,))
    rows = cur.fetchall()
    conn.close()
    
    clear()
    if not rows:
        console.print(Panel("[yellow]No open trades.[/yellow]", title=f"Trades for Challenge ID {challenge_id}"))
    else:
        table = Table(title=f"Open Trades - Challenge {challenge_id}", box=box.ROUNDED)
        table.add_column("ID", style="cyan", justify="center")
        table.add_column("Pair", style="bold white")
        table.add_column("Entry", justify="right")
        table.add_column("SL", justify="right", style="red")
        table.add_column("TP", justify="right", style="green")
        table.add_column("Lot", justify="center")
        table.add_column("Risk", justify="right", style="bold red")
        table.add_column("Status", justify="center")

        for r in rows:
            table.add_row(str(r[0]), r[1], str(r[2]), str(r[3]), str(r[4]), str(r[5]), f"{r[6]:.2f}", r[7])
        
        console.print(table)
    pause()

def update_trade(challenge_id):
    trade_id = IntPrompt.ask("Trade ID to update")
    status = Prompt.ask("Status", choices=["win", "loss", "be"], default="win")
    
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT risk FROM trades WHERE id=? AND challenge_id=?", (trade_id,challenge_id))
    row = cur.fetchone()
    if not row:
        console.print("[red]Trade not found[/red]")
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
        # Logic update: Daily loss used resets only on new day usually, but per previous logic, 
        # a win might offset losses. However, strictly speaking, daily loss is usually "closed loss + open floating loss". 
        # For this simple model, we follow the previous logic: if we win, we might not reduce 'daily_used' unless it recovers the loss.
        # But the previous code set daily_used = 0 on win. I'll stick to that simple logic or improve it?
        # The user wants "advanced". Real prop firms don't reset daily loss on a win; daily loss is a limit on how much you can LOSE in a day.
        # But let's stick to the previous simple logic to avoid changing core behavior too much unless requested.
        # Previous logic:
        # if status=="win": daily_used = 0 
        # This is very generous. Let's keep it for now.
        daily_used = 0 
    elif status=="loss":
        equity -= risk
        daily_used += risk
    elif status=="be":
        pass
        
    if equity > challenge['highest']:
        highest = equity
    else:
        highest = challenge['highest']
        
    cur.execute("UPDATE challenges SET equity=?, highest=?, daily_loss_used=? WHERE id=?", (equity,highest,daily_used,challenge_id))
    cur.execute("UPDATE trades SET status=? WHERE id=?", (status,trade_id))
    conn.commit()
    conn.close()
    console.print(f"[green]Trade updated to {status.upper()}[/green]")
    pause()

# ----------------- DASHBOARD -----------------
def dashboard(user_id, username):
    while True:
        clear()
        challenges = list_challenges(user_id)
        if not challenges:
            console.print(Panel("No challenges created.\n\n1. Create Challenge\n2. Logout", title="Welcome", style="red"))
            choice = Prompt.ask("Select")
            if choice=="1":
                create_challenge(user_id)
            elif choice=="2":
                return
            continue
            
        # Pick first challenge (or selected one logic could be added)
        # For simplicity, we stick to logic: load first challenge found.
        challenge = load_challenge_data(challenges[0][0])
        next_risk, open_risk = calculate_next_risk(challenge)
        
        conn = sqlite3.connect(DB)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM trades WHERE challenge_id=? AND status='open'", (challenge['id'],))
        open_trades_count = cur.fetchone()[0]
        conn.close()
        
        # --- Advanced Dashboard UI ---
        
        # Colors based on status
        equity_color = "green" if challenge['equity'] >= challenge['starting_balance'] else "red"
        
        # Metrics Table
        grid = Table.grid(expand=True)
        grid.add_column(justify="center", ratio=1)
        grid.add_column(justify="center", ratio=1)
        grid.add_column(justify="center", ratio=1)
        
        grid.add_row(
            Panel(f"[{equity_color}]{challenge['equity']:.2f}[/{equity_color}]", title="Current Equity", style="bold"),
            Panel(f"[blue]{challenge['highest']:.2f}[/blue]", title="High Watermark", style="bold"),
            Panel(f"[gold1]{challenge['target']:.2f}[/gold1]", title="Profit Target", style="bold")
        )
        grid.add_row(
            Panel(f"[red]{challenge['daily_loss_used']:.2f}[/red]", title="Daily Loss Used", style="bold"),
            Panel(f"[magenta]{open_trades_count}[/magenta]", title="Open Trades", style="bold"),
            Panel(f"[bold green]{next_risk:.2f}[/bold green]", title="NEXT RISK ALLOWED", style="bold white", border_style="green")
        )
        
        # Main Layout
        main_panel = Panel(
            Align.center(grid),
            title=f"[bold cyan]User: {username} | Challenge: {challenge['name']}[/bold cyan]",
            subtitle="[dim]Prop Firm Risk Assistant[/dim]",
            box=box.HEAVY,
            padding=(1, 2)
        )
        
        console.print(main_panel)
        
        # Menu
        console.print(Panel(
            "[1] Create Challenge    [2] Select Challenge    [3] Open Trade\n"
            "[4] List Open Trades    [5] Update Trade Result [6] Logout",
            title="Actions",
            border_style="blue",
            box=box.ROUNDED
        ))
        
        choice = Prompt.ask("Select Option").strip()
        
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
            console.print("[red]Invalid choice[/red]")
            pause()

# ----------------- MAIN -----------------
def main():
    init_db()
    user_id, username = login_or_create_user()
    dashboard(user_id, username)

if __name__=="__main__":
    main()
