import hashlib
import sqlite3
from datetime import date, datetime, timedelta, time
from pathlib import Path

import pandas as pd
import streamlit as st

APP_DIR = Path(__file__).parent
DB_PATH = APP_DIR / "data" / "medremind.db"
DB_PATH.parent.mkdir(exist_ok=True)

st.set_page_config(page_title="MedRemind — Medicine Reminder", page_icon="💚", layout="wide", initial_sidebar_state="expanded")

# ---------- Database ----------
def db():
    con = sqlite3.connect(DB_PATH, check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con


def init_db():
    con = db()
    con.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        caregiver_name TEXT,
        caregiver_email TEXT,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS medicines (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        dose TEXT NOT NULL,
        dose_time TEXT NOT NULL,
        period TEXT NOT NULL,
        stock INTEGER NOT NULL DEFAULT 0,
        active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id)
    );
    CREATE TABLE IF NOT EXISTS dose_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        medicine_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        dose_date TEXT NOT NULL,
        dose_time TEXT NOT NULL,
        status TEXT NOT NULL,
        recorded_at TEXT NOT NULL,
        UNIQUE(medicine_id, dose_date),
        FOREIGN KEY(medicine_id) REFERENCES medicines(id),
        FOREIGN KEY(user_id) REFERENCES users(id)
    );
    """)
    con.commit()
    con.close()


def pw_hash(password):
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def seed_user():
    con = db()
    row = con.execute("SELECT id FROM users WHERE email=?", ("demo@medremind.app",)).fetchone()
    if row:
        con.close(); return row["id"]
    cur = con.execute("INSERT INTO users(name, caregiver_name, caregiver_email, email, password_hash, created_at) VALUES (?,?,?,?,?,?)",
                      ("Naman", "Family Member", "family@example.com", "demo@medremind.app", pw_hash("medremind123"), datetime.now().isoformat()))
    uid = cur.lastrowid
    starter = [
        (uid, "Metformin", "500 mg · 1 tablet", "08:00", "Morning", 18),
        (uid, "Amlodipine", "5 mg · 1 tablet", "13:00", "Afternoon", 7),
        (uid, "Atorvastatin", "10 mg · 1 tablet", "20:00", "Night", 4),
    ]
    for m in starter:
        con.execute("INSERT INTO medicines(user_id,name,dose,dose_time,period,stock,created_at) VALUES (?,?,?,?,?,?,?)", (*m, datetime.now().isoformat()))
    con.commit(); con.close(); return uid


init_db()
DEMO_USER_ID = seed_user()

# ---------- State ----------
def current_user():
    return st.session_state.get("user")


def load_user(email, password):
    con = db(); row = con.execute("SELECT * FROM users WHERE lower(email)=lower(?) AND password_hash=?", (email.strip(), pw_hash(password))).fetchone(); con.close()
    return dict(row) if row else None


def load_medicines(uid):
    con = db()
    rows = con.execute("SELECT * FROM medicines WHERE user_id=? AND active=1 ORDER BY dose_time", (uid,)).fetchall()
    con.close()
    meds = []
    today = date.today().isoformat()
    con = db()
    for r in rows:
        h = con.execute("SELECT status FROM dose_history WHERE medicine_id=? AND dose_date=?", (r["id"], today)).fetchone()
        meds.append({"id": r["id"], "name": r["name"], "dose": r["dose"], "time": r["dose_time"], "period": r["period"], "stock": r["stock"], "status": h["status"] if h else "pending"})
    con.close()
    return meds


def record_status(uid, med, status):
    today = date.today().isoformat()
    con = db()
    old = con.execute("SELECT status FROM dose_history WHERE medicine_id=? AND dose_date=?", (med["id"], today)).fetchone()
    if status == "taken" and (not old or old["status"] != "taken"):
        con.execute("UPDATE medicines SET stock=MAX(0,stock-1) WHERE id=? AND user_id=?", (med["id"], uid))
    con.execute("INSERT INTO dose_history(medicine_id,user_id,dose_date,dose_time,status,recorded_at) VALUES (?,?,?,?,?,?) ON CONFLICT(medicine_id,dose_date) DO UPDATE SET status=excluded.status, dose_time=excluded.dose_time, recorded_at=excluded.recorded_at",
                (med["id"], uid, today, med["time"], status, datetime.now().isoformat()))
    con.commit(); con.close()


def add_medicine(uid, name, dose, dose_time, period, stock):
    con = db(); con.execute("INSERT INTO medicines(user_id,name,dose,dose_time,period,stock,created_at) VALUES (?,?,?,?,?,?,?)", (uid,name,dose,dose_time,period,stock,datetime.now().isoformat())); con.commit(); con.close()


def delete_medicine(uid, mid):
    con = db(); con.execute("UPDATE medicines SET active=0 WHERE id=? AND user_id=?", (mid, uid)); con.commit(); con.close()


def monthly_stats(uid, year, month):
    con = db()
    start = date(year, month, 1)
    end = date(year + (month == 12), 1 if month == 12 else month + 1, 1)
    rows = con.execute("SELECT dose_date,status FROM dose_history WHERE user_id=? AND dose_date>=? AND dose_date<?", (uid,start.isoformat(),end.isoformat())).fetchall()
    con.close()
    df = pd.DataFrame(rows, columns=["dose_date","status"]) if rows else pd.DataFrame(columns=["dose_date","status"])
    if df.empty:
        return 0, 0, 0, df
    taken = int((df.status == "taken").sum()); missed = int((df.status == "skipped").sum())
    adherence = round(taken / len(df) * 100)
    dates = sorted(set(pd.to_datetime(df.dose_date).dt.date))
    best = cur = 0; prev = None
    for d in dates:
        if prev and d == prev + timedelta(days=1): cur += 1
        else: cur = 1
        best = max(best, cur); prev = d
    return adherence, missed, best, df


# ---------- CSS ----------
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Nunito+Sans:wght@400;600;700;800;900&display=swap');
html, body, [class*="css"] { font-family: 'Nunito Sans', sans-serif; }
.stApp { background:#f5fbfa; }
section[data-testid="stSidebar"] { background:#24484b; }
section[data-testid="stSidebar"] * { color:#eef9f7 !important; }
.brand { display:flex; gap:12px; align-items:center; padding:8px 0 22px; }
.brand-icon { width:46px; height:46px; border-radius:50%; background:#75d6bd; display:grid; place-items:center; color:#18383b; font-size:24px; }
.brand-title { font-size:22px; font-weight:900; line-height:1.1; }
.brand-sub { font-size:12px; opacity:.65; }
.hero { background:#24484b; color:#effbf8; border-radius:18px; padding:34px; position:relative; overflow:hidden; }
.hero:after { content:''; position:absolute; width:220px; height:220px; border-radius:50%; right:-70px; top:-80px; background:#2d5a5d; }
.eyebrow { color:#62cbb0; font-size:13px; font-weight:900; text-transform:uppercase; letter-spacing:.06em; }
.hero h2 { font-size:40px; margin:6px 0; font-weight:900; }
.card { background:white; border:1px solid #dce9e7; border-radius:15px; padding:20px; }
.stat { background:white; border:1px solid #dce9e7; border-radius:15px; padding:20px; }
.stat-value { font-size:29px; font-weight:900; color:#24484b; }
.stat-label { font-size:13px; color:#627778; font-weight:700; }
.med-name { font-size:20px; font-weight:900; }
.muted { color:#687a7b; }
.refill { color:#a56a00; background:#fff4d7; border-radius:999px; padding:4px 9px; font-size:12px; font-weight:800; }
.ok { color:#176e55; background:#def6ed; border-radius:999px; padding:4px 9px; font-size:12px; font-weight:800; }
.danger { color:#a83838; background:#ffe6e6; border-radius:999px; padding:4px 9px; font-size:12px; font-weight:800; }
.small-note { color:#718384; font-size:13px; }
div[data-testid="stMetricValue"] { font-weight:900; }
button[kind="primary"] { background:#70d1b8; color:#18383b; border:0; font-weight:900; }
</style>
""", unsafe_allow_html=True)

