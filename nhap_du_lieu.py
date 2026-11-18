# -*- coding: utf-8 -*-
"""
NHẬP DỮ LIỆU HÀNG LOẠT từ 1 file Excel gồm các sheet (có sheet nào nhập sheet đó):
  VanBan     : Số hiệu*, Tên văn bản*, Cấp ban hành, Đơn vị áp dụng, Nghiệp vụ, Ngày ban hành,
               Hiệu lực từ, Hiệu lực đến, Quan hệ (Thay thế/Sửa đổi/Bổ sung), Số hiệu văn bản gốc, Link, Nội dung tóm tắt
  KienThuc   : Tiêu đề*, Nghiệp vụ, Đơn vị áp dụng, Nội dung*, Số hiệu văn bản, Hiệu lực từ, Hiệu lực đến
  TinhHuong  : Câu hỏi*, Từ gợi ý, Nghiệp vụ, Câu trả lời, Nguồn tài liệu, Số hiệu văn bản, Link wiki,
               Hiệu lực từ, Hiệu lực đến, Nguồn tình huống, Link video
Thứ tự nhập: VanBan -> KienThuc -> TinhHuong (để liên kết đúng số hiệu văn bản).
Mục đã có (trùng số hiệu / tiêu đề + ngày hiệu lực / câu hỏi) được BỎ QUA => nhập lại nhiều lần không bị trùng.

Dùng trong chương trình: trang "Nhập dữ liệu" (User quản lý).
Dùng dòng lệnh:          python nhap_du_lieu.py <file.xlsx> [--thu]   (--thu: chỉ kiểm tra, không ghi)
"""
import io
import re
import sys
import unicodedata
from datetime import date, datetime, timedelta

import openpyxl  # chỉ dùng openpyxl (thuần Python) - không cần pandas

from db import bo_dau, connect, init_db


def norm_header(h):
    h = unicodedata.normalize("NFD", str(h or "").strip().lower().replace("đ", "d"))
    h = "".join(c for c in h if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", "_", h).strip("_")


def _parse_date(s):
    s = (s or "").strip()[:10]
    if not s:
        return None
    m = re.match(r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})", s)
    if m:
        return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
    return s if re.match(r"\d{4}-\d{2}-\d{2}", s) else None

SHEETS = {
    "van_ban": ["VanBan", "Van ban", "Văn bản"],
    "kien_thuc": ["KienThuc", "Kien thuc", "Kiến thức"],
    "tinh_huong": ["TinhHuong", "Tinh huong", "Tình huống"],
}

COLS = {
    "van_ban": {
        "so_hieu": ["so_hieu"], "ten": ["ten_van_ban", "ten", "trich_yeu"], "cap": ["cap_ban_hanh", "cap"],
        "ap_dung": ["don_vi_ap_dung", "ap_dung"], "nghiep_vu": ["nghiep_vu"], "ngay_ban_hanh": ["ngay_ban_hanh"],
        "hieu_luc_tu": ["hieu_luc_tu"], "hieu_luc_den": ["hieu_luc_den"], "quan_he": ["quan_he"],
        "so_hieu_goc": ["so_hieu_van_ban_goc", "van_ban_goc"], "link_wiki": ["link", "link_wiki"],
        "noi_dung": ["noi_dung_tom_tat", "noi_dung"],
    },
    "kien_thuc": {
        "tieu_de": ["tieu_de"], "nghiep_vu": ["nghiep_vu"], "ap_dung": ["don_vi_ap_dung", "ap_dung"],
        "noi_dung": ["noi_dung", "noi_dung_markdown"], "so_hieu": ["so_hieu_van_ban", "so_hieu"],
        "hieu_luc_tu": ["hieu_luc_tu"], "hieu_luc_den": ["hieu_luc_den"],
    },
    "tinh_huong": {
        "cau_hoi": ["cau_hoi", "tinh_huong"], "tu_goi_y": ["tu_goi_y", "tu_khoa"], "nghiep_vu": ["nghiep_vu"],
        "tra_loi": ["cau_tra_loi", "tra_loi"], "nguon_tai_lieu": ["nguon_tai_lieu"],
        "so_hieu": ["so_hieu_van_ban", "so_hieu"], "link_wiki": ["link_wiki"], "hieu_luc_tu": ["hieu_luc_tu"],
        "hieu_luc_den": ["hieu_luc_den"], "nguon": ["nguon_tinh_huong", "nguon"], "video_link": ["link_video"],
    },
}
REQUIRED = {"van_ban": ["so_hieu", "ten"], "kien_thuc": ["tieu_de", "noi_dung"], "tinh_huong": ["cau_hoi"]}
QUAN_HE = {"thay the": "thay_the", "sua doi": "sua_doi", "bo sung": "bo_sung"}


