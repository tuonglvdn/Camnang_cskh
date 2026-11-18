# -*- coding: utf-8 -*-
"""Hàm dùng chung cho các trang: thông báo, file đính kèm, nhập Excel, đọc văn bản."""
import io
import re
import unicodedata
import uuid
from pathlib import Path

import pandas as pd
import streamlit as st

from db import (DATA_DIR, HL_DANG, HL_HET, HL_SAP, UPLOAD_DIR, connect, query,
                query_one)

AUDIO_EXT = {".mp3", ".wav", ".m4a", ".ogg", ".ulaw", ".alaw"}
VIDEO_EXT = {".mp4", ".webm", ".mov"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif"}

# Điểm thi đua (P.CSKH có thể chỉnh)
DIEM = {"cau_hoi_hay": 2, "tl_chuan": 3, "tl_tuong_doi": 1, "binh_luan_hay": 1, "gui_cau_hoi": 0}


# ----------------------------------------------------------------
# File đính kèm
# ----------------------------------------------------------------
def save_upload(uploaded, subdir="khac"):
    """Lưu file người dùng tải lên, trả về đường dẫn tương đối (lưu vào CSDL)."""
    if uploaded is None:
        return ""
    folder = UPLOAD_DIR / subdir
    folder.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r'[<>:"/\\|?*\s]+', "_", uploaded.name)
    name = f"{uuid.uuid4().hex[:8]}_{safe}"
    (folder / name).write_bytes(uploaded.getbuffer())
    return str((folder / name).relative_to(DATA_DIR))


def save_uploads(files, subdir="khac"):
    return ";".join(p for p in (save_upload(f, subdir) for f in (files or [])) if p)


def show_attachments(paths, key_prefix=""):
    for i, rel in enumerate([p for p in (paths or "").split(";") if p]):
        path = DATA_DIR / rel
        if not path.exists():
            st.caption(f"⚠️ Không tìm thấy file {rel}")
            continue
        ext = path.suffix.lower()
        label = path.name.split("_", 1)[-1]
        if ext in AUDIO_EXT:
            st.caption(f"🔊 {label}")
            st.audio(str(path))
        elif ext in VIDEO_EXT:
            st.video(str(path))
        elif ext in IMAGE_EXT:
            st.image(str(path), caption=label)
        else:
            st.download_button(f"📎 {label}", path.read_bytes(), file_name=label,
                               key=f"dl_{key_prefix}_{i}_{rel}")


# ----------------------------------------------------------------
# Thông báo
# ----------------------------------------------------------------
def notify(tieu_de, noi_dung="", lien_ket="", roles=None, user_ids=None, nguoi_tao=None, loai="chung"):
    """Tạo thông báo cho các vai trò (roles) hoặc danh sách user cụ thể. Trả về id."""
    with connect() as c:
        cur = c.execute("INSERT INTO thong_bao(tieu_de, noi_dung, loai, lien_ket, nguoi_tao) "
                        "VALUES (?,?,?,?,?)", (tieu_de, noi_dung, loai, lien_ket, nguoi_tao))
        tb_id = cur.lastrowid
        ids = set(user_ids or [])
        if roles:
            marks = ",".join("?" * len(roles))
            ids |= {r[0] for r in c.execute(f"SELECT id FROM users WHERE active=1 AND role IN ({marks})",
                                             list(roles))}
        ids.discard(nguoi_tao)
        c.executemany("INSERT OR IGNORE INTO thong_bao_nhan(thong_bao_id, user_id) VALUES (?,?)",
                      [(tb_id, uid) for uid in ids])
    return tb_id


def unread_count(user_id):
    r = query_one("SELECT COUNT(*) n FROM thong_bao_nhan WHERE user_id=? AND da_doc_luc IS NULL", (user_id,))
    return r["n"] if r else 0


# ----------------------------------------------------------------
# Hiển thị
# ----------------------------------------------------------------
def badge_hieu_luc(status):
    color = {HL_DANG: "green", HL_SAP: "orange", HL_HET: "red"}.get(status, "gray")
    return f":{color}-badge[{status}]"


def fmt_dt(s):
    if not s:
        return ""
    s = str(s)
    try:
        if len(s) >= 16:
            return f"{s[8:10]}/{s[5:7]}/{s[0:4]} {s[11:16]}"
        return f"{s[8:10]}/{s[5:7]}/{s[0:4]}"
    except Exception:
        return s


def user_map():
    return {u["id"]: u["full_name"] for u in query("SELECT id, full_name FROM users")}


def van_ban_options(include_none=True):
    """{id: 'Số hiệu - Tên'} để chọn văn bản nguồn trong các form."""
    opts = {None: "— Không chọn —"} if include_none else {}
    for v in query("SELECT id, so_hieu, ten FROM van_ban ORDER BY COALESCE(ngay_ban_hanh,'') DESC"):
        opts[v["id"]] = f"{v['so_hieu']} - {v['ten'][:70]}"
    return opts


def to_iso(d):
    return d.isoformat() if d else None


def from_iso(s):
    from datetime import date
    try:
        return date.fromisoformat(s) if s else None
    except ValueError:
        return None


def page_header(title, caption=""):
    st.title(title)
    if caption:
        st.caption(caption)


