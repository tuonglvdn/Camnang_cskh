# -*- coding: utf-8 -*-
"""
CHUYÊN MỤC HỎI-ĐÁP (chỉ dành cho TT CSKH) - mục 2.5.1 tài liệu Trao đổi nghiệp vụ
- Tìm tình huống theo từ khoá / nghiệp vụ
- Like (đồng ý), bình luận (bổ sung, phản biện)
- Bình luận của User quản lý = nội dung chốt (chữ đỏ), các bình luận trước được thu gọn
- Dấu ✓ = User quản lý đã đọc bình luận
- Thêm câu hỏi: nội dung, câu trả lời đề xuất, file đính kèm (ghi âm, ghi hình...)
"""
import html

import streamlit as st

from auth import current_user, is_manager, require_role
from common import (fmt_dt, notify, page_header, save_uploads, show_attachments,
                    user_map)
from db import danh_muc, execute, keyword_clause, query, query_one

user = require_role("dtv", "quan_ly")
manager = is_manager()
names = user_map()
page_header("💬 Chuyên mục hỏi-đáp", "Chia sẻ tình huống thực tế, thắc mắc nghiệp vụ và cách xử lý")

tab_xem, tab_them, tab_cua_toi = st.tabs(["📋 Xem chuyên mục", "➕ Thêm câu hỏi", "📨 Câu hỏi của tôi"])


def render_comment(c):
    tick = " ✅" if c["da_doc"] else ""
    head = f"**{html.escape(names.get(c['user_id'], '?'))}** · <span style='color:gray'>{fmt_dt(c['created_at'])}</span>{tick}"
    body = html.escape(c["noi_dung"]).replace("\n", "<br>")
    if c["la_chot"]:
        body = f"<span style='color:#d62728;font-weight:600'>📌 {body}</span>"
    st.markdown(f"{head}<br>{body}", unsafe_allow_html=True)


def render_post(b):
    with st.container(border=True):
        st.markdown(f"#### {b['cau_hoi']}")
        contributor = names.get(b["nguoi_gui"]) if b["nguoi_gui"] else None
        st.caption(" · ".join(filter(None, [
            b["nghiep_vu"], f"Đóng góp: {contributor}" if contributor else None,
            f"Cập nhật {fmt_dt(b['updated_at'])}"])))
        if b["tra_loi"]:
            st.markdown(b["tra_loi"])
        src = []
        if b["nguon_tai_lieu"]:
            src.append(f"📑 {b['nguon_tai_lieu']}")
        if b["link_wiki"]:
            src.append(f"[Xem văn bản trên wiki]({b['link_wiki']})")
        if src:
            st.caption(" · ".join(src))
        show_attachments(b["file_dinh_kem"], key_prefix=f"hd{b['id']}")

        liked = query_one("SELECT 1 x FROM hd_like WHERE bai_id=? AND user_id=?", (b["id"], user["id"]))
        col_like, col_cmt = st.columns([1, 5])
        label = f"{'💙 Đã thích' if liked else '👍 Thích'} ({b['n_like']})"
        if col_like.button(label, key=f"like_{b['id']}"):
            if liked:
                execute("DELETE FROM hd_like WHERE bai_id=? AND user_id=?", (b["id"], user["id"]))
            else:
                execute("INSERT OR IGNORE INTO hd_like(bai_id, user_id) VALUES (?,?)", (b["id"], user["id"]))
            st.rerun()

        comments = query("SELECT * FROM hd_binh_luan WHERE bai_id=? ORDER BY created_at, id", (b["id"],))
        with col_cmt.expander(f"💬 Bình luận ({len(comments)})", expanded=False):
            chot_idx = max((i for i, c in enumerate(comments) if c["la_chot"]), default=None)
            if chot_idx is not None and chot_idx > 0:
                with st.popover(f"⋯ {chot_idx} bình luận trước"):
                    for c in comments[:chot_idx]:
                        render_comment(c)
                shown = comments[chot_idx:]
            else:
                shown = comments
            for c in shown:
                render_comment(c)

            with st.form(f"cmt_form_{b['id']}", clear_on_submit=True):
                text = st.text_area("Bình luận / góp ý / phản biện", key=f"cmt_{b['id']}", height=80)
                chot = st.checkbox("Đây là nội dung chốt (chữ đỏ)", key=f"chot_{b['id']}") if manager else False
                if st.form_submit_button("Gửi bình luận") and text.strip():
                    execute("INSERT INTO hd_binh_luan(bai_id, user_id, noi_dung, la_chot, da_doc) VALUES (?,?,?,?,?)",
                            (b["id"], user["id"], text.strip(), int(chot), int(manager)))
                    if chot:
                        people = {c["user_id"] for c in comments} | ({b["nguoi_gui"]} if b["nguoi_gui"] else set())
                        notify(f"Đã có nội dung chốt: {b['cau_hoi'][:80]}", text.strip()[:300],
                               "v_hoi_dap.py", user_ids=people, nguoi_tao=user["id"], loai="hd_chot")
                    st.rerun()


