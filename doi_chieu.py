# -*- coding: utf-8 -*-
"""
CẬP NHẬT CÓ ĐỐI CHIẾU từ file dữ liệu gốc (Excel 3 sheet VanBan / KienThuc / TinhHuong).

  phan_tich(file)  -> so sánh file với CSDL: Thêm mới / Thay đổi / Không đổi / Không còn trong file
                      + kiểm tra tự động (lỗi, cảnh báo)
  ap_dung(...)     -> ghi các thay đổi được duyệt, lưu lịch sử từng bản ghi (để hoàn tác)
  hoan_tac(dot_id) -> trả CSDL về trước đợt cập nhật

Đối chiếu theo cột "Mã" (ổn định giữa các phiên bản file); bản ghi cũ chưa có mã thì nhận theo
số hiệu văn bản / tiêu đề + ngày hiệu lực / câu hỏi rồi gắn mã.
"""
import json
import re
from datetime import date, timedelta

from db import connect, now_str, query
from nhap_du_lieu import QUAN_HE, read_workbook, bo_dau

LOAI = {
    "van_ban": {"bang": "van_ban", "ten": "Văn bản", "nhan": "so_hieu",
                "truong": ["so_hieu", "ten", "cap", "ap_dung", "nghiep_vu", "ngay_ban_hanh", "hieu_luc_tu",
                           "hieu_luc_den", "quan_he", "so_hieu_goc", "link_wiki", "noi_dung"]},
    "kien_thuc": {"bang": "kt_bai", "ten": "Kiến thức", "nhan": "tieu_de",
                  "truong": ["tieu_de", "nghiep_vu", "ap_dung", "noi_dung", "so_hieu", "hieu_luc_tu", "hieu_luc_den"]},
    "tinh_huong": {"bang": "nh_tinh_huong", "ten": "Tình huống", "nhan": "cau_hoi",
                   "truong": ["cau_hoi", "tu_goi_y", "nghiep_vu", "tra_loi", "nguon_tai_lieu", "so_hieu", "link_wiki",
                              "hieu_luc_tu", "hieu_luc_den", "nguon", "video_link"]},
}
TEN_TRUONG = {
    "so_hieu": "Số hiệu", "ten": "Tên", "cap": "Cấp ban hành", "ap_dung": "Đơn vị áp dụng", "nghiep_vu": "Nghiệp vụ",
    "ngay_ban_hanh": "Ngày ban hành", "hieu_luc_tu": "Hiệu lực từ", "hieu_luc_den": "Hiệu lực đến",
    "quan_he": "Quan hệ", "so_hieu_goc": "Văn bản gốc", "link_wiki": "Link", "noi_dung": "Nội dung",
    "tieu_de": "Tiêu đề", "cau_hoi": "Câu hỏi", "tu_goi_y": "Từ gợi ý", "tra_loi": "Câu trả lời",
    "nguon_tai_lieu": "Nguồn tài liệu", "nguon": "Nguồn tình huống", "video_link": "Link video",
}


def _chuan(v):
    """So sánh bỏ qua khác biệt khoảng trắng cuối dòng / xuống dòng Windows."""
    if v is None:
        return ""
    s = str(v).replace("\r\n", "\n").replace("\r", "\n")
    return "\n".join(ln.rstrip() for ln in s.split("\n")).strip()


def _bo_du_lieu(ma):
    return ma.split("-")[0] if ma and "-" in ma else ""


# ------------------------------------------------------------------ đọc CSDL về dạng giống file
def _db_rows(loai):
    so_hieu = {r["id"]: r["so_hieu"] for r in query("SELECT id, so_hieu FROM van_ban")}
    rows = query(f"SELECT * FROM {LOAI[loai]['bang']}")
    out = []
    for r in rows:
        d = dict(r)
        if loai == "van_ban":
            d["so_hieu_goc"] = so_hieu.get(r["van_ban_goc_id"], "") if r["quan_he"] else ""
            d["quan_he"] = {"thay_the": "Thay thế", "sua_doi": "Sửa đổi", "bo_sung": "Bổ sung"}.get(r["quan_he"], "")
        else:
            d["so_hieu"] = so_hieu.get(r["van_ban_id"], "")
        if loai == "kien_thuc":
            d["ap_dung"] = r["ap_dung"] or "Tất cả"
        out.append(d)
    return out


