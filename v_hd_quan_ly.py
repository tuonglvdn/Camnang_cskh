# -*- coding: utf-8 -*-
"""
QUẢN LÝ CHUYÊN MỤC HỎI-ĐÁP (User quản lý) - mục 2.5.3
- Xử lý câu hỏi ĐTV gửi: phản hồi, đánh giá (Câu hỏi hay / Trả lời chuẩn / Tương đối chuẩn)
- "Cập nhật chuyên mục hỏi-đáp": chuyển sang trang Soạn thảo, tự điền sẵn nội dung
- Theo dõi bình luận mới: tick Đã đọc, chọn cộng điểm
- Gửi thông báo và kiểm soát ĐTV đã đọc hay chưa (tương tự eoffice)
"""
import pandas as pd
import streamlit as st

from auth import require_role
from common import fmt_dt, notify, page_header, show_attachments, user_map
from db import execute, now_str, query

user = require_role("quan_ly")
names = user_map()
page_header("🛎️ Quản lý chuyên mục hỏi-đáp")

n_moi = query("SELECT COUNT(*) n FROM de_xuat WHERE trang_thai='moi'")[0]["n"]
n_bl = query("SELECT COUNT(*) n FROM hd_binh_luan WHERE da_doc=0")[0]["n"]
tab_moi, tab_da, tab_bl, tab_tb = st.tabs([
    f"📥 Câu hỏi chờ xử lý ({n_moi})", "✅ Đã xử lý", f"💬 Theo dõi bình luận ({n_bl})", "📣 Gửi thông báo"])


def handle_form(d):
    with st.form(f"xl_{d['id']}"):
        ph = st.text_area("Phản hồi cho người gửi", value=d["phan_hoi"] or "", height=100, key=f"ph_{d['id']}")
        c1, c2, c3 = st.columns(3)
        hay = c1.checkbox("Câu hỏi hay", value=bool(d["cau_hoi_hay"]), key=f"hay_{d['id']}")
        chuan = c2.checkbox("Câu trả lời chuẩn", value=bool(d["tl_chuan"]), key=f"ch_{d['id']}")
        td = c3.checkbox("Câu trả lời tương đối chuẩn", value=bool(d["tl_tuong_doi"]), key=f"td_{d['id']}")
        b1, b2 = st.columns(2)
        send = b1.form_submit_button("📤 Gửi phản hồi", type="primary", use_container_width=True)
        publish = b2.form_submit_button("✍️ Cập nhật chuyên mục hỏi-đáp", use_container_width=True)
    if send or publish:
        if chuan and td:
            st.error("Chỉ chọn một trong hai: 'Câu trả lời chuẩn' hoặc 'Tương đối chuẩn'.")
            return
        first_reply = d["trang_thai"] != "da_phan_hoi" or (ph.strip() and ph.strip() != (d["phan_hoi"] or ""))
        execute("""UPDATE de_xuat SET phan_hoi=?, cau_hoi_hay=?, tl_chuan=?, tl_tuong_doi=?,
                   trang_thai='da_phan_hoi', nguoi_phan_hoi=?, ngay_phan_hoi=? WHERE id=?""",
                (ph.strip(), int(hay), int(chuan), int(td), user["id"], now_str(), d["id"]))
        if first_reply and ph.strip():
            notify("User quản lý đã phản hồi câu hỏi của bạn", f"**{d['cau_hoi'][:200]}**\n\n{ph.strip()[:500]}",
                   "v_hoi_dap.py", user_ids=[d["nguoi_gui"]], nguoi_tao=user["id"], loai="phan_hoi")
        if publish:
            st.session_state["hd_prefill"] = {
                "de_xuat_id": d["id"], "cau_hoi": d["cau_hoi"], "nghiep_vu": d["nghiep_vu"],
                "tra_loi": ph.strip() or d["tra_loi_de_xuat"], "file_dinh_kem": d["file_dinh_kem"],
                "nguoi_gui": d["nguoi_gui"],
            }
            st.switch_page("v_hd_soan_thao.py")
        st.success("Đã lưu phản hồi.")
        st.rerun()


def show_de_xuat(d, editable=True):
    with st.container(border=True):
        st.markdown(f"**{d['cau_hoi']}**")
        st.caption(f"#{d['id']} · {names.get(d['nguoi_gui'], '?')} · {d['nghiep_vu']} · {fmt_dt(d['created_at'])}")
        if d["tra_loi_de_xuat"]:
            st.markdown(f"*Câu trả lời đề xuất:* {d['tra_loi_de_xuat']}")
        show_attachments(d["file_dinh_kem"], key_prefix=f"dx{d['id']}")
        if editable:
            handle_form(d)
        else:
            if d["phan_hoi"]:
                st.info(d["phan_hoi"])
            if d["bai_id"]:
                st.caption(f"Đã đăng thành bài #{d['bai_id']}")
            elif st.button("✍️ Đăng lên chuyên mục", key=f"pub_{d['id']}"):
                st.session_state["hd_prefill"] = {
                    "de_xuat_id": d["id"], "cau_hoi": d["cau_hoi"], "nghiep_vu": d["nghiep_vu"],
                    "tra_loi": d["phan_hoi"] or d["tra_loi_de_xuat"], "file_dinh_kem": d["file_dinh_kem"],
                    "nguoi_gui": d["nguoi_gui"]}
                st.switch_page("v_hd_soan_thao.py")


