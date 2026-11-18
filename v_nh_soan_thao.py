# -*- coding: utf-8 -*-
"""
NGÂN HÀNG TÌNH HUỐNG - SOẠN THẢO (User quản lý) - mục 2.2.1
- Biên soạn: câu hỏi, từ gợi ý, nghiệp vụ, câu trả lời, nguồn tài liệu, link wiki, video, hiệu lực
- Khi văn bản nguồn bị thay thế/sửa đổi: lọc theo văn bản để hiệu chỉnh, gắn tag hết hiệu lực
- Nhập từ Excel mẫu; xuất danh sách "thường gặp" để đưa lên web CSKH
"""
import io

import pandas as pd
import streamlit as st

from auth import require_role
from common import (fmt_dt, from_iso, notify, page_header, read_excel_rows,
                    template_bytes, to_iso, van_ban_options)
from db import (HL_DANG, HL_HET, HL_SAP, connect, danh_muc, execute, keyword_clause,
                now_str, query, query_one, trang_thai_hieu_luc)

user = require_role("quan_ly")
page_header("🗂️ Soạn thảo ngân hàng tình huống")

NGUON = ["Hỏi-đáp", "QA", "P.CSKH", "Hướng dẫn TCT", "Điện lực", "Khác"]

prefill = st.session_state.pop("nh_prefill", None)
if prefill:
    st.session_state["nh_draft"] = prefill
    st.session_state.pop("nh_edit_id", None)
edit_id = st.session_state.get("nh_edit_id")
draft = (query_one("SELECT * FROM nh_tinh_huong WHERE id=?", (edit_id,)) if edit_id
         else st.session_state.get("nh_draft", {})) or {}

tab_form, tab_list, tab_excel, tab_top = st.tabs(
    ["📝 Biên soạn", "📋 Danh sách & rà soát", "📥 Nhập từ Excel", "👍 Thường gặp (web CSKH)"])