def _khoa_tu_nhien(loai, r):
    if loai == "van_ban":
        return "vb|" + bo_dau(r.get("so_hieu"))
    if loai == "kien_thuc":
        return "kt|" + _chuan(r.get("tieu_de")) + "|" + (r.get("hieu_luc_tu") or "")
    return "th|" + _chuan(r.get("cau_hoi"))


def _gia_tri_file(loai, r, f):
    v = r.get(f, "")
    if f == "quan_he":
        return {"thay_the": "Thay thế", "sua_doi": "Sửa đổi", "bo_sung": "Bổ sung"}.get(
            QUAN_HE.get(bo_dau(v), ""), "")
    if f == "ap_dung":
        return v or "Tất cả"
    return v


# ------------------------------------------------------------------ phân tích
TRUONG_DOAN = {"tu_goi_y", "nghiep_vu", "nguon_tai_lieu", "cap", "ap_dung"}


def phan_tich(file, giu_o_trong=False):
    """giu_o_trong=True (file chuyển đổi tự động): ô trống không xoá giá trị đang có, và các trường
    do máy đoán (TRUONG_DOAN: từ gợi ý, nghiệp vụ...) chỉ điền khi đang trống, không ghi đè bản đã biên tập."""
    data, loi_doc = read_workbook(file)
    kq = {"data": data, "loi": [f"Đọc file: {e}" for e in loi_doc], "canh_bao": [], "loai": {},
          "giu_o_trong": giu_o_trong}
    for loai, cfg in LOAI.items():
        rows = data.get(loai)
        if rows is None:
            continue
        db = _db_rows(loai)
        theo_ma = {d["ma"]: d for d in db if d.get("ma")}
        theo_khoa = {_khoa_tu_nhien(loai, d): d for d in db}
        them, sua, giu, da_khop = [], [], [], set()
        ma_trong_file = set()
        for r in rows:
            ma = (r.get("ma") or "").strip()
            if ma:
                if ma in ma_trong_file:
                    kq["loi"].append(f"{cfg['ten']}: mã {ma} bị trùng trong file (dòng {r['_dong']}).")
                ma_trong_file.add(ma)
            cu = theo_ma.get(ma) if ma else None
            gan_ma = False
            if cu is None:
                cu = theo_khoa.get(_khoa_tu_nhien(loai, r))
                if cu is not None and cu.get("ma") and ma and cu["ma"] != ma:
                    cu = None              # đã thuộc mã khác -> coi là mục mới
                gan_ma = cu is not None and bool(ma) and not cu.get("ma")
            if cu is None:
                them.append(r)
                continue
            da_khop.add(cu["id"])
            doi = []
            for f in cfg["truong"]:
                moi = _chuan(_gia_tri_file(loai, r, f))
                old = _chuan(cu.get(f))
                if loai == "van_ban" and f == "hieu_luc_den" and not moi:
                    continue
                if giu_o_trong and (not moi or (f in TRUONG_DOAN and old)):
                    continue               # ngày hết hiệu lực tự đặt khi có văn bản thay thế
                if moi != old:
                    doi.append({"truong": f, "cu": old, "moi": moi})
            muc = {"row": r, "cu": cu, "doi": doi, "gan_ma": gan_ma}
            (sua if doi else giu).append(muc)
        # bản ghi cùng bộ dữ liệu (tiền tố mã) nhưng không còn trong file
        bo_set = {_bo_du_lieu(m) for m in ma_trong_file if _bo_du_lieu(m)}
        khong_con = [d for d in db if d["id"] not in da_khop and d.get("ma") and _bo_du_lieu(d["ma"]) in bo_set
                     and not (loai == "tinh_huong" and d.get("het_hieu_luc"))]
        if rows and not ma_trong_file:
            kq["canh_bao"].append(f"{cfg['ten']}: file không có cột Mã, đối chiếu theo nội dung "
                                  "(sửa câu hỏi / tiêu đề sẽ bị coi là mục mới).")
        kq["loai"][loai] = {"them": them, "sua": sua, "giu": giu, "khong_con": khong_con}
    loi, canh_bao = kiem_tra(data)
    kq["loi"] += loi
    kq["canh_bao"] += canh_bao
    return kq


