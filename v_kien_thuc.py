# -*- coding: utf-8 -*-
"""
KIẾN THỨC TỔNG HỢP (Cẩm nang CSKH)
- Kiến thức cô đọng theo từng nghiệp vụ, từng Công ty Điện lực, từng GIAI ĐOẠN hiệu lực
- "Tra cứu tại thời điểm": khách hỏi về quy định trước đây -> chọn ngày để xem hướng dẫn khi đó
- User quản lý: biên soạn, rà soát khi văn bản nguồn thay đổi
"""
from datetime import date

import pandas as pd
import streamlit as st

from auth import current_user, is_manager
from common import fmt_dt, from_iso, page_header, to_iso, van_ban_options
from db import danh_muc, execute, keyword_clause, now_str, query, query_one

user = current_user()
manager = is_manager()
page_header("🧭 Kiến thức tổng hợp", "Kiến thức theo nghiệp vụ, đơn vị áp dụng và giai đoạn hiệu lực của văn bản")

tab_names = ["🔎 Tra cứu"] + (["📝 Biên soạn"] if manager else [])
tabs = st.tabs(tab_names)

with tabs[0]:
    f1, f2, f3, f4 = st.columns([3, 2, 2, 1.6])
    kw = f1.text_input("Từ khoá", key="kt_kw")
    nv = f2.selectbox("Nghiệp vụ", ["Tất cả"] + danh_muc("nghiep_vu"), key="kt_nv")
    dv = f3.selectbox("Đơn vị", ["Tất cả"] + danh_muc("don_vi"), key="kt_dv",
                      index=0 if user.get("don_vi") not in danh_muc("don_vi") else
                      1 + danh_muc("don_vi").index(user["don_vi"]))
    ngay = f4.date_input("Tra cứu tại thời điểm", date.today(), format="DD/MM/YYYY",
                         help="Chọn ngày trong quá khứ để xem hướng dẫn áp dụng ở giai đoạn đó")
    params = []
    where = [keyword_clause(["tieu_de", "noi_dung"], kw, params),
             "(hieu_luc_tu IS NULL OR hieu_luc_tu <= ?)", "(hieu_luc_den IS NULL OR hieu_luc_den >= ?)"]
    params += [ngay.isoformat(), ngay.isoformat()]
    if nv != "Tất cả":
        where.append("nghiep_vu=?")
        params.append(nv)
    if dv != "Tất cả":
        where.append("(ap_dung='Tất cả' OR ap_dung=?)")
        params.append(dv)
    rows = query(f"SELECT * FROM kt_bai WHERE {' AND '.join(where)} ORDER BY nghiep_vu, tieu_de", params)
    if ngay != date.today():
        st.info(f"Đang xem kiến thức áp dụng tại ngày {ngay:%d/%m/%Y}.")
    st.caption(f"{len(rows)} mục kiến thức")
    vb_opts = van_ban_options()
    current_nv = None
    for k in rows:
        if k["nghiep_vu"] != current_nv:
            current_nv = k["nghiep_vu"]
            st.markdown(f"##### {current_nv or 'Chưa phân loại'}")
        with st.expander(f"{k['tieu_de']}" + (f"  ·  {k['ap_dung']}" if k["ap_dung"] != "Tất cả" else "")):
            st.markdown(k["noi_dung"])
            meta = [f"Hiệu lực {fmt_dt(k['hieu_luc_tu']) or '...'} → {fmt_dt(k['hieu_luc_den']) or 'nay'}"]
            if k["van_ban_id"]:
                meta.append(f"📑 {vb_opts.get(k['van_ban_id'], '')}")
            meta.append(f"Cập nhật {fmt_dt(k['updated_at'])}")
            st.caption(" · ".join(meta))

