# -*- coding: utf-8 -*-
"""
SAO LƯU DỮ LIỆU CẨM NANG CSKH (chạy được khi chương trình đang hoạt động).
    python sao_luu.py [thư_mục_sao_lưu] [số_ngày_giữ]
- CSDL: sao lưu an toàn bằng SQLite backup API -> camnang_YYYYMMDD_HHMM.db
- File đính kèm: chép thêm file mới / file thay đổi vào <thư mục>/uploads (không xoá)
- Tự xoá bản sao CSDL cũ hơn N ngày (mặc định 30)
Biến môi trường: CAMNANG_DATA (thư mục dữ liệu), CAMNANG_BACKUP (thư mục sao lưu)
"""
import os
import shutil
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from db import DATA_DIR, DB_PATH, UPLOAD_DIR  # noqa: E402

backup_dir = Path(sys.argv[1] if len(sys.argv) > 1 else os.environ.get("CAMNANG_BACKUP", DATA_DIR / "backup"))
keep_days = int(sys.argv[2]) if len(sys.argv) > 2 else 30
backup_dir.mkdir(parents=True, exist_ok=True)

# 1. CSDL
target = backup_dir / f"camnang_{datetime.now():%Y%m%d_%H%M}.db"
src = sqlite3.connect(DB_PATH)
dst = sqlite3.connect(target)
with dst:
    src.backup(dst)
dst.close()
src.close()
ok = sqlite3.connect(target).execute("PRAGMA integrity_check").fetchone()[0]
print(f"CSDL  -> {target} ({target.stat().st_size / 1024:.0f} KB, kiểm tra: {ok})")

# 2. File đính kèm (chép tăng dần)
n = 0
if UPLOAD_DIR.exists():
    for f in UPLOAD_DIR.rglob("*"):
        if f.is_file():
            out = backup_dir / "uploads" / f.relative_to(UPLOAD_DIR)
            if not out.exists() or out.stat().st_mtime < f.stat().st_mtime:
                out.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, out)
                n += 1
print(f"Đính kèm: chép {n} file mới")

# 3. Xoá bản cũ
cut = time.time() - keep_days * 86400
old = [p for p in backup_dir.glob("camnang_*.db") if p.stat().st_mtime < cut]
for p in old:
    p.unlink()
print(f"Xoá {len(old)} bản sao lưu cũ hơn {keep_days} ngày")
sys.exit(0 if ok == "ok" else 1)