def _cell(v):
    if v is None:
        return ""
    if isinstance(v, datetime):
        return v.date().isoformat()
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).strip()


def read_workbook(file):
    """-> {loai: [dict]}, [lỗi]. file: đường dẫn hoặc file-like (UploadedFile)."""
    data = file.getvalue() if hasattr(file, "getvalue") else open(file, "rb").read()
    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    by_norm = {norm_header(s): s for s in wb.sheetnames}
    out, errors = {}, []
    for loai, names in SHEETS.items():
        sheet = next((by_norm[norm_header(n)] for n in names if norm_header(n) in by_norm), None)
        if not sheet:
            continue
        all_rows = list(wb[sheet].iter_rows(values_only=True))
        if not all_rows:
            continue
        header = [str(h).strip() if h is not None else f"_cot{i}" for i, h in enumerate(all_rows[0])]
        records = [dict(zip(header, row)) for row in all_rows[1:]]
        colmap = {}
        for c in header:
            h = norm_header(c).replace("_", "")
            for key, aliases in COLS[loai].items():
                if h in [a.replace("_", "") for a in aliases] and key not in colmap.values():
                    colmap[c] = key
                    break
        miss = [k for k in REQUIRED[loai] if k not in colmap.values()]
        if miss:
            errors.append(f"Sheet {sheet}: thiếu cột bắt buộc {', '.join(miss)}")
            continue
        rows = []
        for i, rec in enumerate(records, start=2):
            r = {colmap[k]: _cell(v) for k, v in rec.items() if k in colmap}
            if not any(r.get(k) for k in REQUIRED[loai]):
                continue
            if not all(r.get(k) for k in REQUIRED[loai]):
                errors.append(f"Sheet {sheet} dòng {i}: thiếu {', '.join(k for k in REQUIRED[loai] if not r.get(k))}")
                continue
            for k in ("ngay_ban_hanh", "hieu_luc_tu", "hieu_luc_den"):
                if k in r:
                    r[k] = _parse_date(r[k])
            r["_dong"] = i
            rows.append(r)
        out[loai] = rows
    if not out and not errors:
        errors.append("Không thấy sheet VanBan / KienThuc / TinhHuong trong file.")
    return out, errors


