# -*- coding: utf-8 -*-
"""
CẨM NANG CHĂM SÓC KHÁCH HÀNG - TT CSKH EVNCPC
Chạy:  streamlit run app.py
"""
import os
import sys

import streamlit as st
from streamlit import runtime

if not runtime.exists():  # chạy nhầm bằng "python app.py"
    print("Chương trình phải chạy bằng lệnh:  streamlit run app.py   (hoặc nhấp đúp chay.bat)")
    sys.exit(1)

from auth import ROLE_NAMES, current_user, keep_token, login_page, logout
from common import unread_count
from db import init_db

st.set_page_config(page_title="Cẩm nang CSKH", page_icon="📘", layout="wide")
init_db()

# Chế độ DEMO (chạy thử trên web, ví dụ Streamlit Community Cloud):
# bật khi có file DEMO_MODE cạnh app.py, hoặc biến môi trường / secret CAMNANG_DEMO = "1"
def _demo_enabled():
    if os.path.exists(os.path.join(os.path.dirname(os.path.abspath(__file__)), "DEMO_MODE")):
        return True
    if os.environ.get("CAMNANG_DEMO") == "1":
        return True
    try:
        return str(st.secrets.get("CAMNANG_DEMO", "")) == "1"
    except Exception:
        return False


DEMO = _demo_enabled()
if DEMO:
    @st.cache_resource
    def _seed_demo():
        import seed_demo  # noqa: F401  (tạo tài khoản + dữ liệu ví dụ một lần)
        return True
    _seed_demo()

user = current_user()
if not user:
    if DEMO:
        st.info("**Bản chạy thử (DEMO)** – dữ liệu là ví dụ, có thể bị xoá khi máy chủ khởi động lại.  \n"
                "Tài khoản: `admin / admin123` (quản lý) · `dtv1 / 123456` (ĐTV) · `dl1 / 123456` (Điện lực)")
    st.navigation([st.Page(login_page, title="Đăng nhập", icon="🔐")]).run()
    st.stop()

keep_token()
if st.session_state.get("weak_pw"):
    st.warning("⚠️ Bạn đang dùng mật khẩu mặc định / quá đơn giản. Hãy bấm **🔑 Đổi mật khẩu** ở thanh bên trái.")

role = user["role"]
APP_DIR = os.path.dirname(os.path.abspath(__file__))
_missing = [f for f in ("trang_chu", "tro_ly", "ngan_hang", "kien_thuc", "van_ban", "hoi_dap", "hd_quan_ly",
                        "hd_soan_thao", "thong_ke", "nh_soan_thao", "nguoi_dung", "nhap_du_lieu")
            if not os.path.isfile(os.path.join(APP_DIR, "v_" + f + ".py"))]
if _missing:
    st.error("Thiếu file (phải nằm cùng thư mục với app.py): "
             + ", ".join(f"`v_{m}.py`" for m in _missing)
             + ".  \nNếu chạy trên GitHub/Streamlit Cloud: tải đủ các file v_*.py lên repository rồi Reboot app.")
    st.stop()


def P(path, title, icon):
    return st.Page(os.path.join(APP_DIR, path), title=title, icon=icon)


n_unread = unread_count(user["id"])
pages = {
    "Chung": [
        P("v_trang_chu.py", f"Trang chủ{f' ({n_unread})' if n_unread else ''}", "🏠"),
        P("v_tro_ly.py", "Trợ lý tra cứu", "🤖"),
        P("v_ngan_hang.py", "Ngân hàng tình huống", "📚"),
        P("v_kien_thuc.py", "Kiến thức tổng hợp", "🧭"),
        P("v_van_ban.py", "Văn bản, hướng dẫn", "📄"),
    ],
}
if role in ("dtv", "quan_ly"):
    pages["Chuyên mục hỏi-đáp"] = [P("v_hoi_dap.py", "Hỏi-đáp", "💬")]
if role == "quan_ly":
    pages["Chuyên mục hỏi-đáp"] += [
        P("v_hd_quan_ly.py", "Quản lý hỏi-đáp", "🛎️"),
        P("v_hd_soan_thao.py", "Soạn thảo hỏi-đáp", "✍️"),
        P("v_thong_ke.py", "Thống kê - thi đua", "📊"),
    ]
    pages["Quản trị"] = [
        P("v_nh_soan_thao.py", "Soạn thảo tình huống", "🗂️"),
        P("v_nhap_du_lieu.py", "Nhập dữ liệu hàng loạt", "📥"),
        P("v_nguoi_dung.py", "Người dùng - danh mục", "👥"),
    ]

with st.sidebar:
    st.markdown(f"**{user['full_name']}**  \n{ROLE_NAMES[role]} · {user.get('don_vi') or ''}")
    with st.popover("🔑 Đổi mật khẩu", use_container_width=True):
        with st.form("doi_mk", clear_on_submit=True):
            old = st.text_input("Mật khẩu hiện tại", type="password")
            new = st.text_input("Mật khẩu mới (≥ 6 ký tự)", type="password")
            if st.form_submit_button("Đổi"):
                from auth import hash_password, verify_password
                from db import execute, query_one
                row = query_one("SELECT password_hash FROM users WHERE id=?", (user["id"],))
                if not verify_password(old, row["password_hash"]):
                    st.error("Mật khẩu hiện tại không đúng.")
                elif len(new) < 6:
                    st.error("Mật khẩu mới quá ngắn.")
                else:
                    execute("UPDATE users SET password_hash=? WHERE id=?", (hash_password(new), user["id"]))
                    st.session_state["weak_pw"] = new in ("admin123", "123456", "12345678", "password")
                    st.success("Đã đổi mật khẩu.")
    if st.button("Đăng xuất", use_container_width=True):
        logout()

st.navigation(pages).run()
