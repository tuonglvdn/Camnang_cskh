# -*- coding: utf-8 -*-
"""
Cơ sở dữ liệu của Cẩm nang CSKH (SQLite).
- Một file duy nhất data/camnang.db, không cần cài máy chủ CSDL.
- Khi cần chạy cho nhiều đơn vị, có thể chuyển sang SQL Server/PostgreSQL:
  chỉ cần thay hàm get_conn() và chỉnh vài cú pháp SQL.
"""
import os
import re
import sqlite3
import unicodedata
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("CAMNANG_DATA", BASE_DIR / "data"))
DB_PATH = DATA_DIR / "camnang.db"
UPLOAD_DIR = DATA_DIR / "uploads"

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY,
    username      TEXT UNIQUE NOT NULL,
    full_name     TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL CHECK (role IN ('quan_ly', 'dtv', 'dl')),
    don_vi        TEXT DEFAULT '',
    active        INTEGER DEFAULT 1,
    created_at    TEXT DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS danh_muc (
    id    INTEGER PRIMARY KEY,
    loai  TEXT NOT NULL,          -- 'nghiep_vu' | 'don_vi'
    ten   TEXT NOT NULL,
    thu_tu INTEGER DEFAULT 0,
    UNIQUE (loai, ten)
);

-- Văn bản, quy định, hướng dẫn
CREATE TABLE IF NOT EXISTS van_ban (
    id            INTEGER PRIMARY KEY,
    so_hieu       TEXT NOT NULL,
    ten           TEXT NOT NULL,
    cap           TEXT DEFAULT '',     -- QPPL / EVN / CPC / PC
    ap_dung       TEXT DEFAULT 'Tất cả',
    nghiep_vu     TEXT DEFAULT '',
    ngay_ban_hanh TEXT,
    hieu_luc_tu   TEXT,
    hieu_luc_den  TEXT,
    quan_he       TEXT DEFAULT '',     -- 'thay_the' | 'sua_doi' | 'bo_sung'
    van_ban_goc_id INTEGER REFERENCES van_ban(id),
    file_path     TEXT,
    noi_dung      TEXT DEFAULT '',     -- chữ trích từ file, phục vụ tìm kiếm / trợ lý AI
    link_wiki     TEXT DEFAULT '',
    created_by    INTEGER REFERENCES users(id),
    created_at    TEXT DEFAULT (datetime('now', 'localtime'))
);

-- Đề xuất / thắc mắc ĐTV gửi lên (Chuyên mục hỏi-đáp, bước 1)
CREATE TABLE IF NOT EXISTS de_xuat (
    id              INTEGER PRIMARY KEY,
    nguoi_gui       INTEGER NOT NULL REFERENCES users(id),
    cau_hoi         TEXT NOT NULL,
    tra_loi_de_xuat TEXT DEFAULT '',
    nghiep_vu       TEXT DEFAULT '',
    file_dinh_kem   TEXT DEFAULT '',
    trang_thai      TEXT DEFAULT 'moi',   -- 'moi' | 'da_phan_hoi'
    phan_hoi        TEXT DEFAULT '',
    nguoi_phan_hoi  INTEGER REFERENCES users(id),
    ngay_phan_hoi   TEXT,
    cau_hoi_hay     INTEGER DEFAULT 0,
    tl_chuan        INTEGER DEFAULT 0,
    tl_tuong_doi    INTEGER DEFAULT 0,
    bai_id          INTEGER,
    created_at      TEXT DEFAULT (datetime('now', 'localtime'))
);

