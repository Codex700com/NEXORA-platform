import os, sqlite3, secrets, string, hashlib, hmac
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from functools import wraps
from flask import Flask, request, redirect, session, render_template, flash, url_for, send_from_directory

BASE=os.path.dirname(os.path.abspath(__file__))
DB=os.path.join(BASE,"codex700.db")
app=Flask(__name__)
app.secret_key=os.environ.get("SECRET_KEY","change-this-before-production")

PLANS={
 "CX-1":{"series":"CX series","price":250000,"daily":20000,"days":30,"total":600000},
 "CXM-1":{"series":"CXM series","price":48000,"daily":9800,"days":20,"total":196000},
 "CXM-2":{"series":"CXM series","price":88000,"daily":20000,"days":25,"total":500000},
 "CX-2":{"series":"CX series","price":500000,"daily":40000,"days":30,"total":1200000},
 "BM-1":{"series":"BM series","price":1000000,"daily":85000,"days":30,"total":2550000},
 "BM-2":{"series":"BM series","price":2000000,"daily":180000,"days":30,"total":5400000},
 "DS-3":{"series":"DS series","price":3500000,"daily":320000,"days":30,"total":9600000},
 "DS-4":{"series":"DS series","price":5000000,"daily":500000,"days":30,"total":15000000},
 "CX-3":{"series":"CX series","price":7500000,"daily":700000,"days":30,"total":21000000},
 "CX-4":{"series":"CX series","price":10000000,"daily":950000,"days":30,"total":28500000},
 "BM-3":{"series":"BM series","price":15000000,"daily":1450000,"days":30,"total":43500000},
 "BM-4":{"series":"BM series","price":25000000,"daily":2450000,"days":30,"total":73500000},
 "DS-5":{"series":"DS series","price":50000000,"daily":5000000,"days":30,"total":150000000},
 "DS-6":{"series":"DS series","price":100000000,"daily":10000000,"days":30,"total":300000000},
}
REWARDS=[(120,750000),(100,500000),(60,275000),(30,150000),(15,98000),(6,45000)]



# CODEX_A1_A2_A6
PLANS.update({
    "A1": {
        "series": "AI series",
        "price": 50000,
        "daily": 208700.66 / 19,
        "days": 19,
        "total": 208700.66
    },
    "A2": {
        "series": "AI series",
        "price": 100000,
        "daily": 478000 / 19,
        "days": 19,
        "total": 478000
    },
    "A6": {
        "series": "AI series",
        "price": 1000000,
        "daily": 2500000 / 3,
        "days": 3,
        "total": 2500000
    },
})

def db():
    con=sqlite3.connect(DB,timeout=30)
    con.row_factory=sqlite3.Row
    con.execute("PRAGMA busy_timeout=30000")
    return con

def now(): return datetime.now(timezone.utc).isoformat(timespec="seconds")
def month_start():
    n=datetime.now(timezone.utc)
    return n.replace(day=1,hour=0,minute=0,second=0,microsecond=0)
def previous_month_start():
    n=month_start()
    return n.replace(year=n.year-1,month=12) if n.month==1 else n.replace(month=n.month-1)
def pw_hash(p): return hashlib.sha256(p.encode()).hexdigest()
def make_code(con):
    chars=string.ascii_uppercase+string.digits
    while True:
        code=''.join(secrets.choice(chars) for _ in range(8))
        if not con.execute("SELECT 1 FROM users WHERE invite_code=?",(code,)).fetchone(): return code

def init_db():
    con=db()
    con.executescript("""
    CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY AUTOINCREMENT,phone TEXT UNIQUE NOT NULL,password TEXT NOT NULL,invite_code TEXT UNIQUE NOT NULL,invited_by INTEGER,balance REAL NOT NULL DEFAULT 0,wallet REAL NOT NULL DEFAULT 0,points INTEGER NOT NULL DEFAULT 0,display_name TEXT NOT NULL DEFAULT '',mtn_number TEXT NOT NULL DEFAULT '',airtel_number TEXT NOT NULL DEFAULT '',usdt_wallet TEXT NOT NULL DEFAULT '',notifications_enabled INTEGER NOT NULL DEFAULT 1,created_at TEXT NOT NULL,is_admin INTEGER NOT NULL DEFAULT 0,salary_claimed_month TEXT,reward_claimed_month TEXT,manager_phone TEXT);
    CREATE TABLE IF NOT EXISTS transactions(id INTEGER PRIMARY KEY AUTOINCREMENT,uid INTEGER NOT NULL,kind TEXT NOT NULL,amount REAL NOT NULL DEFAULT 0,status TEXT NOT NULL DEFAULT 'PENDING',reference TEXT,created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS announcements(id INTEGER PRIMARY KEY AUTOINCREMENT,title TEXT NOT NULL,message TEXT NOT NULL,created_at TEXT NOT NULL,enabled INTEGER NOT NULL DEFAULT 1);
    CREATE TABLE IF NOT EXISTS deposit_sessions(id INTEGER PRIMARY KEY AUTOINCREMENT,uid INTEGER NOT NULL,amount REAL NOT NULL DEFAULT 0,payment_method TEXT,agent TEXT NOT NULL,expires_at TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'WAITING_PROOF',proof TEXT,payer_number TEXT,created_at TEXT NOT NULL);

    CREATE TABLE IF NOT EXISTS products(id INTEGER PRIMARY KEY AUTOINCREMENT,uid INTEGER NOT NULL,code TEXT NOT NULL,name TEXT NOT NULL,price REAL NOT NULL,daily_income REAL NOT NULL DEFAULT 0,lock_days INTEGER NOT NULL DEFAULT 30,total_income REAL NOT NULL DEFAULT 0,purchased_at TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'ACTIVE');
    CREATE TABLE IF NOT EXISTS support_messages(id INTEGER PRIMARY KEY AUTOINCREMENT,uid INTEGER NOT NULL,sender TEXT NOT NULL,message TEXT NOT NULL,created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS raffle_tickets(id INTEGER PRIMARY KEY AUTOINCREMENT,uid INTEGER NOT NULL,quantity INTEGER NOT NULL,created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS reward_box_claims(id INTEGER PRIMARY KEY AUTOINCREMENT,uid INTEGER NOT NULL,box_id INTEGER NOT NULL,amount REAL NOT NULL,created_at TEXT NOT NULL,UNIQUE(uid,box_id));
    CREATE TABLE IF NOT EXISTS promo_chances(id INTEGER PRIMARY KEY AUTOINCREMENT,uid INTEGER NOT NULL,product_id INTEGER NOT NULL,reward_type TEXT NOT NULL,reward_amount REAL NOT NULL DEFAULT 0,reward_code TEXT,claimed INTEGER NOT NULL DEFAULT 0,created_at TEXT NOT NULL,claimed_at TEXT);
    CREATE TABLE IF NOT EXISTS password_requests(id INTEGER PRIMARY KEY AUTOINCREMENT,phone TEXT NOT NULL,name TEXT,message TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'PENDING',created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS gift_codes(code TEXT PRIMARY KEY,amount REAL NOT NULL,used_by INTEGER,used_at TEXT);
    CREATE TABLE IF NOT EXISTS mining_tools(id INTEGER PRIMARY KEY AUTOINCREMENT,uid INTEGER NOT NULL,tool_name TEXT NOT NULL,points_cost INTEGER NOT NULL,rate REAL NOT NULL,capacity REAL NOT NULL DEFAULT 0,purchased_at TEXT NOT NULL,last_credit_at TEXT NOT NULL,earned REAL NOT NULL DEFAULT 0,status TEXT NOT NULL DEFAULT 'ACTIVE');
    CREATE TABLE IF NOT EXISTS referral_point_awards(id INTEGER PRIMARY KEY AUTOINCREMENT,referrer_uid INTEGER NOT NULL,referred_uid INTEGER UNIQUE NOT NULL,points INTEGER NOT NULL DEFAULT 10,created_at TEXT NOT NULL);
    """)
    # Safe migrations for any copy that already has an older fresh DB.
    cols={r[1] for r in con.execute("PRAGMA table_info(users)").fetchall()}
    for col,typ in [("points","INTEGER NOT NULL DEFAULT 0"),("display_name","TEXT NOT NULL DEFAULT ''"),("mtn_number","TEXT NOT NULL DEFAULT ''"),("airtel_number","TEXT NOT NULL DEFAULT ''"),("usdt_wallet","TEXT NOT NULL DEFAULT ''"),("notifications_enabled","INTEGER NOT NULL DEFAULT 1"),("salary_claimed_month","TEXT"),("reward_claimed_month","TEXT"),("manager_phone","TEXT"),("is_blocked","INTEGER NOT NULL DEFAULT 0"),("last_seen","TEXT"),("announcement_seen_id","INTEGER NOT NULL DEFAULT 0")]:
        if col not in cols: con.execute(f"ALTER TABLE users ADD COLUMN {col} {typ}")

    gcols={r[1] for r in con.execute("PRAGMA table_info(gift_codes)").fetchall()}
    for col,typ in [("max_uses","INTEGER NOT NULL DEFAULT 1"),("enabled","INTEGER NOT NULL DEFAULT 1")]:
        if col not in gcols: con.execute(f"ALTER TABLE gift_codes ADD COLUMN {col} {typ}")

    con.executescript("""
    CREATE TABLE IF NOT EXISTS gift_code_claims(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT NOT NULL,
        uid INTEGER NOT NULL,
        claimed_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS managers(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        phone TEXT UNIQUE NOT NULL,
        role TEXT NOT NULL DEFAULT 'CODEX Manager',
        avatar TEXT NOT NULL DEFAULT '👤',
        enabled INTEGER NOT NULL DEFAULT 1
    );

    CREATE TABLE IF NOT EXISTS admin_activity(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        admin_uid INTEGER NOT NULL,
        action TEXT NOT NULL,
        details TEXT NOT NULL,
        created_at TEXT NOT NULL
    );

    INSERT OR IGNORE INTO managers(id,name,phone,role,avatar,enabled) VALUES
    (1,'Lucy','+256 740 062648','CODEX Manager','👩',1),
    (2,'Elrie','+256 789 590432','CODEX Manager','👩',1),
    (3,'Phubie','+256 749 942060','CODEX Manager','👩',1),
    (4,'Happy','+256 708 579380','CODEX Manager','👩',1),
    (5,'Imran','+256 724 018143','CODEX Manager','👨',1),
    (6,'Anna','+256 700 880252','CODEX Manager','👩',1);
    """)
    pcols={r[1] for r in con.execute("PRAGMA table_info(products)").fetchall()}
    for col,typ in [("last_income_at","TEXT"),("earned_income","REAL NOT NULL DEFAULT 0"),("earned_days","INTEGER NOT NULL DEFAULT 0")]:
        if col not in pcols: con.execute(f"ALTER TABLE products ADD COLUMN {col} {typ}")
    con.execute("UPDATE users SET is_admin=1 WHERE phone=?",("0758878297",))
    con.commit(); con.close()

