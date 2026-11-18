# -*- coding: utf-8 -*-
"""
Đăng nhập + phân quyền.
Vai trò (theo tài liệu "Trao đổi nghiệp vụ CSKH"):
  quan_ly : User quản lý (P.CSKH)  - soạn thảo, quản lý thông báo, thống kê
  dtv     : User ĐTV (gồm QA, Trưởng ca) - xem + gửi câu hỏi Chuyên mục hỏi-đáp
  dl      : User Điện lực           - xem Ngân hàng tình huống, Kiến thức, Văn bản
Giai đoạn sau có thể thay bằng đăng nhập AD/LDAP của đơn vị.
"""
import hashlib
import hmac
import os
import secrets
import time
from datetime import datetime, timedelta

import streamlit as st

ROLE_NAMES = {"quan_ly": "User quản lý", "dtv": "User ĐTV", "dl": "User Điện lực"}
_ITER = 200_000
# Thời gian giữ đăng nhập (giờ) - mặc định 1 ca làm việc. Đổi bằng biến môi trường CAMNANG_SESSION_HOURS
SESSION_HOURS = float(os.environ.get("CAMNANG_SESSION_HOURS", "10"))
WEAK_PASSWORDS = {"admin123", "123456", "12345678", "password"}
MAX_FAIL, LOCK_SEC = 5, 60


def hash_password(password):
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode(), _ITER)
    return f"pbkdf2${_ITER}${salt}${dk.hex()}"


def verify_password(password, stored):
    try:
        _, iters, salt, digest = stored.split("$")
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode(), int(iters))
        return hmac.compare_digest(dk.hex(), digest)
    except Exception:
        return False


def _new_session(user_id):
    from db import execute, now_str
    token = secrets.token_urlsafe(24)
    exp = (datetime.now() + timedelta(hours=SESSION_HOURS)).strftime("%Y-%m-%d %H:%M:%S")
    execute("DELETE FROM phien WHERE expires_at < ?", (now_str(),))  # dọn phiên hết hạn
    execute("INSERT INTO phien(token, user_id, expires_at) VALUES (?,?,?)", (token, user_id, exp))
    return token


def current_user():
    """User đang đăng nhập. Nhấn F5 vẫn giữ đăng nhập nhờ mã phiên trên địa chỉ trang (?t=...)."""
    u = st.session_state.get("user")
    if u:
        return u
    token = st.query_params.get("t")
    if not token:
        return None
    from db import now_str, query_one
    u = query_one("""SELECT u.* FROM phien p JOIN users u ON u.id = p.user_id
                     WHERE p.token=? AND p.expires_at > ? AND u.active=1""", (token, now_str()))
    if not u:
        st.query_params.clear()
        return None
    u.pop("password_hash", None)
    st.session_state["user"] = u
    st.session_state["token"] = token
    return u


def keep_token():
    """Gọi mỗi lần chạy: giữ ?t= trên địa chỉ trang khi chuyển trang."""
    token = st.session_state.get("token")
    if token and st.query_params.get("t") != token:
        st.query_params["t"] = token


def is_manager():
    u = current_user()
    return bool(u and u["role"] == "quan_ly")


def require_role(*roles):
    """Gọi ở đầu trang: chặn người không đủ quyền (phòng khi gõ thẳng URL)."""
    u = current_user()
    if not u or u["role"] not in roles:
        st.error("Bạn không có quyền truy cập trang này.")
        st.stop()
    return u


def login_page():
    from db import query_one
    st.title("📘 Cẩm nang Chăm sóc khách hàng")
    st.caption("Trung tâm CSKH - Tổng công ty Điện lực miền Trung")
    col, _ = st.columns([1, 1.4])
    with col, st.form("login"):
        username = st.text_input("Tên đăng nhập")
        password = st.text_input("Mật khẩu", type="password")
        ok = st.form_submit_button("Đăng nhập", type="primary", use_container_width=True)
    if ok:
        locked_until = st.session_state.get("lock_until", 0)
        if time.time() < locked_until:
            st.error(f"Nhập sai quá {MAX_FAIL} lần. Thử lại sau {int(locked_until - time.time())} giây.")
            return
        u = query_one("SELECT * FROM users WHERE username=? AND active=1", (username.strip().lower(),))
        if u and verify_password(password, u["password_hash"]):
            u.pop("password_hash", None)
            st.session_state["user"] = u
            st.session_state["token"] = _new_session(u["id"])
            st.session_state["weak_pw"] = password in WEAK_PASSWORDS
            st.session_state.pop("fail", None)
            st.query_params["t"] = st.session_state["token"]
            st.rerun()
        else:
            st.session_state["fail"] = st.session_state.get("fail", 0) + 1
            if st.session_state["fail"] >= MAX_FAIL:
                st.session_state["lock_until"] = time.time() + LOCK_SEC
                st.session_state["fail"] = 0
            st.error("Sai tên đăng nhập hoặc mật khẩu.")
            demo = {"dtv1", "dtv2", "dtv3", "dl1"}
            if username.strip().lower() in demo and not query_one(
                    "SELECT 1 x FROM users WHERE username=?", (username.strip().lower(),)):
                st.info("Tài khoản demo chưa được tạo. Mở cửa sổ lệnh trong thư mục chương trình và chạy:  \n"
                        "`python seed_demo.py`  \nrồi đăng nhập lại (không cần tắt chương trình). "
                        "Hoặc đăng nhập **admin** và tạo người dùng ở trang *Người dùng - danh mục*.")


def logout():
    token = st.session_state.get("token")
    if token:
        from db import execute
        execute("DELETE FROM phien WHERE token=?", (token,))
    st.query_params.clear()
    st.session_state.clear()
    st.rerun()