if manager:
    with tabs[1]:
        edit_id = st.session_state.get("kt_edit_id")
        d = query_one("SELECT * FROM kt_bai WHERE id=?", (edit_id,)) if edit_id else {}
        d = d or {}
        nv_list, dv_list, vb_opts = danh_muc("nghiep_vu"), ["Tất cả"] + danh_muc("don_vi"), van_ban_options()
        vb_keys = list(vb_opts)
        if edit_id:
            st.info(f"Đang sửa mục #{edit_id}")
        with st.form(f"kt_form_{edit_id or 'new'}"):
            tieu_de = st.text_input("Tiêu đề *", value=d.get("tieu_de", ""))
            c1, c2, c3 = st.columns(3)
            nghiep_vu = c1.selectbox("Nghiệp vụ", nv_list,
                                     index=nv_list.index(d["nghiep_vu"]) if d.get("nghiep_vu") in nv_list else 0)
            ap_dung = c2.selectbox("Đơn vị áp dụng", dv_list,
                                   index=dv_list.index(d["ap_dung"]) if d.get("ap_dung") in dv_list else 0)
            van_ban_id = c3.selectbox("Văn bản nguồn", vb_keys, format_func=vb_opts.get,
                                      index=vb_keys.index(d.get("van_ban_id")) if d.get("van_ban_id") in vb_keys else 0)
            noi_dung = st.text_area("Nội dung (Markdown: tiêu đề ###, gạch đầu dòng, bảng)",
                                    value=d.get("noi_dung", ""), height=300)
            c4, c5 = st.columns(2)
            hl_tu = c4.date_input("Hiệu lực từ", value=from_iso(d.get("hieu_luc_tu")), format="DD/MM/YYYY")
            hl_den = c5.date_input("Hiệu lực đến", value=from_iso(d.get("hieu_luc_den")), format="DD/MM/YYYY")
            b1, b2 = st.columns(2)
            save = b1.form_submit_button("💾 Lưu", type="primary", use_container_width=True)
            cancel = b2.form_submit_button("Huỷ / soạn mới", use_container_width=True)
        if cancel:
            st.session_state.pop("kt_edit_id", None)
            st.rerun()
        if save:
            if not tieu_de.strip():
                st.error("Nhập tiêu đề.")
            else:
                vals = (tieu_de.strip(), nghiep_vu, ap_dung, noi_dung, van_ban_id, to_iso(hl_tu), to_iso(hl_den))
                if edit_id:
                    execute("""UPDATE kt_bai SET tieu_de=?, nghiep_vu=?, ap_dung=?, noi_dung=?, van_ban_id=?,
                               hieu_luc_tu=?, hieu_luc_den=?, can_ra_soat=0, updated_at=? WHERE id=?""",
                            vals + (now_str(), edit_id))
                else:
                    execute("""INSERT INTO kt_bai(tieu_de, nghiep_vu, ap_dung, noi_dung, van_ban_id, hieu_luc_tu,
                               hieu_luc_den, created_by) VALUES (?,?,?,?,?,?,?,?)""", vals + (user["id"],))
                st.session_state.pop("kt_edit_id", None)
                st.success("Đã lưu.")
                st.rerun()

        st.divider()
        st.markdown("**Danh sách** (chọn dòng để sửa)")
        rows = query("SELECT * FROM kt_bai ORDER BY can_ra_soat DESC, nghiep_vu, tieu_de")
        if rows:
            df = pd.DataFrame([{"#": r["id"], "Rà soát": "⚠️" if r["can_ra_soat"] else "", "Tiêu đề": r["tieu_de"],
                                "Nghiệp vụ": r["nghiep_vu"], "Áp dụng": r["ap_dung"],
                                "Hiệu lực": f"{fmt_dt(r['hieu_luc_tu']) or '...'} → {fmt_dt(r['hieu_luc_den']) or 'nay'}"}
                               for r in rows])
            ev = st.dataframe(df, hide_index=True, use_container_width=True, on_select="rerun",
                              selection_mode="single-row", key="kt_table")
            if ev.selection.rows:
                r = rows[ev.selection.rows[0]]
                b1, b2, b3 = st.columns(3)
                if b1.button("✏️ Sửa", use_container_width=True):
                    st.session_state["kt_edit_id"] = r["id"]
                    st.rerun()
                if b2.button("✅ Đã rà soát", use_container_width=True, disabled=not r["can_ra_soat"]):
                    execute("UPDATE kt_bai SET can_ra_soat=0 WHERE id=?", (r["id"],))
                    st.rerun()
                if b3.button("🗑️ Xoá", use_container_width=True):
                    execute("DELETE FROM kt_bai WHERE id=?", (r["id"],))
                    st.rerun()