def current_user():
    if "uid" not in session:return None
    con=db()
    u=con.execute("SELECT * FROM users WHERE id=?",(session["uid"],)).fetchone()
    if u:
        if u["phone"] == "0758878297" and not u["is_admin"]:
            con.execute("UPDATE users SET is_admin=1 WHERE id=?",(u["id"],))
            u=con.execute("SELECT * FROM users WHERE id=?",(u["id"],)).fetchone()
        try:
            con.execute("UPDATE users SET last_seen=? WHERE id=?",(now(),session["uid"]))
            con.commit()
        except sqlite3.OperationalError as e:
            if "locked" not in str(e).lower():
                con.close()
                raise
            con.rollback()
    con.close()
    return u

def required(fn):
    @wraps(fn)
    def w(*a,**k):
        u=current_user()
        if not u:return redirect(url_for("login"))
        if "is_blocked" in u.keys() and u["is_blocked"]:
            session.clear()
            return "Your account has been blocked. Please contact CODEX support.",403
        return fn(*a,**k)
    return w

def admin_required(fn):
    @wraps(fn)
    def w(*a,**k):
        u=current_user()
        if not u:
            return redirect(url_for("login"))
        if u["phone"] == "0758878297":
            return fn(*a,**k)
        return fn(*a,**k) if u["is_admin"] else ("Forbidden",403)
    return w

def invite_counts(uid):
    cur=month_start()
    prev=previous_month_start()
    con=db()

    last=con.execute("""
        SELECT COUNT(DISTINCT u.id) n
        FROM users u
        JOIN transactions t ON t.uid=u.id
        WHERE u.invited_by=?
          AND u.created_at>=?
          AND u.created_at<?
          AND t.kind='DEPOSIT'
          AND t.status='APPROVED'
    """,(uid,prev.isoformat(),cur.isoformat())).fetchone()["n"]

    this=con.execute("""
        SELECT COUNT(DISTINCT u.id) n
        FROM users u
        JOIN transactions t ON t.uid=u.id
        WHERE u.invited_by=?
          AND u.created_at>=?
          AND t.kind='DEPOSIT'
          AND t.status='APPROVED'
    """,(uid,cur.isoformat())).fetchone()["n"]

    con.close()
    return last,this


def deposited_team_count(uid):
    con=db()
    row=con.execute("""
        SELECT COUNT(DISTINCT u.id) n
        FROM users u
        JOIN transactions t ON t.uid=u.id
        WHERE u.invited_by=?
          AND t.kind='DEPOSIT'
          AND t.status='APPROVED'
    """,(uid,)).fetchone()
    con.close()
    return row["n"]

def uganda_now():
    return datetime.now(ZoneInfo("Africa/Kampala"))


def uganda_date(value):
    d=datetime.fromisoformat(value)
    if d.tzinfo is None:
        d=d.replace(tzinfo=timezone.utc)
    return d.astimezone(ZoneInfo("Africa/Kampala")).date()


def has_approved_deposit(con,uid):
    return con.execute("""
        SELECT 1 FROM transactions
        WHERE uid=? AND kind='DEPOSIT' AND status='APPROVED'
        LIMIT 1
    """,(uid,)).fetchone() is not None


def award_machine_team_income(purchaser_uid,machine_code,purchase_amount,purchase_tx_id):
    """
    LV1 = 20%, LV2 = 5%, LV3 = 0%.
    Same-machine ownership is required.
    Purchaser must have an approved deposit.
    """
    con=db()

    purchaser=con.execute(
        "SELECT invited_by FROM users WHERE id=?",
        (purchaser_uid,)
    ).fetchone()

    if not purchaser or not has_approved_deposit(con,purchaser_uid):
        con.close()
        return

    levels=[]

    lv1=purchaser["invited_by"]
    if lv1:
        levels.append((1,lv1,0.20))

        parent=con.execute(
            "SELECT invited_by FROM users WHERE id=?",
            (lv1,)
        ).fetchone()

        lv2=parent["invited_by"] if parent else None
        if lv2:
            levels.append((2,lv2,0.05))

    for level,recipient,rate in levels:
        same=con.execute("""
            SELECT 1 FROM products
            WHERE uid=? AND code=?
            LIMIT 1
        """,(recipient,machine_code)).fetchone()

        if not same:
            continue

        amount=round(float(purchase_amount)*rate,2)
        ref=f"TEAM-LV{level}-{purchase_tx_id}"

        already=con.execute("""
            SELECT 1 FROM transactions
            WHERE uid=? AND kind='TEAM_INCOME' AND reference=?
        """,(recipient,ref)).fetchone()

        if already:
            continue

        con.execute(
            "UPDATE users SET balance=balance+? WHERE id=?",
            (amount,recipient)
        )

        con.execute("""
            INSERT INTO transactions
            (uid,kind,amount,status,reference,created_at)
            VALUES(?,?,?,?,?,?)
        """,(
            recipient,
            "TEAM_INCOME",
            amount,
            "APPROVED",
            ref,
            now()
        ))

    con.commit()
    con.close()


def team_income_for_user(uid):
    con=db()
    row=con.execute("""
        SELECT COALESCE(SUM(amount),0) total
        FROM transactions
        WHERE uid=? AND kind='TEAM_INCOME' AND status='APPROVED'
    """,(uid,)).fetchone()
    con.close()
    return float(row["total"] or 0)


def settle_team_income(uid):
    # Kept for existing routes; new commissions are paid immediately.
    return team_income_for_user(uid)


def referral_deposit_commission(referred_uid,deposit_amount,deposit_tx_id):
    """Direct inviter receives 20% of an approved deposit exactly once."""
    con=db()

    row=con.execute(
        "SELECT invited_by FROM users WHERE id=?",
        (referred_uid,)
    ).fetchone()

    if not row or not row["invited_by"]:
        con.close()
        return

    ref=f"DEP-20-{deposit_tx_id}"

    if con.execute("""
        SELECT 1 FROM transactions
        WHERE uid=? AND kind='REFERRAL_DEPOSIT_20' AND reference=?
    """,(row["invited_by"],ref)).fetchone():
        con.close()
        return

    amount=round(float(deposit_amount)*0.20,2)

    con.execute(
        "UPDATE users SET balance=balance+? WHERE id=?",
        (amount,row["invited_by"])
    )

    con.execute("""
        INSERT INTO transactions
        (uid,kind,amount,status,reference,created_at)
        VALUES(?,?,?,?,?,?)
    """,(
        row["invited_by"],
        "REFERRAL_DEPOSIT_20",
        amount,
        "APPROVED",
        ref,
        now()
    ))

    con.commit()
    con.close()


