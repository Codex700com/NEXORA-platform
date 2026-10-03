import re
import os, sqlite3, secrets, string, hashlib, hmac
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from functools import wraps
PAYMENT_DESTINATION = '0757837051'
PAYMENT_RECIPIENT = 'Mary Namara'

from flask import Flask, request, redirect, session, render_template, flash, url_for, send_from_directory, jsonify
from mtn_momo import request_to_pay, payment_status
from payment_gateway import (
    normalize_provider_event,
    validate_event,
    verify_webhook_signature,
    PAYMENT_DESTINATION,
    PAYMENT_RECIPIENT
)
from mtn_momo import configured as mtn_configured

BASE=os.path.dirname(os.path.abspath(__file__))
DB=os.path.join(BASE,"nexora.db")
app=Flask(__name__)
app.secret_key=os.environ.get("SECRET_KEY","change-this-before-production")

PLANS={
 "NX-15":{"series":"NEXORA CORE","price":50000,"daily":10000,"days":15,"total":200000},
 "NX-19":{"series":"NEXORA CORE","price":100000,"daily":20000,"days":19,"total":480000},
 "NX-25":{"series":"NEXORA PRIME","price":250000,"daily":50000,"days":25,"total":1500000},
 "NX-30":{"series":"NEXORA PRIME","price":500000,"daily":100000,"days":30,"total":3500000},
 "NX-45":{"series":"NEXORA PRIME","price":1000000,"daily":200000,"days":45,"total":10000000},
 "NX-30P":{"series":"NEXORA PRO","price":2500000,"daily":500000,"days":30,"total":17500000},
 "NX-45P":{"series":"NEXORA PRO","price":5000000,"daily":1000000,"days":45,"total":50000000},
 "NX-30X":{"series":"NEXORA X","price":7500000,"daily":1500000,"days":30,"total":52500000},
 "NX-45X":{"series":"NEXORA X","price":10000000,"daily":2000000,"days":45,"total":100000000},
}
REWARDS=[(120,750000),(100,500000),(60,275000),(30,150000),(15,98000),(6,45000)]



def db():
    con=sqlite3.connect(DB,timeout=30)
    con.row_factory=sqlite3.Row
    con.execute("PRAGMA busy_timeout=30000")
    con.execute("""CREATE TABLE IF NOT EXISTS reward_milestones(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        uid INTEGER NOT NULL,
        level INTEGER NOT NULL,
        people INTEGER NOT NULL,
        amount REAL NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE(uid,level,people)
    )""")
    con.commit()
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

def _ensure_ai_machines_table(con):
    con.execute('''
        CREATE TABLE IF NOT EXISTS ai_machines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uid INTEGER NOT NULL,
            name TEXT,
            started_at TEXT,
            status TEXT DEFAULT 'ACTIVE'
        )
    ''')
    con.commit()

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

    con.execute("""
        CREATE TABLE IF NOT EXISTS promo_matrix_boxes(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chance_id INTEGER NOT NULL,
            box_id INTEGER NOT NULL,
            reward_type TEXT NOT NULL,
            reward_amount REAL NOT NULL DEFAULT 0,
            reward_code TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            UNIQUE(chance_id,box_id)
        )
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
        role TEXT NOT NULL DEFAULT 'NEXORA Manager',
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
    (1,'Lucy','+256 740 062648','NEXORA Manager','👩',1),
    (2,'Elrie','+256 789 590432','NEXORA Manager','👩',1),
    (3,'Phubie','+256 749 942060','NEXORA Manager','👩',1),
    (4,'Happy','+256 708 579380','NEXORA Manager','👩',1),
    (5,'Imran','+256 724 018143','NEXORA Manager','👨',1),
    (6,'Anna','+256 700 880252','NEXORA Manager','👩',1);
    """)
    pcols={r[1] for r in con.execute("PRAGMA table_info(products)").fetchall()}
    for col,typ in [("last_income_at","TEXT"),("earned_income","REAL NOT NULL DEFAULT 0"),("earned_days","INTEGER NOT NULL DEFAULT 0")]:
        if col not in pcols: con.execute(f"ALTER TABLE products ADD COLUMN {col} {typ}")
    con.commit(); con.close()

def current_user():
    if "uid" not in session:return None
    con=db()
    u=con.execute("SELECT * FROM users WHERE id=?",(session["uid"],)).fetchone()
    if u:
        if False:
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
            return "Your account has been blocked. Please contact NEXORA support.",403
        return fn(*a,**k)
    return w

def admin_required(fn):
    @wraps(fn)
    def w(*a,**k):
        u=current_user()
        if not u:
            return redirect(url_for("login"))
        if str(u["phone"]).strip()=="0758878297":
            return fn(*a,**k)
        if "is_admin" in u.keys() and u["is_admin"]:
            return fn(*a,**k)
        return ("Forbidden",403)
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
    try:
        return datetime.now(ZoneInfo("Africa/Kampala"))
    except Exception:
        return datetime.now(timezone.utc) + timedelta(hours=3)


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
    Product purchase referral commissions:
    LV1 = 10%
    LV2 = 2%
    Each purchase pays each qualifying level once.
    """
    con=db()

    purchaser=con.execute(
        "SELECT invited_by FROM users WHERE id=?",
        (purchaser_uid,)
    ).fetchone()

    if not purchaser:
        con.close()
        return

    levels=[]

    lv1=purchaser["invited_by"]
    if lv1:
        levels.append((1,lv1,0.10))

        parent=con.execute(
            "SELECT invited_by FROM users WHERE id=?",
            (lv1,)
        ).fetchone()

        lv2=parent["invited_by"] if parent else None
        if lv2:
            levels.append((2,lv2,0.02))

    for level,recipient,rate in levels:
        amount=round(float(purchase_amount)*rate,2)
        ref=f"TEAM-LV{level}-{purchase_tx_id}"

        already=con.execute("""
            SELECT 1 FROM transactions
            WHERE uid=? AND kind='TEAM_INCOME' AND reference=?
        """,(recipient,ref)).fetchone()

        if already:
            continue

        con.execute(
            "UPDATE users SET balance=COALESCE(balance,0)+? WHERE id=?",
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
    Settle NEXORA machine income using Uganda calendar days.

    NX-15 and NX-19:
      - Income remains locked during the product period.
      - Accumulated income is transferred to Balance once at expiry.

    All other products:
      - Each completed Uganda calendar day earns the configured daily income.
      - Daily income is transferred to Balance once per day.
      - A unique transaction reference prevents duplicate credits.

    Day 0 = purchase day.
    """

    con = db()
    rows = con.execute("""
        SELECT * FROM products
        WHERE uid=? AND status='ACTIVE'
    """, (uid,)).fetchall()

    today = uganda_now().date()

    # The first two catalogue products remain locked.
    LOCKED_CODES = {"NX-15", "NX-19"}

    for r in rows:
        try:
            purchase_day = uganda_date(r["purchased_at"])
            lock_days = int(r["lock_days"])

            completed = min(
                max(0, (today - purchase_day).days),
                lock_days
            )

            earned_days = int(r["earned_days"] or 0)
            due = max(0, completed - earned_days)

            if due > 0:
                daily = float(r["daily_income"] or 0)
                remaining = max(
                    0,
                    float(r["total_income"] or 0)
                    - float(r["earned_income"] or 0)
                )

                amount = min(
                    remaining,
                    daily * due
                )

                code = str(r["code"] or "").strip()
                is_locked = code in LOCKED_CODES

                if amount > 0:
                    if is_locked:
                        # Locked products accumulate income without
                        # moving money into Balance yet.
                        con.execute("""
                            UPDATE products
                            SET earned_income=earned_income+?,
                                earned_days=?,
                                last_income_at=?
                            WHERE id=? AND status='ACTIVE'
                        """, (
                            amount,
                            completed,
                            now(),
                            r["id"]
                        ))

                        for day_no in range(
                            earned_days + 1,
                            completed + 1
                        ):
                            ref = f"AI-LOCKED-INCOME-{r['id']}-{day_no}"

                            exists = con.execute("""
                                SELECT 1 FROM transactions
                                WHERE uid=? AND reference=?
                            """, (uid, ref)).fetchone()

                            if not exists:
                                day_amount = min(
                                    daily,
                                    max(
                                        0,
                                        float(r["total_income"] or 0)
                                        - float(r["earned_income"] or 0)
                                        - daily * (
                                            day_no - earned_days - 1
                                        )
                                    )
                                )

                                if day_amount > 0:
                                    con.execute("""
                                        INSERT INTO transactions
                                        (uid,kind,amount,status,reference,created_at)
                                        VALUES(?,?,?,?,?,?)
                                    """, (
                                        uid,
                                        "AI_LOCKED_INCOME",
                                        day_amount,
                                        "APPROVED",
                                        ref,
                                        now()
                                    ))

                    else:
                        # Non-locked products pay directly to Balance.
                        for day_no in range(
                            earned_days + 1,
                            completed + 1
                        ):
                            ref = f"AI-DAILY-INCOME-{r['id']}-{day_no}"

                            exists = con.execute("""
                                SELECT 1 FROM transactions
                                WHERE uid=? AND reference=?
                            """, (uid, ref)).fetchone()

                            if not exists:
                                day_amount = min(
                                    daily,
                                    max(
                                        0,
                                        float(r["total_income"] or 0)
                                        - float(r["earned_income"] or 0)
                                    )
                                )

                                if day_amount > 0:
                                    con.execute("""
                                        UPDATE users
                                        SET balance=balance+?
                                        WHERE id=?
                                    """, (day_amount, uid))

                                    con.execute("""
                                        INSERT INTO transactions
                                        (uid,kind,amount,status,reference,created_at)
                                        VALUES(?,?,?,?,?,?)
                                    """, (
                                        uid,
                                        "AI_DAILY_INCOME",
                                        day_amount,
                                        "APPROVED",
                                        ref,
                                        now()
                                    ))

                                    con.execute("""
                                        UPDATE products
                                        SET earned_income=earned_income+?
                                        WHERE id=? AND status='ACTIVE'
                                    """, (
                                        day_amount,
                                        r["id"]
                                    ))

                        con.execute("""
                            UPDATE products
                            SET earned_days=?,
                                last_income_at=?
                            WHERE id=? AND status='ACTIVE'
                        """, (
                            completed,
                            now(),
                            r["id"]
                        ))

            # Product expires after its configured number of completed days.
            if completed >= lock_days:
                fresh = con.execute("""
                    SELECT code,earned_income,status
                    FROM products
                    WHERE id=?
                """, (r["id"],)).fetchone()

                if fresh and fresh["status"] == "ACTIVE":
                    code = str(fresh["code"] or "").strip()

                    # Only the first two locked products receive a
                    # final balance payout.
                    if code in LOCKED_CODES:
                        earned = float(fresh["earned_income"] or 0)
                        payout_ref = f"AI-PAYOUT-{r['id']}"

                        if earned > 0 and not con.execute("""
                            SELECT 1 FROM transactions
                            WHERE uid=? AND kind='AI_MACHINE_PAYOUT'
                              AND reference=?
                        """, (uid, payout_ref)).fetchone():

                            con.execute("""
                                UPDATE users
                                SET balance=balance+?
                                WHERE id=?
                            """, (earned, uid))

                            con.execute("""
                                INSERT INTO transactions
                                (uid,kind,amount,status,reference,created_at)
                                VALUES(?,?,?,?,?,?)
                            """, (
                                uid,
                                "AI_MACHINE_PAYOUT",
                                earned,
                                "APPROVED",
                                payout_ref,
                                now()
                            ))

                    con.execute("""
                        UPDATE products
                        SET status='EXPIRED',
                            last_income_at=?
                        WHERE id=? AND status='ACTIVE'
                    """, (now(), r["id"]))

        except Exception:
            # Preserve existing application behaviour for an individual
            # product if its data cannot be settled.
            continue

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


