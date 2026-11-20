# -*- coding: utf-8 -*-
"""
NHẬP / CẬP NHẬT DỮ LIỆU CÓ ĐỐI CHIẾU (User quản lý)
File gốc Excel 3 sheet (VanBan, KienThuc, TinhHuong) -> so sánh với CSDL -> quản lý xem từng thay đổi
-> duyệt -> cập nhật; lưu lịch sử từng đợt để hoàn tác.
"""
import difflib
import hashlib
import html
import io
import json
import re

import pandas as pd
import streamlit as st

from auth import require_role
from common import fmt_dt, notify, page_header
from db import query
from chuyen_doi import KIEU, chuyen, doc_file, nhan_dang, tien_to_mac_dinh, xuat_excel
from doi_chieu import LOAI, TEN_TRUONG, ap_dung, hoan_tac, phan_tich
from huong_dan import HD_NHAP_DU_LIEU, nut_huong_dan
from nhap_du_lieu import template_workbook

user = require_role("quan_ly")
page_header("📥 Nhập / cập nhật dữ liệu có đối chiếu",
            "File gốc là nguồn duy nhất: sửa số liệu trong file gốc rồi nạp lại, xem từng thay đổi trước khi duyệt")
nut_huong_dan(HD_NHAP_DU_LIEU, "hd_nhap_du_lieu")

XU_LY = {"Đánh dấu cần rà soát": "ra_soat", "Hết hiệu lực": "het_hieu_luc", "Giữ nguyên": "giu"}


def diff_html(cu, moi, ngu_canh=10):
    """Tô màu chỗ khác nhau theo từ: đỏ gạch = bỏ, xanh = thêm; đoạn giống nhau dài được rút gọn."""
    a, b = cu.split(" "), moi.split(" ")
    out = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if op == "equal":
            seg = a[i1:i2]
            if len(seg) > 2 * ngu_canh + 3:
                seg = seg[:ngu_canh] + ["…"] + seg[-ngu_canh:]
            out.append(html.escape(" ".join(seg)))
        if op in ("delete", "replace"):
            out.append("<span style='background:#fbdcdc;color:#a3191f;text-decoration:line-through'>"
                       + html.escape(" ".join(a[i1:i2])) + "</span>")
        if op in ("insert", "replace"):
            out.append("<span style='background:#d7f5dc;color:#11612a;font-weight:600'>"
                       + html.escape(" ".join(b[j1:j2])) + "</span>")
    return " ".join(out).replace("\n", "<br>")


def nhan(loai, d):
    return str(d.get(LOAI[loai]["nhan"]) or "")[:110]


tab_cn, tab_cd, tab_ls, tab_mau = st.tabs(["🔄 Cập nhật có đối chiếu", "🪄 Chuyển file Excel bất kỳ",
                                          "🕘 Lịch sử cập nhật", "📄 File mẫu"])