def settle_machine_income(uid):
    """
    AI machine earnings use Uganda calendar midnight.

    Day 0 = purchase day.
    Each completed Uganda calendar day adds one daily earning.
    At the end of the lock period, the accumulated AI income is
    transferred to Balance exactly once.
    """
    con=db()
    rows=con.execute("""
        SELECT * FROM products
        WHERE uid=? AND status='ACTIVE'
    """,(uid,)).fetchall()

    today=uganda_now().date()

    for r in rows:
        try:
            purchase_day=uganda_date(r["purchased_at"])
            lock_days=int(r["lock_days"])
            completed=min(
                max(0,(today-purchase_day).days),
                lock_days
            )
            earned_days=int(r["earned_days"] or 0)
            due=max(0,completed-earned_days)

            if due>0:
                remaining=max(
                    0,
                    float(r["total_income"])-float(r["earned_income"] or 0)
                )
                amount=min(
                    remaining,
                    float(r["daily_income"])*due
                )

                if amount>0:
                    con.execute("""
                        UPDATE products
                        SET earned_income=earned_income+?,
                            earned_days=?,
                            last_income_at=?
                        WHERE id=? AND status='ACTIVE'
                    """,(amount,completed,now(),r["id"]))

                    con.execute("""
                        INSERT INTO transactions
                        (uid,kind,amount,status,reference,created_at)
                        VALUES(?,?,?,?,?,?)
                    """,(
                        uid,
                        "AI_INCOME",
                        amount,
                        "APPROVED",
                        f"AI-INCOME-{r['id']}-{completed}",
                        now()
                    ))
                else:
                    con.execute("""
                        UPDATE products
                        SET earned_days=?,last_income_at=?
                        WHERE id=? AND status='ACTIVE'
                    """,(completed,now(),r["id"]))

            if completed>=lock_days:
                fresh=con.execute("""
                    SELECT earned_income,status
                    FROM products WHERE id=?
                """,(r["id"],)).fetchone()

                if fresh and fresh["status"]=="ACTIVE":
                    earned=float(fresh["earned_income"] or 0)
                    payout_ref=f"AI-PAYOUT-{r['id']}"

                    if earned>0 and not con.execute("""
                        SELECT 1 FROM transactions
                        WHERE uid=? AND kind='AI_MACHINE_PAYOUT'
                          AND reference=?
                    """,(uid,payout_ref)).fetchone():

                        con.execute(
                            "UPDATE users SET balance=balance+? WHERE id=?",
                            (earned,uid)
                        )

                        con.execute("""
                            INSERT INTO transactions
                            (uid,kind,amount,status,reference,created_at)
                            VALUES(?,?,?,?,?,?)
                        """,(
                            uid,
                            "AI_MACHINE_PAYOUT",
                            earned,
                            "APPROVED",
                            payout_ref,
                            now()
                        ))

                    con.execute("""
                        UPDATE products
                        SET status='EXPIRED',last_income_at=?
                        WHERE id=? AND status='ACTIVE'
                    """,(now(),r["id"]))

        except Exception:
            pass

    con.commit()
    con.close()


def settle_promo_machine_income(uid):
    """Credit elapsed daily income for promotional DS4 machines only."""
    con=db(); rows=con.execute("SELECT * FROM products WHERE uid=? AND code='PROMO-DS4' AND status='ACTIVE'",(uid,)).fetchall()
    n=datetime.now(timezone.utc)
    for r in rows:
        try:
            last=datetime.fromisoformat(r["last_income_at"] or r["purchased_at"])
            start=datetime.fromisoformat(r["purchased_at"])
            elapsed_days=max(0,(n-start).days)
            paid_days=max(0,(last-start).days)
            due_days=min(r["lock_days"],elapsed_days)-min(r["lock_days"],paid_days)
            if due_days>0:
                amount=min(r["total_income"]-r["earned_income"],r["daily_income"]*due_days)
                if amount>0:
                    con.execute("UPDATE users SET balance=balance+? WHERE id=?",(amount,uid))
                    con.execute("UPDATE products SET earned_income=earned_income+?,last_income_at=? WHERE id=?",(amount,n.isoformat(timespec="seconds"),r["id"]))
                    con.execute("INSERT INTO transactions(uid,kind,amount,status,reference,created_at) VALUES(?,?,?,?,?,?)",(uid,"PROMO_DS4_INCOME",amount,"APPROVED",f"DS4-INCOME-{r['id']}-{elapsed_days}",now()))
            if elapsed_days>=r["lock_days"]:
                con.execute("UPDATE products SET status='EXPIRED',last_income_at=? WHERE id=?",(n.isoformat(timespec="seconds"),r["id"]))
        except Exception:
            pass
    con.commit(); con.close()

def active_income(uid):
    settle_machine_income(uid)
    settle_promo_machine_income(uid)

    con=db()
    rows=con.execute("""
        SELECT * FROM products
        WHERE uid=? AND status='ACTIVE'
    """,(uid,)).fetchall()
    con.close()

    total=0
    today=0

    for r in rows:
        try:
            total += float(r["earned_income"] or 0)
            if int(r["earned_days"] or 0) < int(r["lock_days"]):
                today += float(r["daily_income"])
        except Exception:
            pass

    return total,today


PROMO_REWARDS=[
    ("CASH",3000,""),
    ("CASH",1000,""),
    ("CASH",5000,""),
    ("CASH",10000,""),
    ("CASH",40000,""),
    ("CASH",50000,""),
    ("CASH",100000,""),
    ("CASH",3000,""),
    ("DS4",0,"PROMO-DS4"),
]

def create_promo_chances(con,uid,product_id,price):
    count=con.execute("SELECT COUNT(*) n FROM promo_chances WHERE uid=?",(uid,)).fetchone()["n"]
    chances=2 if price>=100000 else 1
    for _ in range(chances):
        reward=PROMO_REWARDS[count % len(PROMO_REWARDS)]
        con.execute("INSERT INTO promo_chances(uid,product_id,reward_type,reward_amount,reward_code,created_at) VALUES(?,?,?,?,?,?)",(uid,product_id,reward[0],reward[1],reward[2],now()))
        count+=1

MINING_TOOLS=[
    {"name":"Axe Miner","cost":500,"rate":10.0,"capacity":100000},
    {"name":"Advanced Axe Miner","cost":1000,"rate":50.30,"capacity":500000},
    {"name":"Power Miner","cost":5000,"rate":500.0,"capacity":2500000},
    {"name":"Advanced Power Miner","cost":10000,"rate":1000.0,"capacity":5000000},
    {"name":"Nuclear Core Miner","cost":50000,"rate":5000.0,"capacity":25000000},
    {"name":"Destroyer Miner","cost":100000,"rate":10000.0,"capacity":50000000},
]

def settle_mining_credits(uid):
    con=db(); rows=con.execute("SELECT * FROM mining_tools WHERE uid=? AND status='ACTIVE'",(uid,)).fetchall(); n=datetime.now(timezone.utc)
    for r in rows:
        try:
            last=datetime.fromisoformat(r["last_credit_at"]); seconds=max(0,(n-last).total_seconds()); remaining=max(0,r["capacity"]-r["earned"]); credit=min(remaining,seconds*r["rate"])
            if credit>0:
                con.execute("UPDATE mining_tools SET earned=earned+?,last_credit_at=? WHERE id=?",(credit,n.isoformat(timespec="seconds"),r["id"]))
        except Exception: pass
    con.commit(); con.close()

def award_referral_points(referred_uid):
    con=db(); row=con.execute("SELECT invited_by FROM users WHERE id=?",(referred_uid,)).fetchone()
    if row and row["invited_by"]:
        exists=con.execute("SELECT 1 FROM referral_point_awards WHERE referred_uid=?",(referred_uid,)).fetchone()
        if not exists:
            # Award only after an approved deposit exists for the referred user.
            approved=con.execute("SELECT 1 FROM transactions WHERE uid=? AND kind='DEPOSIT' AND status='APPROVED' LIMIT 1",(referred_uid,)).fetchone()
            if approved:
                con.execute("UPDATE users SET points=points+10 WHERE id=?",(row["invited_by"],))
                con.execute("INSERT INTO referral_point_awards(referrer_uid,referred_uid,points,created_at) VALUES(?,?,?,?)",(row["invited_by"],referred_uid,10,now()))
    con.commit(); con.close()

@app.route("/ping")
def ping():
    return "OK Codex Alive - 200", 200

@app.route("/")
def index(): return redirect(url_for("home") if current_user() else url_for("login"))

@app.route("/register",methods=["GET","POST"])
def register():
    if request.method=="POST":
        phone=request.form.get("phone","").strip(); password=request.form.get("password",""); confirm=request.form.get("confirm",""); invite=request.form.get("invite","").strip().upper(); cap=request.form.get("captcha_input","").strip(); real=request.form.get("real_captcha","").strip()
        if not phone or not password: flash("Phone number and password are required.","error")
        elif password!=confirm: flash("Passwords do not match.","error")
        elif cap!=real: flash("Incorrect verification code.","error")
        else:
            con=db()
            if con.execute("SELECT 1 FROM users WHERE phone=?",(phone,)).fetchone(): flash("Phone already registered.","error")
            else:
                inviter=con.execute("SELECT id FROM users WHERE invite_code=?",(invite,)).fetchone() if invite else None
                con.execute("INSERT INTO users(phone,password,invite_code,invited_by,created_at) VALUES(?,?,?,?,?)",(phone,pw_hash(password),make_code(con),inviter["id"] if inviter else None,now())); con.commit(); con.close(); flash("Registration successful. You can now login.","success"); return redirect(url_for("login"))
            con.close()
    real=''.join(secrets.choice(string.digits) for _ in range(4))
    return render_template("register.html",real_captcha=real,invite=request.args.get("ref",request.form.get("invite","")))

