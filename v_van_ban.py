# -*- coding: utf-8 -*-
"""
VĂN BẢN, HƯỚNG DẪN (Cẩm nang CSKH)
- Mọi user: tra cứu theo số hiệu, tên, NỘI DUNG văn bản; lọc cấp ban hành, nghiệp vụ, hiệu lực
- User quản lý: upload văn bản; khai báo văn bản thay thế / sửa đổi / bổ sung
  => tự đánh dấu "cần rà soát" mọi tình huống, bài hỏi-đáp, kiến thức dựa trên văn bản cũ
  => thông báo đến người dùng
"""
from datetime import timedelta

import streamlit as st

from auth import current_user, is_manager
from common import (badge_hieu_luc, extract_text, fmt_dt, notify, page_header,
                    save_upload, to_iso, van_ban_options)
from db import (DATA_DIR, HL_DANG, HL_HET, HL_SAP, bo_dau, connect, danh_muc,
                keyword_clause, query, query_one, trang_thai_hieu_luc)

user = current_user()
manager = is_manager()
page_header("📄 Văn bản, hướng dẫn", "Văn bản QPPL, EVN, EVNCPC, Công ty Điện lực - tra cứu theo nội dung và hiệu lực")

CAP = ["QPPL", "EVN", "EVNCPC", "Công ty Điện lực", "TT CSKH"]
QUAN_HE = {"": "Văn bản mới (độc lập)", "thay_the": "Thay thế văn bản", "sua_doi": "Sửa đổi văn bản",
           "bo_sung": "Bổ sung văn bản"}

tabs = ["🔎 Tra cứu"] + (["➕ Thêm văn bản", "⚠️ Rà soát nội dung"] if manager else [])
tab_objs = st.tabs(tabs)


def snippets(text, kw, n=4, width=110):
    words = [w for w in bo_dau(kw).split() if len(w) > 1]
    if not words or not text:
        return []
    out = []
    for line in text.splitlines():
        if all(w in bo_dau(line) for w in words):
            out.append(line.strip()[:width * 2])
            if len(out) >= n:
                break
    return out


with tab_objs[0]:
    f1, f2, f3, f4 = st.columns([3, 1.5, 2, 2])
    kw = f1.text_input("Từ khoá (số hiệu, tên, nội dung)", placeholder="VD: 05/2024 hoặc 'bậc thang sinh hoạt'")
    cap = f2.selectbox("Cấp ban hành", ["Tất cả"] + CAP)
    nv = f3.selectbox("Nghiệp vụ", ["Tất cả"] + danh_muc("nghiep_vu"), key="vb_nv")
    hl = f4.multiselect("Hiệu lực", [HL_DANG, HL_SAP, HL_HET], default=[HL_DANG, HL_SAP], key="vb_hl")
    params = []
    where = [keyword_clause(["so_hieu", "ten", "noi_dung"], kw, params)]
    if cap != "Tất cả":
        where.append("cap=?")
        params.append(cap)
    if nv != "Tất cả":
        where.append("nghiep_vu=?")
        params.append(nv)
    rows = query(f"SELECT * FROM van_ban WHERE {' AND '.join(where)} "
                 "ORDER BY COALESCE(hieu_luc_tu, ngay_ban_hanh) DESC LIMIT 200", params)
    for r in rows:
        r["hl"] = trang_thai_hieu_luc(r["hieu_luc_tu"], r["hieu_luc_den"])
    rows = [r for r in rows if r["hl"] in hl]
    st.caption(f"{len(rows)} văn bản")
    for v in rows:
        with st.expander(f"{v['so_hieu']} — {v['ten']}"):
            st.markdown(f"{badge_hieu_luc(v['hl'])} :gray-badge[{v['cap']}] :gray-badge[Áp dụng: {v['ap_dung']}]"
                        + (f" :gray-badge[{v['nghiep_vu']}]" if v["nghiep_vu"] else ""))
            st.caption(f"Ban hành {fmt_dt(v['ngay_ban_hanh'])} · Hiệu lực {fmt_dt(v['hieu_luc_tu']) or '...'}"
                       f" → {fmt_dt(v['hieu_luc_den']) or 'nay'}")
            # Lược đồ văn bản
            if v["van_ban_goc_id"]:
                goc = query_one("SELECT so_hieu, ten FROM van_ban WHERE id=?", (v["van_ban_goc_id"],))
                if goc:
                    st.markdown(f"↩️ {QUAN_HE.get(v['quan_he'], '')}: **{goc['so_hieu']}** - {goc['ten']}")
            for con in query("SELECT so_hieu, ten, quan_he FROM van_ban WHERE van_ban_goc_id=?", (v["id"],)):
                verb = {"thay_the": "Bị thay thế bởi", "sua_doi": "Được sửa đổi bởi",
                        "bo_sung": "Được bổ sung bởi"}.get(con["quan_he"], "Liên quan")
                st.markdown(f"↪️ {verb}: **{con['so_hieu']}** - {con['ten']}")
            for s in snippets(v["noi_dung"], kw):
                st.markdown(f"> …{s}…")
            n_lk = query_one("""SELECT (SELECT COUNT(*) FROM nh_tinh_huong WHERE van_ban_id=?) +
                                       (SELECT COUNT(*) FROM hd_bai WHERE van_ban_id=? AND an=0) +
                                       (SELECT COUNT(*) FROM kt_bai WHERE van_ban_id=?) n""",
                             (v["id"],) * 3)["n"]
            st.caption(f"{n_lk} tình huống / kiến thức dẫn chiếu văn bản này")
            c1, c2 = st.columns(2)
            if v["file_path"] and (DATA_DIR / v["file_path"]).exists():
                p = DATA_DIR / v["file_path"]
                c1.download_button("⬇️ Tải văn bản", p.read_bytes(), p.name.split("_", 1)[-1], key=f"vbdl_{v['id']}")
            if v["link_wiki"]:
                c2.link_button("Mở trên wiki", v["link_wiki"])

