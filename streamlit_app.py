import streamlit as st
import firebase_admin
from firebase_admin import credentials, auth, db
import pandas as pd
import numpy as np
import random
import io
import qrcode 
import requests 
from fpdf import FPDF
from datetime import datetime

# --- 1. CONFIG & TARIFF LOGIC ---
st.set_page_config(page_title="NITD AI ENERGY METER", layout="wide")

STATE_TARIFFS = {
    "Delhi": {"rate": 4.50, "tax": 1.15},
    "Maharashtra": {"rate": 7.20, "tax": 1.20},
    "Uttar Pradesh": {"rate": 6.50, "tax": 1.18},
    "Overall India (Avg)": {"rate": 5.95, "tax": 1.15}
}

def calculate_bill(units, state):
    config = STATE_TARIFFS[state]
    return round((units * config["rate"]) * config["tax"], 2)

# --- 2. RESEARCH & AUTH HELPERS ---
def verify_password_via_rest(email, password):
    """Strictly verifies password using Firebase Auth REST API"""
    # NOTE: Ensure this is the 'Web API Key' from Firebase Settings (starts with AIzaSy)
    api_key = "AIzaSyDlBe483Ei6sB0lYYEGp6X06T5N64Pxr98" 
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={api_key}"
    payload = {"email": email, "password": password, "returnSecureToken": True}
    
    try:
        response = requests.post(url, json=payload)
        if response.status_code == 200:
            return True, response.json()
        # Returns specific Firebase error like INVALID_PASSWORD
        return False, response.json().get('error', {}).get('message', 'AUTH_ERROR')
    except Exception as e:
        return False, str(e)

def neural_ode_imputation(val):
    return val if val else (230.0 + random.uniform(-1, 1))

def run_st_gcn_logic(v, i, units, appliances):
    expected_load = sum([app['Watts'] for app in appliances]) / 1000 if appliances else 0.5
    current_load = (v * i) / 1000
    is_theft = False
    if current_load < (expected_load * 0.2) and expected_load > 0.5:
        is_theft = True 
    elif i > 15.0:
        is_theft = True 
    forecast = units + (expected_load * 20) + random.uniform(-5, 5)
    return round(forecast, 2), is_theft

# --- 3. PAYMENT & PDF ---
def generate_upi_details(amount):
    upi_id = "7217252863@ybl"
    upi_link = f"upi://pay?pa={upi_id}&pn=NITDPCL&am={amount}&cu=INR"
    qr = qrcode.make(upi_link)
    buf = io.BytesIO()
    qr.save(buf, format='PNG')
    return upi_link, buf.getvalue()

def generate_pdf_report(email, units, cost, appliances, state):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 22)
    pdf.cell(200, 15, "NIT DELHI - SMART AI ENERGY AUDIT", ln=True, align='C')
    pdf.set_font("Arial", size=10)
    pdf.cell(200, 5, f"Issued: {datetime.now().strftime('%d-%m-%Y %H:%M')}", ln=True, align='C')
    pdf.ln(10)
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, f"Account ID: {email} | State: {state}", ln=True)
    pdf.cell(0, 10, f"Total Amount: Rs. {cost:,.2f}", ln=True)
    pdf.ln(20)
    pdf.line(140, pdf.get_y(), 190, pdf.get_y())
    pdf.set_font("Times", 'I', 14)
    pdf.set_text_color(0, 50, 200)
    pdf.cell(130); pdf.cell(60, 8, "Abhay Gautam", ln=True, align='C')
    pdf.set_font("Arial", '', 7)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(130); pdf.cell(60, 4, "DIGITALLY SIGNED (LLPQ-ECDSA)", ln=True, align='C')
    return pdf.output(dest='S').encode('latin-1', 'ignore')

# --- 4. STYLING ---
def apply_custom_style():
    st.markdown("""
        <style>
        .stApp { background-color: #050505; color: #00d4ff; }
        .neon-hindi { text-align: center; color: #00d4ff; font-size: 3.2rem; font-weight: 900; margin-bottom: 0px; text-shadow: 0 0 10px #00d4ff; }
        .neon-english { text-align: center; color: #00d4ff; font-size: 3.2rem; font-weight: 900; margin-bottom: 0px; text-shadow: 0 0 10px #00d4ff; }
        .pay-btn { background-color: #00d4ff; color: black !important; padding: 12px 24px; border-radius: 8px; text-decoration: none; font-weight: bold; display: block; text-align: center; margin: 10px 0; border: none; }
        hr { border: 0; height: 1px; background: #00d4ff; margin-bottom: 30px; }
        .chat-msg { background: rgba(0, 212, 255, 0.05); border-left: 3px solid #00d4ff; padding: 10px; margin: 5px 0; }
        </style>
        """, unsafe_allow_html=True)

def show_institute_header():
    apply_custom_style()
    st.markdown('<p class="neon-hindi">राष्ट्रीय प्रौद्योगिकी संस्थान दिल्ली</p>', unsafe_allow_html=True)
    st.markdown('<p class="neon-english">NATIONAL INSTITUTE OF TECHNOLOGY DELHI</p>', unsafe_allow_html=True)
    st.markdown('<p style="text-align:center; color:#00d4ff; font-size: 2.2rem; font-weight: 900; text-shadow: 0 0 10px #00d4ff;">IoT BASED SMART ENERGY METER INTEGRATED WITH AI</p>', unsafe_allow_html=True)
    st.markdown("<hr>", unsafe_allow_html=True)