# ---------- Auth ----------
if "user" not in st.session_state:
    st.session_state.user = None
if "page" not in st.session_state:
    st.session_state.page = "Today"

if not current_user():
    st.markdown('<div style="max-width:760px;margin:10vh auto;text-align:center"><div style="font-size:52px">💚</div><h1 style="font-size:46px;font-weight:900;color:#24484b">MedRemind</h1><p style="font-size:19px;color:#627778">Care made simple — medicine reminders, adherence tracking and family summaries.</p></div>', unsafe_allow_html=True)
    left, center, right = st.columns([1,1.2,1])
    with center:
        with st.form("login"):
            st.subheader("Welcome back")
            email = st.text_input("Email", value="demo@medremind.app")
            password = st.text_input("Password", type="password", value="medremind123")
            if st.form_submit_button("Sign in", use_container_width=True, type="primary"):
                user = load_user(email, password)
                if user:
                    st.session_state.user = user; st.rerun()
                else: st.error("Invalid email or password.")
        st.caption("Demo account: demo@medremind.app / medremind123")
    st.stop()

uid = current_user()["id"]
medicines = load_medicines(uid)

# ---------- Sidebar ----------
with st.sidebar:
    st.markdown('<div class="brand"><div class="brand-icon">♥</div><div><div class="brand-title">MedRemind</div><div class="brand-sub">Care made simple</div></div></div>', unsafe_allow_html=True)
    st.markdown("### Navigation")
    for label, icon in [("Today","⌂"),("Medicines","💊"),("Calendar","▣"),("Family","👥")]:
        if st.button(f"{icon}  {label}", key=f"nav_{label}", use_container_width=True):
            st.session_state.page = label; st.rerun()
    st.divider()
    st.markdown("**Need help?**")
    st.caption("Ask a family member to review your schedule.")
    st.divider()
    st.caption(f"Signed in as **{current_user()['name']}**")
    if st.button("↪ Sign out", use_container_width=True):
        st.session_state.user = None; st.rerun()