# ------------------------------------------------------------------ kiểm tra tự động
def _so(s):
    """'1.420.500' -> 1420500 ; '-11.600' ; '+37.300' ; '2,0%' -> 2.0 ; không phải số -> None."""
    s = str(s or "").replace("*", "").replace(" ", "").strip()
    m = re.fullmatch(r"([+-]?)(\d{1,3}(?:\.\d{3})+|\d+)(?:,(\d+))?(%?)", s)
    if not m:
        return None
    v = float(m.group(2).replace(".", "") + ("." + m.group(3) if m.group(3) else ""))
    return -v if m.group(1) == "-" else v


def _bang(md):
    """Các bảng Markdown trong văn bản -> list[(header, rows)]."""
    out, cur = [], []
    for ln in (md or "").splitlines() + [""]:
        s = ln.strip()
        if s.startswith("|"):
            cur.append([c.strip() for c in s.strip("|").split("|")])
            continue
        if len(cur) >= 3:
            out.append((cur[0], [r for r in cur[2:] if len(r) == len(cur[0])]))
        cur = []
    return out


def _bac_thang(md):
    """Bậc giá sinh hoạt đầu tiên trong bảng biểu giá -> [(số kWh của bậc, đơn giá)]."""
    steps, prev_end = [], 0
    for ln in (md or "").splitlines():
        m = re.search(r"Bậc\s*\d+\s*:\s*Cho kWh\s*(?:từ\s*(\d+)\s*-\s*(\d+)|đến\s*(\d+)|từ\s*(\d+)\s*trở lên)"
                      r"\s*\|\s*([\d.]+)", ln)
        if not m:
            if steps and "Bậc" not in ln and ln.strip().startswith("|") and _so(ln.split("|")[-2]) is not None:
                break
            continue
        gia = _so(m.group(5))
        if m.group(4):
            steps.append((10 ** 9, gia))
            break
        end = int(m.group(2) or m.group(3))
        steps.append((end - prev_end, gia))
        prev_end = end
    return steps if len(steps) >= 3 else []


def _tien(kwh, steps):
    t, rest = 0, kwh
    for size, price in steps:
        use = min(rest, size)
        t += use * price
        rest -= use
        if rest <= 0:
            break
    return t


def _f(n):
    return f"{n:,.0f}".replace(",", ".")