with tab_form:
    if edit_id:
        st.info(f"Đang sửa tình huống #{edit_id}")
    elif draft.get("hd_bai_id"):
        st.info(f"Biên soạn từ bài hỏi-đáp #{draft['hd_bai_id']}")
    nv_list, vb_opts = danh_muc("nghiep_vu"), van_ban_options()
    vb_keys = list(vb_opts)
    with st.form(f"nh_form_{edit_id or 'new'}_{draft.get('hd_bai_id', '')}"):
        cau_hoi = st.text_area("Câu hỏi *", value=draft.get("cau_hoi", ""), height=90)
        c1, c2, c3 = st.columns(3)
        nghiep_vu = c1.selectbox("Nghiệp vụ", nv_list,
                                 index=nv_list.index(draft["nghiep_vu"]) if draft.get("nghiep_vu") in nv_list else 0)
        tu_goi_y = c2.text_input("Từ gợi ý", value=draft.get("tu_goi_y", ""))
        nguon = c3.selectbox("Nguồn tình huống", NGUON,
                             index=NGUON.index(draft["nguon"]) if draft.get("nguon") in NGUON else 0)
        tra_loi = st.text_area("Câu trả lời", value=draft.get("tra_loi", "") or "", height=200)
        c4, c5 = st.columns(2)
        nguon_tl = c4.text_input("Nguồn tài liệu (điều, khoản...)", value=draft.get("nguon_tai_lieu", ""))
        van_ban_id = c5.selectbox("Văn bản nguồn", vb_keys, format_func=vb_opts.get,
                                  index=vb_keys.index(draft.get("van_ban_id")) if draft.get("van_ban_id") in vb_keys else 0)
        c6, c7 = st.columns(2)
        link_wiki = c6.text_input("Link văn bản trên wiki", value=draft.get("link_wiki", ""))
        video = c7.text_input("Link video hướng dẫn (nếu có)", value=draft.get("video_link", ""))
        c8, c9, c10 = st.columns(3)
        hl_tu = c8.date_input("Hiệu lực từ", value=from_iso(draft.get("hieu_luc_tu")), format="DD/MM/YYYY")
        hl_den = c9.date_input("Hiệu lực đến", value=from_iso(draft.get("hieu_luc_den")), format="DD/MM/YYYY")
        het = c10.checkbox("Gắn tag hết hiệu lực", value=bool(draft.get("het_hieu_luc")))
        gui_tb = st.checkbox("Thông báo cho ĐTV và Điện lực", value=not edit_id)
        b1, b2 = st.columns(2)
        save = b1.form_submit_button("💾 Lưu", type="primary", use_container_width=True)
        cancel = b2.form_submit_button("Huỷ / soạn mới", use_container_width=True)

    if cancel:
        st.session_state.pop("nh_edit_id", None)
        st.session_state.pop("nh_draft", None)
        st.rerun()
    if save:
        if not cau_hoi.strip():
            st.error("Nhập câu hỏi.")
        elif hl_tu and hl_den and hl_den < hl_tu:
            st.error("Ngày hết hiệu lực phải sau ngày bắt đầu.")
        else:
            vals = (cau_hoi.strip(), tu_goi_y.strip(), nghiep_vu, tra_loi.strip(), nguon_tl.strip(), van_ban_id,
                    link_wiki.strip(), video.strip(), nguon, to_iso(hl_tu), to_iso(hl_den), int(het))
            if edit_id:
                execute("""UPDATE nh_tinh_huong SET cau_hoi=?, tu_goi_y=?, nghiep_vu=?, tra_loi=?, nguon_tai_lieu=?,
                           van_ban_id=?, link_wiki=?, video_link=?, nguon=?, hieu_luc_tu=?, hieu_luc_den=?,
                           het_hieu_luc=?, can_ra_soat=0, updated_at=? WHERE id=?""", vals + (now_str(), edit_id))
                th_id = edit_id
            else:
                th_id = execute("""INSERT INTO nh_tinh_huong(cau_hoi, tu_goi_y, nghiep_vu, tra_loi, nguon_tai_lieu,
                                   van_ban_id, link_wiki, video_link, nguon, hieu_luc_tu, hieu_luc_den, het_hieu_luc,
                                   hd_bai_id, created_by) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                                vals + (draft.get("hd_bai_id"), user["id"]))
            if gui_tb:
                notify(f"Ngân hàng tình huống: {cau_hoi.strip()[:100]}",
                       f"{'Cập nhật' if edit_id else 'Mới'} - nghiệp vụ {nghiep_vu}", "v_ngan_hang.py",
                       roles=["dtv", "dl"], nguoi_tao=user["id"], loai="thong_bao_tay")
            st.session_state.pop("nh_edit_id", None)
            st.session_state.pop("nh_draft", None)
            st.success(f"Đã lưu tình huống #{th_id}.")

with tab_list:
    f1, f2, f3, f4 = st.columns([2, 2, 1.5, 1])
    kw = f1.text_input("Từ khoá", key="nh_l_kw")
    vb_opts = van_ban_options()
    vb_f = f2.selectbox("Văn bản nguồn", list(vb_opts), key="nh_l_vb",
                        format_func=lambda k: "Tất cả" if k is None else vb_opts[k])
    hl_f = f3.multiselect("Hiệu lực", [HL_DANG, HL_SAP, HL_HET], key="nh_l_hl")
    rs = f4.checkbox("Cần rà soát", key="nh_l_rs")
    params = []
    where = [keyword_clause(["cau_hoi", "tu_goi_y", "tra_loi", "nguon_tai_lieu"], kw, params)]
    if vb_f:
        where.append("van_ban_id=?")
        params.append(vb_f)
    if rs:
        where.append("can_ra_soat=1")
    rows = query(f"SELECT * FROM nh_tinh_huong WHERE {' AND '.join(where)} "
                 "ORDER BY can_ra_soat DESC, updated_at DESC", params)
    for r in rows:
        r["hl"] = trang_thai_hieu_luc(r["hieu_luc_tu"], r["hieu_luc_den"], r["het_hieu_luc"])
    if hl_f:
        rows = [r for r in rows if r["hl"] in hl_f]
    if not rows:
        st.info("Không có tình huống.")
    else:
        df = pd.DataFrame([{"#": r["id"], "Rà soát": "⚠️" if r["can_ra_soat"] else "", "Câu hỏi": r["cau_hoi"],
                            "Nghiệp vụ": r["nghiep_vu"], "Hiệu lực": r["hl"], "Nguồn": r["nguon"],
                            "Cập nhật": fmt_dt(r["updated_at"])} for r in rows])
        ev = st.dataframe(df, hide_index=True, use_container_width=True, on_select="rerun",
                          selection_mode="single-row", key="nh_l_table")
        if ev.selection.rows:
            r = rows[ev.selection.rows[0]]
            st.markdown(f"**#{r['id']}** {r['cau_hoi']}")
            b1, b2, b3, b4 = st.columns(4)
            if b1.button("✏️ Sửa", use_container_width=True):
                st.session_state["nh_edit_id"] = r["id"]
                st.rerun()
            if b2.button("✅ Đã rà soát", use_container_width=True, disabled=not r["can_ra_soat"]):
                execute("UPDATE nh_tinh_huong SET can_ra_soat=0 WHERE id=?", (r["id"],))
                st.rerun()
            if b3.button("🏷️ Gắn tag hết hiệu lực", use_container_width=True, disabled=r["hl"] == HL_HET):
                execute("UPDATE nh_tinh_huong SET het_hieu_luc=1, can_ra_soat=0, updated_at=? WHERE id=?",
                        (now_str(), r["id"]))
                st.rerun()
            if b4.button("🗑️ Xoá", use_container_width=True):
                execute("DELETE FROM nh_binh_chon WHERE th_id=?", (r["id"],))
                execute("DELETE FROM nh_binh_luan WHERE th_id=?", (r["id"],))
                execute("DELETE FROM nh_tinh_huong WHERE id=?", (r["id"],))
                st.rerun()

with tab_excel:
    st.download_button("⬇️ Tải file mẫu", template_bytes(), "mau_tinh_huong.xlsx", key="nh_tpl")
    nguon_x = st.selectbox("Nguồn của các tình huống trong file", NGUON, index=1)
    up = st.file_uploader("Chọn file Excel/CSV theo mẫu", type=["xlsx", "csv"], key="nh_excel")
    if up:
        items, errors = read_excel_rows(up)
        for e in errors:
            st.warning(e)
        st.dataframe(pd.DataFrame(items), use_container_width=True, hide_index=True)
        if items and st.button(f"Nhập {len(items)} tình huống", type="primary"):
            with connect() as c:
                c.executemany("""INSERT INTO nh_tinh_huong(cau_hoi, tu_goi_y, nghiep_vu, tra_loi, nguon_tai_lieu,
                                 van_ban_id, link_wiki, hieu_luc_tu, hieu_luc_den, nguon, created_by)
                                 VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                              [(i.get("cau_hoi"), i.get("tu_goi_y", ""), i.get("nghiep_vu", ""), i.get("tra_loi", ""),
                                i.get("nguon_tai_lieu", ""), i.get("van_ban_id"), i.get("link_wiki", ""),
                                i.get("hieu_luc_tu"), i.get("hieu_luc_den"), nguon_x, user["id"]) for i in items])
            st.success(f"Đã nhập {len(items)} tình huống.")

with tab_top:
    st.caption("Tình huống được ĐTV/Điện lực bình chọn 'thường gặp' nhiều nhất - căn cứ đưa vào ngân hàng câu hỏi trên web CSKH.")
    rows = query("""SELECT t.cau_hoi AS "Câu hỏi", t.tra_loi AS "Câu trả lời", t.nghiep_vu AS "Nghiệp vụ",
                           COUNT(b.user_id) AS "Lượt bình chọn"
                    FROM nh_tinh_huong t JOIN nh_binh_chon b ON b.th_id=t.id
                    WHERE t.het_hieu_luc=0 GROUP BY t.id ORDER BY "Lượt bình chọn" DESC LIMIT 100""")
    df = pd.DataFrame(rows)
    if df.empty:
        st.info("Chưa có bình chọn.")
    else:
        st.dataframe(df, hide_index=True, use_container_width=True)
        buf = io.BytesIO()
        df.to_excel(buf, index=False)
        st.download_button("⬇️ Xuất Excel cho web CSKH", buf.getvalue(), "tinh_huong_thuong_gap.xlsx")