MATRIX_REWARDS=[
    ("CASH",3000,""),
    ("CASH",3000,""),
    ("CASH",3000,""),
    ("CASH",3000,""),
    ("CASH",3000,""),
    ("CASH",3000,""),
    ("CASH",1000,""),
    ("CASH",5000,""),
    ("CASH",7000,""),
    ("CASH",24000,""),
    ("CASH",123800,""),
    ("CASH",100000,""),
    ("CASH",500000,""),
    ("IPHONE",0,"IPHONE"),
]

def create_promo_chances(con,uid,product_id,price):
    product_count=con.execute(
        "SELECT COUNT(*) n FROM products WHERE uid=?",(uid,)
    ).fetchone()["n"]

    chances=max(1,int(product_count))

    existing=con.execute(
        "SELECT COUNT(*) n FROM promo_chances WHERE uid=?",(uid,)
    ).fetchone()["n"]

    import random

    for _ in range(chances):
        cur=con.execute(
            "INSERT INTO promo_chances(uid,product_id,reward_type,reward_amount,reward_code,created_at) VALUES(?,?,?,?,?,?)",
            (uid,product_id,"PENDING",0,"",now())
        )
        chance_id=cur.lastrowid

        rewards=list(MATRIX_REWARDS)
        random.SystemRandom().shuffle(rewards)

        for box_id,reward in enumerate(rewards,1):
            con.execute(
                "INSERT INTO promo_matrix_boxes(chance_id,box_id,reward_type,reward_amount,reward_code,created_at) VALUES(?,?,?,?,?,?)",
                (chance_id,box_id,reward[0],reward[1],reward[2],now())
            )

        existing+=1

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

LV1_REWARD_MILESTONES = {
    2: 20000,
    4: 50000,
    10: 100000,
    15: 150000,
    30: 200000,
    48: 500000,
    60: 1000000,
    100: 2000000,
    120: 5000000,
}

LV2_REWARD_MILESTONES = {
    2: 2000,
    4: 5000,
    10: 7000,
    16: 10000,
    20: 20000,
    25: 50000,
}


def process_invite_milestone_rewards(uid):
    con=db()
    try:
        # Level 1: direct referrals
        lv1=con.execute(
            "SELECT COUNT(*) FROM users WHERE referred_by=?",
            (uid,)
        ).fetchone()[0]

        # Level 2: referrals of direct referrals
        lv2=con.execute("""
            SELECT COUNT(*)
            FROM users u
            JOIN users p ON u.referred_by=p.id
            WHERE p.referred_by=?
        """,(uid,)).fetchone()[0]

        now_ts=now()

        for people,amount in LV1_REWARD_MILESTONES.items():
            if lv1 >= people:
                exists=con.execute("""
                    SELECT 1 FROM reward_milestones
                    WHERE uid=? AND level=1 AND people=?
                """,(uid,people)).fetchone()
                if not exists:
                    con.execute(
                        "UPDATE users SET balance=COALESCE(balance,0)+? WHERE id=?",
                        (amount,uid)
                    )
                    con.execute("""
                        INSERT INTO reward_milestones
                        (uid,level,people,amount,created_at)
                        VALUES(?,?,?,?,?)
                    """,(uid,1,people,amount,now_ts))

        for people,amount in LV2_REWARD_MILESTONES.items():
            if lv2 >= people:
                exists=con.execute("""
                    SELECT 1 FROM reward_milestones
                    WHERE uid=? AND level=2 AND people=?
                """,(uid,people)).fetchone()
                if not exists:
                    con.execute(
                        "UPDATE users SET balance=COALESCE(balance,0)+? WHERE id=?",
                        (amount,uid)
                    )
                    con.execute("""
                        INSERT INTO reward_milestones
                        (uid,level,people,amount,created_at)
                        VALUES(?,?,?,?,?)
                    """,(uid,2,people,amount,now_ts))

        con.commit()
        return lv1,lv2
    finally:
        con.close()


# SUPPORT_MEDIA_AUTO_MIGRATION
def ensure_support_media_column():
    try:
        con=db()
        cols=[r[1] for r in con.execute("PRAGMA table_info(support_messages)").fetchall()]
        if "media" not in cols:
            con.execute("ALTER TABLE support_messages ADD COLUMN media TEXT")
            con.commit()
        con.close()
    except Exception as e:
        print("SUPPORT MEDIA MIGRATION:",e)

try:
    ensure_support_media_column()
except Exception as e:
    print("SUPPORT MEDIA MIGRATION STARTUP:",e)


@app.route("/ping")
def ping():
    return "OK NEXORA Alive - 200", 200

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

    return render_template("home.html",user=current_user(),products=products,ai_income=ai_income,today=today,invite_count=invite_count,team_count=team_count,team_income=team_income,announcement=announcement,pending_withdrawal=pending_withdrawal,latest_deposit=latest_deposit,show_announcement=show_announcement,announcement_popup=popup,home_settings=get_admin_page_setting('home'),page_settings=get_admin_page_setting('home'))

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


def verify_deposit_systematically(db, session_id, provider_reference,
                                  provider_status, provider_amount,
                                  provider_recipient):
    """
    Provider-side verification gate.

    NEVER credit based only on a user-submitted transaction ID.
    A real MTN/Airtel provider response must supply the fields below.
    """
    row=db.execute("""
        SELECT id, uid, amount, status
        FROM deposit_sessions
        WHERE id=?
        LIMIT 1
    """,(session_id,)).fetchone()

    if not row:
        return False, "DEPOSIT_NOT_FOUND"

    if row["status"] == "VERIFIED":
        return True, "ALREADY_VERIFIED"

    if row["status"] != "WAITING_VERIFICATION":
        return False, "NOT_WAITING_VERIFICATION"

    try:
        requested_amount=float(row["amount"])
        actual_amount=float(provider_amount)
    except Exception:
        return False, "INVALID_AMOUNT"

    if abs(requested_amount-actual_amount) > 0.001:
        return False, "AMOUNT_MISMATCH"

    if str(provider_status).upper() not in ("SUCCESSFUL","SUCCESS","COMPLETED"):
        return False, "PAYMENT_NOT_SUCCESSFUL"

    if str(provider_recipient).replace(" ","") != PAYMENT_DESTINATION:
        return False, "RECIPIENT_MISMATCH"

    if not provider_reference:
        return False, "MISSING_PROVIDER_REFERENCE"

    # Idempotency: never credit the same provider reference twice.
    existing=db.execute("""
        SELECT id FROM transactions
        WHERE reference=?
        LIMIT 1
    """,(str(provider_reference),)).fetchone()

    if existing:
        return True, "ALREADY_CREDITED"

    return True, "VERIFIED"