def kiem_tra(data):
    loi, canh_bao = [], []
    vb_file = {bo_dau(r["so_hieu"]): r for r in data.get("van_ban", [])}
    vb_db = {bo_dau(r["so_hieu"]) for r in query("SELECT so_hieu FROM van_ban")}

    for loai, rows in data.items():
        ten = LOAI[loai]["ten"]
        for r in rows:
            nhan = f"{ten} dòng {r['_dong']}" + (f" ({r['ma']})" if r.get("ma") else "")
            if r.get("hieu_luc_tu") and r.get("hieu_luc_den") and r["hieu_luc_den"] < r["hieu_luc_tu"]:
                loi.append(f"{nhan}: ngày hết hiệu lực trước ngày bắt đầu.")
            sh = r.get("so_hieu") if loai != "van_ban" else r.get("so_hieu_goc")
            if sh and bo_dau(sh) not in vb_file and bo_dau(sh) not in vb_db:
                canh_bao.append(f"{nhan}: chưa có văn bản số hiệu '{sh}' (sẽ không liên kết được).")
            noi_dung = r.get("noi_dung") or r.get("tra_loi") or ""
            for header, trs in _bang(noi_dung):
                h = [bo_dau(x) for x in header]
                i_cu = next((i for i, x in enumerate(h) if re.search(r"\bcu\b", x)), None)
                i_moi = next((i for i, x in enumerate(h) if re.search(r"\bmoi\b", x)), None)
                i_cl = next((i for i, x in enumerate(h) if re.search(r"chenh lech|giam \(dong", x)), None)
                if None in (i_cu, i_moi, i_cl):
                    continue
                giam = "giam" in h[i_cl]
                for tr in trs:
                    a, b, c = _so(tr[i_cu]), _so(tr[i_moi]), _so(tr[i_cl])
                    if None in (a, b, c):
                        continue
                    dung = (a - b) if giam else (b - a)
                    if abs(dung - c) > 0.5:
                        loi.append(f"{nhan}: bảng có dòng '{tr[0]}' ghi {header[i_cl]} = {tr[i_cl]}; "
                                   f"tính lại từ giá cũ {tr[i_cu]} và giá mới {tr[i_moi]} được {_f(dung)}.")
            if loai == "van_ban" and QUAN_HE.get(bo_dau(r.get("quan_he", ""))) == "thay_the":
                goc = vb_file.get(bo_dau(r.get("so_hieu_goc", "")))
                if goc and goc.get("hieu_luc_den") and r.get("hieu_luc_tu"):
                    can = (date.fromisoformat(r["hieu_luc_tu"]) - timedelta(days=1)).isoformat()
                    if goc["hieu_luc_den"] != can:
                        canh_bao.append(f"{nhan}: văn bản gốc {goc['so_hieu']} hết hiệu lực {goc['hieu_luc_den']}, "
                                        f"không liền trước ngày văn bản mới có hiệu lực {r['hieu_luc_tu']}.")

    # Tính lại tiền điện sinh hoạt bậc thang trong các bảng "Mức sử dụng (kWh) ... giá cũ ... giá mới"
    kt = data.get("kien_thuc", [])
    bieu = [(r, _bac_thang(r["noi_dung"])) for r in kt if "biểu giá" in r["tieu_de"].lower()]
    bieu = [(r, s) for r, s in bieu if s]
    cu = next((s for r, s in bieu if r.get("hieu_luc_den")), None)
    moi = next((s for r, s in bieu if not r.get("hieu_luc_den")), None)
    if cu and moi:
        for loai in ("kien_thuc", "tinh_huong"):
            for r in data.get(loai, []):
                nhan = f"{LOAI[loai]['ten']} dòng {r['_dong']}" + (f" ({r['ma']})" if r.get("ma") else "")
                for header, trs in _bang(r.get("noi_dung") or r.get("tra_loi") or ""):
                    h = [bo_dau(x) for x in header]
                    if "kwh" not in h[0]:
                        continue
                    i_cu = next((i for i, x in enumerate(h) if "tien" in x and re.search(r"\bcu\b", x)), None)
                    i_moi = next((i for i, x in enumerate(h) if "tien" in x and re.search(r"\bmoi\b", x)), None)
                    if i_cu is None or i_moi is None:
                        continue
                    for tr in trs:
                        kwh = _so(tr[0])
                        if kwh is None:
                            continue
                        for i, steps, nhan_gia in ((i_cu, cu, "giá cũ"), (i_moi, moi, "giá mới")):
                            ghi, tinh = _so(tr[i]), _tien(int(kwh), steps)
                            if ghi is not None and abs(ghi - tinh) > 0.5:
                                loi.append(f"{nhan}: {int(kwh)} kWh theo {nhan_gia} ghi {tr[i]}; "
                                           f"tính lại theo biểu giá được {_f(tinh)}.")
    elif any(len(_bang(r.get("noi_dung"))) and "kwh" in bo_dau(r.get("noi_dung", "")) and "tien" in
             bo_dau(r.get("noi_dung", "")) for r in data.get("kien_thuc", [])):
        canh_bao.append("Không tìm thấy đủ biểu giá cũ / mới trong sheet KienThuc nên chưa tính lại được tiền điện.")
    return loi, canh_bao


# ------------------------------------------------------------------ áp dụng
def _ghi_lich_su(c, dot_id, bang, ban_ghi_id, thao_tac):
    cu = c.execute(f"SELECT * FROM {bang} WHERE id=?", (ban_ghi_id,)).fetchone()
    c.execute("INSERT INTO lich_su(dot_id, bang, ban_ghi_id, thao_tac, du_lieu_cu) VALUES (?,?,?,?,?)",
              (dot_id, bang, ban_ghi_id, thao_tac, json.dumps(dict(cu), ensure_ascii=False) if cu else None))