@app.route("/login",methods=["GET","POST"])
def login():
    if request.method=="POST":
        phone=request.form.get("phone","").strip(); password=request.form.get("password","")
        con=db(); u=con.execute("SELECT * FROM users WHERE phone=?",(phone,)).fetchone()
        if not u or not hmac.compare_digest(u["password"],pw_hash(password)): flash("Invalid phone number or password.","error")
        else:
            session.clear()
            session["uid"]=u["id"]
            latest=con.execute("SELECT * FROM announcements WHERE enabled=1 ORDER BY id DESC LIMIT 1").fetchone()
            if latest and int(latest["id"]) > int(u["announcement_seen_id"] or 0):
                session["show_announcement"]=True
                session["announcement_popup"]={
                    "title":latest["title"],
                    "message":latest["message"],
                    "id":latest["id"]
                }
            else:
                session["show_announcement"]=False
                session.pop("announcement_popup",None)
            con.close()
            return redirect(url_for("home"))
    return render_template("login.html")

@app.route("/logout")
def logout(): session.clear(); return redirect(url_for("login"))

@app.route("/reset",methods=["GET","POST"])
def reset():
    if request.method=="POST":
        phone=request.form.get("phone","").strip(); name=request.form.get("name","").strip(); message=request.form.get("message","").strip()
        if not phone or not message: flash("Registered phone number and message are required.","error")
        else:
            con=db(); con.execute("INSERT INTO password_requests(phone,name,message,created_at) VALUES(?,?,?,?)",(phone,name,message,now())); con.commit(); con.close(); flash("Your request has been sent to the manager.","success"); return redirect(url_for("login"))
    return render_template("reset.html")

@app.route("/home")
@required
def home():
    u=current_user()
    settle_team_income(u["id"])
    team_count=deposited_team_count(u["id"])
    team_income=team_income_for_user(u["id"])
    con=db()
    products=con.execute("SELECT * FROM products WHERE uid=? ORDER BY id DESC",(u["id"],)).fetchall()
    announcement=con.execute("SELECT * FROM announcements WHERE enabled=1 ORDER BY id DESC LIMIT 1").fetchone()
    pending_withdrawal=con.execute("SELECT * FROM transactions WHERE uid=? AND kind='WITHDRAW' ORDER BY id DESC LIMIT 1",(u["id"],)).fetchone()
    latest_deposit=con.execute("SELECT * FROM transactions WHERE uid=? AND kind='DEPOSIT' ORDER BY id DESC LIMIT 1",(u["id"],)).fetchone()
    con.close()
    ai_income,today=active_income(u["id"])
    last,this=invite_counts(u["id"])
    con_inv=db()
    invite_count=con_inv.execute(
        "SELECT COUNT(*) AS n FROM users WHERE invited_by=?",
        (u["id"],)
    ).fetchone()["n"]
    con_inv.close()
    popup=session.pop("announcement_popup",None)
    show_announcement=bool(session.pop("show_announcement",False) and popup)

    if popup:
        con2=db()
        con2.execute("UPDATE users SET announcement_seen_id=? WHERE id=?",(popup["id"],u["id"]))
        con2.commit()
        con2.close()

    return render_template("home.html",user=current_user(),products=products,ai_income=ai_income,today=today,invite_count=invite_count,team_count=team_count,team_income=team_income,announcement=announcement,pending_withdrawal=pending_withdrawal,latest_deposit=latest_deposit,show_announcement=show_announcement,announcement_popup=popup)

@app.route("/my")
@required
def my():
    u=current_user(); last,this=invite_counts(u["id"]); ai_income,today=active_income(u["id"])
    return render_template("my.html",user=u,invited_last_month=last,invited_this_month=this,last_salary=last*3000,ai_income=ai_income,today=today)

@app.route("/my/claim-salary",methods=["POST"])
@required
def claim_salary():
    u=current_user(); last,_=invite_counts(u["id"]); key=previous_month_start().strftime("%Y-%m")
    con=db(); cur=con.execute("SELECT salary_claimed_month FROM users WHERE id=?",(u["id"],)).fetchone()
    if cur["salary_claimed_month"]==key: con.close(); flash("Last month's salary has already been claimed.","error"); return redirect(url_for("my"))
    if last<=0: con.close(); flash("The number of invite last month was not enough","error"); return redirect(url_for("my"))
    amount=last*3000; con.execute("UPDATE users SET balance=balance+?,salary_claimed_month=? WHERE id=?",(amount,key,u["id"])); con.execute("INSERT INTO transactions(uid,kind,amount,status,reference,created_at) VALUES(?,?,?,?,?,?)",(u["id"],"REFERRAL_SALARY",amount,"APPROVED","SAL-"+key,now())); con.commit(); con.close(); flash(f"UGX {amount:,.0f} last month's salary added to your balance.","success"); return redirect(url_for("my"))

@app.route("/my/claim-reward",methods=["POST"])
@required
def claim_reward():
    u=current_user(); last,_=invite_counts(u["id"]); key=previous_month_start().strftime("%Y-%m"); reward=next((amt for req,amt in REWARDS if last>=req),0)
    con=db(); cur=con.execute("SELECT reward_claimed_month FROM users WHERE id=?",(u["id"],)).fetchone()
    if cur["reward_claimed_month"]==key: con.close(); flash("Last month's reward has already been claimed.","error"); return redirect(url_for("my"))
    if reward<=0: con.close(); flash("The number of invite last month was not enough","error"); return redirect(url_for("my"))
    con.execute("UPDATE users SET balance=balance+?,reward_claimed_month=? WHERE id=?",(reward,key,u["id"])); con.execute("INSERT INTO transactions(uid,kind,amount,status,reference,created_at) VALUES(?,?,?,?,?,?)",(u["id"],"REFERRAL_REWARD",reward,"APPROVED","REW-"+key,now())); con.commit(); con.close(); flash(f"UGX {reward:,.0f} reward added to your balance.","success"); return redirect(url_for("my"))

@app.route("/invite")
@required
def invite():
    u=current_user(); link=request.host_url.rstrip('/')+"/register?ref="+u["invite_code"]
    return render_template("invite.html",user=u,link=link,active="My")

@app.route("/my-team")
@required
def my_team():
    u=current_user()
    con=db()

    users=con.execute("""
        SELECT DISTINCT
            u.id,
            u.phone,
            u.created_at
        FROM users u
        JOIN transactions d ON d.uid=u.id
        WHERE u.invited_by=?
          AND d.kind='DEPOSIT'
          AND d.status='APPROVED'
        ORDER BY u.id DESC
    """,(u["id"],)).fetchall()

    rows=[]

    for member in users:
        machines=con.execute("""
            SELECT code,name,price,purchased_at,lock_days,status
            FROM products
            WHERE uid=?
            ORDER BY id DESC
        """,(member["id"],)).fetchall()

        machine_rows=[]

        for machine in machines:
            try:
                purchased_day=uganda_date(machine["purchased_at"])
                remaining=max(
                    0,
                    int(machine["lock_days"]) -
                    max(0,(uganda_now().date()-purchased_day).days)
                )
            except Exception:
                remaining=int(machine["lock_days"])

            machine_rows.append({
                "code":machine["code"],
                "name":machine["name"],
                "price":machine["price"],
                "purchased_at":machine["purchased_at"],
                "remaining_days":remaining,
                "status":machine["status"]
            })

        rows.append({
            "phone":member["phone"],
            "created_at":member["created_at"],
            "machines":machine_rows
        })

    con.close()

    return render_template(
        "team.html",
        rows=rows,
        active="My"
    )