def import_data(data, user_id=None, dry_run=False):
    """Ghi vào CSDL. Trả về (thống kê, ghi chú)."""
    stats = {k: {"them": 0, "bo_qua": 0} for k in SHEETS}
    notes = []
    with connect() as c:
        def vb_id(so_hieu):
            if not so_hieu:
                return None
            r = c.execute("SELECT id FROM van_ban WHERE lower(so_hieu)=lower(?)", (so_hieu.strip(),)).fetchone()
            return r[0] if r else None

        # 1. Văn bản
        for r in data.get("van_ban", []):
            if vb_id(r["so_hieu"]):
                stats["van_ban"]["bo_qua"] += 1
                continue
            qh = QUAN_HE.get(bo_dau(r.get("quan_he", "")), "")
            goc = vb_id(r.get("so_hieu_goc")) if qh else None
            if qh and not goc:
                notes.append(f"Văn bản {r['so_hieu']}: chưa có văn bản gốc '{r.get('so_hieu_goc')}', bỏ qua quan hệ.")
                qh = ""
            c.execute("""INSERT INTO van_ban(so_hieu, ten, cap, ap_dung, nghiep_vu, ngay_ban_hanh, hieu_luc_tu,
                         hieu_luc_den, quan_he, van_ban_goc_id, noi_dung, link_wiki, created_by)
                         VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                      (r["so_hieu"], r["ten"], r.get("cap", ""), r.get("ap_dung") or "Tất cả", r.get("nghiep_vu", ""),
                       r.get("ngay_ban_hanh"), r.get("hieu_luc_tu"), r.get("hieu_luc_den"), qh, goc,
                       r.get("noi_dung", ""), r.get("link_wiki", ""), user_id))
            stats["van_ban"]["them"] += 1
            if qh == "thay_the" and goc and r.get("hieu_luc_tu"):
                den = (date.fromisoformat(r["hieu_luc_tu"]) - timedelta(days=1)).isoformat()
                c.execute("UPDATE van_ban SET hieu_luc_den=? WHERE id=? AND (hieu_luc_den IS NULL OR hieu_luc_den>?)",
                          (den, goc, den))
            if qh and goc:
                n = sum(c.execute(f"UPDATE {t} SET can_ra_soat=1 WHERE van_ban_id=?", (goc,)).rowcount
                        for t in ("nh_tinh_huong", "hd_bai", "kt_bai"))
                if n:
                    notes.append(f"Văn bản {r['so_hieu']}: đánh dấu {n} nội dung cần rà soát.")

        # 2. Kiến thức
        for r in data.get("kien_thuc", []):
            dup = c.execute("SELECT 1 FROM kt_bai WHERE tieu_de=? AND COALESCE(hieu_luc_tu,'')=?",
                            (r["tieu_de"], r.get("hieu_luc_tu") or "")).fetchone()
            if dup:
                stats["kien_thuc"]["bo_qua"] += 1
                continue
            c.execute("""INSERT INTO kt_bai(tieu_de, nghiep_vu, ap_dung, noi_dung, van_ban_id, hieu_luc_tu,
                         hieu_luc_den, created_by) VALUES (?,?,?,?,?,?,?,?)""",
                      (r["tieu_de"], r.get("nghiep_vu", ""), r.get("ap_dung") or "Tất cả", r["noi_dung"],
                       vb_id(r.get("so_hieu")), r.get("hieu_luc_tu"), r.get("hieu_luc_den"), user_id))
            stats["kien_thuc"]["them"] += 1

        # 3. Tình huống
        for r in data.get("tinh_huong", []):
            if c.execute("SELECT 1 FROM nh_tinh_huong WHERE cau_hoi=?", (r["cau_hoi"],)).fetchone():
                stats["tinh_huong"]["bo_qua"] += 1
                continue
            c.execute("""INSERT INTO nh_tinh_huong(cau_hoi, tu_goi_y, nghiep_vu, tra_loi, nguon_tai_lieu, van_ban_id,
                         link_wiki, video_link, nguon, hieu_luc_tu, hieu_luc_den, created_by)
                         VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                      (r["cau_hoi"], r.get("tu_goi_y", ""), r.get("nghiep_vu", ""), r.get("tra_loi", ""),
                       r.get("nguon_tai_lieu", ""), vb_id(r.get("so_hieu")), r.get("link_wiki", ""),
                       r.get("video_link", ""), r.get("nguon", ""), r.get("hieu_luc_tu"), r.get("hieu_luc_den"),
                       user_id))
            stats["tinh_huong"]["them"] += 1

        if dry_run:
            c.rollback()
    return stats, notes


def template_workbook():
    """File mẫu 3 sheet."""
    sheets = {
        "VanBan": ["Số hiệu", "Tên văn bản", "Cấp ban hành", "Đơn vị áp dụng", "Nghiệp vụ", "Ngày ban hành",
                   "Hiệu lực từ", "Hiệu lực đến", "Quan hệ", "Số hiệu văn bản gốc", "Link", "Nội dung tóm tắt"],
        "KienThuc": ["Tiêu đề", "Nghiệp vụ", "Đơn vị áp dụng", "Nội dung", "Số hiệu văn bản", "Hiệu lực từ",
                     "Hiệu lực đến"],
        "TinhHuong": ["Câu hỏi", "Từ gợi ý", "Nghiệp vụ", "Câu trả lời", "Nguồn tài liệu", "Số hiệu văn bản",
                      "Link wiki", "Hiệu lực từ", "Hiệu lực đến", "Nguồn tình huống", "Link video"],
    }
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for name, cols in sheets.items():
        ws = wb.create_sheet(name)
        ws.append(cols)
        for i in range(len(cols)):
            ws.column_dimensions[chr(65 + i)].width = 22
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    init_db()
    data, errs = read_workbook(sys.argv[1])
    for e in errs:
        print("[LỖI]", e)
    st_, notes = import_data(data, dry_run="--thu" in sys.argv)
    for k, v in st_.items():
        print(f"{k:11s}: thêm {v['them']}, bỏ qua (đã có) {v['bo_qua']}")
    for n in notes:
        print("-", n)
    if "--thu" in sys.argv:
        print("(chế độ thử - chưa ghi vào CSDL)")