def _vals(loai, r, vb_id):
    if loai == "van_ban":
        qh = QUAN_HE.get(bo_dau(r.get("quan_he", "")), "")
        goc = vb_id(r.get("so_hieu_goc")) if qh else None
        return {"so_hieu": r["so_hieu"], "ten": r["ten"], "cap": r.get("cap", ""), "ap_dung": r.get("ap_dung") or "Tất cả",
                "nghiep_vu": r.get("nghiep_vu", ""), "ngay_ban_hanh": r.get("ngay_ban_hanh"),
                "hieu_luc_tu": r.get("hieu_luc_tu"), "quan_he": qh if goc else "", "van_ban_goc_id": goc,
                "link_wiki": r.get("link_wiki", ""), "noi_dung": r.get("noi_dung", ""),
                **({"hieu_luc_den": r["hieu_luc_den"]} if r.get("hieu_luc_den") else {})}
    if loai == "kien_thuc":
        return {"tieu_de": r["tieu_de"], "nghiep_vu": r.get("nghiep_vu", ""), "ap_dung": r.get("ap_dung") or "Tất cả",
                "noi_dung": r["noi_dung"], "van_ban_id": vb_id(r.get("so_hieu")),
                "hieu_luc_tu": r.get("hieu_luc_tu"), "hieu_luc_den": r.get("hieu_luc_den")}
    return {"cau_hoi": r["cau_hoi"], "tu_goi_y": r.get("tu_goi_y", ""), "nghiep_vu": r.get("nghiep_vu", ""),
            "tra_loi": r.get("tra_loi", ""), "nguon_tai_lieu": r.get("nguon_tai_lieu", ""),
            "van_ban_id": vb_id(r.get("so_hieu")), "link_wiki": r.get("link_wiki", ""),
            "video_link": r.get("video_link", ""), "nguon": r.get("nguon", ""),
            "hieu_luc_tu": r.get("hieu_luc_tu"), "hieu_luc_den": r.get("hieu_luc_den")}


