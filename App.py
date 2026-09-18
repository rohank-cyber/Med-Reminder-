import streamlit as st
import pandas as pd
import plotly.express as px
import requests
import firebase_admin

from datetime import datetime, date, timedelta
from firebase_admin import credentials, firestore
from twilio.rest import Client


# ============================================================
# PAGE CONFIG
# ============================================================

st.set_page_config(
    page_title="MedRemind",
    page_icon="💊",
    layout="wide",
    initial_sidebar_state="expanded"
)


# ============================================================
# CUSTOM CSS
# ============================================================

st.markdown("""
<style>

.stApp {
    background-color: #f4f7fb;
}

section[data-testid="stSidebar"] {
    background-color: #ffffff;
}

.main-title {
    font-size: 42px;
    font-weight: 800;
    color: #1565c0;
    margin-bottom: 5px;
}

.subtitle {
    color: #607d8b;
    font-size: 17px;
    margin-bottom: 25px;
}

.card {
    background-color: white;
    padding: 22px;
    border-radius: 18px;
    box-shadow: 0px 3px 12px rgba(0,0,0,0.08);
    margin-bottom: 15px;
}

.metric-card {
    background-color: white;
    padding: 20px;
    border-radius: 18px;
    text-align: center;
    box-shadow: 0px 3px 12px rgba(0,0,0,0.08);
}

.metric-number {
    font-size: 32px;
    font-weight: 800;
    color: #1565c0;
}

.metric-label {
    color: #607d8b;
    font-size: 15px;
}

.warning-box {
    padding: 15px;
    border-radius: 12px;
    background-color: #fff3cd;
    border-left: 5px solid #ffb300;
}

.success-box {
    padding: 15px;
    border-radius: 12px;
    background-color: #d4edda;
    border-left: 5px solid #28a745;
}

.danger-box {
    padding: 15px;
    border-radius: 12px;
    background-color: #f8d7da;
    border-left: 5px solid #dc3545;
}

.stButton > button {
    border-radius: 10px;
    min-height: 45px;
    font-weight: 600;
}

h1, h2, h3 {
    color: #263238;
}

</style>
""", unsafe_allow_html=True)


# ============================================================
# FIREBASE INITIALIZATION
# ============================================================

@st.cache_resource
def initialize_firebase():

    if not firebase_admin._apps:

        cred = credentials.Certificate("serviceAccountKey.json")

        firebase_admin.initialize_app(cred)

    return firestore.client()


try:

    db = initialize_firebase()

except Exception as e:

    st.error("Firebase initialization failed.")
    st.code(str(e))
    st.stop()


# ============================================================
# SESSION STATE
# ============================================================

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if "uid" not in st.session_state:
    st.session_state.uid = None

if "email" not in st.session_state:
    st.session_state.email = None

if "role" not in st.session_state:
    st.session_state.role = None

if "name" not in st.session_state:
    st.session_state.name = None


# ============================================================
# FIREBASE AUTH REST API
# ============================================================

def firebase_signup(email, password):

    api_key = st.secrets["FIREBASE_API_KEY"]

    url = (
        "https://identitytoolkit.googleapis.com/v1/"
        "accounts:signUp?key=" + api_key
    )

    payload = {
        "email": email,
        "password": password,
        "returnSecureToken": True
    }

    response = requests.post(url, json=payload)

    return response.json()


def firebase_login(email, password):

    api_key = st.secrets["FIREBASE_API_KEY"]

    url = (
        "https://identitytoolkit.googleapis.com/v1/"
        "accounts:signInWithPassword?key=" + api_key
    )

    payload = {
        "email": email,
        "password": password,
        "returnSecureToken": True
    }

    response = requests.post(url, json=payload)

    return response.json()


# ============================================================
# FIREBASE USER FUNCTIONS
# ============================================================

def create_user_profile(uid, email, name, role, caregiver_phone=""):

    db.collection("users").document(uid).set({

        "uid": uid,
        "email": email,
        "name": name,
        "role": role,
        "caregiver_phone": caregiver_phone,
        "created_at": firestore.SERVER_TIMESTAMP

    })