if manager:
    with tab_objs[1]:
        vb_opts = van_ban_options()
        with st.form("them_vb", clear_on_submit=True):
            c1, c2 = st.columns([1, 2])
            so_hieu = c1.text_input("Số hiệu *", placeholder="VD: 05/2024/TT-BCT")
            ten = c2.text_input("Trích yếu / tên văn bản *")
            c3, c4, c5 = st.columns(3)
            cap = c3.selectbox("Cấp ban hành", CAP)
            ap_dung = c4.selectbox("Đơn vị áp dụng", ["Tất cả"] + danh_muc("don_vi"))
            nghiep_vu = c5.selectbox("Nghiệp vụ", [""] + danh_muc("nghiep_vu"))
            c6, c7, c8 = st.columns(3)
            ngay_bh = c6.date_input("Ngày ban hành", value=None, format="DD/MM/YYYY")
            hl_tu = c7.date_input("Hiệu lực từ", value=None, format="DD/MM/YYYY")
            hl_den = c8.date_input("Hiệu lực đến (nếu có)", value=None, format="DD/MM/YYYY")
            c9, c10 = st.columns(2)
            quan_he = c9.selectbox("Quan hệ với văn bản khác", list(QUAN_HE), format_func=QUAN_HE.get)
            goc_id = c10.selectbox("Văn bản bị thay thế / sửa đổi / bổ sung", list(vb_opts), format_func=vb_opts.get)
            file = st.file_uploader("File văn bản (docx, pdf, txt) - nội dung sẽ được trích để tìm kiếm",
                                    type=["docx", "pdf", "txt"])
            link_wiki = st.text_input("Link trên wiki / eoffice")
            gui_tb = st.checkbox("Thông báo văn bản mới cho ĐTV và Điện lực", value=True)
            ok = st.form_submit_button("💾 Lưu văn bản", type="primary")

        if ok:
            if not so_hieu.strip() or not ten.strip():
                st.error("Nhập số hiệu và tên văn bản.")
            elif quan_he and not goc_id:
                st.error("Chọn văn bản bị thay thế / sửa đổi / bổ sung.")
            else:
                path = save_upload(file, "van_ban")
                text = extract_text(DATA_DIR / path) if path else ""
                with connect() as c:
                    vb_id = c.execute("""INSERT INTO van_ban(so_hieu, ten, cap, ap_dung, nghiep_vu, ngay_ban_hanh,
                                         hieu_luc_tu, hieu_luc_den, quan_he, van_ban_goc_id, file_path, noi_dung,
                                         link_wiki, created_by) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                                      (so_hieu.strip(), ten.strip(), cap, ap_dung, nghiep_vu, to_iso(ngay_bh),
                                       to_iso(hl_tu), to_iso(hl_den), quan_he, goc_id if quan_he else None,
                                       path, text, link_wiki.strip(), user["id"])).lastrowid
                    n_rs = 0
                    if quan_he and goc_id:
                        if quan_he == "thay_the" and hl_tu:
                            c.execute("""UPDATE van_ban SET hieu_luc_den=? WHERE id=?
                                         AND (hieu_luc_den IS NULL OR hieu_luc_den >= ?)""",
                                      ((hl_tu - timedelta(days=1)).isoformat(), goc_id, hl_tu.isoformat()))
                        for tbl in ("nh_tinh_huong", "hd_bai", "kt_bai"):
                            n_rs += c.execute(f"UPDATE {tbl} SET can_ra_soat=1 WHERE van_ban_id=?", (goc_id,)).rowcount
                if n_rs:
                    notify(f"Cần rà soát {n_rs} nội dung do văn bản {so_hieu.strip()} {QUAN_HE[quan_he].lower()}",
                           vb_opts.get(goc_id, ""), "v_van_ban.py", roles=["quan_ly"], loai="ra_soat")
                if gui_tb:
                    notify(f"Văn bản mới: {so_hieu.strip()} - {ten.strip()[:100]}",
                           f"{QUAN_HE[quan_he]} {vb_opts.get(goc_id, '') if quan_he else ''}".strip(),
                           "v_van_ban.py", roles=["dtv", "dl", "quan_ly"], nguoi_tao=user["id"], loai="van_ban")
                st.success(f"Đã lưu văn bản #{vb_id}. Trích được {len(text):,} ký tự nội dung."
                           + (f" Đã đánh dấu {n_rs} nội dung cần rà soát." if n_rs else ""))

    with tab_objs[2]:
        st.caption("Nội dung dẫn chiếu văn bản đã bị thay thế / sửa đổi / bổ sung. Mở trang soạn thảo, lọc 'Cần rà soát' để xử lý.")
        c1, c2, c3 = st.columns(3)
        n1 = query_one("SELECT COUNT(*) n FROM nh_tinh_huong WHERE can_ra_soat=1")["n"]
        n2 = query_one("SELECT COUNT(*) n FROM hd_bai WHERE can_ra_soat=1 AND an=0")["n"]
        n3 = query_one("SELECT COUNT(*) n FROM kt_bai WHERE can_ra_soat=1")["n"]
        c1.metric("Ngân hàng tình huống", n1)
        c1.page_link("v_nh_soan_thao.py", label="Mở soạn thảo tình huống", icon="🗂️")
        c2.metric("Chuyên mục hỏi-đáp", n2)
        c2.page_link("v_hd_soan_thao.py", label="Mở soạn thảo hỏi-đáp", icon="✍️")
        c3.metric("Kiến thức tổng hợp", n3)
        c3.page_link("v_kien_thuc.py", label="Mở kiến thức tổng hợp", icon="🧭")
        rows = query("""SELECT 'Tình huống' AS loai, t.cau_hoi AS noi_dung, v.so_hieu FROM nh_tinh_huong t
                        LEFT JOIN van_ban v ON v.id=t.van_ban_id WHERE t.can_ra_soat=1
                        UNION ALL SELECT 'Hỏi-đáp', b.cau_hoi, v.so_hieu FROM hd_bai b
                        LEFT JOIN van_ban v ON v.id=b.van_ban_id WHERE b.can_ra_soat=1 AND b.an=0
                        UNION ALL SELECT 'Kiến thức', k.tieu_de, v.so_hieu FROM kt_bai k
                        LEFT JOIN van_ban v ON v.id=k.van_ban_id WHERE k.can_ra_soat=1""")
        if rows:
            st.dataframe([{"Loại": r["loai"], "Nội dung": r["noi_dung"], "Văn bản nguồn cũ": r["so_hieu"]}
                          for r in rows], hide_index=True, width="stretch")