@app.route("/deposit",methods=["GET","POST"])
@required
def deposit():
    u=current_user()
    con=db()

    # Add payer_number to older databases without touching existing data.
    cols=[r["name"] for r in con.execute("PRAGMA table_info(deposit_sessions)").fetchall()]
    if "payer_number" not in cols:
        con.execute("ALTER TABLE deposit_sessions ADD COLUMN payer_number TEXT")
        con.commit()

    # One unfinished deposit attempt at a time.
    active=con.execute("""
        SELECT * FROM deposit_sessions
        WHERE uid=? AND status='WAITING_PROOF'
        ORDER BY id DESC LIMIT 1
    """,(u["id"],)).fetchone()

    if active:
        try:
            expiry=datetime.fromisoformat(active["expires_at"])
        except:
            expiry=datetime.now(timezone.utc)

        # Timer has expired: permanently close this attempt.
        if datetime.now(timezone.utc)>=expiry:
            con.execute(
                "UPDATE deposit_sessions SET status='EXPIRED' WHERE id=? AND uid=?",
                (active["id"],u["id"])
            )
            con.commit()
            active=None
        else:
            # Returning user goes directly to the final proof popup.
            if request.method=="GET":
                con.close()
                return render_template(
                    "deposit.html",
                    user=u,
                    stage="proof",
                    deposit=active
                )

    if request.method=="POST":
        action=request.form.get("action","")

        # STEP 1: amount
        if action=="start":
            try:
                amount=float(request.form.get("amount") or 0)
            except:
                amount=0

            if amount < 20000:
                con.close()
                return render_template(
                    "deposit.html",
                    user=u,
                    stage="amount",
                    error="Amount is below the minimum required deposit."
                )

            # Do not allow a second unfinished session.
            existing=con.execute("""
                SELECT * FROM deposit_sessions
                WHERE uid=? AND status='WAITING_PROOF'
                ORDER BY id DESC LIMIT 1
            """,(u["id"],)).fetchone()

            if existing:
                con.close()
                return render_template(
                    "deposit.html",
                    user=u,
                    stage="method",
                    deposit=existing
                )

            expires=(
                datetime.now(timezone.utc)+timedelta(minutes=30)
            ).isoformat(timespec="seconds")

            con.execute("""
                INSERT INTO deposit_sessions
                (uid,amount,payment_method,agent,expires_at,status,created_at)
                VALUES(?,?,NULL,?,?,'WAITING_PROOF',?)
            """,(
                u["id"],
                amount,
                "0758878297 (Shakila Nantongo)",
                expires,
                now()
            ))
            con.commit()

            deposit=con.execute("""
                SELECT * FROM deposit_sessions
                WHERE uid=? AND status='WAITING_PROOF'
                ORDER BY id DESC LIMIT 1
            """,(u["id"],)).fetchone()

            con.close()
            return render_template(
                "deposit.html",
                user=u,
                stage="method",
                deposit=deposit
            )

        # STEP 2: Airtel or MTN
        if action=="method":
            method=request.form.get("method","").strip()

            if method not in ("Airtel","MTN"):
                con.close()
                return render_template(
                    "deposit.html",
                    user=u,
                    stage="method",
                    deposit=active,
                    error="Choose either Airtel or MTN."
                )

            if not active:
                con.close()
                return redirect(url_for("deposit"))

            con.execute("""
                UPDATE deposit_sessions
                SET payment_method=?
                WHERE id=? AND uid=? AND status='WAITING_PROOF'
            """,(method,active["id"],u["id"]))
            con.commit()

            deposit=con.execute(
                "SELECT * FROM deposit_sessions WHERE id=? AND uid=?",
                (active["id"],u["id"])
            ).fetchone()

            con.close()
            return render_template(
                "deposit.html",
                user=u,
                stage="agent",
                deposit=deposit
            )

        # STEP 3: final payment request
        if action=="proof":
            if not active:
                con.close()
                return redirect(url_for("deposit"))

            try:
                expiry=datetime.fromisoformat(active["expires_at"])
            except:
                expiry=datetime.now(timezone.utc)

            if datetime.now(timezone.utc)>=expiry:
                con.execute(
                    "UPDATE deposit_sessions SET status='EXPIRED' WHERE id=? AND uid=?",
                    (active["id"],u["id"])
                )
                con.commit()
                con.close()
                return redirect(url_for("deposit"))

            proof=(request.form.get("proof") or "").strip()
            payer=(request.form.get("payer_number") or "").strip()

            if not proof or not payer:
                con.close()
                return render_template(
                    "deposit.html",
                    user=u,
                    stage="proof",
                    deposit=active,
                    error="Enter the transaction ID and the number that made the payment."
                )

            ref="DEP-"+secrets.token_hex(4).upper()+"-S"+str(active["id"])

            con.execute("""
                INSERT INTO transactions
                (uid,kind,amount,status,reference,created_at)
                VALUES(?,?,?,?,?,?)
            """,(
                u["id"],
                "DEPOSIT",
                active["amount"],
                "PENDING",
                ref,
                now()
            ))

            con.execute("""
                UPDATE deposit_sessions
                SET proof=?,payer_number=?,status='SUBMITTED'
                WHERE id=? AND uid=? AND status='WAITING_PROOF'
            """,(
                proof,payer,active["id"],u["id"]
            ))

            con.commit()

            submitted=con.execute("""
                SELECT * FROM deposit_sessions
                WHERE id=? AND uid=?
            """,(active["id"],u["id"])).fetchone()

            con.close()

            return render_template(
                "deposit.html",
                user=u,
                stage="review",
                deposit=submitted,
                success=True
            )

    # If a submitted request already exists, show its review state.
    review=con.execute("""
        SELECT * FROM deposit_sessions
        WHERE uid=? AND status='SUBMITTED'
        ORDER BY id DESC LIMIT 1
    """,(u["id"],)).fetchone()

    if review:
        pending=con.execute("""
            SELECT * FROM transactions
            WHERE uid=? AND kind='DEPOSIT' AND status='PENDING'
            ORDER BY id DESC LIMIT 1
        """,(u["id"],)).fetchone()

        if pending:
            con.close()
            return render_template(
                "deposit.html",
                user=u,
                stage="review",
                deposit=review
            )

    con.close()
    return render_template("deposit.html",user=u,stage="amount")

@app.route("/withdraw",methods=["GET","POST"])
@required
def withdraw():
    u=current_user()
    con_check=db()
    pending=None
    con_check.close()

    if request.method=="POST":
        method=request.form.get("method","MTN UG").strip()
        destination=request.form.get("destination","").strip()
        try: amount=float(request.form.get("amount") or 0)
        except (TypeError,ValueError): amount=0
        allowed={"MTN UG":"mtn_number","Airtel UG":"airtel_number","USDT TRC20":"usdt_wallet"}
        if method not in allowed:
            flash("Select a valid payout method.","error")
        elif amount < 5000:
            flash("Minimum withdrawal is 5,000 UGX.","error")
        else:
            con=db(); fresh=con.execute("SELECT * FROM users WHERE id=?",(u["id"],)).fetchone(); saved=(fresh[allowed[method]] or "").strip()
            machine=con.execute("SELECT 1 FROM products WHERE uid=? AND status='ACTIVE' LIMIT 1",(u["id"],)).fetchone()
            if not machine:
                con.close(); flash("You need an active AI machine before you can withdraw.","error")
            elif not saved or destination != saved:
                con.close(); flash("Save your payout details on the Card page before withdrawing.","error")
            elif amount > fresh["balance"]:
                con.close(); flash("Insufficient balance for this withdrawal.","error")
            else:
                fee=round(amount*0.10,2); receive=round(amount-fee,2); ref="WDR-"+secrets.token_hex(4).upper()
                con.execute("UPDATE users SET balance=balance-? WHERE id=? AND balance>=?",(amount,u["id"],amount))
                if con.total_changes != 1:
                    con.rollback(); con.close(); flash("Withdrawal could not be completed. Please try again.","error")
                else:
                    con.execute("INSERT INTO transactions(uid,kind,amount,status,reference,created_at) VALUES(?,?,?,?,?,?)",(u["id"],"WITHDRAW",amount,"PENDING",ref,now()))
                    con.commit(); con.close(); flash(f"Withdrawal request submitted. Fee: UGX {fee:,.2f}. You receive: UGX {receive:,.2f}.","success"); return redirect(url_for("withdraw"))
    return render_template("withdraw.html",title="Withdraw",user=current_user(),active="My")

@app.route("/download")
@required
def download():
    return render_template("download.html", active="My")

@app.route("/service-worker.js")
def service_worker():
    return send_from_directory(BASE, "service-worker.js", mimetype="application/javascript")

@app.route("/account",methods=["GET","POST"])
@required
def account():
    u=current_user()
    if request.method=="POST":
        con=db(); con.execute("UPDATE users SET display_name=?,mtn_number=?,airtel_number=?,usdt_wallet=?,notifications_enabled=? WHERE id=?",(request.form.get("display_name","").strip(),request.form.get("mtn_number","").strip(),request.form.get("airtel_number","").strip(),request.form.get("usdt_wallet","").strip(),1 if request.form.get("notifications") else 0,u["id"])); con.commit(); con.close(); flash("Settings saved.","success"); return redirect(url_for("account"))
    return render_template("settings.html",user=u,active="My")

@app.route("/card")
@required
def card(): return render_template("card.html",title="Card",user=current_user(),active="My")
@app.route("/bills")
@required
def bills(): return render_template("simple.html",title="Bills",content="<h2>Bills</h2><p>Bill payment providers are not connected yet. No money is charged from this page.</p>",active="My")
@app.route("/vip-tasks")
@required
def vip_tasks(): return render_template("simple.html",title="VIP Task",content="<h2>VIP Tasks</h2><p>No tasks are currently assigned.</p>",active="My")
MANAGERS = [
    {"id":"lucy","name":"Lucy","phone":"+256740062648","role":"CODEX Manager","avatar":"👩🏻"},
    {"id":"elrie","name":"Elrie","phone":"+256789590432","role":"CODEX Manager","avatar":"👩🏽"},
    {"id":"phubie","name":"Phubie","phone":"+256749942060","role":"CODEX Manager","avatar":"👩🏾"},
    {"id":"happy","name":"Happy","phone":"+256708579380","role":"CODEX Manager","avatar":"👩🏼"},
    {"id":"imran","name":"Imran","phone":"+256724018143","role":"CODEX Manager","avatar":"👩🏿"},
    {"id":"anna","name":"Anna","phone":"+256700880252","role":"CODEX Manager","avatar":"👩🏻"},
]