def get_user_profile(uid):

    doc = db.collection("users").document(uid).get()

    if doc.exists:
        return doc.to_dict()

    return {}


# ============================================================
# MEDICINE FUNCTIONS
# ============================================================

def add_medicine(
    user_id,
    name,
    dosage,
    timing,
    frequency,
    caregiver_phone,
    refill_quantity,
    interaction_notes
):

    data = {

        "user_id": user_id,

        "name": name,

        "dosage": dosage,

        "timing": timing,

        "frequency": frequency,

        "caregiver_phone": caregiver_phone,

        "refill_quantity": refill_quantity,

        "remaining": refill_quantity,

        "interaction_notes": interaction_notes,

        "created_at": firestore.SERVER_TIMESTAMP,

        "active": True
    }

    db.collection("medicines").add(data)


def get_medicines(user_id):

    docs = (
        db.collection("medicines")
        .where("user_id", "==", user_id)
        .where("active", "==", True)
        .stream()
    )

    medicines = []

    for doc in docs:

        data = doc.to_dict()

        data["id"] = doc.id

        medicines.append(data)

    return medicines


def delete_medicine(medicine_id):

    db.collection("medicines").document(medicine_id).update({

        "active": False

    })


# ============================================================
# DOSE HISTORY
# ============================================================

def log_dose(
    user_id,
    medicine_id,
    medicine_name,
    dosage,
    scheduled_time,
    status
):

    db.collection("dose_history").add({

        "user_id": user_id,

        "medicine_id": medicine_id,

        "medicine_name": medicine_name,

        "dosage": dosage,

        "scheduled_time": scheduled_time,

        "status": status,

        "timestamp": firestore.SERVER_TIMESTAMP

    })


def get_dose_history(user_id):

    docs = (
        db.collection("dose_history")
        .where("user_id", "==", user_id)
        .stream()
    )

    records = []

    for doc in docs:

        data = doc.to_dict()

        data["id"] = doc.id

        records.append(data)

    return records


# ============================================================
# TWILIO SMS
# ============================================================

def send_sms(message, recipient=None):

    try:

        account_sid = st.secrets["TWILIO_ACCOUNT_SID"]
        auth_token = st.secrets["TWILIO_AUTH_TOKEN"]
        from_number = st.secrets["TWILIO_FROM_NUMBER"]

        if recipient is None:
            recipient = st.secrets["CAREGIVER_PHONE"]

        client = Client(
            account_sid,
            auth_token
        )

        sms = client.messages.create(

            body=message,

            from_=from_number,

            to=recipient
        )

        return True, sms.sid

    except Exception as e:

        return False, str(e)


# ============================================================
# SMS ALERT MESSAGE
# ============================================================

def create_missed_dose_message(
    patient,
    medicine,
    dosage,
    scheduled_time
):

    message = f"""⚠️ MedRemind Alert

Patient: {patient}

Medicine: {medicine}

Dosage: {dosage}

Scheduled: {scheduled_time}

Status: MISSED

Please check on the patient.

— MedRemind"""

    return message


# ============================================================
# LOG SMS
# ============================================================

def log_sms(
    user_id,
    medicine_name,
    recipient,
    status,
    message,
    message_sid=""
):

    db.collection("sms_logs").add({

        "user_id": user_id,

        "medicine_name": medicine_name,

        "recipient": recipient,

        "status": status,

        "message": message,

        "message_sid": message_sid,

        "timestamp": firestore.SERVER_TIMESTAMP

    })


# ============================================================
# CHECK MISSED DOSE
# ============================================================