# ---------- Header ----------
now = datetime.now()
header_l, header_r = st.columns([5,1])
with header_l:
    st.markdown(f'<div class="eyebrow">{now.strftime("%A · %d %B").upper()}</div>', unsafe_allow_html=True)
    st.markdown(f"# Good morning, {current_user()['name']} ☀️")
with header_r:
    st.write("")
    if st.button("🔔", help="Notifications"):
        low = [m for m in medicines if m["stock"] <= 5]
        if low: st.info("Refill soon: " + ", ".join(m["name"] for m in low))
        else: st.success("No refill alerts today.")

# ---------- Today ----------
def dose_row(m):
    c1,c2,c3,c4 = st.columns([3.1,1.4,1.5,2.3])
    with c1:
        st.markdown(f'<div class="med-name">💊 {m["name"]}</div><div class="muted">{m["dose"]}</div>', unsafe_allow_html=True)
    with c2: st.markdown(f'**{m["time"]}**<br><span class="muted">{m["period"]}</span>', unsafe_allow_html=True)
    with c3:
        if m["stock"] <= 5: st.markdown(f'<span class="refill">⚠ Refill soon · {m["stock"]}</span>', unsafe_allow_html=True)
        else: st.markdown(f'<span class="ok">{m["stock"]} tablets</span>', unsafe_allow_html=True)
    with c4:
        if m["status"] == "taken":
            st.success("✓ Taken", icon="💚")
        else:
            a,b,c = st.columns(3)
            with a:
                if st.button("✓ Take", key=f"take_{m['id']}"):
                    record_status(uid,m,"taken"); st.rerun()
            with b:
                if st.button("◷ Snooze", key=f"snooze_{m['id']}"):
                    record_status(uid,m,"snoozed"); st.rerun()
            with c:
                if st.button("→ Skip", key=f"skip_{m['id']}"):
                    record_status(uid,m,"skipped"); st.rerun()