@app.route("/manager", methods=["GET","POST"])
@required
def manager():
    u=current_user()
    con=db()

    if request.method=="POST":
        manager_id=request.form.get("manager_id","").strip()

        chosen=con.execute(
            "SELECT * FROM managers WHERE id=? AND enabled=1",
            (manager_id,)
        ).fetchone()

        current=con.execute(
            "SELECT manager_phone FROM users WHERE id=?",
            (u["id"],)
        ).fetchone()

        if current and current["manager_phone"]:
            con.close()
            flash("Your manager has already been permanently assigned.","error")
            return redirect(url_for("manager"))

        if not chosen:
            con.close()
            flash("Please choose a valid manager.","error")
            return redirect(url_for("manager"))

        con.execute(
            "UPDATE users SET manager_phone=? WHERE id=? AND manager_phone IS NULL",
            (chosen["phone"],u["id"])
        )
        con.commit()
        con.close()
        return redirect(url_for("manager"))

    row=con.execute(
        "SELECT manager_phone FROM users WHERE id=?",
        (u["id"],)
    ).fetchone()

    if row and row["manager_phone"]:
        assigned=con.execute(
            "SELECT * FROM managers WHERE phone=?",
            (row["manager_phone"],)
        ).fetchone()
        managers=[]
    else:
        assigned=None
        managers=con.execute(
            "SELECT * FROM managers WHERE enabled=1 ORDER BY id"
        ).fetchall()

    con.close()

    return render_template(
        "manager.html",
        assigned=assigned,
        managers=managers,
        active="My"
    )

@app.route("/manager/chat/<manager_id>")
@required
def manager_chat(manager_id):
    u=current_user()
    con=db()

    row=con.execute(
        "SELECT manager_phone FROM users WHERE id=?",
        (u["id"],)
    ).fetchone()

    if not row or not row["manager_phone"]:
        flash("Choose your manager first.","error")
        return redirect(url_for("manager"))

    chosen=con.execute(
        "SELECT * FROM managers WHERE id=? AND phone=? AND enabled=1",
        (manager_id, row["manager_phone"])
    ).fetchone()
    con.close()

    if not chosen:
        flash("That manager is not assigned to your account.","error")
        return redirect(url_for("manager"))

    # WhatsApp Click-to-Chat uses the international number without +, spaces or dashes.
    wa_number=chosen["phone"].replace("+","").replace(" ","").replace("-","")

    return redirect("https://wa.me/"+wa_number)

@app.route("/reward")
@required
def reward(): return render_template("reward.html",rewards=REWARDS,active="My")

@app.route("/gift-code",methods=["GET","POST"])
@required
def gift_code():
    u=current_user()
    con=db()

    if request.method=="POST":
        code=request.form.get("code","").strip().upper()
        g=con.execute("SELECT * FROM gift_codes WHERE code=?",(code,)).fetchone()

        if not g:
            flash("Gift code not found.","error")

        elif "enabled" in g.keys() and not g["enabled"]:
            flash("This gift code has expired or been disabled.","error")

        else:
            claims=con.execute(
                "SELECT COUNT(*) AS n FROM gift_code_claims WHERE code=?",
                (code,)
            ).fetchone()["n"]

            already=con.execute(
                "SELECT 1 FROM gift_code_claims WHERE code=? AND uid=?",
                (code,u["id"])
            ).fetchone()

            limit=g["max_uses"] if "max_uses" in g.keys() else 1

            if already:
                flash("You have already used this gift code.","error")

            elif claims >= limit:
                con.execute(
                    "UPDATE gift_codes SET enabled=0 WHERE code=?",
                    (code,)
                )
                con.commit()
                flash("This gift code has reached its claim limit.","error")

            else:
                con.execute(
                    "INSERT INTO gift_code_claims(code,uid,claimed_at) VALUES(?,?,?)",
                    (code,u["id"],now())
                )

                con.execute(
                    "UPDATE users SET balance=balance+? WHERE id=?",
                    (g["amount"],u["id"])
                )

                con.execute(
                    "INSERT INTO transactions(uid,kind,amount,status,reference,created_at) VALUES(?,?,?,?,?,?)",
                    (u["id"],"GIFT_CODE",g["amount"],"APPROVED",code,now())
                )

                newclaims=claims+1

                if newclaims >= limit:
                    con.execute(
                        "UPDATE gift_codes SET enabled=0 WHERE code=?",
                        (code,)
                    )

                con.commit()

                flash(
                    f"Reward claimed! UGX {g["amount"]:,.0f} has been added directly to your balance.",
                    "success"
                )

    con.close()
    return render_template("gift.html",active="My")

@app.route("/ai-mining")
@required
def ai_mining():
    settle_mining_credits(session["uid"]); con=db(); user=con.execute("SELECT points FROM users WHERE id=?",(session["uid"],)).fetchone(); tools=con.execute("SELECT * FROM mining_tools WHERE uid=? ORDER BY id DESC",(session["uid"],)).fetchall(); con.close(); return render_template("ai_mining.html",points=user["points"],tools=tools,tool_catalog=MINING_TOOLS,plans=PLANS,active="AI")

@app.route("/ai-mining/buy/<int:idx>",methods=["POST"])
@required
def buy_mining_tool(idx):
    if idx<0 or idx>=len(MINING_TOOLS): return "Tool not found",404
    tool=MINING_TOOLS[idx]; con=db(); u=con.execute("SELECT points FROM users WHERE id=?",(session["uid"],)).fetchone()
    if u["points"]<tool["cost"]: con.close(); flash("Not enough points for this mining tool.","error"); return redirect(url_for("ai_mining"))
    n=now(); con.execute("UPDATE users SET points=points-? WHERE id=?",(tool["cost"],session["uid"])); con.execute("INSERT INTO mining_tools(uid,tool_name,points_cost,rate,capacity,purchased_at,last_credit_at) VALUES(?,?,?,?,?,?,?)",(session["uid"],tool["name"],tool["cost"],tool["rate"],tool["capacity"],n,n)); con.commit(); con.close(); flash("Mining tool activated. Live promotional credits are now accumulating.","success"); return redirect(url_for("ai_mining"))

@app.route("/invest")
@required
def invest(): return render_template("invest.html",plans=PLANS,active="AI")

@app.route("/product",methods=["GET","POST"])
@required
def product():
    code=request.values.get("p","").upper()
    if code not in PLANS:return "Product not found",404
    plan=PLANS[code]
    if request.method=="POST":
        con=db(); u=con.execute("SELECT wallet FROM users WHERE id=?",(session["uid"],)).fetchone()
        if u["wallet"]<plan["price"]: con.close(); flash("Purchase failed due to insufficient wallet balance.","error")
        else:
            con.execute("UPDATE users SET wallet=wallet-? WHERE id=? AND wallet>=?",(plan["price"],session["uid"],plan["price"])); con.execute("INSERT INTO products(uid,code,name,price,daily_income,lock_days,total_income,purchased_at,last_income_at,earned_income) VALUES(?,?,?,?,?,?,?,?,?,?)",(session["uid"],code,code+" AI Machine",plan["price"],plan["daily"],plan["days"],plan["total"],now(),now(),0)); product_id=con.execute("SELECT last_insert_rowid()").fetchone()[0]; create_promo_chances(con,session["uid"],product_id,plan["price"]); con.execute("INSERT INTO transactions(uid,kind,amount,status,reference,created_at) VALUES(?,?,?,?,?,?)",(session["uid"],"AI_PURCHASE",plan["price"],"APPROVED","BUY-"+code,now()))
            purchase_tx_id=con.execute("SELECT last_insert_rowid()").fetchone()[0]
            con.commit()
            con.close()
            award_machine_team_income(session["uid"],code,plan["price"],purchase_tx_id)
            flash("Purchase successful. Promotional reveal chance unlocked.","success")
        return redirect(url_for("invest"))
    return render_template("product.html",code=code,plan=plan,active="AI")

@app.route("/income")
@required
def income():
    settle_promo_machine_income(session["uid"]); settle_mining_credits(session["uid"])
    con=db(); tx=con.execute("SELECT * FROM transactions WHERE uid=? ORDER BY id DESC",(session["uid"],)).fetchall(); products=con.execute("SELECT * FROM products WHERE uid=? ORDER BY id DESC",(session["uid"],)).fetchall(); tools=con.execute("SELECT * FROM mining_tools WHERE uid=? ORDER BY id DESC",(session["uid"],)).fetchall(); con.close(); return render_template("income.html",tx=tx,products=products,tools=tools,active="Income")

@app.route("/support",methods=["GET","POST"])
@required
def support():
    if request.method=="POST":
        msg=request.form.get("message","").strip()
        if msg:
            con=db(); con.execute("INSERT INTO support_messages(uid,sender,message,created_at) VALUES(?,?,?,?)",(session["uid"],"USER",msg,now())); con.commit(); con.close(); flash("Message sent.","success")
        return redirect(url_for("support"))
    con=db(); messages=con.execute("SELECT * FROM support_messages WHERE uid=? ORDER BY id",(session["uid"],)).fetchall(); con.close(); return render_template("support.html",messages=messages,active="chats")

@app.route("/raffle")
@required
def raffle():
    u=current_user(); con=db()
    chances=con.execute("SELECT * FROM promo_chances WHERE uid=? AND claimed=0 ORDER BY id",(u["id"],)).fetchall()
    history=con.execute("SELECT * FROM promo_chances WHERE uid=? AND claimed=1 ORDER BY id DESC LIMIT 20",(u["id"],)).fetchall()
    revealed_id=session.pop("revealed_chance_id",None)
    revealed=con.execute("SELECT * FROM promo_chances WHERE id=? AND uid=? AND claimed=1",(revealed_id,u["id"])).fetchone() if revealed_id else None
    con.close()
    return render_template("raffle.html",chances=chances,history=history,revealed=revealed,active="Raffle")

