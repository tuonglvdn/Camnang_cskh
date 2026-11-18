# -*- coding: utf-8 -*-
"""
Tạo dữ liệu DEMO để chạy thử (KHÔNG chạy trên hệ thống thật).
    python seed_demo.py
Tài khoản: admin/admin123 (quản lý), dtv1..dtv3/123456 (ĐTV), dl1/123456 (Điện lực)
Lưu ý: nội dung tình huống dưới đây chỉ là VÍ DỤ minh hoạ, không phải quy định chính thức.
"""
import sys
from datetime import date, timedelta

for _s in (sys.stdout, sys.stderr):  # tiếng Việt trên console Windows
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from auth import hash_password  # noqa: E402
from db import connect, init_db  # noqa: E402

init_db()
today = date.today()
D = lambda n: (today + timedelta(days=n)).isoformat()  # noqa: E731

DEMO_USERS = [("dtv1", "Nguyễn Văn An", "dtv", "TT CSKH"), ("dtv2", "Trần Thị Bình", "dtv", "TT CSKH"),
              ("dtv3", "Lê Văn Cường", "dtv", "TT CSKH"), ("dl1", "Phạm Thị Dung", "dl", "PC Quảng Trị")]

with connect() as c:
    # 1. Tài khoản demo: luôn tạo nếu chưa có (mật khẩu 123456)
    for u in DEMO_USERS:
        c.execute("INSERT OR IGNORE INTO users(username, full_name, password_hash, role, don_vi) VALUES (?,?,?,?,?)",
                  (u[0], u[1], hash_password("123456"), u[2], u[3]))
    c.execute("UPDATE users SET active=1 WHERE username IN ('dtv1','dtv2','dtv3','dl1')")
    print("Tài khoản demo: dtv1, dtv2, dtv3 (ĐTV), dl1 (Điện lực) - mật khẩu 123456")
    ids = {r[0]: r[1] for r in c.execute("SELECT username, id FROM users")}

    # 2. Nội dung ví dụ: chỉ tạo khi CSDL chưa có tình huống nào
    has_content = c.execute("SELECT COUNT(*) FROM nh_tinh_huong").fetchone()[0] > 0
    if has_content:
        print("Đã có nội dung, không tạo thêm nội dung ví dụ.")
