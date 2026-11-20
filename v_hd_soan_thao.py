# -*- coding: utf-8 -*-
"""
SOẠN THẢO CHUYÊN MỤC HỎI-ĐÁP (User quản lý) - mục 2.5.2
- Biên soạn bài: câu hỏi, từ gợi ý, nghiệp vụ, câu trả lời, nguồn tài liệu, link văn bản trên wiki
- Tự điền sẵn khi bấm "Cập nhật chuyên mục hỏi-đáp" từ trang Quản lý
- Danh sách để rà soát khi văn bản nguồn bị thay thế / sửa đổi; chuyển vào Ngân hàng tình huống
- Nhập hàng loạt từ file Excel mẫu
"""
import pandas as pd
import streamlit as st

from auth import require_role
from common import (fmt_dt, notify, page_header, read_excel_rows, save_uploads,
                    show_attachments, template_bytes, user_map, van_ban_options)
from db import connect, danh_muc, execute, keyword_clause, now_str, query, query_one

user = require_role("quan_ly")
names = user_map()
page_header("✍️ Soạn thảo chuyên mục hỏi-đáp")

prefill = st.session_state.pop("hd_prefill", None)
if prefill:
    st.session_state["hd_draft"] = prefill
    st.session_state.pop("hd_edit_id", None)
edit_id = st.session_state.get("hd_edit_id")
draft = query_one("SELECT * FROM hd_bai WHERE id=?", (edit_id,)) if edit_id else st.session_state.get("hd_draft", {})
draft = draft or {}

tab_form, tab_list, tab_excel = st.tabs(["📝 Biên soạn", "📋 Danh sách & rà soát", "📥 Nhập từ Excel"])