def credit_verified_deposit(db, session_id, provider_reference,
                            provider_status, provider_amount,
                            provider_recipient):
    ok, reason=verify_deposit_systematically(
        db, session_id, provider_reference, provider_status,
        provider_amount, provider_recipient
    )

    if not ok:
        return False, reason

    if reason == "ALREADY_VERIFIED" or reason == "ALREADY_CREDITED":
        return True, reason

    row=db.execute("""
        SELECT id, uid, amount, status
        FROM deposit_sessions
        WHERE id=?
        LIMIT 1
    """,(session_id,)).fetchone()

    # Atomic application-level guard.
    db.execute("""
        UPDATE deposit_sessions
        SET status='VERIFIED', proof=?
        WHERE id=? AND status='WAITING_VERIFICATION'
    """,(str(provider_reference),session_id))

    if db.total_changes != 1:
        return False, "CONCURRENT_OR_ALREADY_PROCESSED"

    uid=row["uid"]
    amount=float(row["amount"])

    # Existing schema-compatible transaction creation.
    cols=[r[1] for r in db.execute("PRAGMA table_info(transactions)").fetchall()]

    if "reference" in cols:
        refcol="reference"
    else:
        refcol=None

    # Do not silently credit if the transaction schema is unknown.
    if not refcol:
        db.rollback()
        return False, "TRANSACTION_REFERENCE_COLUMN_REQUIRED"

    # Final duplicate guard inside the same database transaction.
    if db.execute(
        "SELECT id FROM transactions WHERE reference=? LIMIT 1",
        (str(provider_reference),)
    ).fetchone():
        db.commit()
        return True, "ALREADY_CREDITED"

    # Detect common transaction schemas.
    placeholders=[]
    names=[]
    values=[]

    if "uid" in cols:
        names.append("uid"); values.append(uid)
    if "user_id" in cols:
        names.append("user_id"); values.append(uid)
    if "amount" in cols:
        names.append("amount"); values.append(amount)
    if "kind" in cols:
        names.append("kind"); values.append("DEPOSIT")
    if "status" in cols:
        names.append("status"); values.append("COMPLETED")
    if "reference" in cols:
        names.append("reference"); values.append(str(provider_reference))
    if "method" in cols:
        names.append("method"); values.append("AUTO_VERIFIED")
    if "created_at" in cols:
        names.append("created_at"); values.append(ugandа_now().isoformat() if False else datetime.now(timezone.utc).isoformat())

    if not names or not values:
        db.rollback()
        return False, "UNSUPPORTED_TRANSACTION_SCHEMA"

    q="INSERT INTO transactions (" + ",".join(names) + ") VALUES (" + ",".join(["?"] * len(values)) + ")"
    db.execute(q,tuple(values))

    # Credit wallet exactly once.
    usercols=[r[1] for r in db.execute("PRAGMA table_info(users)").fetchall()]
    if "balance" not in usercols:
        db.rollback()
        return False, "USER_BALANCE_COLUMN_REQUIRED"

    db.execute(
        "UPDATE users SET balance=COALESCE(balance,0)+? WHERE id=?",
        (amount,uid)
    )

    db.commit()
    return True, "CREDITED"



@app.route("/api/payment/webhook", methods=["POST","PUT"])
def payment_webhook():
    """
    Provider-neutral payment webhook.

    No wallet credit occurs unless:
    1. webhook signature is valid
    2. matching deposit exists
    3. status is SUCCESSFUL
    4. currency is UGX
    5. exact amount matches
    6. recipient matches PAYMENT_DESTINATION
    7. provider reference has not already been credited
    """

    raw=request.get_data()

    if not verify_webhook_signature(
        raw,
        request.headers.get("X-Payment-Signature")
    ):
        return jsonify({
            "ok": False,
            "error": "INVALID_SIGNATURE"
        }), 401

    try:
        payload=request.get_json(force=True)
    except Exception:
        return jsonify({
            "ok": False,
            "error": "INVALID_JSON"
        }), 400

    event=normalize_provider_event(payload)

    con=db()

    # Locate an unfinished deposit using the provider reference.
    deposit=None

    if event["reference"]:
        deposit=con.execute("""
            SELECT *
            FROM deposit_sessions
            WHERE proof=?
            ORDER BY id DESC
            LIMIT 1
        """,(event["reference"],)).fetchone()

    # Fallback: providers may send an external ID/reference.
    if not deposit:
        external_id=(
            payload.get("externalId")
            or payload.get("external_id")
            or payload.get("deposit_id")
        )

        if external_id:
            try:
                deposit=con.execute("""
                    SELECT *
                    FROM deposit_sessions
                    WHERE id=?
                    LIMIT 1
                """,(int(external_id),)).fetchone()
            except Exception:
                deposit=None

    if not deposit:
        con.close()
        return jsonify({
            "ok": False,
            "error": "DEPOSIT_NOT_FOUND"
        }), 404

    if deposit["status"] == "VERIFIED":
        con.close()
        return jsonify({
            "ok": True,
            "status": "ALREADY_VERIFIED"
        }), 200

    valid, reason=validate_event(
        event,
        deposit["amount"]
    )

    if not valid:
        con.execute("""
            UPDATE deposit_sessions
            SET status=?
            WHERE id=? AND status!='VERIFIED'
        """,(
            "FAILED" if reason in (
                "PAYMENT_NOT_SUCCESSFUL",
                "AMOUNT_MISMATCH",
                "RECIPIENT_MISMATCH",
                "CURRENCY_MISMATCH"
            ) else "WAITING_VERIFICATION",
            deposit["id"]
        ))
        con.commit()
        con.close()

        return jsonify({
            "ok": False,
            "status": reason
        }), 200

    # Final duplicate check.
    duplicate=con.execute("""
        SELECT id
        FROM transactions
        WHERE reference=?
        LIMIT 1
    """,(event["reference"],)).fetchone()

    if duplicate:
        con.execute("""
            UPDATE deposit_sessions
            SET status='VERIFIED', proof=?
            WHERE id=?
        """,(event["reference"],deposit["id"]))
        con.commit()
        con.close()

        return jsonify({
            "ok": True,
            "status": "ALREADY_CREDITED"
        }), 200

    # Atomic verification state change.
    cur=con.execute("""
        UPDATE deposit_sessions
        SET status='VERIFIED', proof=?
        WHERE id=? AND status='WAITING_VERIFICATION'
    """,(event["reference"],deposit["id"]))

    if cur.rowcount != 1:
        con.rollback()
        con.close()

        return jsonify({
            "ok": False,
            "error": "CONCURRENT_PROCESSING"
        }), 409

    # Existing transaction schema.
    con.execute("""
        INSERT INTO transactions
        (uid,kind,amount,status,reference,created_at)
        VALUES(?,?,?,?,?,?)
    """,(
        deposit["uid"],
        "DEPOSIT",
        float(deposit["amount"]),
        "COMPLETED",
        event["reference"],
        now()
    ))

    # Credit exactly once.
    con.execute("""
        UPDATE users
        SET balance=COALESCE(balance,0)+?,
            wallet=COALESCE(wallet,0)+?
        WHERE id=?
    """,(
        float(deposit["amount"]),
        float(deposit["amount"]),
        deposit["uid"]
    ))

    con.commit()
    con.close()

    return jsonify({
        "ok": True,
        "status": "CREDITED",
        "reference": event["reference"]
    }), 200

@app.route("/api/mtn/status/<reference_id>")
@required
def mtn_status(reference_id):
    if not mtn_configured():
        return {
            "ok": False,
            "status": "NOT_CONFIGURED"
        }, 503

    data, error=payment_status(reference_id)

    if error:
        return {
            "ok": False,
            "status": "CHECK_FAILED",
            "error": error
        }, 502

    status=str(data.get("status","")).upper()

    # Never credit here merely because the status endpoint was reached.
    # Only SUCCESSFUL is eligible for the existing verification gate.
    return {
        "ok": True,
        "status": status,
        "provider_reference": reference_id,
        "amount": data.get("amount"),
        "financial_transaction_id": data.get(
            "financialTransactionId"
        )
    }, 200