if not has_content:
    with connect() as c:
        ids = {r[0]: r[1] for r in c.execute("SELECT username, id FROM users")}
        vb1 = c.execute("""INSERT INTO van_ban(so_hieu, ten, cap, nghiep_vu, ngay_ban_hanh, hieu_luc_tu, noi_dung, created_by)
            VALUES ('VD-01/HD-CPC', 'Hướng dẫn mẫu về cấp điện sinh hoạt (VÍ DỤ)', 'EVNCPC', 'Cấp điện mới', ?, ?, ?, ?)""",
            (D(-400), D(-390), "Điều 1. Hồ sơ đề nghị cấp điện sinh hoạt gồm giấy đề nghị và giấy tờ tuỳ thân.\n"
             "Điều 2. Thời gian giải quyết cấp điện khu vực thành phố, thị xã tối đa 3 ngày làm việc.\n"
             "Điều 3. Khách hàng thuê nhà được cấp định mức theo số người thuê khi có giấy tờ chứng minh.",
             ids["admin"])).lastrowid
        c.execute("""INSERT INTO van_ban(so_hieu, ten, cap, nghiep_vu, ngay_ban_hanh, hieu_luc_tu, noi_dung, created_by)
            VALUES ('VD-02/QĐ-EVN', 'Quy định mẫu về giá bán lẻ điện (VÍ DỤ)', 'EVN', 'Giá điện', ?, ?, ?, ?)""",
            (D(-200), D(-190), "Điều 1. Giá bán lẻ điện sinh hoạt áp dụng theo bậc thang.\n"
             "Điều 2. Kỳ hoá đơn có thời điểm đổi giá được tính theo tỷ lệ số ngày trước và sau ngày đổi giá.",
             ids["admin"]))

        th = [
            ("Khách hàng thuê nhà muốn được tính giá điện theo định mức cho người thuê thì cần làm gì?",
             "thuê nhà, định mức, sinh viên", "Giá điện",
             "- Chủ nhà hoặc người thuê nộp **giấy tờ chứng minh thời gian thuê** và danh sách người thuê.\n"
             "- Điện lực cấp định mức theo số người thuê (VÍ DỤ minh hoạ).", "VD-01/HD-CPC Điều 3", vb1, "Hỏi-đáp", None, None, 0),
            ("Thời gian giải quyết cấp điện sinh hoạt ở thành phố là bao lâu?", "cấp điện mới, thời gian, 3 ngày",
             "Cấp điện mới", "Tối đa **3 ngày làm việc** kể từ khi nhận đủ hồ sơ (VÍ DỤ).", "VD-01/HD-CPC Điều 2", vb1,
             "Hướng dẫn TCT", None, None, 0),
            ("Hoá đơn kỳ có đổi giá được tính như thế nào?", "đổi giá, hoá đơn, tỷ lệ ngày", "Hoá đơn - Thu tiền",
             "Sản lượng được phân bổ theo **tỷ lệ số ngày** trước và sau ngày đổi giá (VÍ DỤ).", "VD-02/QĐ-EVN Điều 2", None,
             "QA", D(30), None, 0),
            ("Khách hàng hỏi về biểu giá cũ trước năm 2020", "giá cũ", "Giá điện",
             "Áp dụng biểu giá cũ (VÍ DỤ - đã hết hiệu lực).", "", None, "Khác", D(-2000), D(-1500), 0),
        ]
        for t in th:
            c.execute("""INSERT INTO nh_tinh_huong(cau_hoi, tu_goi_y, nghiep_vu, tra_loi, nguon_tai_lieu, van_ban_id, nguon,
                         hieu_luc_tu, hieu_luc_den, het_hieu_luc, created_by) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                      t + (ids["admin"],))

        dx = c.execute("""INSERT INTO de_xuat(nguoi_gui, cau_hoi, tra_loi_de_xuat, nghiep_vu, trang_thai, phan_hoi,
                          nguoi_phan_hoi, ngay_phan_hoi, cau_hoi_hay, tl_chuan)
                          VALUES (?, 'KH báo công tơ quay nhanh bất thường, ĐTV cần hướng dẫn gì?',
                          'Ghi nhận yêu cầu kiểm định công tơ, hẹn lịch Điện lực kiểm tra.', 'Ghi chỉ số - Công tơ',
                          'da_phan_hoi', 'Đúng hướng, bổ sung thông tin chi phí kiểm định.', ?, datetime('now','localtime'), 1, 1)""",
                       (ids["dtv1"], ids["admin"])).lastrowid
        c.execute("""INSERT INTO de_xuat(nguoi_gui, cau_hoi, nghiep_vu) VALUES (?, 'KH muốn sang tên hợp đồng khi mua nhà
                     nhưng chủ cũ còn nợ tiền điện thì xử lý thế nào?', 'Hợp đồng mua bán điện')""", (ids["dtv2"],))
        bai = c.execute("""INSERT INTO hd_bai(cau_hoi, tu_goi_y, nghiep_vu, tra_loi, nguon_tai_lieu, nguoi_gui, de_xuat_id,
                           tac_gia) VALUES ('KH báo công tơ quay nhanh bất thường, ĐTV cần hướng dẫn gì?', 'công tơ, kiểm định',
                           'Ghi chỉ số - Công tơ', '1. Ghi nhận yêu cầu kiểm tra/kiểm định công tơ.\n2. Hẹn lịch Điện lực kiểm tra.\n3. Thông tin chi phí kiểm định (VÍ DỤ).',
                           'Quy trình mẫu', ?, ?, ?)""", (ids["dtv1"], dx, ids["admin"])).lastrowid
        c.execute("UPDATE de_xuat SET bai_id=? WHERE id=?", (bai, dx))
        for u in ("dtv2", "dtv3"):
            c.execute("INSERT INTO hd_like(bai_id, user_id) VALUES (?,?)", (bai, ids[u]))
        c.execute("INSERT INTO hd_binh_luan(bai_id, user_id, noi_dung) VALUES (?,?,?)",
                  (bai, ids["dtv2"], "Nên nhắc KH tắt hết thiết bị để tự kiểm tra trước."))
        c.execute("INSERT INTO hd_binh_luan(bai_id, user_id, noi_dung, la_chot, da_doc) VALUES (?,?,?,1,1)",
                  (bai, ids["admin"], "Chốt: hướng dẫn KH tự kiểm tra trước, sau đó ghi nhận yêu cầu kiểm định."))
        c.execute("INSERT INTO hd_binh_luan(bai_id, user_id, noi_dung) VALUES (?,?,?)",
                  (bai, ids["dtv3"], "Đã rõ, cảm ơn anh/chị."))

        c.execute("""INSERT INTO kt_bai(tieu_de, nghiep_vu, noi_dung, van_ban_id, hieu_luc_tu, created_by)
                     VALUES ('Hồ sơ cấp điện sinh hoạt', 'Cấp điện mới',
                     '### Hồ sơ gồm\n- Giấy đề nghị mua điện\n- Giấy tờ tuỳ thân\n\n### Thời gian\n- Thành phố, thị xã: tối đa 3 ngày làm việc (VÍ DỤ)',
                     ?, ?, ?)""", (vb1, D(-390), ids["admin"]))
    print("Đã tạo dữ liệu demo. Đăng nhập admin/admin123 hoặc dtv1/123456.")

# 3. Dữ liệu thật đặt cạnh chương trình (file DuLieu_*.xlsx, ví dụ DuLieu_GiaDien_2026.xlsx) - nhập nếu chưa có
from pathlib import Path  # noqa: E402

from nhap_du_lieu import import_data, read_workbook  # noqa: E402

for _f in sorted(Path(__file__).resolve().parent.glob("DuLieu_*.xlsx")):
    _data, _errs = read_workbook(str(_f))
    _stats, _ = import_data(_data)
    print(f"{_f.name}: " + ", ".join(f"{k} +{v['them']}" for k, v in _stats.items()))