-- Bài đăng trong Chuyên mục hỏi-đáp (bước 2)
CREATE TABLE IF NOT EXISTS hd_bai (
    id             INTEGER PRIMARY KEY,
    cau_hoi        TEXT NOT NULL,
    tu_goi_y       TEXT DEFAULT '',
    nghiep_vu      TEXT DEFAULT '',
    tra_loi        TEXT DEFAULT '',
    nguon_tai_lieu TEXT DEFAULT '',
    van_ban_id     INTEGER REFERENCES van_ban(id),
    link_wiki      TEXT DEFAULT '',
    file_dinh_kem  TEXT DEFAULT '',
    nguoi_gui      INTEGER REFERENCES users(id),   -- ĐTV đóng góp (nếu có)
    de_xuat_id     INTEGER REFERENCES de_xuat(id),
    tac_gia        INTEGER REFERENCES users(id),   -- user quản lý biên soạn
    an             INTEGER DEFAULT 0,
    can_ra_soat    INTEGER DEFAULT 0,
    created_at     TEXT DEFAULT (datetime('now', 'localtime')),
    updated_at     TEXT DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS hd_like (
    bai_id     INTEGER REFERENCES hd_bai(id),
    user_id    INTEGER REFERENCES users(id),
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    PRIMARY KEY (bai_id, user_id)
);

CREATE TABLE IF NOT EXISTS hd_binh_luan (
    id         INTEGER PRIMARY KEY,
    bai_id     INTEGER REFERENCES hd_bai(id),
    user_id    INTEGER REFERENCES users(id),
    noi_dung   TEXT NOT NULL,
    la_chot    INTEGER DEFAULT 0,   -- bình luận chốt của user quản lý (chữ đỏ)
    da_doc     INTEGER DEFAULT 0,   -- user quản lý đã tick đọc
    la_hay     INTEGER DEFAULT 0,   -- được cộng điểm
    created_at TEXT DEFAULT (datetime('now', 'localtime'))
);

-- Ngân hàng tình huống
CREATE TABLE IF NOT EXISTS nh_tinh_huong (
    id             INTEGER PRIMARY KEY,
    cau_hoi        TEXT NOT NULL,
    tu_goi_y       TEXT DEFAULT '',
    nghiep_vu      TEXT DEFAULT '',
    tra_loi        TEXT DEFAULT '',
    nguon_tai_lieu TEXT DEFAULT '',
    van_ban_id     INTEGER REFERENCES van_ban(id),
    link_wiki      TEXT DEFAULT '',
    video_link     TEXT DEFAULT '',
    nguon          TEXT DEFAULT '',     -- Hỏi-đáp / QA / TCT / Điện lực / Khác
    hieu_luc_tu    TEXT,
    hieu_luc_den   TEXT,
    het_hieu_luc   INTEGER DEFAULT 0,   -- gắn tag hết hiệu lực thủ công
    hd_bai_id      INTEGER REFERENCES hd_bai(id),
    can_ra_soat    INTEGER DEFAULT 0,
    created_by     INTEGER REFERENCES users(id),
    created_at     TEXT DEFAULT (datetime('now', 'localtime')),
    updated_at     TEXT DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS nh_binh_chon (
    th_id      INTEGER REFERENCES nh_tinh_huong(id),
    user_id    INTEGER REFERENCES users(id),
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    PRIMARY KEY (th_id, user_id)
);

CREATE TABLE IF NOT EXISTS nh_binh_luan (
    id         INTEGER PRIMARY KEY,
    th_id      INTEGER REFERENCES nh_tinh_huong(id),
    user_id    INTEGER REFERENCES users(id),
    noi_dung   TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now', 'localtime'))
);

-- Kiến thức tổng hợp (theo nghiệp vụ, đơn vị, giai đoạn hiệu lực)
CREATE TABLE IF NOT EXISTS kt_bai (
    id          INTEGER PRIMARY KEY,
    tieu_de     TEXT NOT NULL,
    nghiep_vu   TEXT DEFAULT '',
    ap_dung     TEXT DEFAULT 'Tất cả',
    noi_dung    TEXT DEFAULT '',
    van_ban_id  INTEGER REFERENCES van_ban(id),
    hieu_luc_tu TEXT,
    hieu_luc_den TEXT,
    can_ra_soat INTEGER DEFAULT 0,
    created_by  INTEGER REFERENCES users(id),
    updated_at  TEXT DEFAULT (datetime('now', 'localtime'))
);

-- Thông báo + theo dõi đã đọc (tương tự eoffice)
CREATE TABLE IF NOT EXISTS thong_bao (
    id         INTEGER PRIMARY KEY,
    tieu_de    TEXT NOT NULL,
    noi_dung   TEXT DEFAULT '',
    loai       TEXT DEFAULT 'chung',
    lien_ket   TEXT DEFAULT '',
    nguoi_tao  INTEGER REFERENCES users(id),
    created_at TEXT DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS thong_bao_nhan (
    thong_bao_id INTEGER REFERENCES thong_bao(id),
    user_id      INTEGER REFERENCES users(id),
    da_doc_luc   TEXT,
    PRIMARY KEY (thong_bao_id, user_id)
);

-- Nhật ký câu hỏi gửi Trợ lý tra cứu (phát hiện lỗ hổng tài liệu)
CREATE TABLE IF NOT EXISTS tl_nhat_ky (
    id         INTEGER PRIMARY KEY,
    user_id    INTEGER REFERENCES users(id),
    cau_hoi    TEXT,
    tra_loi    TEXT,
    danh_gia   INTEGER,   -- 1 đúng, -1 sai, NULL chưa đánh giá
    created_at TEXT DEFAULT (datetime('now', 'localtime'))
);

-- Phiên đăng nhập (giữ đăng nhập khi nhấn F5)
CREATE TABLE IF NOT EXISTS phien (
    token      TEXT PRIMARY KEY,
    user_id    INTEGER REFERENCES users(id),
    expires_at TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now', 'localtime'))
);

CREATE INDEX IF NOT EXISTS ix_bl_bai ON hd_binh_luan(bai_id);
CREATE INDEX IF NOT EXISTS ix_like_bai ON hd_like(bai_id);
CREATE INDEX IF NOT EXISTS ix_tbn_user ON thong_bao_nhan(user_id, da_doc_luc);
"""

DEFAULT_NGHIEP_VU = [
    "Cấp điện mới", "Hợp đồng mua bán điện", "Giá điện", "Hoá đơn - Thu tiền",
    "Ghi chỉ số - Công tơ", "Ngừng, giảm cung cấp điện", "Sự cố - Mất điện",
    "Điện mặt trời áp mái", "Dịch vụ trực tuyến", "Khác",
]
DEFAULT_DON_VI = [
    "TT CSKH", "PC Quảng Bình", "PC Quảng Trị", "PC Thừa Thiên Huế", "PC Đà Nẵng",
    "PC Quảng Nam", "PC Quảng Ngãi", "PC Bình Định", "PC Phú Yên", "PC Khánh Hoà",
    "PC Gia Lai", "PC Kon Tum", "PC Đắk Lắk", "PC Đắk Nông",
]


# ----------------------------------------------------------------
# Tìm kiếm tiếng Việt không phân biệt dấu / hoa thường
# ----------------------------------------------------------------
def bo_dau(text):
    """'Hóa Đơn' -> 'hoa don' (để tìm 'hoa don' vẫn ra 'Hoá đơn')."""
    if text is None:
        return ""
    text = unicodedata.normalize("NFD", str(text).replace("đ", "d").replace("Đ", "D"))
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", text.lower()).strip()


def keyword_clause(columns, keyword, params):
    """Tạo điều kiện WHERE: mọi từ trong keyword đều phải xuất hiện (bỏ dấu)."""
    words = [w for w in bo_dau(keyword).split() if w]
    if not words:
        return "1=1"
    joined = " || ' ' || ".join(f"COALESCE({c}, '')" for c in columns)
    parts = []
    for w in words:
        parts.append(f"bo_dau({joined}) LIKE ?")
        params.append(f"%{w}%")
    return " AND ".join(parts)


def get_conn():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")   # nhiều người đọc cùng lúc
    conn.create_function("bo_dau", 1, bo_dau, deterministic=True)
    return conn


@contextmanager
def connect():
    conn = get_conn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def query(sql, params=()):
    with connect() as c:
        return [dict(r) for r in c.execute(sql, params).fetchall()]


def query_one(sql, params=()):
    rows = query(sql, params)
    return rows[0] if rows else None


def execute(sql, params=()):
    with connect() as c:
        cur = c.execute(sql, params)
        return cur.lastrowid


def init_db():
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    with connect() as c:
        c.executescript(SCHEMA)
        if not c.execute("SELECT 1 FROM danh_muc LIMIT 1").fetchone():
            c.executemany("INSERT INTO danh_muc(loai, ten, thu_tu) VALUES ('nghiep_vu', ?, ?)",
                          [(t, i) for i, t in enumerate(DEFAULT_NGHIEP_VU)])
            c.executemany("INSERT INTO danh_muc(loai, ten, thu_tu) VALUES ('don_vi', ?, ?)",
                          [(t, i) for i, t in enumerate(DEFAULT_DON_VI)])
        if not c.execute("SELECT 1 FROM users LIMIT 1").fetchone():
            from auth import hash_password
            c.execute("INSERT INTO users(username, full_name, password_hash, role, don_vi) "
                      "VALUES ('admin', 'Quản trị hệ thống', ?, 'quan_ly', 'TT CSKH')",
                      (hash_password("admin123"),))


def danh_muc(loai):
    return [r["ten"] for r in query("SELECT ten FROM danh_muc WHERE loai=? ORDER BY thu_tu, ten", (loai,))]


# ----------------------------------------------------------------
# Hiệu lực
# ----------------------------------------------------------------
HL_DANG = "Đang có hiệu lực"
HL_SAP = "Sắp có hiệu lực"
HL_HET = "Hết hiệu lực"


def trang_thai_hieu_luc(tu, den, het_tag=0, tai_ngay=None):
    d = (tai_ngay or date.today()).isoformat()
    if het_tag:
        return HL_HET
    if den and den < d:
        return HL_HET
    if tu and tu > d:
        return HL_SAP
    return HL_DANG


def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