def ap_dung(kq, ten_file, user_id, chon_sua=None, xu_ly_khong_con=None):
    """chon_sua: set (loai, id) được duyệt sửa (None = tất cả).
    xu_ly_khong_con: {(loai, id): 'ra_soat' | 'het_hieu_luc' | 'giu'} (mặc định 'ra_soat')."""
    xu_ly_khong_con = xu_ly_khong_con or {}
    dem = {k: {"them": 0, "sua": 0, "gan_ma": 0, "khong_con": 0} for k in LOAI}
    with connect() as c:
        dot_id = c.execute("INSERT INTO dot_cap_nhat(ten_file, bo_du_lieu, nguoi) VALUES (?,?,?)",
                           (ten_file, "", user_id)).lastrowid
        bo = set()

        def vb_id(sh):
            if not sh:
                return None
            r = c.execute("SELECT id FROM van_ban WHERE lower(so_hieu)=lower(?)", (sh.strip(),)).fetchone()
            return r[0] if r else None

        for loai in ("van_ban", "kien_thuc", "tinh_huong"):     # văn bản trước để liên kết số hiệu
            if loai not in kq["loai"]:
                continue
            bang = LOAI[loai]["bang"]
            ph = kq["loai"][loai]
            nguon = lambda r: {"ma": r.get("ma") or None, "nguon_file": ten_file,  # noqa: E731
                               "nguon_vi_tri": r.get("nguon_vi_tri", "")}
            for r in ph["them"]:
                v = {**_vals(loai, r, vb_id), **nguon(r), "created_by": user_id}
                cols = ",".join(v)
                new_id = c.execute(f"INSERT INTO {bang}({cols}) VALUES ({','.join('?' * len(v))})",
                                   list(v.values())).lastrowid
                c.execute("INSERT INTO lich_su(dot_id, bang, ban_ghi_id, thao_tac) VALUES (?,?,?,'them')",
                          (dot_id, bang, new_id))
                dem[loai]["them"] += 1
                bo.add((r.get("ma") or "").split("-")[0])
                if loai == "van_ban" and v.get("quan_he") == "thay_the" and v.get("hieu_luc_tu"):
                    den = (date.fromisoformat(v["hieu_luc_tu"]) - timedelta(days=1)).isoformat()
                    _ghi_lich_su(c, dot_id, "van_ban", v["van_ban_goc_id"], "sua")
                    c.execute("UPDATE van_ban SET hieu_luc_den=? WHERE id=? AND (hieu_luc_den IS NULL OR hieu_luc_den>?)",
                              (den, v["van_ban_goc_id"], den))
            for m in ph["sua"] + ph["giu"]:
                cu, r = m["cu"], m["row"]
                if m["doi"] and (chon_sua is None or (loai, cu["id"]) in chon_sua):
                    _ghi_lich_su(c, dot_id, bang, cu["id"], "sua")
                    v = _vals(loai, r, vb_id)
                    if kq.get("giu_o_trong"):
                        doi_f = {d["truong"] for d in m["doi"]}
                        bo = set(LOAI[loai]["truong"]) - doi_f
                        if "so_hieu" in bo:
                            bo |= {"van_ban_id"}
                        if "so_hieu_goc" in bo and "quan_he" in bo:
                            bo |= {"van_ban_goc_id"}
                        v = {k: x for k, x in v.items() if k not in bo}
                    v = {**v, **nguon(r), "updated_at": now_str()}
                    if bang in ("nh_tinh_huong", "kt_bai"):
                        v["can_ra_soat"] = 0
                    sets = ",".join(f"{k}=?" for k in v)
                    c.execute(f"UPDATE {bang} SET {sets} WHERE id=?", list(v.values()) + [cu["id"]])
                    dem[loai]["sua"] += 1
                elif m["gan_ma"] or (r.get("nguon_vi_tri") and r.get("nguon_vi_tri") != cu.get("nguon_vi_tri")):
                    _ghi_lich_su(c, dot_id, bang, cu["id"], "sua")
                    c.execute(f"UPDATE {bang} SET ma=?, nguon_file=?, nguon_vi_tri=? WHERE id=?",
                              (r.get("ma") or cu.get("ma"), ten_file, r.get("nguon_vi_tri", ""), cu["id"]))
                    dem[loai]["gan_ma"] += 1
                bo.add((r.get("ma") or "").split("-")[0])
            for d in ph["khong_con"]:
                cach = xu_ly_khong_con.get((loai, d["id"]), "ra_soat")
                if cach == "giu":
                    continue
                _ghi_lich_su(c, dot_id, bang, d["id"], cach)
                if cach == "het_hieu_luc":
                    if bang == "nh_tinh_huong":
                        c.execute("UPDATE nh_tinh_huong SET het_hieu_luc=1, updated_at=? WHERE id=?", (now_str(), d["id"]))
                    else:
                        c.execute(f"UPDATE {bang} SET hieu_luc_den=? WHERE id=?",
                                  ((date.today() - timedelta(days=1)).isoformat(), d["id"]))
                elif bang != "van_ban":
                    c.execute(f"UPDATE {bang} SET can_ra_soat=1 WHERE id=?", (d["id"],))
                dem[loai]["khong_con"] += 1
        c.execute("UPDATE dot_cap_nhat SET bo_du_lieu=?, tom_tat=? WHERE id=?",
                  (", ".join(sorted(b for b in bo if b)), json.dumps(dem, ensure_ascii=False), dot_id))
    return dot_id, dem


def hoan_tac(dot_id):
    """Trả các bản ghi về như trước đợt cập nhật (xoá mục đã thêm, khôi phục mục đã sửa)."""
    with connect() as c:
        rows = c.execute("SELECT * FROM lich_su WHERE dot_id=? ORDER BY id DESC", (dot_id,)).fetchall()
        for h in rows:
            if h["thao_tac"] == "them":
                if h["bang"] == "nh_tinh_huong":
                    c.execute("DELETE FROM nh_binh_chon WHERE th_id=?", (h["ban_ghi_id"],))
                    c.execute("DELETE FROM nh_binh_luan WHERE th_id=?", (h["ban_ghi_id"],))
                c.execute(f"DELETE FROM {h['bang']} WHERE id=?", (h["ban_ghi_id"],))
            elif h["du_lieu_cu"]:
                cu = json.loads(h["du_lieu_cu"])
                cu.pop("id", None)
                sets = ",".join(f"{k}=?" for k in cu)
                c.execute(f"UPDATE {h['bang']} SET {sets} WHERE id=?", list(cu.values()) + [h["ban_ghi_id"]])
        c.execute("UPDATE dot_cap_nhat SET hoan_tac=1 WHERE id=?", (dot_id,))
    return len(rows)