with tab_cd:
    if st.session_state.pop("cd_msg", None):
        st.success("Đã đưa file vừa chuyển sang tab **🔄 Cập nhật có đối chiếu** - mở tab đó để xem Thêm / Thay đổi và duyệt.")
    st.markdown("Tải file Excel **bất kỳ** (tài liệu đào tạo, bảng so sánh mới - cũ, danh mục văn bản, hỏi - đáp...). "
                "Chương trình tự nhận dạng từng sheet, chuyển sang file mẫu 3 sheet, giữ **vị trí ô gốc**, "
                "giữ **màu chữ** (xanh → đậm, đỏ → gạch ngang) và tạo **Mã** ổn định. Không cần AI.")
    upc = st.file_uploader("Chọn file Excel gốc", type=["xlsx", "xlsm"], key=f"cd_up_{st.session_state.get('dc_n', 0)}")
    if upc:
        b = upc.getvalue()
        h = hashlib.sha1(b).hexdigest()
        if st.session_state.get("cd_hash") != h:
            with st.spinner("Đang đọc cấu trúc file..."):
                shs = doc_file(b)
            st.session_state.update(cd_hash=h, cd_shs=shs, cd_nd=nhan_dang(shs), cd_cache={})
            st.session_state["cd_tt"] = tien_to_mac_dinh(upc.name)
        shs, nd = st.session_state["cd_shs"], st.session_state["cd_nd"]
        tt = st.text_input("Mã bộ dữ liệu (tiền tố của Mã)", key="cd_tt", max_chars=16,
                           help="Giữ nguyên tiền tố này cho các phiên bản sau của cùng tài liệu để đối chiếu đúng.")
        st.markdown("**Cách đọc từng sheet** - chương trình đã đoán, có thể đổi ở cột *Cách đọc*:")
        nguoc = {v: k for k, v in KIEU.items()}
        ed = st.data_editor(
            pd.DataFrame([{"Sheet": x["sheet"], "Tiêu đề": x["tieu_de"], "Kích thước": x["kich_thuoc"],
                           "Cách đọc": KIEU[x["kieu"]], "Ghi chú": x["ghi_chu"]} for x in nd]),
            hide_index=True, width="stretch", key=f"cd_ed_{h[:8]}", disabled=["Sheet", "Tiêu đề", "Kích thước", "Ghi chú"],
            column_config={"Cách đọc": st.column_config.SelectboxColumn(options=list(KIEU.values()), required=True,
                                                                         width="medium")})
        kieu = {r["Sheet"]: nguoc[r["Cách đọc"]] for r in ed.to_dict("records")}
        khoa = (tt, tuple(sorted(kieu.items())))
        cache = st.session_state["cd_cache"]
        if khoa not in cache:
            with st.spinner("Đang chuyển" + (" (có sheet nhờ AI đọc, có thể mất 1-2 phút)..." if "ai" in kieu.values() else "...")):
                cache[khoa] = chuyen(shs, kieu, tt, upc.name)
        kq = cache[khoa]
        n = {k: len(v) for k, v in kq["data"].items()}
        c1, c2, c3 = st.columns(3)
        c1.metric("Văn bản", n["van_ban"])
        c2.metric("Bài kiến thức", n["kien_thuc"])
        c3.metric("Tình huống", n["tinh_huong"])
        if kq["loi_ai"]:
            st.error("**AI ghi số liệu không có trong file gốc - phải kiểm tra:**\n\n"
                     + "\n".join(f"- {x}" for x in kq["loi_ai"]))
        if kq["canh_bao"]:
            with st.expander(f"⚠️ {len(kq['canh_bao'])} điểm cần xem lại", expanded=True):
                st.markdown("\n".join(f"- {x}" for x in kq["canh_bao"]))
        for x in kq["ghi_chu"]:
            st.caption(x)
        xem = {"van_ban": ("Văn bản", "so_hieu", "ten"), "kien_thuc": ("Kiến thức", "tieu_de", "noi_dung"),
               "tinh_huong": ("Tình huống", "cau_hoi", "tra_loi")}
        co = [k for k in xem if kq["data"][k]]
        if co:
            for t, loai in zip(st.tabs([f"{xem[k][0]} ({n[k]})" for k in co]), co):
                with t:
                    rows = kq["data"][loai]
                    st.dataframe(pd.DataFrame([{"Mã": r["ma"], "Nội dung": r[xem[loai][1]][:120],
                                                "Nghiệp vụ": r.get("nghiep_vu", ""),
                                                "Vị trí nguồn": r.get("nguon_vi_tri", "")} for r in rows]),
                                 hide_index=True, width="stretch", height=min(400, 38 + 35 * len(rows)))
                    i = st.selectbox("Xem thử 1 mục", range(len(rows)), key=f"cd_xem_{loai}",
                                     format_func=lambda j, rows=rows, loai=loai: f"{rows[j]['ma']} · {rows[j][xem[loai][1]][:80]}")
                    with st.container(border=True, height=420):
                        r = rows[i]
                        st.markdown(f"**{r[xem[loai][1]]}**")
                        if loai == "van_ban":
                            st.caption(f"{r['ten']} · hiệu lực từ {r.get('hieu_luc_tu') or '?'}")
                        st.markdown(r.get(xem[loai][2]) or "")
        b_ra = xuat_excel(kq, upc.name)
        ten_ra = re.sub(r"\.xls[xm]?$", "", upc.name, flags=re.I) + "_DA_CHUYEN.xlsx"
        c1, c2 = st.columns(2)
        c1.download_button("⬇️ Tải file đã chuyển (sửa thêm trong Excel)", b_ra, ten_ra, width="stretch")
        if c2.button("➡️ Đối chiếu & duyệt ngay", type="primary", width="stretch", disabled=not any(n.values())):
            st.session_state["cd_chuyen"] = (ten_ra, b_ra)
            for k in ("dc_hash", "dc_kq"):
                st.session_state.pop(k, None)
            st.session_state["cd_msg"] = True
            st.rerun()
        st.caption("File đã chuyển vẫn phải qua bước đối chiếu và duyệt - không ghi thẳng vào hệ thống. "
                   "Khi đối chiếu file chuyển tự động, ô trống và các trường máy đoán (nghiệp vụ, từ gợi ý...) "
                   "không ghi đè dữ liệu đã biên tập.")

