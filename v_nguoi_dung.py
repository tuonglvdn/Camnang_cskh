# -*- coding: utf-8 -*-
"""QUẢN TRỊ: người dùng, phân quyền, danh mục nghiệp vụ / đơn vị."""
import pandas as pd
import streamlit as st

from auth import ROLE_NAMES, hash_password, require_role
from common import page_header, read_excel_rows  # noqa: F401
from db import connect, danh_muc, execute, query

me = require_role("quan_ly")
page_header("👥 Người dùng - danh mục")

t_user, t_add, t_dm = st.tabs(["Danh sách người dùng", "Thêm người dùng", "Danh mục"])
role_keys = list(ROLE_NAMES)
don_vi = danh_muc("don_vi")

with t_user:
    st.caption("Sửa trực tiếp trong bảng rồi bấm Lưu. Bỏ tick 'Hoạt động' để khoá tài khoản.")
    users = query("SELECT id, username, full_name, role, don_vi, active FROM users ORDER BY role, full_name")
    df = pd.DataFrame(users)
    df["active"] = df["active"].astype(bool)
    edited = st.data_editor(
        df, hide_index=True, width="stretch", key="user_editor", disabled=["id", "username"],
        column_config={
            "id": None, "username": "Tên đăng nhập", "full_name": "Họ tên",
            "role": st.column_config.SelectboxColumn("Vai trò", options=role_keys, required=True),
            "don_vi": st.column_config.SelectboxColumn("Đơn vị", options=don_vi),
            "active": st.column_config.CheckboxColumn("Hoạt động"),
        })
    st.caption("Vai trò: " + " · ".join(f"`{k}` = {v}" for k, v in ROLE_NAMES.items()))
    if st.button("💾 Lưu thay đổi", type="primary"):
        with connect() as c:
            for r in edited.to_dict("records"):
                if r["id"] == me["id"] and (r["role"] != "quan_ly" or not r["active"]):
                    st.warning("Không thể tự hạ quyền / khoá chính mình - bỏ qua dòng này.")
                    continue
                c.execute("UPDATE users SET full_name=?, role=?, don_vi=?, active=? WHERE id=?",
                          (r["full_name"], r["role"], r["don_vi"], int(r["active"]), r["id"]))
        st.success("Đã lưu.")

    st.divider()
    st.markdown("**Đặt lại mật khẩu**")
    c1, c2, c3 = st.columns([2, 2, 1])
    opts = {u["id"]: f"{u['full_name']} ({u['username']})" for u in users}
    uid = c1.selectbox("Người dùng", list(opts), format_func=opts.get)
    pw = c2.text_input("Mật khẩu mới", type="password")
    if c3.button("Đặt lại", width="stretch") and len(pw) >= 6:
        execute("UPDATE users SET password_hash=? WHERE id=?", (hash_password(pw), uid))
        st.success("Đã đặt lại mật khẩu.")

with t_add:
    with st.form("add_user", clear_on_submit=True):
        c1, c2 = st.columns(2)
        username = c1.text_input("Tên đăng nhập *")
        full_name = c2.text_input("Họ tên *")
        c3, c4, c5 = st.columns(3)
        role = c3.selectbox("Vai trò", role_keys, format_func=ROLE_NAMES.get, index=1)
        dv = c4.selectbox("Đơn vị", don_vi)
        pw = c5.text_input("Mật khẩu ban đầu *", type="password")
        if st.form_submit_button("Thêm", type="primary"):
            if not (username.strip() and full_name.strip() and len(pw) >= 6):
                st.error("Nhập đủ thông tin, mật khẩu tối thiểu 6 ký tự.")
            else:
                try:
                    execute("INSERT INTO users(username, full_name, password_hash, role, don_vi) VALUES (?,?,?,?,?)",
                            (username.strip().lower(), full_name.strip(), hash_password(pw), role, dv))
                    st.success(f"Đã thêm {full_name}.")
                except Exception:
                    st.error("Tên đăng nhập đã tồn tại.")

    st.markdown("**Thêm hàng loạt từ Excel** (cột: username, full_name, role, don_vi, password)")
    up = st.file_uploader("File Excel", type=["xlsx"], key="user_xlsx")
    if up is not None:
        data = pd.read_excel(up, dtype=str).fillna("")
        st.dataframe(data, hide_index=True)
        if st.button(f"Nhập {len(data)} người dùng"):
            ok = 0
            with connect() as c:
                for r in data.to_dict("records"):
                    if r.get("username") and r.get("password") and r.get("role") in role_keys:
                        c.execute("INSERT OR IGNORE INTO users(username, full_name, password_hash, role, don_vi) "
                                  "VALUES (?,?,?,?,?)", (r["username"].strip().lower(), r.get("full_name", ""),
                                                         hash_password(r["password"]), r["role"], r.get("don_vi", "")))
                        ok += 1
            st.success(f"Đã nhập {ok} người dùng.")

with t_dm:
    for loai, label in (("nghiep_vu", "Nghiệp vụ"), ("don_vi", "Đơn vị")):
        st.markdown(f"**{label}**")
        cur = pd.DataFrame({"ten": danh_muc(loai)})
        ed = st.data_editor(cur, num_rows="dynamic", hide_index=True, key=f"dm_{loai}",
                            column_config={"ten": st.column_config.TextColumn(label, required=True)})
        if st.button(f"Lưu danh mục {label.lower()}", key=f"save_{loai}"):
            names = [str(x).strip() for x in ed["ten"].tolist() if str(x).strip() and str(x) != "nan"]
            with connect() as c:
                c.execute("DELETE FROM danh_muc WHERE loai=?", (loai,))
                c.executemany("INSERT OR IGNORE INTO danh_muc(loai, ten, thu_tu) VALUES (?,?,?)",
                              [(loai, n, i) for i, n in enumerate(names)])
            st.success("Đã lưu.")
            st.rerun()