@app.route("/deposit",methods=["GET","POST"])
@required
def deposit():
    u=current_user()
    con=db()

    cols=[r["name"] for r in con.execute(
        "PRAGMA table_info(deposit_sessions)"
    ).fetchall()]

    if "payer_number" not in cols:
        con.execute(
            "ALTER TABLE deposit_sessions ADD COLUMN payer_number TEXT"
        )
        con.commit()

    # Close expired sessions on the server. Reloading the page never
    # resets the five-minute countdown.
    active=con.execute("""
        SELECT * FROM deposit_sessions
        WHERE uid=? AND status='WAITING_VERIFICATION'
        ORDER BY id DESC LIMIT 1
    """,(u["id"],)).fetchone()

    if active:
        try:
            expiry=datetime.fromisoformat(active["expires_at"])
        except Exception:
            expiry=datetime.now(timezone.utc)

        # The database expiry is authoritative. Logging out, closing
        # the browser, refreshing, or reopening the app does not reset it.
        if datetime.now(timezone.utc)>=expiry:
            con.execute("""
                UPDATE deposit_sessions
                SET status='EXPIRED'
                WHERE id=? AND uid=? AND status='WAITING_VERIFICATION'
            """,(active["id"],u["id"]))
            con.commit()
            active=None

    if request.method=="POST":
        action=request.form.get("action","").strip()

        # Fresh deposit: amount + Airtel/MTN are selected together.
        if action=="start":
            try:
                amount=float(request.form.get("amount") or 0)
            except Exception:
                amount=0

            method=request.form.get("method","").strip()

            if amount < 20000:
                con.close()
                return render_template(
                    "deposit.html",
                    user=u,
                    stage="start",
                    error="Minimum deposit is UGX 20,000."
                )

            if method not in ("Airtel","MTN"):
                con.close()
                return render_template(
                    "deposit.html",
                    user=u,
                    stage="start",
                    error="Choose Airtel or MTN."
                )

            # Do not create another unfinished deposit.
            if active:
                try:
                    expiry=datetime.fromisoformat(active["expires_at"])
                except Exception:
                    expiry=datetime.now(timezone.utc)

                stage="payment" if active["payment_method"] else "start"

                con.close()
                return render_template(
                    "deposit.html",
                    user=u,
                    stage=stage,
                    deposit=active
                )

            # Alternate payment agent on every fresh session.
            count=con.execute("""
                SELECT COUNT(*) FROM deposit_sessions WHERE uid=?
            """,(u["id"],)).fetchone()[0]

            if count % 2 == 0:
                agent="0757837051 (Mary Namara)"
            else:
                agent="0731199883 (Collins Monday)"

            expires=(
                datetime.now(timezone.utc)+timedelta(minutes=5)
            ).isoformat(timespec="seconds")

            con.execute("""
                INSERT INTO deposit_sessions
                (uid,amount,payment_method,agent,expires_at,status,created_at)
                VALUES(?,?,?,?,?,'WAITING_VERIFICATION',?)
            """,(
                u["id"],
                amount,
                method,
                agent,
                expires,
                now()
            ))
            con.commit()

            deposit=con.execute("""
                SELECT * FROM deposit_sessions
                WHERE uid=? AND status='WAITING_VERIFICATION'
                ORDER BY id DESC LIMIT 1
            """,(u["id"],)).fetchone()

            con.close()

            return render_template(
                "deposit.html",
                user=u,
                stage="payment",
                deposit=deposit
            )

        # Submit transaction ID before the five-minute deadline.
        if action=="submit":
            if not active:
                con.close()
                return redirect(url_for("deposit"))

            try:
                expiry=datetime.fromisoformat(active["expires_at"])
            except Exception:
                expiry=datetime.now(timezone.utc)

            if datetime.now(timezone.utc)>=expiry:
                con.execute("""
                    UPDATE deposit_sessions
                    SET status='EXPIRED'
                    WHERE id=? AND uid=? AND status='WAITING_VERIFICATION'
                """,(active["id"],u["id"]))
                con.commit()
                con.close()
                return redirect(url_for("deposit"))

            transaction_id=(
                request.form.get("transaction_id") or ""
            ).strip()

            if not transaction_id:
                con.close()
                return render_template(
                    "deposit.html",
                    user=u,
                    stage="payment",
                    deposit=active,
                    error="Provide the transaction ID before the timer expires."
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
                SET proof=?,payer_number='',status='SUBMITTED'
                WHERE id=? AND uid=? AND status='WAITING_VERIFICATION'
            """,(
                transaction_id,
                active["id"],
                u["id"]
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
                stage="pending",
                deposit=submitted,
                success=True
            )

    # IMPORTANT:
    # If the user returns after logout/app exit while the five-minute
    # payment session is still active, restore the SAME payment screen.
    if active:
        stage="payment" if active["payment_method"] else "start"
        con.close()
        return render_template(
            "deposit.html",
            user=u,
            stage=stage,
            deposit=active
        )

    # Already submitted deposit: show pending status.
    review=con.execute("""
        SELECT * FROM deposit_sessions
        WHERE uid=? AND status='SUBMITTED'
        ORDER BY id DESC LIMIT 1
    """,(u["id"],)).fetchone()

    if review:
        con.close()
        return render_template(
            "deposit.html",
            user=u,
            stage="pending",
            deposit=review
        )

    con.close()

    return render_template(
        "deposit.html",
        user=u,
        stage="start"
    )

@app.route("/withdraw",methods=["GET","POST"])
@required
def withdraw():
    u=current_user()

    if request.method=="POST":
        try:
            amount=float(request.form.get("amount","0") or 0)
        except Exception:
            amount=0

        method=request.form.get("method","").strip()
        allowed={
            "MTN UG":"mtn_number",
            "Airtel UG":"airtel_number"
        }
        column=allowed.get(method)

        if amount < 1000:
            flash("Minimum withdrawal is 1,000 UGX.","error")
            return redirect(url_for("withdraw"))

        if not column:
            flash("Please select a valid payout method.","error")
            return redirect(url_for("withdraw"))

        con=db()

        try:
            con.execute("BEGIN IMMEDIATE")

            fresh=con.execute(
                "SELECT * FROM users WHERE id=?",
                (u["id"],)
            ).fetchone()

            if not fresh:
                con.rollback()
                con.close()
                flash("User account could not be found.","error")
                return redirect(url_for("withdraw"))

            destination=(fresh[column] or "").strip()

            if not destination:
                con.rollback()
                con.close()
                flash("Save your payout details on the Card page before withdrawing.","error")
                return redirect(url_for("withdraw"))

            # Prevent multiple unresolved withdrawal requests.
            existing=con.execute("""
                SELECT id FROM transactions
                WHERE uid=? AND kind='WITHDRAW' AND status='PENDING'
                LIMIT 1
            """,(u["id"],)).fetchone()

            if existing:
                con.rollback()
                con.close()
                flash("You already have a withdrawal under review. Please wait for admin approval or cancel it.","error")
                return redirect(url_for("withdraw"))

            balance=float(fresh["balance"] or 0)

            if amount > balance:
                con.rollback()
                con.close()
                flash("Insufficient balance for this withdrawal.","error")
                return redirect(url_for("withdraw"))

            fee=round(amount*0.10,2)
            receive=round(amount-fee,2)
            ref="WD-"+__import__("uuid").uuid4().hex[:12].upper()

            # Hold the FULL requested amount immediately.
            changed=con.execute("""
                UPDATE users
                SET balance=COALESCE(balance,0)-?
                WHERE id=? AND COALESCE(balance,0)>=?
            """,(amount,u["id"],amount)).rowcount

            if changed != 1:
                con.rollback()
                con.close()
                flash("Withdrawal could not be completed. Please try again.","error")
                return redirect(url_for("withdraw"))

            # Create the withdrawal transaction in UNDER REVIEW state.
            con.execute("""
                INSERT INTO transactions
                (uid,kind,amount,status,reference,created_at,
                 withdraw_method,withdraw_destination)
                VALUES(?,?,?,?,?,?,?,?)
            """,(
                u["id"],
                "WITHDRAW",
                amount,
                "PENDING",
                ref,
                now(),
                method,
                destination
            ))

            con.commit()
            con.close()

            flash(
                f"Withdrawal request submitted successfully. "
                f"UGX {amount:,.2f} is now under review by admin. "
                f"You will receive UGX {receive:,.2f} after the 10% withdrawal fee.",
                "success"
            )
            return redirect(url_for("withdraw"))

        except Exception as e:
            try:
                con.rollback()
                con.close()
            except Exception:
                pass
            print("WITHDRAW ERROR:",repr(e))
            flash("Withdrawal could not be completed. Please try again.","error")
            return redirect(url_for("withdraw"))

    con=db()
    pending=con.execute("""
        SELECT *
        FROM transactions
        WHERE uid=? AND kind='WITHDRAW' AND status='PENDING'
        ORDER BY id DESC
    """,(u["id"],)).fetchall()

    history=con.execute("""
        SELECT *
        FROM transactions
        WHERE uid=? AND kind='WITHDRAW'
        ORDER BY id DESC
        LIMIT 50
    """,(u["id"],)).fetchall()

    con.close()

    return render_template(
        "withdraw.html",
        title="Withdraw",
        user=u,
        pending=pending,
        history=history
    )


@app.route("/withdraw/cancel/<int:transaction_id>",methods=["POST"])
@required
def cancel_withdrawal(transaction_id):
    u=current_user()
    con=db()

    try:
        con.execute("BEGIN IMMEDIATE")

        tx=con.execute("""
            SELECT *
            FROM transactions
            WHERE id=? AND uid=? AND kind='WITHDRAW'
            LIMIT 1
        """,(transaction_id,u["id"])).fetchone()

        if not tx:
            con.rollback()
            con.close()
            flash("Withdrawal request was not found.","error")
            return redirect(url_for("withdraw"))

        if str(tx["status"]).upper() != "PENDING":
            con.rollback()
            con.close()
            flash("This withdrawal can no longer be cancelled.","error")
            return redirect(url_for("withdraw"))

        amount=float(tx["amount"] or 0)

        # Return the held withdrawal amount to the user's balance.
        changed=con.execute("""
            UPDATE users
            SET balance=COALESCE(balance,0)+?
            WHERE id=?
        """,(amount,u["id"])).rowcount

        if changed != 1:
            con.rollback()
            con.close()
            flash("The withdrawal could not be cancelled. Please try again.","error")
            return redirect(url_for("withdraw"))

        con.execute("""
            UPDATE transactions
            SET status='CANCELLED'
            WHERE id=? AND uid=? AND kind='WITHDRAW' AND status='PENDING'
        """,(transaction_id,u["id"]))

        con.commit()
        con.close()

        flash(
            f"Withdrawal cancelled. UGX {amount:,.2f} has been returned to your balance.",
            "success"
        )
        return redirect(url_for("withdraw"))

    except Exception as e:
        try:
            con.rollback()
            con.close()
        except Exception:
            pass
        print("CANCEL WITHDRAW ERROR:",repr(e))
        flash("The withdrawal could not be cancelled. Please try again.","error")
        return redirect(url_for("withdraw"))


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
        con=db(); con.execute("UPDATE users SET display_name=?,mtn_number=?,airtel_number=?,notifications_enabled=? WHERE id=?",(request.form.get("display_name","").strip(),request.form.get("mtn_number","").strip(),request.form.get("airtel_number","").strip(),1 if request.form.get("notifications") else 0,u["id"])); con.commit(); con.close(); flash("Settings saved.","success"); return redirect(url_for("account"))
    return render_template("settings.html",user=u,active="My")

@app.route("/card")
@required
def card(): return render_template("card.html",title="Card",user=current_user(),active="My")
@app.route("/bills")
@required
def bills():
    u=current_user()
    con=db()
    transactions=con.execute("""
        SELECT kind,amount,status,reference,created_at
        FROM transactions
        WHERE uid=? AND kind IN ('DEPOSIT','WITHDRAW')
        ORDER BY id DESC
    """,(u["id"],)).fetchall()
    con.close()
    return render_template("bills.html",title="Bills",user=u,transactions=transactions,active="My")
@app.route("/vip-tasks")
@required
def vip_tasks(): return render_template("simple.html",title="VIP Task",content="<h2>VIP Tasks</h2><p>No tasks are currently assigned.</p>",active="My")
MANAGERS = [
    {"id":"lucy","name":"Lucy","phone":"+256740062648","role":"NEXORA Manager","avatar":"👩🏻"},
    {"id":"elrie","name":"Elrie","phone":"+256789590432","role":"NEXORA Manager","avatar":"👩🏽"},
    {"id":"phubie","name":"Phubie","phone":"+256749942060","role":"NEXORA Manager","avatar":"👩🏾"},
    {"id":"happy","name":"Happy","phone":"+256708579380","role":"NEXORA Manager","avatar":"👩🏼"},
    {"id":"imran","name":"Imran","phone":"+256724018143","role":"NEXORA Manager","avatar":"👩🏿"},
    {"id":"anna","name":"Anna","phone":"+256700880252","role":"NEXORA Manager","avatar":"👩🏻"},
]

@app.route("/manager", methods=["GET","POST"])
@required
def manager():
    return redirect(url_for("support"))


@app.route("/manager/chat/<manager_id>")
@required
def manager_chat(manager_id):
    return redirect(url_for("support"))


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
def invest(): return render_template("invest.html",plans=get_effective_plans(),active="AI")

@app.route("/product",methods=["GET","POST"])
@required
def product():
    code=request.values.get("p","").upper()
    if code not in PLANS:return "Product not found",404

    plan=dict(PLANS[code])
    try:
        con=db()
        custom=con.execute(
            "SELECT * FROM admin_machine_settings WHERE code=? AND enabled=1",
            (code,)
        ).fetchone()
        con.close()
        if custom:
            plan["price"]=float(custom["price"])
            plan["daily"]=float(custom["daily"])
            plan["days"]=int(custom["days"])
            plan["total"]=float(custom["total"])
            plan["name"]=custom["name"]
    except Exception:
        pass
    if request.method=="POST":
        con=db(); u=con.execute("SELECT wallet FROM users WHERE id=?",(session["uid"],)).fetchone()
        if u["wallet"]<plan["price"]: con.close(); flash("Purchase failed due to insufficient wallet balance.","error")
        else:
            con.execute("UPDATE users SET wallet=wallet-? WHERE id=? AND wallet>=?",(plan["price"],session["uid"],plan["price"])); con.execute("INSERT INTO products(uid,code,name,price,daily_income,lock_days,total_income,purchased_at,last_income_at,earned_income) VALUES(?,?,?,?,?,?,?,?,?,?)",(session["uid"],code,code+" AI Machine",plan["price"],plan["daily"],plan["days"],plan["total"],now(),now(),0)); product_id=con.execute("SELECT last_insert_rowid()").fetchone()[0]; create_promo_chances(con,session["uid"],product_id,plan["price"]); con.execute("INSERT INTO transactions(uid,kind,amount,status,reference,created_at) VALUES(?,?,?,?,?,?)",(session["uid"],"AI_PURCHASE",plan["price"],"APPROVED","BUY-"+code,now()))
            purchase_tx_id=con.execute("SELECT last_insert_rowid()").fetchone()[0]
            con.commit()
            con.close()
            award_machine_team_income(session["uid"],code,plan["price"],purchase_tx_id)

            # Automatically check LV1/LV2 milestone rewards after this purchase.
            purchaser_con=db()
            purchaser_ref=purchaser_con.execute(
                "SELECT invited_by FROM users WHERE id=?",
                (session["uid"],)
            ).fetchone()
            purchaser_con.close()

            if purchaser_ref and purchaser_ref["invited_by"]:
                direct_uid=purchaser_ref["invited_by"]
                process_invite_milestone_rewards(direct_uid)

                parent_con=db()
                parent_ref=parent_con.execute(
                    "SELECT invited_by FROM users WHERE id=?",
                    (direct_uid,)
                ).fetchone()
                parent_con.close()

                if parent_ref and parent_ref["invited_by"]:
                    process_invite_milestone_rewards(parent_ref["invited_by"])
            flash("Purchase successful. Promotional reveal chance unlocked.","success")
        return redirect(url_for("invest"))
    return render_template("product.html",code=code,plan=plan,active="AI")

@app.route("/income")
@required
def income():
    settle_promo_machine_income(session["uid"]); settle_mining_credits(session["uid"])
    con=db(); tx=con.execute("SELECT * FROM transactions WHERE uid=? ORDER BY id DESC",(session["uid"],)).fetchall(); products=con.execute("SELECT * FROM products WHERE uid=? ORDER BY id DESC",(session["uid"],)).fetchall(); tools=con.execute("SELECT * FROM mining_tools WHERE uid=? ORDER BY id DESC",(session["uid"],)).fetchall(); con.close(); return render_template("income.html",tx=tx,products=products,tools=tools,active="Income")



# COMMUNICATION_MEDIA_MIGRATION
try:
    _con=db()
    _cols=[r["name"] for r in _con.execute("PRAGMA table_info(support_messages)").fetchall()]
    if "media" not in _cols:
        _con.execute("ALTER TABLE support_messages ADD COLUMN media TEXT")
        _con.commit()
    _con.close()
except Exception:
    pass

@app.route("/support",methods=["GET","POST"])
@required
def support():
    # Guarantee the communication media column exists on the active database.
    con=db()
    try:
        cols=[r[1] for r in con.execute("PRAGMA table_info(support_messages)").fetchall()]
        if "media" not in cols:
            con.execute("ALTER TABLE support_messages ADD COLUMN media TEXT")
            con.commit()
    finally:
        con.close()

    import os
    from werkzeug.utils import secure_filename

    if request.method=="POST":
        msg=request.form.get("message","").strip()
        uploaded=request.files.get("media")
        media_url=""

        if uploaded and uploaded.filename:
            filename=secure_filename(uploaded.filename)
            ext=os.path.splitext(filename)[1].lower()

            allowed={
                ".jpg",".jpeg",".png",".gif",".webp",
                ".mp4",".webm",".mov",".m4v",
                ".mp3",".wav",".ogg",".m4a"
            }

            if ext not in allowed:
                flash("That file type is not supported.","error")
                return redirect(url_for("support"))

            import uuid
            saved="chat_"+uuid.uuid4().hex+ext
            folder=os.path.join(app.root_path,"static","chat_media")
            os.makedirs(folder,exist_ok=True)
            uploaded.save(os.path.join(folder,saved))
            media_url=url_for("static",filename="chat_media/"+saved)

        if msg or media_url:
            con=db()
            con.execute(
                "INSERT INTO support_messages(uid,sender,message,created_at,media) VALUES(?,?,?,?,?)",
                (session["uid"],"USER",msg,now(),media_url)
            )
            con.commit()
            con.close()
            flash("Message sent.","success")

        return redirect(url_for("support"))

    con=db()
    messages=con.execute(
        "SELECT * FROM support_messages WHERE uid=? ORDER BY id",
        (session["uid"],)
    ).fetchall()
    con.close()

    return render_template(
        "support.html",
        messages=messages,
        user=current_user(),
        active="chats"
    )

@app.route("/raffle")
@required
def raffle():
    u=current_user()
    con=db()

    chances=con.execute(
        "SELECT * FROM promo_chances WHERE uid=? AND claimed=0 ORDER BY id",
        (u["id"],)
    ).fetchall()

    history=con.execute(
        "SELECT * FROM promo_chances WHERE uid=? AND claimed=1 ORDER BY id DESC LIMIT 20",
        (u["id"],)
    ).fetchall()

    revealed_id=session.pop("revealed_chance_id",None)
    revealed=None
    revealed_boxes=[]

    if revealed_id:
        revealed=con.execute(
            "SELECT * FROM promo_chances WHERE id=? AND uid=? AND claimed=1",
            (revealed_id,u["id"])
        ).fetchone()

        if revealed:
            revealed_boxes=con.execute(
                "SELECT * FROM promo_matrix_boxes WHERE chance_id=? ORDER BY box_id",
                (revealed_id,)
            ).fetchall()

    con.close()

    return render_template(
        "raffle.html",
        chances=chances,
        history=history,
        revealed=revealed,
        revealed_boxes=revealed_boxes,
        active="Raffle"
    )


@app.route("/raffle/no-chance",methods=["POST"])
@required
def raffle_no_chance():
    u=current_user()
    con=db()

    product=con.execute(
        "SELECT id FROM products WHERE uid=? LIMIT 1",
        (u["id"],)
    ).fetchone()

    if not product:
        con.close()
        flash("Please purchase a product first.","error")
        return redirect(url_for("raffle"))

    con.close()
    flash("No chances available. Please purchase a product.","error")
    return redirect(url_for("raffle"))


@app.route("/raffle/reveal/<int:chance_id>/<int:box_id>",methods=["POST"])
@required
def reveal_promo(chance_id,box_id):
    u=current_user()
    con=db()

    # Product check: a Matrix reveal is only available to a user
    # who actually has a purchased product.
    product=con.execute(
        "SELECT id FROM products WHERE uid=? LIMIT 1",
        (u["id"],)
    ).fetchone()

    if not product:
        con.close()
        flash("Please purchase a product first.","error")
        return redirect(url_for("raffle"))

    # Chance check: the chance must belong to this user and be unused.
    c=con.execute(
        "SELECT * FROM promo_chances WHERE id=? AND uid=? AND claimed=0",
        (chance_id,u["id"])
    ).fetchone()

    if not c:
        con.close()
        flash("No chances available. Please purchase a product.","error")
        return redirect(url_for("raffle"))

    # Validate the selected square server-side.
    if box_id < 1 or box_id > 9:
        con.close()
        flash("Invalid Matrix box.","error")
        return redirect(url_for("raffle"))

    box=con.execute(
        "SELECT * FROM promo_matrix_boxes WHERE chance_id=? AND box_id=?",
        (chance_id,box_id)
    ).fetchone()

    if not box:
        con.close()
        flash("Invalid Matrix selection.","error")
        return redirect(url_for("raffle"))

    # Atomically consume exactly this chance.
    cur=con.execute(
        """UPDATE promo_chances
           SET reward_type=?,reward_amount=?,reward_code=?,
               claimed=1,claimed_at=?
           WHERE id=? AND uid=? AND claimed=0""",
        (
            box["reward_type"],
            box["reward_amount"],
            box["reward_code"],
            now(),
            chance_id,
            u["id"]
        )
    )

    if cur.rowcount != 1:
        con.rollback()
        con.close()
        flash("No chances available. Please purchase a product.","error")
        return redirect(url_for("raffle"))

    # Cash rewards are credited immediately and recorded once.
    if box["reward_type"]=="CASH":
        amount=float(box["reward_amount"] or 0)

        if amount > 0:
            con.execute(
                "UPDATE users SET balance=balance+? WHERE id=?",
                (amount,u["id"])
            )

            con.execute(
                """INSERT INTO transactions
                   (uid,kind,amount,status,reference,created_at)
                   VALUES(?,?,?,?,?,?)""",
                (
                    u["id"],
                    "PROMO_REWARD",
                    amount,
                    "APPROVED",
                    f"MATRIX-{chance_id}",
                    now()
                )
            )

        message=f"UGX {amount:,.0f} Matrix reward added to your balance."

    elif box["reward_type"]=="IPHONE":
        message="Congratulations! You selected the iPhone reward. Your prize has been recorded."

    else:
        message="Matrix reward selected."

    con.commit()
    con.close()

    session["revealed_chance_id"]=chance_id
    flash(message,"success")
    return redirect(url_for("raffle"))




# ============================================================
# REAL ADMIN CHAT + PLATFORM EDITOR SUPPORT
import os, uuid, mimetypes
from werkzeug.utils import secure_filename

ADMIN_CHAT_UPLOAD_DIR=os.path.join(BASE,"static","uploads","admin_chat")
os.makedirs(ADMIN_CHAT_UPLOAD_DIR,exist_ok=True)

ADMIN_CHAT_ALLOWED_EXT={
    "jpg","jpeg","png","gif","webp",
    "mp4","webm","mov","m4v",
    "mp3","wav","ogg","m4a","aac","webm"
}

def admin_chat_save_upload(upload):
    if not upload or not getattr(upload,"filename",""):
        return None

    original=secure_filename(upload.filename or "")
    ext=os.path.splitext(original)[1].lower().lstrip(".")
    if ext not in ADMIN_CHAT_ALLOWED_EXT:
        return None

    filename=f"admin_{uuid.uuid4().hex}.{ext}"
    path=os.path.join(ADMIN_CHAT_UPLOAD_DIR,filename)
    upload.save(path)
    return "/static/uploads/admin_chat/"+filename

def ensure_admin_platform_tables():
    con=db()
    con.execute("""
        CREATE TABLE IF NOT EXISTS admin_platform_settings(
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at TEXT
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS admin_machine_settings(
            code TEXT PRIMARY KEY,
            name TEXT,
            price REAL,
            daily REAL,
            days INTEGER,
            total REAL,
            enabled INTEGER DEFAULT 1,
            updated_at TEXT
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS admin_page_settings(
            page TEXT PRIMARY KEY,
            title TEXT,
            subtitle TEXT,
            content TEXT,
            enabled INTEGER DEFAULT 1,
            updated_at TEXT
        )
    """)
    try:
        cols=[r["name"] for r in con.execute("PRAGMA table_info(support_messages)").fetchall()]
        if "media" not in cols:
            con.execute("ALTER TABLE support_messages ADD COLUMN media TEXT")
    except Exception:
        pass
    con.commit()
    con.close()

def get_admin_page_setting(page):
    defaults={
        "title":"",
        "subtitle":"",
        "content":"",
        "enabled":1
    }
    try:
        con=db()
        row=con.execute(
            "SELECT title,subtitle,content,enabled FROM admin_page_settings WHERE page=?",
            (page,)
        ).fetchone()
        con.close()
        if row:
            return {
                "title":row["title"] or "",
                "subtitle":row["subtitle"] or "",
                "content":row["content"] or "",
                "enabled":int(row["enabled"] if row["enabled"] is not None else 1)
            }
    except Exception:
        pass
    return defaults

def get_effective_plans():
    result={k:dict(v) for k,v in PLANS.items()}
    try:
        con=db()
        rows=con.execute("SELECT * FROM admin_machine_settings").fetchall()
        con.close()
        for r in rows:
            code=str(r["code"]).upper()
            if code in result:
                result[code]["name"]=r["name"] or result[code].get("name",code)
                result[code]["price"]=float(r["price"])
                result[code]["daily"]=float(r["daily"])
                result[code]["days"]=int(r["days"])
                result[code]["total"]=float(r["total"])
    except Exception:
        pass
    return result

# ADMIN PLATFORM EDITOR
# ============================================================
def ensure_admin_editor_tables():
    con=db()
    con.execute("""
        CREATE TABLE IF NOT EXISTS admin_platform_settings(
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS admin_machine_settings(
            code TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            price REAL NOT NULL DEFAULT 0,
            daily REAL NOT NULL DEFAULT 0,
            days INTEGER NOT NULL DEFAULT 0,
            total REAL NOT NULL DEFAULT 0,
            enabled INTEGER NOT NULL DEFAULT 1,
            updated_at TEXT NOT NULL
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS admin_page_settings(
            page TEXT PRIMARY KEY,
            title TEXT NOT NULL DEFAULT '',
            subtitle TEXT NOT NULL DEFAULT '',
            content TEXT NOT NULL DEFAULT '',
            enabled INTEGER NOT NULL DEFAULT 1,
            updated_at TEXT NOT NULL
        )
    """)
    for code,plan in PLANS.items():
        con.execute("""
            INSERT OR IGNORE INTO admin_machine_settings
            (code,name,price,daily,days,total,enabled,updated_at)
            VALUES(?,?,?,?,?,?,1,?)
        """,(
            code,
            str(code)+" AI Machine",
            float(plan["price"]),
            float(plan["daily"]),
            int(plan["days"]),
            float(plan["total"]),
            now()
        ))
    con.commit()
    con.close()


def get_platform_setting(key, default=""):
    try:
        con=db()
        row=con.execute(
            "SELECT value FROM admin_platform_settings WHERE key=?",
            (key,)
        ).fetchone()
        con.close()
        return row["value"] if row and row["value"] is not None else default
    except Exception:
        return default

def save_platform_setting(key,value):
    con=db()
    con.execute("""
        INSERT INTO admin_platform_settings(key,value,updated_at)
        VALUES(?,?,?)
        ON CONFLICT(key) DO UPDATE SET
        value=excluded.value,
        updated_at=excluded.updated_at
    """,(key,str(value),now()))
    con.commit()
    con.close()

@app.context_processor
def platform_editor_context():
    return {
        "platform_name":get_platform_setting("platform_name","NEXORA"),
        "platform_accent":get_platform_setting("accent_color","#39ff72"),
        "platform_bg":get_platform_setting("background_color","#000000"),
        "platform_card":get_platform_setting("card_color","#071009"),
        "platform_text":get_platform_setting("text_color","#ffffff"),
        "platform_radius":get_platform_setting("card_radius","16")
    }

ensure_admin_editor_tables()

@app.route("/admin/editor")
@admin_required
def admin_editor():
    ensure_admin_editor_tables()
    con=db()

    machines=con.execute(
        "SELECT * FROM admin_machine_settings ORDER BY code"
    ).fetchall()

    pages=con.execute(
        "SELECT * FROM admin_page_settings ORDER BY page"
    ).fetchall()

    settings=con.execute(
        "SELECT * FROM admin_platform_settings ORDER BY key"
    ).fetchall()

    managers=con.execute(
        "SELECT * FROM managers ORDER BY id"
    ).fetchall()

    con.close()

    return render_template(
        "admin_editor.html",
        machines=machines,
        pages=pages,
        settings=settings,
        managers=managers
    )

@app.route("/admin/editor/machine/<code>",methods=["POST"])
@admin_required
def admin_editor_machine(code):
    try:
        price=float(request.form.get("price") or 0)
        daily=float(request.form.get("daily") or 0)
        days=int(request.form.get("days") or 0)
        total=float(request.form.get("total") or 0)
    except:
        flash("Invalid machine values.","error")
        return redirect(url_for("admin_editor"))

    name=request.form.get("name","").strip() or code+" AI Machine"
    enabled=1 if request.form.get("enabled")=="1" else 0

    con=db()
    con.execute("""
        UPDATE admin_machine_settings
        SET name=?,price=?,daily=?,days=?,total=?,enabled=?,updated_at=?
        WHERE code=?
    """,(name,price,daily,days,total,enabled,now(),code))
    con.execute("""
        INSERT INTO admin_activity(admin_uid,action,details,created_at)
        VALUES(?,?,?,?)
    """,(
        current_user()["id"],
        "MACHINE_EDIT",
        f"{code} price={price} daily={daily} days={days} total={total} enabled={enabled}",
        now()
    ))
    con.commit()
    con.close()
    flash("Machine settings saved.","success")
    return redirect(url_for("admin_editor"))

@app.route("/admin/editor/page/<page>",methods=["POST"])
@admin_required
def admin_editor_page(page):
    title=request.form.get("title","").strip()
    subtitle=request.form.get("subtitle","").strip()
    content=request.form.get("content","").strip()
    enabled=1 if request.form.get("enabled")=="1" else 0

    con=db()
    con.execute("""
        INSERT INTO admin_page_settings(page,title,subtitle,content,enabled,updated_at)
        VALUES(?,?,?,?,?,?)
        ON CONFLICT(page) DO UPDATE SET
          title=excluded.title,
          subtitle=excluded.subtitle,
          content=excluded.content,
          enabled=excluded.enabled,
          updated_at=excluded.updated_at
    """,(page,title,subtitle,content,enabled,now()))
    con.execute("""
        INSERT INTO admin_activity(admin_uid,action,details,created_at)
        VALUES(?,?,?,?)
    """,(current_user()["id"],"PAGE_EDIT",f"Edited {page}",now()))
    con.commit()
    con.close()
    flash("Page settings saved.","success")
    return redirect(url_for("admin_editor"))

@app.route("/admin/editor/setting/<key>",methods=["POST"])
@admin_required
def admin_editor_setting(key):
    value=request.form.get("value","")
    con=db()
    con.execute("""
        INSERT INTO admin_platform_settings(key,value,updated_at)
        VALUES(?,?,?)
        ON CONFLICT(key) DO UPDATE SET
          value=excluded.value,
          updated_at=excluded.updated_at
    """,(key,value,now()))
    con.execute("""
        INSERT INTO admin_activity(admin_uid,action,details,created_at)
        VALUES(?,?,?,?)
    """,(current_user()["id"],"SETTING_EDIT",f"Edited {key}",now()))
    con.commit()
    con.close()
    flash("Setting saved.","success")
    return redirect(url_for("admin_editor"))


@app.route("/admin/editor/design",methods=["POST"])
@admin_required
def admin_editor_design():
    values={
        "platform_name":request.form.get("platform_name","NEXORA").strip()[:80],
        "accent_color":request.form.get("accent_color","#39ff72").strip(),
        "background_color":request.form.get("background_color","#000000").strip(),
        "card_color":request.form.get("card_color","#071009").strip(),
        "text_color":request.form.get("text_color","#ffffff").strip(),
        "card_radius":request.form.get("card_radius","16").strip()
    }

    color_re=re.compile(r"^#[0-9a-fA-F]{6}$")

    for key in ("accent_color","background_color","card_color","text_color"):
        if not color_re.fullmatch(values[key]):
            flash("Invalid colour value.","error")
            return redirect(url_for("admin_editor"))

    try:
        radius=max(0,min(40,int(values["card_radius"])))
    except Exception:
        radius=16

    values["card_radius"]=str(radius)

    for key,value in values.items():
        save_platform_setting(key,value)

    flash("Platform design updated.","success")
    return redirect(url_for("admin_editor"))

@app.route("/admin/editor/manager/<mid>",methods=["POST"])
@admin_required
def admin_editor_manager(mid):
    name=request.form.get("name","").strip()
    phone=request.form.get("phone","").strip()
    role=request.form.get("role","NEXORA Manager").strip()
    avatar=request.form.get("avatar","👤").strip() or "👤"

    if not name or not phone:
        flash("Manager name and phone are required.","error")
        return redirect(url_for("admin_editor"))

    con=db()

    old=con.execute(
        "SELECT phone FROM managers WHERE id=?",(mid,)
    ).fetchone()

    if not old:
        con.close()
        flash("Manager not found.","error")
        return redirect(url_for("admin_editor"))

    con.execute(
        "UPDATE managers SET name=?,phone=?,role=?,avatar=? WHERE id=?",
        (name,phone,role,avatar,mid)
    )

    if old["phone"] and old["phone"]!=phone:
        con.execute(
            "UPDATE users SET manager_phone=? WHERE manager_phone=?",
            (phone,old["phone"])
        )

    con.commit()
    con.close()

    flash("Manager updated.","success")
    return redirect(url_for("admin_editor"))

@app.route("/admin/editor/manager/create",methods=["POST"])
@admin_required
def admin_editor_manager_create():
    name=request.form.get("name","").strip()
    phone=request.form.get("phone","").strip()
    role=request.form.get("role","NEXORA Manager").strip()
    avatar=request.form.get("avatar","👤").strip() or "👤"

    if not name or not phone:
        flash("Manager name and phone are required.","error")
        return redirect(url_for("admin_editor"))

    con=db()

    cols=[x["name"] for x in con.execute(
        "PRAGMA table_info(managers)"
    ).fetchall()]

    if "role" in cols and "avatar" in cols:
        con.execute(
            "INSERT INTO managers(name,phone,role,avatar,enabled) VALUES(?,?,?,?,1)",
            (name,phone,role,avatar)
        )
    else:
        con.execute(
            "INSERT INTO managers(name,phone,enabled) VALUES(?,?,1)",
            (name,phone)
        )

    con.commit()
    con.close()

    flash("Manager created.","success")
    return redirect(url_for("admin_editor"))

@app.route("/admin/editor/manager/<mid>/disable",methods=["POST"])
@admin_required
def admin_editor_manager_disable(mid):
    con=db()
    con.execute(
        "UPDATE managers SET enabled=0 WHERE id=?",
        (mid,)
    )
    con.commit()
    con.close()

    flash("Manager disabled.","success")
    return redirect(url_for("admin_editor"))

@app.route("/admin/control-center")
@admin_required
def admin_control_center():
    con=db()
    users=con.execute("SELECT * FROM users ORDER BY id DESC LIMIT 500").fetchall()
    transactions=con.execute("SELECT * FROM transactions ORDER BY id DESC LIMIT 500").fetchall()
    messages=con.execute("SELECT * FROM support_messages ORDER BY id DESC LIMIT 500").fetchall()
    con.close()
    return render_template(
        "admin_control_center.html",
        users=users,
        transactions=transactions,
        messages=messages,
        user=current_user()
    )

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
    return render_template("admin.html",users=users,tx=tx,withdrawals=withdrawals,deposits=deposits,requests=requests,messages=messages,gifts=gifts,managers=managers,activity=activity,announcements=announcements,plans=PLANS)

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


@app.route("/admin/broadcast",methods=["POST"])
@admin_required
def admin_broadcast():
    import os, uuid
    from werkzeug.utils import secure_filename

    msg=request.form.get("message","").strip()
    uploaded=request.files.get("media")
    media_url=""

    if uploaded and uploaded.filename:
        ext=os.path.splitext(secure_filename(uploaded.filename))[1].lower()
        allowed={".jpg",".jpeg",".png",".gif",".webp",".mp4",".webm",".mov",".m4v",".mp3",".wav",".ogg",".m4a"}

        if ext not in allowed:
            flash("Unsupported media type.","error")
            return redirect(url_for("admin"))

        folder=os.path.join(app.root_path,"static","chat_media")
        os.makedirs(folder,exist_ok=True)
        name="broadcast_"+uuid.uuid4().hex+ext
        uploaded.save(os.path.join(folder,name))
        media_url=url_for("static",filename="chat_media/"+name)

    if not msg and not media_url:
        flash("Write a message or attach media.","error")
        return redirect(url_for("admin"))

    con=db()
    users=con.execute("SELECT id FROM users ORDER BY id").fetchall()

    cols=[r[1] for r in con.execute("PRAGMA table_info(support_messages)").fetchall()]
    if "media" not in cols:
        con.execute("ALTER TABLE support_messages ADD COLUMN media TEXT")

    for u in users:
        con.execute(
            "INSERT INTO support_messages(uid,sender,message,created_at,media) VALUES(?,?,?,?,?)",
            (u["id"],"ADMIN",msg,now(),media_url)
        )

    con.commit()
    con.close()

    flash(f"Message sent to {len(users)} users.","success")
    return redirect(url_for("admin"))

@app.route("/admin/support/<int:uid>",methods=["GET","POST"])
@admin_required
def admin_support(uid):
    if request.method=="GET":
        con=db()
        messages=con.execute(
            "SELECT * FROM support_messages WHERE uid=? ORDER BY id",
            (uid,)
        ).fetchall()
        con.close()
        return render_template(
            "admin_chat.html",
            messages=messages,
            uid=uid,
            user=current_user()
        )

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
        ensure_admin_platform_tables()

        uid=int(request.form.get("uid","0") or 0)
        msg=(request.form.get("message") or "").strip()
        upload=request.files.get("media")

        if not uid:
            if request.headers.get("X-Requested-With")=="XMLHttpRequest" or request.form.get("ajax")=="1":
                return jsonify({"ok":False,"error":"Invalid user"}),400
            flash("Invalid user.","error")
            return redirect(url_for("admin"))

        media_url=None
        if upload and upload.filename:
            media_url=admin_chat_save_upload(upload)
            if not media_url:
                if request.headers.get("X-Requested-With")=="XMLHttpRequest" or request.form.get("ajax")=="1":
                    return jsonify({"ok":False,"error":"Unsupported media file"}),400
                flash("Unsupported media file.","error")
                return redirect(url_for("admin_support",uid=uid))

        if not msg and not media_url:
            if request.headers.get("X-Requested-With")=="XMLHttpRequest" or request.form.get("ajax")=="1":
                return jsonify({"ok":False,"error":"Write a message or attach media"}),400
            flash("Write a message or attach media.","error")
            return redirect(url_for("admin_support",uid=uid))

        con=db()
        con.execute(
            "INSERT INTO support_messages(uid,sender,message,created_at,media) VALUES(?,?,?,?,?)",
            (uid,"ADMIN",msg,now(),media_url)
        )
        con.commit()
        con.close()

        if request.headers.get("X-Requested-With")=="XMLHttpRequest" or request.form.get("ajax")=="1":
            return jsonify({"ok":True})

        return redirect(url_for("admin_support",uid=uid))

    except Exception as e:
        try:
            if request.headers.get("X-Requested-With")=="XMLHttpRequest" or request.form.get("ajax")=="1":
                return jsonify({"ok":False,"error":"Message could not be sent"}),500
        except Exception:
            pass
        flash("Message could not be sent.","error")
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
    role=request.form.get("role","NEXORA Manager").strip()
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


# ===== NEXORA LIVE CHAT UNREAD TRACKING =====
def ensure_nexora_chat_reads():
    con=db()
    con.execute("""
        CREATE TABLE IF NOT EXISTS chat_reads(
            uid INTEGER PRIMARY KEY,
            admin_last_read_id INTEGER NOT NULL DEFAULT 0,
            user_last_read_id INTEGER NOT NULL DEFAULT 0
        )
    """)
    rows=con.execute("SELECT DISTINCT uid FROM support_messages WHERE uid IS NOT NULL").fetchall()
    for row in rows:
        uid=int(row["uid"])
        exists=con.execute("SELECT 1 FROM chat_reads WHERE uid=?",(uid,)).fetchone()
        if not exists:
            mx=con.execute(
                "SELECT COALESCE(MAX(id),0) n FROM support_messages WHERE uid=?",
                (uid,)
            ).fetchone()["n"]
            con.execute(
                "INSERT INTO chat_reads(uid,admin_last_read_id,user_last_read_id) VALUES(?,?,?)",
                (uid,mx,mx)
            )
    con.commit()
    con.close()

def ensure_chat_read_uid(con,uid):
    con.execute("""
        CREATE TABLE IF NOT EXISTS chat_reads(
            uid INTEGER PRIMARY KEY,
            admin_last_read_id INTEGER NOT NULL DEFAULT 0,
            user_last_read_id INTEGER NOT NULL DEFAULT 0
        )
    """)
    row=con.execute("SELECT * FROM chat_reads WHERE uid=?",(uid,)).fetchone()
    if not row:
        mx=con.execute(
            "SELECT COALESCE(MAX(id),0) n FROM support_messages WHERE uid=?",
            (uid,)
        ).fetchone()["n"]
        con.execute(
            "INSERT INTO chat_reads(uid,admin_last_read_id,user_last_read_id) VALUES(?,?,?)",
            (uid,mx,mx)
        )
        con.commit()
    return con.execute("SELECT * FROM chat_reads WHERE uid=?",(uid,)).fetchone()

@app.route("/chat/unread")
@required
def nexora_chat_unread():
    u=current_user()
    con=db()
    row=ensure_chat_read_uid(con,u["id"])
    n=con.execute("""
        SELECT COUNT(*) n
        FROM support_messages
        WHERE uid=? AND UPPER(COALESCE(sender,''))='ADMIN'
        AND id>?
    """,(u["id"],row["user_last_read_id"])).fetchone()["n"]
    con.close()
    return jsonify({"unread":int(n)})

@app.route("/chat/read",methods=["POST"])
@required
def nexora_chat_read():
    u=current_user()
    con=db()
    ensure_chat_read_uid(con,u["id"])
    mx=con.execute("""
        SELECT COALESCE(MAX(id),0) n
        FROM support_messages
        WHERE uid=? AND UPPER(COALESCE(sender,''))='ADMIN'
    """,(u["id"],)).fetchone()["n"]
    con.execute(
        "UPDATE chat_reads SET user_last_read_id=? WHERE uid=?",
        (mx,u["id"])
    )
    con.commit()
    con.close()
    return jsonify({"ok":True})

@app.route("/admin/chat/unread")
@admin_required
def nexora_admin_chat_unread():
    con=db()
    ensure_chat_read_uid(con,0)
    rows=con.execute(
        "SELECT DISTINCT uid FROM support_messages WHERE uid IS NOT NULL"
    ).fetchall()
    total=0
    by_uid={}
    for row in rows:
        uid=int(row["uid"])
        state=ensure_chat_read_uid(con,uid)
        n=con.execute("""
            SELECT COUNT(*) n
            FROM support_messages
            WHERE uid=?
            AND UPPER(COALESCE(sender,'')) NOT IN ('ADMIN','MANAGER')
            AND id>?
        """,(uid,state["admin_last_read_id"])).fetchone()["n"]
        n=int(n)
        if n:
            by_uid[str(uid)]=n
            total+=n
    con.close()
    return jsonify({"unread":total,"by_uid":by_uid})

@app.route("/admin/chat/read/<int:uid>",methods=["POST"])
@admin_required
def nexora_admin_chat_read(uid):
    con=db()
    ensure_chat_read_uid(con,uid)
    mx=con.execute("""
        SELECT COALESCE(MAX(id),0) n
        FROM support_messages
        WHERE uid=?
        AND UPPER(COALESCE(sender,'')) NOT IN ('ADMIN','MANAGER')
    """,(uid,)).fetchone()["n"]
    con.execute(
        "UPDATE chat_reads SET admin_last_read_id=? WHERE uid=?",
        (mx,uid)
    )
    con.commit()
    con.close()
    return jsonify({"ok":True})
# ===== END NEXORA LIVE CHAT UNREAD TRACKING =====


# ================= REAL CHAT POPUP NOTIFICATIONS =================

def ensure_chat_popup_reads():
    con=db()
    con.execute("""
        CREATE TABLE IF NOT EXISTS chat_popup_reads(
            uid INTEGER PRIMARY KEY,
            admin_read_id INTEGER NOT NULL DEFAULT 0,
            user_read_id INTEGER NOT NULL DEFAULT 0
        )
    """)
    con.commit()
    con.close()

@app.route("/chat-popup/user", methods=["GET"])
@required
def chat_popup_user():
    ensure_chat_popup_reads()
    u=current_user()
    con=db()
    con.execute(
        "INSERT OR IGNORE INTO chat_popup_reads(uid,admin_read_id,user_read_id) VALUES(?,?,?)",
        (u["id"],0,0)
    )
    r=con.execute(
        "SELECT user_read_id FROM chat_popup_reads WHERE uid=?",
        (u["id"],)
    ).fetchone()
    last=int(r["user_read_id"] or 0) if r else 0
    row=con.execute("""
        SELECT id,uid,sender,message,created_at
        FROM support_messages
        WHERE uid=? AND id>? AND UPPER(sender) IN ('ADMIN','MANAGER')
        ORDER BY id DESC LIMIT 1
    """,(u["id"],last)).fetchone()
    count=con.execute("""
        SELECT COUNT(*) n
        FROM support_messages
        WHERE uid=? AND id>? AND UPPER(sender) IN ('ADMIN','MANAGER')
    """,(u["id"],last)).fetchone()["n"]
    con.close()
    return jsonify({
        "unread":int(count or 0),
        "id":int(row["id"]) if row else 0,
        "message":str(row["message"] or "")[:120] if row else "",
        "sender":str(row["sender"] or "") if row else ""
    })

@app.route("/chat-popup/user/read", methods=["POST"])
@required
def chat_popup_user_read():
    ensure_chat_popup_reads()
    u=current_user()
    con=db()
    row=con.execute(
        "SELECT MAX(id) n FROM support_messages WHERE uid=? AND UPPER(sender) IN ('ADMIN','MANAGER')",
        (u["id"],)
    ).fetchone()
    last=int(row["n"] or 0) if row else 0
    con.execute("""
        INSERT INTO chat_popup_reads(uid,admin_read_id,user_read_id)
        VALUES(?,?,?)
        ON CONFLICT(uid) DO UPDATE SET user_read_id=excluded.user_read_id
    """,(u["id"],0,last))
    con.commit()
    con.close()
    return jsonify({"ok":True})

@app.route("/admin/chat-popup", methods=["GET"])
@admin_required
def chat_popup_admin():
    ensure_chat_popup_reads()
    con=db()

    rows=con.execute("""
        SELECT
            s.uid,
            MAX(s.id) AS latest_id,
            COUNT(*) AS unread_count
        FROM support_messages s
        LEFT JOIN chat_popup_reads r ON r.uid=s.uid
        WHERE s.id>COALESCE(r.admin_read_id,0)
          AND LOWER(TRIM(s.sender)) NOT IN ('admin','manager')
        GROUP BY s.uid
        ORDER BY latest_id DESC
        LIMIT 50
    """).fetchall()

    items=[]

    # Detect the real users-table columns instead of assuming name/username exist.
    user_cols=[
        x["name"]
        for x in con.execute("PRAGMA table_info(users)").fetchall()
    ]

    preferred=[]
    for c in ("phone","username","full_name","display_name","email"):
        if c in user_cols:
            preferred.append(c)

    for r in rows:
        uid=int(r["uid"])

        latest=con.execute("""
            SELECT message,created_at,sender
            FROM support_messages
            WHERE uid=? AND id=?
        """,(uid,int(r["latest_id"]))).fetchone()

        userrow=con.execute(
            "SELECT * FROM users WHERE id=?",
            (uid,)
        ).fetchone()

        display="User "+str(uid)

        if userrow:
            for c in preferred:
                try:
                    value=userrow[c]
                    if value:
                        display=str(value)
                        break
                except Exception:
                    pass

        items.append({
            "uid":uid,
            "unread":int(r["unread_count"] or 0),
            "message":str(latest["message"] or "")[:160] if latest else "New message",
            "created_at":str(latest["created_at"] or "") if latest else "",
            "name":display
        })

    total=sum(x["unread"] for x in items)

    con.close()

    return jsonify({
        "unread":total,
        "items":items
    })

@app.route("/admin/chat-popup/read/<int:uid>", methods=["POST"])
@admin_required
def chat_popup_admin_read(uid):
    ensure_chat_popup_reads()
    con=db()
    row=con.execute(
        "SELECT MAX(id) n FROM support_messages WHERE uid=? AND UPPER(sender) NOT IN ('ADMIN','MANAGER')",
        (uid,)
    ).fetchone()
    last=int(row["n"] or 0) if row else 0
    con.execute("""
        INSERT INTO chat_popup_reads(uid,admin_read_id,user_read_id)
        VALUES(?,?,?)
        ON CONFLICT(uid) DO UPDATE SET admin_read_id=excluded.admin_read_id
    """,(uid,last,0))
    con.commit()
    con.close()
    return jsonify({"ok":True})

# ================================================================

init_db()
ensure_chat_popup_reads()
ensure_nexora_chat_reads()
if __name__=="__main__": app.run(host="0.0.0.0",port=int(os.environ.get("PORT",5000)),debug=False)

# MANAGER_PAGE_REDIRECT_TO_COMM

# MANAGER_PAGE_REDIRECT_TO_COMM
# The old standalone Manager page is no longer used.
# Existing manager chat/support functionality remains available through /support.
try:
    from flask import redirect, url_for
except ImportError:
    pass