with tab_mau:
    st.download_button("⬇️ Tải file mẫu (3 sheet)", template_workbook(), "mau_nhap_du_lieu.xlsx")
    st.markdown("""
- Cột **Mã** giữ cố định giữa các phiên bản file, dạng `<BỘ DỮ LIỆU>-<loại>-<số>`, ví dụ `GIA2026-TH-III.07`.
  Phần trước dấu `-` đầu tiên là **bộ dữ liệu**: mục cùng bộ mà không còn trong file mới sẽ được báo *Không còn trong file*.
- Cột **Vị trí nguồn** ghi sheet / dòng của file gốc (ví dụ `CAU HOI!B15`) để ĐTV, QA đối chiếu.
- Số liệu trong bảng nên nhập vào ô Excel hoặc bảng Markdown, **không dán dạng ảnh**, để chương trình kiểm tra được.
""")

with tab_cn:
    up = st.file_uploader("Chọn file dữ liệu gốc (Excel)", type=["xlsx"], key=f"dc_up_{st.session_state.get('dc_n', 0)}")
    nguon = (up.name, up.getvalue(), False) if up else None
    if not up and st.session_state.get("cd_chuyen"):
        ten_c, b_c = st.session_state["cd_chuyen"]
        nguon = (ten_c, b_c, True)
        c1, c2 = st.columns([5, 1])
        c1.info(f"Đang đối chiếu file **{ten_c}** vừa chuyển ở tab 🪄.")
        if c2.button("✖ Bỏ file này"):
            for k in ("cd_chuyen", "dc_hash", "dc_kq"):
                st.session_state.pop(k, None)
            st.rerun()
    if nguon:
        ten_up, b_up, tu_dong = nguon
        h = hashlib.sha1(b_up + bytes([tu_dong])).hexdigest()
        if st.session_state.get("dc_hash") != h:
            with st.spinner("Đang đối chiếu với dữ liệu hiện có..."):
                st.session_state["dc_kq"] = phan_tich(io.BytesIO(b_up), giu_o_trong=tu_dong)
            st.session_state["dc_hash"] = h
        kq = st.session_state["dc_kq"]

        # ---- kiểm tra tự động
        if kq["loi"]:
            st.error(f"**{len(kq['loi'])} lỗi cần xem lại trong file gốc:**\n\n" + "\n".join(f"- {e}" for e in kq["loi"]))
        else:
            st.success("Kiểm tra tự động: không phát hiện lỗi số liệu, ngày hiệu lực, mã trùng.")
        if kq["canh_bao"]:
            with st.expander(f"⚠️ {len(kq['canh_bao'])} cảnh báo"):
                st.markdown("\n".join(f"- {w}" for w in kq["canh_bao"]))

        # ---- tóm tắt
        tom = pd.DataFrame([{"Loại": LOAI[k]["ten"], "Thêm mới": len(v["them"]), "Thay đổi": len(v["sua"]),
                             "Không đổi": len(v["giu"]), "Không còn trong file": len(v["khong_con"])}
                            for k, v in kq["loai"].items()])
        st.dataframe(tom, hide_index=True, width="stretch")

        chon_sua, xu_ly = set(), {}
        for loai, ph in kq["loai"].items():
            ten = LOAI[loai]["ten"]
            if not (ph["them"] or ph["sua"] or ph["khong_con"]):
                continue
            st.subheader(ten)
            if ph["them"]:
                with st.expander(f"➕ Thêm mới ({len(ph['them'])})"):
                    st.dataframe(pd.DataFrame([{"Mã": r.get("ma", ""), "Nội dung": nhan(loai, r),
                                                "Vị trí nguồn": r.get("nguon_vi_tri", "")} for r in ph["them"]]),
                                 hide_index=True, width="stretch")
            if ph["sua"]:
                st.markdown(f"**✏️ Thay đổi ({len(ph['sua'])})** - bỏ tick mục chưa muốn cập nhật")
                for m in ph["sua"]:
                    cu = m["cu"]
                    with st.container(border=True):
                        ok = st.checkbox(f"**{m['row'].get('ma') or ''}** {nhan(loai, m['row'])}", value=True,
                                         key=f"dc_ok_{loai}_{cu['id']}")
                        if ok:
                            chon_sua.add((loai, cu["id"]))
                        for d in m["doi"]:
                            st.markdown(f"<div style='font-size:.9rem'><b>{TEN_TRUONG.get(d['truong'], d['truong'])}:</b> "
                                        f"{diff_html(d['cu'], d['moi'])}</div>", unsafe_allow_html=True)
            if ph["khong_con"]:
                st.markdown(f"**➖ Không còn trong file mới ({len(ph['khong_con'])})** - chọn cách xử lý")
                df = pd.DataFrame([{"id": d["id"], "Mã": d.get("ma"), "Nội dung": nhan(loai, d),
                                    "Xử lý": "Đánh dấu cần rà soát" if loai != "van_ban" else "Giữ nguyên"}
                                   for d in ph["khong_con"]])
                ed = st.data_editor(df, hide_index=True, width="stretch", key=f"dc_kc_{loai}",
                                    disabled=["id", "Mã", "Nội dung"],
                                    column_config={"id": None, "Xử lý": st.column_config.SelectboxColumn(
                                        options=list(XU_LY), required=True)})
                for r in ed.to_dict("records"):
                    xu_ly[(loai, r["id"])] = XU_LY[r["Xử lý"]]

        tong = sum(len(v["them"]) + len(v["sua"]) + len(v["khong_con"]) for v in kq["loai"].values())
        gan_ma = sum(1 for v in kq["loai"].values() for m in v["giu"] if m["gan_ma"])
        if tong == 0:
            st.info("File gốc trùng khớp với dữ liệu hiện có, không có gì cần cập nhật."
                    + (f" Sẽ gắn mã / vị trí nguồn cho {gan_ma} mục." if gan_ma else ""))
        dong_y = True
        if kq["loi"]:
            dong_y = st.checkbox("Tôi đã xem các lỗi ở trên và vẫn muốn cập nhật")
        if (tong or gan_ma) and st.button("✅ Duyệt & cập nhật", type="primary", disabled=not dong_y):
            dot_id, dem = ap_dung(kq, ten_up, user["id"], chon_sua, xu_ly)
            n_them = sum(v["them"] for v in dem.values())
            n_sua = sum(v["sua"] for v in dem.values())
            if n_them or n_sua:
                notify(f"Cập nhật dữ liệu: thêm {n_them}, thay đổi {n_sua} nội dung",
                       f"Theo file {ten_up}. Xem lại các tình huống / kiến thức liên quan.",
                       "v_ngan_hang.py", roles=["dtv", "dl"], nguoi_tao=user["id"], loai="thong_bao_tay")
            for k in ("dc_hash", "dc_kq", "cd_chuyen", "cd_hash"):
                st.session_state.pop(k, None)
            st.session_state["dc_n"] = st.session_state.get("dc_n", 0) + 1
            st.session_state["dc_done"] = (dot_id, dem)
            st.rerun()
    if st.session_state.get("dc_done"):
        dot_id, dem = st.session_state.pop("dc_done")
        st.success(f"Đã cập nhật (đợt #{dot_id}): " + " · ".join(
            f"{LOAI[k]['ten']}: thêm {v['them']}, sửa {v['sua']}, gắn mã {v['gan_ma']}, không còn {v['khong_con']}"
            for k, v in dem.items() if any(v.values())))

