# -*- coding: utf-8 -*-
"""Trang chủ: thông báo chưa đọc, số liệu nhanh, tình huống mới."""
import streamlit as st

from auth import current_user
from common import fmt_dt, page_header
from db import HL_SAP, execute, now_str, query, query_one

user = current_user()
page_header(f"Xin chào, {user['full_name']}", "Cẩm nang Chăm sóc khách hàng - tra cứu nhanh, thống nhất cách trả lời")

c1, c2, c3, c4 = st.columns(4)
c1.metric("Tình huống trong ngân hàng", query_one("SELECT COUNT(*) n FROM nh_tinh_huong")["n"])
c2.metric("Bài hỏi-đáp", query_one("SELECT COUNT(*) n FROM hd_bai WHERE an=0")["n"])
c3.metric("Văn bản, hướng dẫn", query_one("SELECT COUNT(*) n FROM van_ban")["n"])
c4.metric("Sắp có hiệu lực", query_one(
    "SELECT COUNT(*) n FROM nh_tinh_huong WHERE hieu_luc_tu > date('now','localtime')")["n"],
    help=f"Tình huống {HL_SAP.lower()} - nên đào tạo trước (ví dụ kỳ đổi giá điện)")

st.subheader("🔔 Thông báo")
show_all = st.toggle("Xem cả thông báo đã đọc", value=False)
cond = "" if show_all else "AND n.da_doc_luc IS NULL"
rows = query(f"""
    SELECT t.*, n.da_doc_luc, u.full_name AS nguoi_tao_ten
    FROM thong_bao_nhan n JOIN thong_bao t ON t.id = n.thong_bao_id
    LEFT JOIN users u ON u.id = t.nguoi_tao
    WHERE n.user_id = ? {cond}
    ORDER BY t.created_at DESC LIMIT 50""", (user["id"],))

if not rows:
    st.info("Không có thông báo mới.")
else:
    if not show_all and st.button(f"Đánh dấu đã đọc tất cả ({len(rows)})"):
        execute("UPDATE thong_bao_nhan SET da_doc_luc=? WHERE user_id=? AND da_doc_luc IS NULL",
                (now_str(), user["id"]))
        st.rerun()
    for t in rows:
        with st.container(border=True):
            left, right = st.columns([6, 1])
            mark = "" if t["da_doc_luc"] else "🆕 "
            left.markdown(f"{mark}**{t['tieu_de']}**")
            left.caption(f"{fmt_dt(t['created_at'])} · {t['nguoi_tao_ten'] or 'Hệ thống'}")
            if t["noi_dung"]:
                left.markdown(t["noi_dung"])
            if not t["da_doc_luc"] and right.button("Đã đọc", key=f"read_{t['id']}"):
                execute("UPDATE thong_bao_nhan SET da_doc_luc=? WHERE thong_bao_id=? AND user_id=?",
                        (now_str(), t["id"], user["id"]))
                st.rerun()
            if t["lien_ket"]:
                try:
                    right.page_link(t["lien_ket"], label="Mở", icon="➡️")
                except Exception:
                    pass  # trang không thuộc quyền của user này

st.subheader("🆕 Tình huống mới cập nhật")
for r in query("SELECT id, cau_hoi, nghiep_vu, updated_at FROM nh_tinh_huong "
               "ORDER BY updated_at DESC LIMIT 5"):
    st.markdown(f"- **{r['cau_hoi']}**  \n  :gray[{r['nghiep_vu']} · {fmt_dt(r['updated_at'])}]")
