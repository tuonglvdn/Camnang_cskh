# -*- coding: utf-8 -*-
"""
NGÂN HÀNG TÌNH HUỐNG - XEM (mọi user: ĐTV, Điện lực, quản lý) - mục 2.2.2
- Tìm theo từ khoá (câu hỏi / từ gợi ý), nghiệp vụ, hiệu lực (Hết / Đang / Sắp có hiệu lực)
- Chọn tình huống -> "Thêm" để xem đầy đủ; xem cùng lúc nhiều tình huống của các lần tìm khác nhau
- Bình chọn "tình huống thường gặp" và bình luận
"""
import html

import pandas as pd
import streamlit as st

from auth import current_user
from common import badge_hieu_luc, fmt_dt, page_header, user_map
from db import (HL_DANG, HL_HET, HL_SAP, danh_muc, execute, keyword_clause, query,
                query_one, trang_thai_hieu_luc)

user = current_user()
names = user_map()
page_header("📚 Ngân hàng tình huống", "Tình huống thường gặp do P.CSKH biên soạn từ hỏi-đáp, QA, hướng dẫn TCT, góp ý Điện lực")

basket = st.session_state.setdefault("nh_basket", [])

f1, f2, f3 = st.columns([3, 2, 3])
kw = f1.text_input("Từ khoá", placeholder="VD: đổi giá, công tơ, sang tên hợp đồng...")
nv = f2.selectbox("Nghiệp vụ", ["Tất cả"] + danh_muc("nghiep_vu"))
hl = f3.multiselect("Hiệu lực", [HL_DANG, HL_SAP, HL_HET], default=[HL_DANG, HL_SAP])

params = []
where = [keyword_clause(["t.cau_hoi", "t.tu_goi_y"], kw, params)]
if nv != "Tất cả":
    where.append("t.nghiep_vu = ?")
    params.append(nv)
rows = query(f"""SELECT t.*, (SELECT COUNT(*) FROM nh_binh_chon b WHERE b.th_id=t.id) AS n_vote
                 FROM nh_tinh_huong t WHERE {' AND '.join(where)}
                 ORDER BY n_vote DESC, t.updated_at DESC LIMIT 300""", params)
for r in rows:
    r["hl"] = trang_thai_hieu_luc(r["hieu_luc_tu"], r["hieu_luc_den"], r["het_hieu_luc"])
rows = [r for r in rows if r["hl"] in hl]

st.markdown(f"**Kết quả tìm kiếm** ({len(rows)})")
if rows:
    df = pd.DataFrame([{"Câu hỏi": r["cau_hoi"], "Nghiệp vụ": r["nghiep_vu"], "Hiệu lực": r["hl"],
                        "Thường gặp": r["n_vote"]} for r in rows])
    ev = st.dataframe(df, hide_index=True, use_container_width=True, on_select="rerun",
                      selection_mode="multi-row", key="nh_table", height=min(420, 38 + 35 * len(rows)),
                      column_config={"Câu hỏi": st.column_config.TextColumn(width="large"),
                                     "Thường gặp": st.column_config.NumberColumn("👍 Thường gặp", width="small")})
    chosen = [rows[i]["id"] for i in ev.selection.rows]
    if st.button(f"➕ Thêm ({len(chosen)}) vào nội dung chi tiết", disabled=not chosen, type="primary"):
        for i in chosen:
            if i not in basket:
                basket.append(i)
        st.rerun()
else:
    st.info("Không tìm thấy tình huống phù hợp. Thử từ khoá khác hoặc hỏi Trợ lý tra cứu.")

st.divider()
h1, h2 = st.columns([4, 1])
h1.subheader(f"Nội dung chi tiết ({len(basket)})")
if basket and h2.button("Xoá tất cả", use_container_width=True):
    basket.clear()
    st.rerun()
if not basket:
    st.caption("Chọn tình huống ở bảng trên rồi bấm Thêm. Có thể tìm từ khoá khác và thêm tiếp để xem cùng lúc.")

for th_id in list(basket):
    t = query_one("SELECT * FROM nh_tinh_huong WHERE id=?", (th_id,))
    if not t:
        basket.remove(th_id)
        continue
    status = trang_thai_hieu_luc(t["hieu_luc_tu"], t["hieu_luc_den"], t["het_hieu_luc"])
    with st.container(border=True):
        top, close = st.columns([12, 1])
        top.markdown(f"{badge_hieu_luc(status)} :gray-badge[{t['nghiep_vu']}]  \n**❓ {t['cau_hoi']}**")
        if close.button("✖", key=f"close_{th_id}", help="Bỏ khỏi danh sách xem"):
            basket.remove(th_id)
            st.rerun()
        st.markdown(t["tra_loi"] or "_(chưa có câu trả lời)_")
        meta = []
        if t["hieu_luc_tu"] or t["hieu_luc_den"]:
            meta.append(f"Hiệu lực: {fmt_dt(t['hieu_luc_tu']) or '...'} → {fmt_dt(t['hieu_luc_den']) or 'nay'}")
        if t["nguon_tai_lieu"]:
            meta.append(f"📑 {t['nguon_tai_lieu']}")
        if t["link_wiki"]:
            meta.append(f"[Văn bản trên wiki]({t['link_wiki']})")
        if meta:
            st.caption(" · ".join(meta))
        if t["video_link"]:
            st.video(t["video_link"])

        voted = query_one("SELECT 1 x FROM nh_binh_chon WHERE th_id=? AND user_id=?", (th_id, user["id"]))
        n_vote = query_one("SELECT COUNT(*) n FROM nh_binh_chon WHERE th_id=?", (th_id,))["n"]
        cmts = query("SELECT * FROM nh_binh_luan WHERE th_id=? ORDER BY created_at", (th_id,))
        v, c = st.columns([1, 4])
        if v.button(f"{'✅ Đã bình chọn' if voted else '👍 Tình huống thường gặp'} ({n_vote})", key=f"vote_{th_id}"):
            if voted:
                execute("DELETE FROM nh_binh_chon WHERE th_id=? AND user_id=?", (th_id, user["id"]))
            else:
                execute("INSERT OR IGNORE INTO nh_binh_chon(th_id, user_id) VALUES (?,?)", (th_id, user["id"]))
            st.rerun()
        with c.expander(f"💬 Bình luận ({len(cmts)})"):
            for cm in cmts:
                st.markdown(f"**{html.escape(names.get(cm['user_id'], '?'))}** · "
                            f"<span style='color:gray'>{fmt_dt(cm['created_at'])}</span><br>"
                            f"{html.escape(cm['noi_dung'])}", unsafe_allow_html=True)
            with st.form(f"nhcmt_{th_id}", clear_on_submit=True):
                text = st.text_area("Góp ý", height=70, key=f"nhtxt_{th_id}")
                if st.form_submit_button("Gửi") and text.strip():
                    execute("INSERT INTO nh_binh_luan(th_id, user_id, noi_dung) VALUES (?,?,?)",
                            (th_id, user["id"], text.strip()))
                    st.rerun()