# ------------------------------------------------------------------ Xem
with tab_xem:
    f1, f2, f3 = st.columns([3, 2, 1.3])
    kw = f1.text_input("Từ khoá", placeholder="VD: thuê nhà định mức (gõ không dấu cũng được)")
    nv = f2.selectbox("Nghiệp vụ", ["Tất cả"] + danh_muc("nghiep_vu"))
    sort = f3.selectbox("Sắp xếp", ["Mới nhất", "Nhiều thích nhất", "Nhiều bình luận"])

    params = []
    where = ["b.an = 0", keyword_clause(["b.cau_hoi", "b.tu_goi_y", "b.tra_loi"], kw, params)]
    if nv != "Tất cả":
        where.append("b.nghiep_vu = ?")
        params.append(nv)
    order = {"Mới nhất": "b.updated_at DESC", "Nhiều thích nhất": "n_like DESC",
             "Nhiều bình luận": "n_cmt DESC"}[sort]
    posts = query(f"""
        SELECT b.*,
               (SELECT COUNT(*) FROM hd_like l WHERE l.bai_id=b.id) AS n_like,
               (SELECT COUNT(*) FROM hd_binh_luan c WHERE c.bai_id=b.id) AS n_cmt
        FROM hd_bai b WHERE {' AND '.join(where)}
        ORDER BY {order} LIMIT 200""", params)

    st.caption(f"Tìm thấy {len(posts)} tình huống")
    per_page = 10
    pages = max(1, (len(posts) + per_page - 1) // per_page)
    page = st.number_input("Trang", 1, pages, 1, key="hd_page") if pages > 1 else 1
    for b in posts[(page - 1) * per_page: page * per_page]:
        render_post(b)

# ------------------------------------------------------------------ Thêm câu hỏi
with tab_them:
    st.markdown("Gửi thắc mắc hoặc chia sẻ tình huống thực tế. User quản lý sẽ giải đáp, "
                "biên soạn lại và đăng lên chuyên mục; bạn sẽ nhận được thông báo.")
    with st.form("them_cau_hoi", clear_on_submit=True):
        nv_new = st.selectbox("Nghiệp vụ", danh_muc("nghiep_vu"))
        q = st.text_area("Câu hỏi / tình huống *", height=120)
        a = st.text_area("Câu trả lời đề xuất (nếu có)", height=120)
        files = st.file_uploader("File đính kèm (ghi âm cuộc gọi, video diễn giải, văn bản...)",
                                 accept_multiple_files=True,
                                 type=["mp3", "wav", "m4a", "mp4", "webm", "pdf", "docx", "xlsx", "png", "jpg"])
        if st.form_submit_button("Gửi câu hỏi", type="primary"):
            if not q.strip():
                st.error("Vui lòng nhập nội dung câu hỏi.")
            else:
                paths = save_uploads(files, "de_xuat")
                dx_id = execute("INSERT INTO de_xuat(nguoi_gui, cau_hoi, tra_loi_de_xuat, nghiep_vu, file_dinh_kem) "
                                "VALUES (?,?,?,?,?)", (user["id"], q.strip(), a.strip(), nv_new, paths))
                notify(f"Câu hỏi mới từ {user['full_name']}", q.strip()[:300], "v_hd_quan_ly.py",
                       roles=["quan_ly"], nguoi_tao=user["id"], loai="de_xuat")
                st.success(f"Đã gửi câu hỏi #{dx_id}. Cảm ơn bạn đã đóng góp!")

# ------------------------------------------------------------------ Câu hỏi của tôi
with tab_cua_toi:
    mine = query("SELECT * FROM de_xuat WHERE nguoi_gui=? ORDER BY created_at DESC", (user["id"],))
    if not mine:
        st.info("Bạn chưa gửi câu hỏi nào.")
    for d in mine:
        with st.container(border=True):
            status = ":green-badge[Đã phản hồi]" if d["trang_thai"] == "da_phan_hoi" else ":orange-badge[Chờ xử lý]"
            tags = " ".join(t for t, on in [(":violet-badge[Câu hỏi hay]", d["cau_hoi_hay"]),
                                            (":blue-badge[Trả lời chuẩn]", d["tl_chuan"]),
                                            (":gray-badge[Trả lời tương đối chuẩn]", d["tl_tuong_doi"])] if on)
            st.markdown(f"{status} {tags}  \n**{d['cau_hoi']}**")
            st.caption(f"#{d['id']} · {d['nghiep_vu']} · gửi {fmt_dt(d['created_at'])}")
            if d["tra_loi_de_xuat"]:
                st.markdown(f"*Đề xuất của bạn:* {d['tra_loi_de_xuat']}")
            if d["phan_hoi"]:
                st.info(f"**Phản hồi ({names.get(d['nguoi_phan_hoi'], '')}, {fmt_dt(d['ngay_phan_hoi'])}):** "
                        f"{d['phan_hoi']}")
            if d["bai_id"]:
                st.caption("✅ Đã được biên soạn và đăng lên chuyên mục hỏi-đáp.")