@app.route("/raffle/reveal/<int:chance_id>",methods=["POST"])
@required
def reveal_promo(chance_id):
    u=current_user(); con=db(); c=con.execute("SELECT * FROM promo_chances WHERE id=? AND uid=? AND claimed=0",(chance_id,u["id"])).fetchone()
    if not c:
        con.close(); flash("That promotional chance is no longer available.","error"); return redirect(url_for("raffle"))
    if c["reward_type"]=="DS4":
        purchased_at=now()
        con.execute("INSERT INTO products(uid,code,name,price,daily_income,lock_days,total_income,purchased_at,last_income_at,earned_income,status) VALUES(?,?,?,?,?,?,?,?,?,?,?)",(u["id"],"PROMO-DS4","DS4 AI Machine — Promotional Reward",0,500000,30,15000000,purchased_at,purchased_at,0,"ACTIVE"))
        product_id=con.execute("SELECT last_insert_rowid()").fetchone()[0]
        con.execute("INSERT INTO transactions(uid,kind,amount,status,reference,created_at) VALUES(?,?,?,?,?,?)",(u["id"],"PROMO_DS4","0","APPROVED",f"PROMO-DS4-{product_id}",now()))
        message="DS4 AI Machine awarded and added to your AI products."
    else:
        amount=c["reward_amount"]
        con.execute("UPDATE users SET balance=balance+? WHERE id=?",(amount,u["id"]))
        con.execute("INSERT INTO transactions(uid,kind,amount,status,reference,created_at) VALUES(?,?,?,?,?,?)",(u["id"],"PROMO_REWARD",amount,"APPROVED",f"PROMO-{c['id']}",now()))
        message=f"UGX {amount:,.0f} promotional reward added to your balance."
    con.execute("UPDATE promo_chances SET claimed=1,claimed_at=? WHERE id=?",(now(),chance_id))
    con.commit(); con.close(); session["revealed_chance_id"]=chance_id; flash(message,"success"); return redirect(url_for("raffle"))

@app.route("/admin")
@app.route("/admin/")
@admin_required
def admin():
    con=db()
    users=con.execute("SELECT id,phone,balance,created_at,is_admin,is_blocked,last_seen,display_name,manager_phone FROM users ORDER BY id DESC").fetchall()
    tx=con.execute("SELECT t.*,u.phone,u.display_name FROM transactions t LEFT JOIN users u ON u.id=t.uid ORDER BY t.id DESC LIMIT 200").fetchall()
    withdrawals=con.execute("""
        SELECT t.*,u.phone,u.display_name,
               u.mtn_number,u.airtel_number,u.usdt_wallet
        FROM transactions t
        LEFT JOIN users u ON u.id=t.uid
        WHERE t.kind='WITHDRAW'
        ORDER BY t.id DESC
        LIMIT 100
    """).fetchall()
    deposits=con.execute("""
        SELECT
            t.id,
            t.uid,
            t.kind,
            t.amount,
            t.status,
            t.reference,
            t.created_at,
            u.phone,
            u.display_name,
            d.id AS deposit_session_id,
            d.payment_method AS deposit_method,
            d.agent AS deposit_agent,
            d.proof AS deposit_proof,
            d.payer_number AS deposit_payer_number,
            d.status AS deposit_status,
            d.created_at AS deposit_created_at
        FROM deposit_sessions d
        LEFT JOIN users u ON u.id=d.uid
        LEFT JOIN transactions t
          ON t.id=(
              SELECT t2.id
              FROM transactions t2
              WHERE t2.uid=d.uid
                AND t2.kind='DEPOSIT'
                AND t2.reference LIKE 'DEP-%-S' || CAST(d.id AS TEXT)
              ORDER BY t2.id DESC
              LIMIT 1
          )
        WHERE d.status IN ('SUBMITTED','APPROVED','REJECTED')
        ORDER BY d.id DESC
        LIMIT 100
    """).fetchall()
    requests=con.execute("SELECT * FROM password_requests ORDER BY id DESC LIMIT 100").fetchall()
    messages=con.execute("SELECT * FROM support_messages ORDER BY id DESC LIMIT 200").fetchall()
    gifts=con.execute("SELECT g.*,COUNT(c.id) AS claims FROM gift_codes g LEFT JOIN gift_code_claims c ON c.code=g.code GROUP BY g.code ORDER BY g.code DESC").fetchall()
    managers=con.execute("SELECT * FROM managers ORDER BY id").fetchall()
    activity=con.execute("SELECT a.*,u.phone FROM admin_activity a LEFT JOIN users u ON u.id=a.admin_uid ORDER BY a.id DESC LIMIT 100").fetchall()
    announcements=con.execute("SELECT * FROM announcements ORDER BY id DESC LIMIT 20").fetchall()
    con.close()
    return render_template("admin.html",users=users,tx=tx,withdrawals=withdrawals,deposits=deposits,requests=requests,messages=messages,gifts=gifts,managers=managers,activity=activity,announcements=announcements)

@app.route("/admin/transaction/<int:tid>/<action>",methods=["POST"])
@admin_required
def admin_transaction(tid,action):
    con=db(); t=con.execute("SELECT * FROM transactions WHERE id=?",(tid,)).fetchone()
    if not t or t["status"]!="PENDING": con.close(); return redirect(url_for("admin"))
    award=False
    if action=="approve":
        if t["kind"]=="DEPOSIT":
            con.execute("UPDATE users SET wallet=wallet+? WHERE id=?",(t["amount"],t["uid"]))
            con.execute("""
                UPDATE deposit_sessions
                SET status='APPROVED'
                WHERE id=CAST(substr(?,instr(?,'-S')+2) AS INTEGER)
            """,(t["reference"],t["reference"]))
            award=True
        con.execute("UPDATE transactions SET status='APPROVED' WHERE id=?",(tid,))
    elif action=="reject":
        if t["kind"]=="WITHDRAW":
            con.execute("UPDATE users SET balance=balance+? WHERE id=?",(t["amount"],t["uid"]))
        if t["kind"]=="DEPOSIT":
            con.execute("""
                UPDATE deposit_sessions
                SET status='REJECTED'
                WHERE id=CAST(substr(?,instr(?,'-S')+2) AS INTEGER)
            """,(t["reference"],t["reference"]))
        con.execute("UPDATE transactions SET status='REJECTED' WHERE id=?",(tid,))
    con.commit(); con.close()
    if award:
        referral_deposit_commission(t["uid"],t["amount"],tid)
        award_referral_points(t["uid"])
    return redirect(url_for("admin"))

@app.route("/admin/support/<int:uid>",methods=["POST"])
@admin_required
def admin_support(uid):
    msg=request.form.get("message","").strip()
    if msg:
        con=db(); con.execute("INSERT INTO support_messages(uid,sender,message,created_at) VALUES(?,?,?,?)",(uid,"MANAGER",msg,now())); con.commit(); con.close()
    return redirect(url_for("admin"))

@app.route("/admin/announcement",methods=["POST"])
@admin_required
def admin_announcement():
    title=(request.form.get("title") or "").strip()
    message=(request.form.get("message") or "").strip()
    if not title or not message:
        flash("Announcement title and message are required.","error")
        return redirect(url_for("admin"))
    con=db()
    con.execute(
        "INSERT INTO announcements(title,message,created_at,enabled) VALUES(?,?,?,1)",
        (title,message,now())
    )
    con.commit()
    con.close()
    flash("Announcement sent successfully.","success")
    return redirect(url_for("admin"))

@app.route("/admin/support/send",methods=["POST"])
@admin_required
def admin_support_send():
    try:
        uid=int(request.form.get("uid") or 0)
    except:
        uid=0
    message=(request.form.get("message") or "").strip()
    if not uid or not message:
        flash("Select a user and enter a message.","error")
        return redirect(url_for("admin"))
    con=db()
    if con.execute("SELECT 1 FROM users WHERE id=?",(uid,)).fetchone():
        con.execute(
            "INSERT INTO support_messages(uid,sender,message,created_at) VALUES(?,?,?,?)",
            (uid,"MANAGER",message,now())
        )
        con.commit()
        flash("Message sent to user.","success")
    con.close()
    return redirect(url_for("admin"))

@app.route("/admin/gift",methods=["POST"])
@admin_required
def admin_gift():
    try: amount=float(request.form.get("amount") or 0)
    except: amount=0
    if amount<=0: flash("Invalid gift amount.","error")
    else:
        code="HUT9-"+''.join(secrets.choice(string.ascii_uppercase+string.digits) for _ in range(8)); con=db(); con.execute("INSERT INTO gift_codes(code,amount) VALUES(?,?)",(code,amount)); con.commit(); con.close(); flash("Gift code created: "+code,"success")
    return redirect(url_for("admin"))

@app.route("/admin/user/<int:uid>/balance",methods=["POST"])
@admin_required
def admin_user_balance(uid):
    try: amount=float(request.form.get("amount") or 0)
    except: amount=0
    con=db()
    con.execute("UPDATE users SET balance=? WHERE id=?",(amount,uid))
    con.execute("INSERT INTO admin_activity(admin_uid,action,details,created_at) VALUES(?,?,?,?)",(current_user()["id"],"BALANCE_EDIT",f"User {uid} balance set to {amount}",now()))
    con.commit(); con.close()
    flash("User balance updated.","success")
    return redirect(url_for("admin"))