with tab_moi:
    rows = query("SELECT * FROM de_xuat WHERE trang_thai='moi' ORDER BY created_at")
    if not rows:
        st.success("Không còn câu hỏi chờ xử lý.")
    for d in rows:
        show_de_xuat(d)

with tab_da:
    rows = query("SELECT * FROM de_xuat WHERE trang_thai='da_phan_hoi' ORDER BY ngay_phan_hoi DESC LIMIT 50")
    for d in rows:
        show_de_xuat(d, editable=False)

# ------------------------------------------------------------------ Theo dõi bình luận
with tab_bl:
    rows = query("""SELECT c.id, c.created_at, c.user_id, c.noi_dung, b.cau_hoi
                    FROM hd_binh_luan c JOIN hd_bai b ON b.id = c.bai_id
                    WHERE c.da_doc = 0 ORDER BY c.created_at""")
    if not rows:
        st.success("Không có bình luận mới.")
    else:
        df = pd.DataFrame([{
            "id": r["id"], "Thời gian": fmt_dt(r["created_at"]), "Người bình luận": names.get(r["user_id"], "?"),
            "Tình huống": r["cau_hoi"][:80], "Nội dung bình luận": r["noi_dung"],
            "Đã đọc": True, "Cộng điểm (bình luận hay)": False} for r in rows])
        edited = st.data_editor(
            df, hide_index=True, use_container_width=True, key="bl_editor",
            disabled=["id", "Thời gian", "Người bình luận", "Tình huống", "Nội dung bình luận"],
            column_config={"id": None, "Nội dung bình luận": st.column_config.TextColumn(width="large")})
        if st.button("💾 Lưu (tick đã đọc & cộng điểm)", type="primary"):
            for r in edited.to_dict("records"):
                if r["Đã đọc"]:
                    execute("UPDATE hd_binh_luan SET da_doc=1, la_hay=? WHERE id=?",
                            (int(r["Cộng điểm (bình luận hay)"]), r["id"]))
            st.success("Đã cập nhật.")
            st.rerun()

# ------------------------------------------------------------------ Gửi thông báo
with tab_tb:
    posts = query("SELECT id, cau_hoi FROM hd_bai WHERE an=0 ORDER BY updated_at DESC LIMIT 100")
    post_opts = {p["id"]: p["cau_hoi"][:100] for p in posts}
    with st.form("gui_tb", clear_on_submit=True):
        tieu_de = st.text_input("Tiêu đề *", placeholder="VD: Lưu ý tình huống mới về kỳ đổi giá điện")
        noi_dung = st.text_area("Nội dung", height=100)
        lien_quan = st.multiselect("Tình huống liên quan", list(post_opts), format_func=post_opts.get)
        doi_tuong = st.radio("Gửi đến", ["Tất cả ĐTV", "ĐTV + Điện lực"], horizontal=True)
        if st.form_submit_button("📣 Gửi thông báo", type="primary"):
            if not tieu_de.strip():
                st.error("Nhập tiêu đề.")
            else:
                body = noi_dung.strip()
                if lien_quan:
                    body += "\n\n" + "\n".join(f"- {post_opts[i]}" for i in lien_quan)
                roles = ["dtv"] if doi_tuong == "Tất cả ĐTV" else ["dtv", "dl"]
                notify(tieu_de.strip(), body, "v_hoi_dap.py" if roles == ["dtv"] else "",
                       roles=roles, nguoi_tao=user["id"], loai="thong_bao_tay")
                st.success("Đã gửi thông báo.")

    st.subheader("Theo dõi tình trạng đọc")
    sent = query("""SELECT t.id, t.tieu_de, t.created_at,
                           COUNT(n.user_id) AS tong, COUNT(n.da_doc_luc) AS da_doc
                    FROM thong_bao t JOIN thong_bao_nhan n ON n.thong_bao_id = t.id
                    WHERE t.loai IN ('thong_bao_tay', 'van_ban')
                    GROUP BY t.id ORDER BY t.created_at DESC LIMIT 30""")
    for t in sent:
        pct = t["da_doc"] / t["tong"] if t["tong"] else 0
        with st.expander(f"{t['tieu_de']} — đã đọc {t['da_doc']}/{t['tong']} ({pct:.0%}) · {fmt_dt(t['created_at'])}"):
            st.progress(pct)
            chua = query("""SELECT u.full_name, u.don_vi FROM thong_bao_nhan n JOIN users u ON u.id=n.user_id
                            WHERE n.thong_bao_id=? AND n.da_doc_luc IS NULL ORDER BY u.full_name""", (t["id"],))
            if chua:
                st.markdown("**Chưa đọc:** " + ", ".join(f"{c['full_name']}" for c in chua))
                if st.button("🔁 Nhắc lại người chưa đọc", key=f"remind_{t['id']}"):
                    ids = [r["user_id"] for r in query(
                        "SELECT user_id FROM thong_bao_nhan WHERE thong_bao_id=? AND da_doc_luc IS NULL", (t["id"],))]
                    notify(f"[Nhắc] {t['tieu_de']}", "Vui lòng đọc thông báo trước đó.", user_ids=ids,
                           nguoi_tao=user["id"], loai="nhac")
                    st.success(f"Đã nhắc {len(ids)} người.")
            else:
                st.success("Tất cả đã đọc.")