def check_for_missed_dose(
    medicine,
    patient_name,
    user_id
):

    current_time = datetime.now()

    timing = medicine.get("timing", "")

    if not timing:
        return False

    try:

        scheduled = datetime.strptime(
            timing,
            "%H:%M"
        ).replace(
            year=current_time.year,
            month=current_time.month,
            day=current_time.day
        )

    except:

        return False

    difference = (
        current_time - scheduled
    ).total_seconds() / 3600

    if difference < 2:

        return False

    today = date.today().isoformat()

    history = get_dose_history(user_id)

    for record in history:

        if (
            record.get("medicine_id") == medicine["id"]
            and record.get("scheduled_date") == today
        ):

            return False

    return True


# ============================================================
# SEND MISSED DOSE ALERT
# ============================================================

def send_missed_dose_alert(
    medicine,
    patient_name,
    user_id
):

    caregiver_phone = medicine.get(
        "caregiver_phone"
    )

    if not caregiver_phone:

        caregiver_phone = st.secrets[
            "CAREGIVER_PHONE"
        ]

    message = create_missed_dose_message(

        patient_name,

        medicine.get("name", "Medicine"),

        medicine.get("dosage", ""),

        medicine.get("timing", "")

    )

    success, result = send_sms(

        message,

        caregiver_phone

    )

    status = "SENT" if success else "FAILED"

    log_sms(

        user_id,

        medicine.get("name", ""),

        caregiver_phone,

        status,

        message,

        result if success else ""

    )

    return success, result


# ============================================================
# LOGIN PAGE
# ============================================================

def login_page():

    st.markdown(
        '<div class="main-title">💊 MedRemind</div>',
        unsafe_allow_html=True
    )

    st.markdown(
        '<div class="subtitle">'
        'Smart Medicine Reminder & Adherence Tracker'
        '</div>',
        unsafe_allow_html=True
    )

    tab1, tab2 = st.tabs(
        ["🔐 Login", "📝 Create Account"]
    )

    # --------------------------------------------------------
    # LOGIN
    # --------------------------------------------------------

    with tab1:

        st.subheader("Welcome Back")

        email = st.text_input(
            "Email",
            key="login_email"
        )

        password = st.text_input(
            "Password",
            type="password",
            key="login_password"
        )

        if st.button(
            "Login",
            use_container_width=True
        ):

            if not email or not password:

                st.warning(
                    "Please enter email and password."
                )

            else:

                result = firebase_login(
                    email,
                    password
                )

                if "localId" in result:

                    uid = result["localId"]

                    profile = get_user_profile(
                        uid
                    )

                    st.session_state.logged_in = True

                    st.session_state.uid = uid

                    st.session_state.email = email

                    st.session_state.name = profile.get(
                        "name",
                        email.split("@")[0]
                    )

                    st.session_state.role = profile.get(
                        "role",
                        "elder"
                    )

                    st.success(
                        "Login successful!"
                    )

                    st.rerun()

                else:

                    st.error(
                        result.get(
                            "error",
                            {}
                        ).get(
                            "message",
                            "Login failed."
                        )
                    )

    # --------------------------------------------------------
    # SIGNUP
    # --------------------------------------------------------

    with tab2:

        st.subheader("Create Account")

        name = st.text_input(
            "Full Name"
        )

        email = st.text_input(
            "Email",
            key="signup_email"
        )

        password = st.text_input(
            "Password",
            type="password",
            key="signup_password"
        )

        role = st.selectbox(
            "Account Type",
            [
                "elder",
                "caregiver"
            ]
        )

        caregiver_phone = st.text_input(
            "Caregiver Phone Number",
            placeholder="+919876543210"
        )

        if st.button(
            "Create Account",
            use_container_width=True
        ):

            if not name or not email or not password:

                st.warning(
                    "Please fill all required fields."
                )

            else:

                result = firebase_signup(
                    email,
                    password
                )

                if "localId" in result:

                    uid = result["localId"]

                    create_user_profile(

                        uid,

                        email,

                        name,

                        role,

                        caregiver_phone
                    )

                    st.success(
                        "Account created successfully!"
                    )

                    st.info(
                        "Go to the Login tab."
                    )

                else:

                    st.error(
                        result.get(
                            "error",
                            {}
                        ).get(
                            "message",
                            "Signup failed."
                        )
                    )