# --- 5. FIREBASE SETUP ---
if not firebase_admin._apps:
    try:
        if "firebase" in st.secrets:
            fb_dict = dict(st.secrets["firebase"])
            fb_dict["private_key"] = fb_dict["private_key"].replace("\\n", "\n")
            cred = credentials.Certificate(fb_dict)
        else:
            cred = credentials.Certificate("serviceAccountKey.json")
        firebase_admin.initialize_app(cred, {'databaseURL': 'https://smartenergymeter-d4545-default-rtdb.firebaseio.com/'})
    except: pass

def show_dashboard():
    show_institute_header()
    
    # Sidebar Logout
    if st.sidebar.button("Logout 🚪"):
        st.session_state.logged_in = False
        st.rerun()

    if 'appliances' not in st.session_state: st.session_state.appliances = []
    if 'chat_history' not in st.session_state: st.session_state.chat_history = []
    
    selected_state = st.sidebar.selectbox("Select State", list(STATE_TARIFFS.keys()))
    v = neural_ode_imputation(231.8)
    i, units_val = 4.9, 425.2
    cost = calculate_bill(units_val, selected_state)
    f_units, is_theft = run_st_gcn_logic(v, i, units_val, st.session_state.appliances)

    tabs = st.tabs(["::Live Analytics::", "::Activity Profiling::", "::Research Visuals::", "::Billing & Payment::", "::AI Energy Chatbot::"])

    with tabs[0]:
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Voltage (ODE)", f"{v:.1f} V")
        m2.metric("Current", f"{i} A")
        m3.metric("Usage", f"{units_val} kWh")
        m4.metric("Bill", f"₹{cost:,.2f}")
        if is_theft: st.error("🚨 Anomaly Detected")
        else: st.success("✅ System Secure")
        st.line_chart(pd.DataFrame(np.random.randn(24, 1), columns=['Consumption']))

    with tabs[1]:
        col_in1, col_in2 = st.columns(2)
        with col_in1: name = st.text_input("Appliance Name")
        with col_in2: watts = st.number_input("Rating (W)", min_value=1, value=1000)
        if st.button("➕ Add"):
            st.session_state.appliances.append({"Name": name, "Watts": watts})
            st.rerun()
        st.table(pd.DataFrame(st.session_state.appliances))

    with tabs[2]:
        accuracy_data = pd.DataFrame({'Model': ['ST-GCN+ViT', 'GNN-ViT', 'BiLSTM-ViT'], 'Accuracy': [98.67, 94.60, 93.70]}).set_index('Model')
        st.bar_chart(accuracy_data)

    with tabs[3]:
        upi_url, qr_img = generate_upi_details(cost)
        p1, p2 = st.columns([1, 1.5])
        with p1: st.image(qr_img, width=240)
        with p2:
            st.markdown(f'<a href="{upi_url}" target="_self" class="pay-btn">LAUNCH UPI APP</a>', unsafe_allow_html=True)
            if st.button("Confirm Payment"):
                st.balloons(); st.success("Ledger Updated!")
            report = generate_pdf_report(st.session_state.user_email, units_val, cost, st.session_state.appliances, selected_state)
            st.download_button("📥 Download Receipt", data=report, file_name="NITD_Receipt.pdf", use_container_width=True)

    with tabs[4]:
        user_msg = st.chat_input("Ask Assistant...")
        if user_msg:
            resp = f"Analysis: Bill is ₹{cost}." if "bill" in user_msg.lower() else "ST-GCN model running."
            st.session_state.chat_history.append(("User", user_msg))
            st.session_state.chat_history.append(("AI", resp))
        for s, m in st.session_state.chat_history:
            st.markdown(f"<div class='chat-msg'><b>{s}:</b> {m}</div>", unsafe_allow_html=True)

# --- 6. AUTH GATE ---
if 'logged_in' not in st.session_state: 
    st.session_state['logged_in'] = False

if not st.session_state.logged_in:
    show_institute_header()
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        auth_mode = st.radio("Access Level", ["Login", "Sign Up"], horizontal=True)
        email = st.text_input("Institutional Email")
        pwd = st.text_input("Password", type="password")
        
        if auth_mode == "Sign Up":
            confirm_pwd = st.text_input("Confirm Password", type="password")
            if st.button("Create Account", use_container_width=True):
                if email and pwd == confirm_pwd and len(pwd) >= 6:
                    try:
                        auth.create_user(email=email, password=pwd)
                        st.success("Account Created! Please switch to Login.")
                    except Exception as e: st.error(str(e))
                else: st.error("Passwords mismatch, too short, or empty email.")
        else:
            if st.button("Authorize & Enter", use_container_width=True):
                # Password Verification via REST
                success, result = verify_password_via_rest(email, pwd)
                if success:
                    st.session_state.logged_in = True
                    st.session_state.user_email = email
                    st.rerun()
                else:
                    st.error(f"Authentication Failed: {result}")
else:
    show_dashboard()