with tab_form:
    if edit_id:
        st.info(f"Đang sửa bài #{edit_id}")
    elif draft.get("de_xuat_id"):
        st.info(f"Biên soạn từ câu hỏi #{draft['de_xuat_id']} của {names.get(draft.get('nguoi_gui'), '')}")
    nv_list = danh_muc("nghiep_vu")
    vb_opts = van_ban_options()
    form_key = f"hd_form_{edit_id or 'new'}_{draft.get('de_xuat_id', '')}"
    with st.form(form_key):
        cau_hoi = st.text_area("Câu hỏi / tình huống *", value=draft.get("cau_hoi", ""), height=100)
        c1, c2 = st.columns(2)
        nghiep_vu = c1.selectbox("Nghiệp vụ", nv_list,
                                 index=nv_list.index(draft["nghiep_vu"]) if draft.get("nghiep_vu") in nv_list else 0)
        tu_goi_y = c2.text_input("Từ gợi ý (cách nhau dấu phẩy)", value=draft.get("tu_goi_y", ""))
        tra_loi = st.text_area("Câu trả lời", value=draft.get("tra_loi", "") or "", height=200,
                               help="Hỗ trợ Markdown: **in đậm**, gạch đầu dòng '- ', bảng...")
        c3, c4 = st.columns(2)
        nguon = c3.text_input("Nguồn tài liệu (điều, khoản...)", value=draft.get("nguon_tai_lieu", ""))
        vb_keys = list(vb_opts)
        van_ban_id = c4.selectbox("Văn bản nguồn (để rà soát khi thay thế)", vb_keys, format_func=vb_opts.get,
                                  index=vb_keys.index(draft.get("van_ban_id")) if draft.get("van_ban_id") in vb_keys else 0)
        link_wiki = st.text_input("Đường link văn bản trên wiki", value=draft.get("link_wiki", ""))
        old_files = draft.get("file_dinh_kem", "") or ""
        if old_files:
            st.caption(f"Đã có {len(old_files.split(';'))} file đính kèm (giữ nguyên, có thể thêm file).")
        files = st.file_uploader("Thêm file đính kèm", accept_multiple_files=True)
        gui_tb = st.checkbox("Gửi thông báo cho ĐTV về tình huống này", value=not edit_id)
        b1, b2 = st.columns([1, 1])
        save = b1.form_submit_button("💾 Lưu & đăng", type="primary", width="stretch")
        cancel = b2.form_submit_button("Huỷ / soạn bài mới", width="stretch")

    if cancel:
        st.session_state.pop("hd_edit_id", None)
        st.session_state.pop("hd_draft", None)
        st.rerun()
    if save:
        if not cau_hoi.strip():
            st.error("Nhập câu hỏi.")
        else:
            files_all = ";".join(p for p in [old_files, save_uploads(files, "hoi_dap")] if p)
            vals = (cau_hoi.strip(), tu_goi_y.strip(), nghiep_vu, tra_loi.strip(), nguon.strip(),
                    van_ban_id, link_wiki.strip(), files_all)
            if edit_id:
                execute("""UPDATE hd_bai SET cau_hoi=?, tu_goi_y=?, nghiep_vu=?, tra_loi=?, nguon_tai_lieu=?,
                           van_ban_id=?, link_wiki=?, file_dinh_kem=?, can_ra_soat=0, updated_at=? WHERE id=?""",
                        vals + (now_str(), edit_id))
                bai_id = edit_id
            else:
                bai_id = execute("""INSERT INTO hd_bai(cau_hoi, tu_goi_y, nghiep_vu, tra_loi, nguon_tai_lieu,
                                    van_ban_id, link_wiki, file_dinh_kem, nguoi_gui, de_xuat_id, tac_gia)
                                    VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                                 vals + (draft.get("nguoi_gui"), draft.get("de_xuat_id"), user["id"]))
                if draft.get("de_xuat_id"):
                    execute("UPDATE de_xuat SET bai_id=?, trang_thai='da_phan_hoi' WHERE id=?",
                            (bai_id, draft["de_xuat_id"]))
                    notify("Câu hỏi của bạn đã được đăng lên chuyên mục hỏi-đáp", cau_hoi.strip()[:300],
                           "v_hoi_dap.py", user_ids=[draft.get("nguoi_gui")], nguoi_tao=user["id"])
            if gui_tb:
                notify(f"Tình huống mới: {cau_hoi.strip()[:100]}", f"Nghiệp vụ: {nghiep_vu}",
                       "v_hoi_dap.py", roles=["dtv"], nguoi_tao=user["id"], loai="thong_bao_tay")
            st.session_state.pop("hd_edit_id", None)
            st.session_state.pop("hd_draft", None)
            st.success(f"Đã lưu bài #{bai_id}.")

# ------------------------------------------------------------------ Danh sách & rà soát
with tab_list:
    f1, f2, f3 = st.columns([2, 2, 1])
    kw = f1.text_input("Tìm theo từ khoá / nguồn tài liệu", key="hd_list_kw")
    vb_opts = van_ban_options()
    vb_filter = f2.selectbox("Văn bản nguồn", list(vb_opts), format_func=lambda k: "Tất cả" if k is None else vb_opts[k],
                             key="hd_list_vb")
    only_review = f3.checkbox("Chỉ bài cần rà soát", key="hd_list_rs")
    params = []
    where = ["an=0", keyword_clause(["cau_hoi", "tu_goi_y", "tra_loi", "nguon_tai_lieu"], kw, params)]
    if vb_filter:
        where.append("van_ban_id=?")
        params.append(vb_filter)
    if only_review:
        where.append("can_ra_soat=1")
    rows = query(f"SELECT * FROM hd_bai WHERE {' AND '.join(where)} ORDER BY can_ra_soat DESC, updated_at DESC", params)
    df = pd.DataFrame([{"#": r["id"], "Rà soát": "⚠️" if r["can_ra_soat"] else "", "Câu hỏi": r["cau_hoi"],
                        "Nghiệp vụ": r["nghiep_vu"], "Nguồn": r["nguon_tai_lieu"],
                        "Cập nhật": fmt_dt(r["updated_at"])} for r in rows])
    if df.empty:
        st.info("Không có bài nào.")
    else:
        ev = st.dataframe(df, hide_index=True, width="stretch", on_select="rerun",
                          selection_mode="single-row", key="hd_table")
        sel = ev.selection.rows
        if sel:
            r = rows[sel[0]]
            st.markdown(f"**Bài #{r['id']}:** {r['cau_hoi']}")
            show_attachments(r["file_dinh_kem"], key_prefix=f"st{r['id']}")
            b1, b2, b3, b4 = st.columns(4)
            if b1.button("✏️ Sửa", width="stretch"):
                st.session_state["hd_edit_id"] = r["id"]
                st.rerun()
            if b2.button("✅ Đã rà soát, còn phù hợp", width="stretch", disabled=not r["can_ra_soat"]):
                execute("UPDATE hd_bai SET can_ra_soat=0 WHERE id=?", (r["id"],))
                st.rerun()
            if b3.button("📚 Chuyển vào ngân hàng tình huống", width="stretch"):
                st.session_state["nh_prefill"] = {k: r[k] for k in (
                    "cau_hoi", "tu_goi_y", "nghiep_vu", "tra_loi", "nguon_tai_lieu", "van_ban_id", "link_wiki")}
                st.session_state["nh_prefill"].update({"hd_bai_id": r["id"], "nguon": "Hỏi-đáp"})
                st.switch_page("v_nh_soan_thao.py")
            if b4.button("🗑️ Xoá (ẩn) bài", width="stretch"):
                execute("UPDATE hd_bai SET an=1, updated_at=? WHERE id=?", (now_str(), r["id"]))
                st.rerun()
        st.caption("Chọn một dòng để sửa, ẩn hoặc chuyển vào ngân hàng tình huống. "
                   "Bài sau khi chọn Sửa sẽ mở ở tab Biên soạn.")

# ------------------------------------------------------------------ Nhập Excel
with tab_excel:
    st.download_button("⬇️ Tải file mẫu", template_bytes(), "mau_tinh_huong.xlsx")
    up = st.file_uploader("Chọn file Excel/CSV theo mẫu", type=["xlsx", "csv"], key="hd_excel")
    if up:
        items, errors = read_excel_rows(up)
        for e in errors:
            st.warning(e)
        st.dataframe(pd.DataFrame(items), width="stretch", hide_index=True)
        if items and st.button(f"Nhập {len(items)} bài vào chuyên mục hỏi-đáp", type="primary"):
            with connect() as c:
                c.executemany("""INSERT INTO hd_bai(cau_hoi, tu_goi_y, nghiep_vu, tra_loi, nguon_tai_lieu,
                                 van_ban_id, link_wiki, tac_gia) VALUES (?,?,?,?,?,?,?,?)""",
                              [(i.get("cau_hoi"), i.get("tu_goi_y", ""), i.get("nghiep_vu", ""), i.get("tra_loi", ""),
                                i.get("nguon_tai_lieu", ""), i.get("van_ban_id"), i.get("link_wiki", ""), user["id"])
                               for i in items])
            st.success(f"Đã nhập {len(items)} bài.")