# ----------------------------------------------------------------
# Nhập tình huống hàng loạt từ Excel (theo "cấu trúc file mặc định")
# ----------------------------------------------------------------
TEMPLATE_COLUMNS = ["Câu hỏi", "Từ gợi ý", "Nghiệp vụ", "Câu trả lời", "Nguồn tài liệu",
                    "Số hiệu văn bản", "Link wiki", "Hiệu lực từ", "Hiệu lực đến"]

HEADER_MAP = {
    "cau_hoi": "cau_hoi", "tinh_huong": "cau_hoi",
    "tu_goi_y": "tu_goi_y", "tu_khoa": "tu_goi_y",
    "nghiep_vu": "nghiep_vu",
    "cau_tra_loi": "tra_loi", "tra_loi": "tra_loi",
    "nguon_tai_lieu": "nguon_tai_lieu", "nguon": "nguon_tai_lieu",
    "so_hieu_van_ban": "so_hieu", "so_hieu": "so_hieu", "van_ban": "so_hieu",
    "link_wiki": "link_wiki", "duong_link_van_ban_tren_wiki": "link_wiki", "wiki": "link_wiki",
    "hieu_luc_tu": "hieu_luc_tu", "hieu_luc_den": "hieu_luc_den",
}


def norm_header(h):
    h = unicodedata.normalize("NFD", str(h or "").strip().lower().replace("đ", "d"))
    h = "".join(c for c in h if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", "_", h).strip("_")


def template_bytes():
    df = pd.DataFrame([{
        "Câu hỏi": "Khách hàng thuê nhà muốn được tính giá điện theo định mức cho người thuê thì cần làm gì?",
        "Từ gợi ý": "thuê nhà, định mức, sinh viên, người lao động",
        "Nghiệp vụ": "Giá điện",
        "Câu trả lời": "Chủ nhà hoặc người thuê nộp giấy tờ chứng minh thời gian thuê ...",
        "Nguồn tài liệu": "Thông tư ... Điều ...",
        "Số hiệu văn bản": "",
        "Link wiki": "",
        "Hiệu lực từ": "2025-05-10",
        "Hiệu lực đến": "",
    }], columns=TEMPLATE_COLUMNS)
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        df.to_excel(w, index=False, sheet_name="TinhHuong")
        ws = w.sheets["TinhHuong"]
        for col, width in zip("ABCDEFGHI", (50, 30, 20, 70, 30, 18, 30, 14, 14)):
            ws.column_dimensions[col].width = width
    return buf.getvalue()


def read_excel_rows(uploaded):
    """Đọc file Excel/CSV theo mẫu -> list dict với khoá chuẩn (cau_hoi, tra_loi, ...)."""
    if uploaded.name.lower().endswith(".csv"):
        df = pd.read_csv(uploaded, dtype=str, encoding="utf-8-sig")
    else:
        df = pd.read_excel(uploaded, dtype=str)
    df = df.fillna("")
    cols = {c: HEADER_MAP.get(norm_header(c)) for c in df.columns}
    so_hieu_to_id = {v["so_hieu"].strip().lower(): v["id"] for v in query("SELECT id, so_hieu FROM van_ban")}
    rows, errors = [], []
    for i, rec in enumerate(df.to_dict("records"), start=2):
        r = {cols[k]: str(v).strip() for k, v in rec.items() if cols.get(k)}
        if not r.get("cau_hoi"):
            continue
        for k in ("hieu_luc_tu", "hieu_luc_den"):
            r[k] = _parse_date(r.get(k, ""))
        sh = r.pop("so_hieu", "").lower()
        r["van_ban_id"] = so_hieu_to_id.get(sh) if sh else None
        if sh and not r["van_ban_id"]:
            errors.append(f"Dòng {i}: chưa có văn bản số hiệu '{sh}' trong hệ thống (vẫn nhập, không liên kết).")
        rows.append(r)
    return rows, errors


def _parse_date(s):
    s = (s or "").strip()[:10]
    if not s:
        return None
    m = re.match(r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})", s)
    if m:
        return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
    return s if m else None


# ----------------------------------------------------------------
# Đọc nội dung văn bản (Word / PDF / txt) để tìm kiếm & trợ lý AI
# ----------------------------------------------------------------
def extract_text(path):
    path = Path(path)
    ext = path.suffix.lower()
    try:
        if ext in (".docx", ".docm"):
            # Ưu tiên bộ đọc của TTS_Doc_v2 nếu đặt chung thư mục (đọc được cả bảng, file đổi đuôi)
            try:
                from TTS_Doc_v2 import read_document
                return read_document(path)
            except Exception:
                from docx import Document
                doc = Document(str(path))
                lines = [p.text for p in doc.paragraphs if p.text.strip()]
                for t in doc.tables:
                    for row in t.rows:
                        lines.append(", ".join(c.text.strip() for c in row.cells if c.text.strip()))
                return "\n".join(lines)
        if ext == ".pdf":
            import pdfplumber
            with pdfplumber.open(str(path)) as pdf:
                return "\n".join((p.extract_text() or "") for p in pdf.pages)
        if ext == ".txt":
            return path.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        st.warning(f"Không trích được nội dung từ {path.name}: {e}")
    return ""