with tab_ls:
    dots = query("""SELECT d.*, u.full_name FROM dot_cap_nhat d LEFT JOIN users u ON u.id=d.nguoi
                    ORDER BY d.id DESC LIMIT 50""")
    if not dots:
        st.info("Chưa có đợt cập nhật nào.")
    moi_nhat = next((d["id"] for d in dots if not d["hoan_tac"]), None)
    for d in dots:
        tom = json.loads(d["tom_tat"] or "{}")
        mo_ta = " · ".join(f"{LOAI[k]['ten']}: +{v['them']} / sửa {v['sua']} / không còn {v['khong_con']}"
                           for k, v in tom.items() if any(v.values()))
        with st.container(border=True):
            st.markdown(f"**Đợt #{d['id']}** · {fmt_dt(d['created_at'])} · {d['full_name'] or ''} · `{d['ten_file']}`"
                        + (" · :red-badge[Đã hoàn tác]" if d["hoan_tac"] else ""))
            st.caption(mo_ta or "Chỉ gắn mã / vị trí nguồn")
            if d["id"] == moi_nhat:
                c1, c2 = st.columns([3, 2])
                xn = c1.checkbox("Tôi muốn trả dữ liệu về như trước đợt này", key=f"ht_{d['id']}")
                if c2.button("↩️ Hoàn tác đợt này", key=f"htb_{d['id']}", disabled=not xn):
                    n = hoan_tac(d["id"])
                    st.success(f"Đã hoàn tác {n} thao tác của đợt #{d['id']}.")
                    st.rerun()
    st.caption("Chỉ hoàn tác được đợt mới nhất chưa hoàn tác, để dữ liệu không bị lệch giữa các đợt.")