if st.session_state.page == "Today":
    taken = sum(m["status"] == "taken" for m in medicines)
    adherence = round(taken/len(medicines)*100) if medicines else 0
    next_med = next((m for m in medicines if m["status"] in ("pending","snoozed")), None)
    if next_med:
        st.markdown(f'<div class="hero"><div class="eyebrow">Next medicine</div><h2>{next_med["name"]}</h2><div style="font-size:18px;opacity:.75">{next_med["dose"]} · {next_med["period"]}</div><div style="margin-top:20px;font-size:27px;font-weight:900">◷ {next_med["time"]}</div></div>', unsafe_allow_html=True)
        st.write("")
        if st.button("✓  Mark as taken", type="primary"):
            record_status(uid,next_med,"taken"); st.rerun()
    else:
        st.markdown('<div class="hero"><div class="eyebrow">Next medicine</div><h2>All done for today!</h2><div style="opacity:.75;font-size:18px">You have completed your medicine schedule.</div></div>', unsafe_allow_html=True)
    st.write("")
    h1,h2 = st.columns([4,1])
    with h1:
        st.markdown('<div class="eyebrow">Today’s schedule</div><h2 style="margin-top:0;font-weight:900">Your medicines</h2>', unsafe_allow_html=True)
    with h2:
        if st.button("＋ Add medicine", use_container_width=True): st.session_state.page="Medicines"; st.session_state.show_add=True; st.rerun()
    for m in medicines:
        st.markdown('<div class="card">', unsafe_allow_html=True); dose_row(m); st.markdown('</div>', unsafe_allow_html=True); st.write("")
    s1,s2,s3 = st.columns(3)
    with s1: st.markdown(f'<div class="stat"><div class="stat-value">{adherence}%</div><div class="stat-label">Today’s adherence</div></div>', unsafe_allow_html=True)
    with s2: st.markdown(f'<div class="stat"><div class="stat-value">{len(medicines)}</div><div class="stat-label">Doses scheduled</div></div>', unsafe_allow_html=True)
    with s3: st.markdown(f'<div class="stat"><div class="stat-value">{sum(m["stock"]<=5 for m in medicines)}</div><div class="stat-label">Refills needed</div></div>', unsafe_allow_html=True)

# ---------- Medicines ----------
elif st.session_state.page == "Medicines":
    st.markdown('<div class="eyebrow">All medicines</div><h1 style="font-weight:900">Medicine cabinet</h1>', unsafe_allow_html=True)
    if st.button("＋ Add medicine", type="primary"): st.session_state.show_add=True
    if st.session_state.get("show_add"):
        with st.expander("Add a new medicine", expanded=True):
            with st.form("add_med"):
                a,b = st.columns(2)
                with a: name=st.text_input("Medicine name"); dose=st.text_input("Dosage", placeholder="500 mg · 1 tablet"); period=st.selectbox("Time of day", ["Morning","Afternoon","Night"])
                with b: dose_time=st.time_input("Time", value=time(8,0)); stock=st.number_input("Tablets in stock", min_value=0, max_value=10000, value=30, step=1)
                x,y=st.columns(2)
                with x: save=st.form_submit_button("Save medicine", type="primary", use_container_width=True)
                with y: cancel=st.form_submit_button("Cancel", use_container_width=True)
                if save:
                    if not name.strip() or not dose.strip(): st.error("Enter medicine name and dosage.")
                    else: add_medicine(uid,name.strip(),dose.strip(),dose_time.strftime("%H:%M"),period,int(stock)); st.session_state.show_add=False; st.success("Medicine added."); st.rerun()
                if cancel: st.session_state.show_add=False; st.rerun()
    for m in medicines:
        with st.container(border=True):
            c1,c2,c3 = st.columns([3,2,1])
            with c1: st.markdown(f'### 💊 {m["name"]}'); st.write(m["dose"])
            with c2: st.write(f'**{m["time"]}** · {m["period"]}'); st.write(f'{m["stock"]} tablets remaining')
            with c3:
                if m["stock"] <= 5: st.warning("Refill soon")
                if st.button("Delete", key=f"del_{m['id']}"):
                    delete_medicine(uid,m["id"]); st.rerun()