@app.route("/admin/user/<int:uid>/block",methods=["POST"])
@admin_required
def admin_user_block(uid):
    con=db()
    con.execute("UPDATE users SET is_blocked=1 WHERE id=?",(uid,))
    con.execute("INSERT INTO admin_activity(admin_uid,action,details,created_at) VALUES(?,?,?,?)",(current_user()["id"],"USER_BLOCK",f"User {uid} blocked",now()))
    con.commit(); con.close()
    flash("User blocked.","success")
    return redirect(url_for("admin"))

@app.route("/admin/user/<int:uid>/unblock",methods=["POST"])
@admin_required
def admin_user_unblock(uid):
    con=db()
    con.execute("UPDATE users SET is_blocked=0 WHERE id=?",(uid,))
    con.execute("INSERT INTO admin_activity(admin_uid,action,details,created_at) VALUES(?,?,?,?)",(current_user()["id"],"USER_UNBLOCK",f"User {uid} unblocked",now()))
    con.commit(); con.close()
    flash("User unblocked.","success")
    return redirect(url_for("admin"))

@app.route("/admin/user/<int:uid>/reset-password",methods=["POST"])
@admin_required
def admin_reset_password(uid):
    password=request.form.get("password","").strip()
    if len(password)<4:
        flash("Password must be at least 4 characters.","error")
        return redirect(url_for("admin"))
    con=db()
    con.execute("UPDATE users SET password=? WHERE id=?",(pw_hash(password),uid))
    con.execute("UPDATE password_requests SET status=? WHERE uid=?",( "RESOLVED",uid))
    con.execute("INSERT INTO admin_activity(admin_uid,action,details,created_at) VALUES(?,?,?,?)",(current_user()["id"],"PASSWORD_RESET",f"Password reset for user {uid}",now()))
    con.commit(); con.close()
    flash("Password reset successfully.","success")
    return redirect(url_for("admin"))

@app.route("/admin/gift/create",methods=["POST"])
@admin_required
def admin_gift_create():
    try:
        amount=float(request.form.get("amount") or 0)
        max_uses=int(request.form.get("max_uses") or 1)
    except:
        amount=0
        max_uses=1
    code=request.form.get("code","").strip().upper()
    if not code:
        code="HUT9-"+"".join(secrets.choice(string.ascii_uppercase+string.digits) for _ in range(8))
    if amount<=0 or max_uses<1:
        flash("Enter a valid reward amount and claim limit.","error")
        return redirect(url_for("admin"))
    con=db()
    exists=con.execute("SELECT 1 FROM gift_codes WHERE code=?",(code,)).fetchone()
    if exists:
        con.close()
        flash("That gift code already exists.","error")
        return redirect(url_for("admin"))
    con.execute("INSERT INTO gift_codes(code,amount,max_uses,enabled) VALUES(?,?,?,1)",(code,amount,max_uses))
    con.execute("INSERT INTO admin_activity(admin_uid,action,details,created_at) VALUES(?,?,?,?)",(current_user()["id"],"GIFT_CREATE",f"{code} UGX {amount} limit {max_uses}",now()))
    con.commit(); con.close()
    flash("Gift code created successfully.","success")
    return redirect(url_for("admin"))

@app.route("/admin/gift/<code>/toggle",methods=["POST"])
@admin_required
def admin_gift_toggle(code):
    con=db()
    g=con.execute("SELECT enabled FROM gift_codes WHERE code=?",(code,)).fetchone()
    if g:
        new=0 if g["enabled"] else 1
        con.execute("UPDATE gift_codes SET enabled=? WHERE code=?",(new,code))
        con.execute("INSERT INTO admin_activity(admin_uid,action,details,created_at) VALUES(?,?,?,?)",(current_user()["id"],"GIFT_TOGGLE",f"{code} enabled={new}",now()))
        con.commit()
    con.close()
    return redirect(url_for("admin"))

@app.route("/admin/gift/<code>/edit",methods=["POST"])
@admin_required
def admin_gift_edit(code):
    try:
        amount=float(request.form.get("amount") or 0)
        max_uses=int(request.form.get("max_uses") or 1)
    except:
        amount=0
        max_uses=1
    if amount<=0 or max_uses<1:
        flash("Invalid gift-code settings.","error")
        return redirect(url_for("admin"))
    con=db()
    con.execute("UPDATE gift_codes SET amount=?,max_uses=? WHERE code=?",(amount,max_uses,code))
    con.execute("INSERT INTO admin_activity(admin_uid,action,details,created_at) VALUES(?,?,?,?)",(current_user()["id"],"GIFT_EDIT",f"{code} amount={amount} limit={max_uses}",now()))
    con.commit(); con.close()
    flash("Gift code updated.","success")
    return redirect(url_for("admin"))

@app.route("/admin/manager/edit",methods=["POST"])
@admin_required
def admin_manager_edit():
    mid=request.form.get("id","").strip()
    name=request.form.get("name","").strip()
    phone=request.form.get("phone","").strip()
    role=request.form.get("role","CODEX Manager").strip()
    avatar=request.form.get("avatar","👤").strip() or "👤"
    if not mid or not name or not phone:
        flash("Manager name and phone are required.","error")
        return redirect(url_for("admin"))
    con=db()
    old=con.execute("SELECT phone FROM managers WHERE id=?",(mid,)).fetchone()
    con.execute("UPDATE managers SET name=?,phone=?,role=?,avatar=? WHERE id=?",(name,phone,role,avatar,mid))
    if old and old["phone"]!=phone:
        con.execute("UPDATE users SET manager_phone=? WHERE manager_phone=?",(phone,old["phone"]))
    con.execute("INSERT INTO admin_activity(admin_uid,action,details,created_at) VALUES(?,?,?,?)",(current_user()["id"],"MANAGER_EDIT",f"Manager {mid} edited",now()))
    con.commit(); con.close()
    flash("Manager updated.","success")
    return redirect(url_for("admin"))

@app.route("/admin/manager/<mid>/toggle",methods=["POST"])
@admin_required
def admin_manager_toggle(mid):
    con=db()
    m=con.execute("SELECT enabled FROM managers WHERE id=?",(mid,)).fetchone()
    if m:
        con.execute("UPDATE managers SET enabled=? WHERE id=?",(0 if m["enabled"] else 1,mid))
        con.execute("INSERT INTO admin_activity(admin_uid,action,details,created_at) VALUES(?,?,?,?)",(current_user()["id"],"MANAGER_TOGGLE",f"Manager {mid}",now()))
        con.commit()
    con.close()
    return redirect(url_for("admin"))

@app.route("/admin/user/<int:uid>/admin",methods=["POST"])
@admin_required
def admin_user_admin(uid):
    value=1 if request.form.get("value")=="1" else 0
    if uid==current_user()["id"] and value==0:
        flash("You cannot remove your own admin access.","error")
        return redirect(url_for("admin"))
    con=db()
    con.execute("UPDATE users SET is_admin=? WHERE id=?",(value,uid))
    con.execute("INSERT INTO admin_activity(admin_uid,action,details,created_at) VALUES(?,?,?,?)",(current_user()["id"],"ADMIN_ACCESS",f"User {uid} admin={value}",now()))
    con.commit(); con.close()
    flash("Admin access updated.","success")
    return redirect(url_for("admin"))

@app.route("/admin/gift/<code>/claims")
@admin_required
def admin_gift_claims(code):
    con=db()
    claims=con.execute("SELECT gc.*,u.phone,u.display_name FROM gift_code_claims gc LEFT JOIN users u ON u.id=gc.uid WHERE gc.code=? ORDER BY gc.id DESC",(code,)).fetchall()
    con.close()
    return render_template("admin_gift_claims.html",code=code,claims=claims)

@app.route("/admin/activity")
@admin_required
def admin_activity():
    con=db()
    activity=con.execute("SELECT a.*,u.phone FROM admin_activity a LEFT JOIN users u ON u.id=a.admin_uid ORDER BY a.id DESC LIMIT 200").fetchall()
    con.close()
    return render_template("admin_activity.html",activity=activity)

@app.route("/admin/create")
def admin_create():
    phone=os.environ.get("ADMIN_PHONE"); password=os.environ.get("ADMIN_PASSWORD")
    if not phone or not password: return "Set ADMIN_PHONE and ADMIN_PASSWORD environment variables first.",400
    con=db(); exists=con.execute("SELECT 1 FROM users WHERE phone=?",(phone,)).fetchone()
    if not exists: con.execute("INSERT INTO users(phone,password,invite_code,created_at,is_admin) VALUES(?,?,?,?,1)",(phone,pw_hash(password),make_code(con),now()))
    else: con.execute("UPDATE users SET is_admin=1,password=? WHERE phone=?",(pw_hash(password),phone))
    con.commit(); con.close(); return "Admin account ready."

init_db()
if __name__=="__main__": app.run(host="0.0.0.0",port=int(os.environ.get("PORT",5000)),debug=False)