# ============================================================
# DASHBOARD
# ============================================================

def dashboard():

    user_id = st.session_state.uid

    patient_name = st.session_state.name

    medicines = get_medicines(user_id)

    history = get_dose_history(user_id)

    st.markdown(
        f"""
        <div class="main-title">
        Good day, {patient_name} 👋
        </div>

        <div class="subtitle">
        Welcome to your MedRemind dashboard
        </div>
        """,
        unsafe_allow_html=True
    )

    # --------------------------------------------------------
    # AUTOMATIC CHECK
    # --------------------------------------------------------

    for medicine in medicines:

        try:

            if check_for_missed_dose(
                medicine,
                patient_name,
                user_id
            ):

                pass

        except:

            pass

    # --------------------------------------------------------
    # METRICS
    # --------------------------------------------------------

    total_medicines = len(medicines)

    taken = sum(
        1
        for x in history
        if x.get("status") == "Taken"
    )

    skipped = sum(
        1
        for x in history
        if x.get("status") == "Skipped"
    )

    total_doses = taken + skipped

    adherence = (
        (taken / total_doses) * 100
        if total_doses > 0
        else 100
    )

    c1, c2, c3, c4 = st.columns(4)

    with c1:

        st.markdown(
            f"""
            <div class="metric-card">
            <div class="metric-number">
            {total_medicines}
            </div>
            <div class="metric-label">
            Active Medicines
            </div>
            </div>
            """,
            unsafe_allow_html=True
        )

    with c2:

        st.markdown(
            f"""
            <div class="metric-card">
            <div class="metric-number">
            {taken}
            </div>
            <div class="metric-label">
            Doses Taken
            </div>
            </div>
            """,
            unsafe_allow_html=True
        )

    with c3:

        st.markdown(
            f"""
            <div class="metric-card">
            <div class="metric-number">
            {skipped}
            </div>
            <div class="metric-label">
            Doses Missed
            </div>
            </div>
            """,
            unsafe_allow_html=True
        )

    with c4:

        st.markdown(
            f"""
            <div class="metric-card">
            <div class="metric-number">
            {adherence:.1f}%
            </div>
            <div class="metric-label">
            Adherence
            </div>
            </div>
            """,
            unsafe_allow_html=True
        )

    st.divider()

    # --------------------------------------------------------
    # TODAY'S MEDICINES
    # --------------------------------------------------------

    st.subheader("💊 Today's Medicines")

    if not medicines:

        st.info(
            "No medicines added yet."
        )

    for medicine in medicines:

        col1, col2, col3, col4 = st.columns(
            [2, 1, 1, 1]
        )

        with col1:

            st.markdown(
                f"### 💊 {medicine.get('name')}"

            )

            st.write(
                f"Dosage: {medicine.get('dosage')}"
            )

            st.write(
                f"Time: {medicine.get('timing')}"
            )

        with col2:

            if st.button(
                "✅ Taken",
                key=f"taken_{medicine['id']}"
            ):

                log_dose(

                    user_id,

                    medicine["id"],

                    medicine["name"],

                    medicine.get(
                        "dosage",
                        ""
                    ),

                    medicine.get(
                        "timing",
                        ""
                    ),

                    "Taken"

                )

                st.success(
                    "Dose marked as Taken."
                )

                st.rerun()

        with col3:

            if st.button(
                "❌ Skip",
                key=f"skip_{medicine['id']}"
            ):

                log_dose(

                    user_id,

                    medicine["id"],

                    medicine["name"],

                    medicine.get(
                        "dosage",
                        ""
                    ),

                    medicine.get(
                        "timing",
                        ""
                    ),

                    "Skipped"

                )

                success, result = send_missed_dose_alert(

                    medicine,

                    patient_name,

                    user_id

                )

                if success:

                    st.warning(
                        "Dose skipped and caregiver SMS sent."
                    )

                else:

                    st.warning(
                        "Dose skipped, but SMS failed."
                    )

                    st.code(str(result))

                st.rer