# ---------- Calendar ----------
elif st.session_state.page == "Calendar":
    st.markdown('<div class="eyebrow">Adherence history</div><h1 style="font-weight:900">Calendar</h1>', unsafe_allow_html=True)
    selected = st.date_input("Month", value=date.today(), label_visibility="collapsed")
    y,m = selected.year, selected.month
    adherence, missed, best, hist = monthly_stats(uid,y,m)
    total = len(hist)
    taken_count = int((hist.status=="taken").sum()) if not hist.empty else 0
    st.markdown(f"### {selected.strftime('%B %Y')}")
    a,b,c,d=st.columns(4)
    a.metric("Adherence", f"{adherence}%")
    b.metric("Taken doses", taken_count)
    c.metric("Missed doses", missed)
    d.metric("Best streak", f"{best} days")
    cal = pd.DataFrame(index=range(1,32), columns=["Status"])
    import calendar
    days = calendar.monthrange(y,m)[1]
    cal = cal.iloc[:days]
    status_by_day={}
    if not hist.empty:
        for _,r in hist.iterrows(): status_by_day[int(pd.to_datetime(r.dose_date).day)] = r.status
    cols = st.columns(7)
    for i,wd in enumerate(["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]): cols[i].markdown(f"**{wd}**")
    first = date(y,m,1).weekday()
    cells = [None]*first + list(range(1,days+1))
    for start in range(0,len(cells),7):
        row=st.columns(7)
        for j,daynum in enumerate(cells[start:start+7]):
            with row[j]:
                if daynum is None: st.write("")
                else:
                    s=status_by_day.get(daynum)
                    label = "✓" if s=="taken" else "×" if s=="skipped" else "~" if s=="snoozed" else "·"
                    st.markdown(f'<div style="text-align:center;padding:10px;border-radius:10px;background:{"#def6ed" if s=="taken" else "#ffe6e6" if s=="skipped" else "#edf3f2"};font-weight:800">{daynum}<br>{label}</div>', unsafe_allow_html=True)
    st.caption("✓ taken · × skipped · ~ snoozed · · no record")

# ---------- Family ----------
elif st.session_state.page == "Family":
    st.markdown('<div class="eyebrow">Caregiver summary</div><h1 style="font-weight:900">Family view</h1>', unsafe_allow_html=True)
    taken = sum(m["status"] == "taken" for m in medicines); adherence = round(taken/len(medicines)*100) if medicines else 0
    c1,c2=st.columns([1.2,1])
    with c1:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown(f'### {current_user()["name"]}’s daily progress')
        st.progress(adherence/100)
        st.markdown(f'<div class="stat-value">{adherence}%</div><div class="muted">adherence today</div>', unsafe_allow_html=True)
        st.caption("Updated from the medicine schedule on this device.")
        st.markdown('</div>', unsafe_allow_html=True)
    with c2:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown("### Missed dose alerts")
        skipped=[m for m in medicines if m["status"]=="skipped"]
        if skipped:
            for m in skipped: st.error(f'{m["name"]} was skipped at {m["time"]}.')
        else: st.success("✓ No missed doses today")
        st.markdown('</div>', unsafe_allow_html=True)
    st.write("")
    st.markdown("### Caregiver details")
    st.info(f"Name: {current_user().get('caregiver_name') or 'Not provided'}\n\nEmail: {current_user().get('caregiver_email') or 'Not provided'}")
