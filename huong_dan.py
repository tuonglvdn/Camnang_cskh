# -*- coding: utf-8 -*-
"""Nút ❓ Hướng dẫn ngay trên trang (mở hộp thoại). Nội dung viết ngắn, theo từng việc cần làm."""
import streamlit as st

HD_NHAP_DU_LIEU = {
    "tieu_de": "Nhập & cập nhật dữ liệu có đối chiếu",
    "muc": {
        "⚡ Bắt đầu nhanh": """
**Nguyên tắc:** file Excel gốc là nguồn duy nhất. Số liệu sai → **sửa file gốc rồi nạp lại**, không sửa tay trên web.

| Bạn đang có... | Vào tab |
|---|---|
| File đúng mẫu 3 sheet (VanBan, KienThuc, TinhHuong) | 🔄 **Cập nhật có đối chiếu** |
| File Excel khác (tài liệu đào tạo, bảng so sánh, danh mục văn bản...) | 🪄 **Chuyển file Excel bất kỳ** |
| Vừa duyệt nhầm | 🕘 **Lịch sử cập nhật** → Hoàn tác |
| Muốn tự soạn file mới | 📄 **File mẫu** → tải mẫu |

Không có gì được ghi vào hệ thống cho tới khi bạn bấm **✅ Duyệt & cập nhật**.
""",
        "🔄 Cập nhật": """
1. Tab **🔄 Cập nhật có đối chiếu** → chọn file Excel.
2. Xem **khung đỏ** (lỗi) và **khung vàng** (cảnh báo).  
   Có lỗi đỏ → mở file gốc theo *Vị trí nguồn* (ví dụ `CAU HOI!B15`), sửa, nạp lại.
3. Xem bảng tóm tắt và từng nhóm:
   - ➕ **Thêm mới**: xem nhanh danh sách.
   - ✏️ **Thay đổi**: chữ đỏ gạch = cũ, chữ xanh = mới. **Bỏ tick** mục chưa muốn cập nhật.
   - ➖ **Không còn trong file**: chọn *Đánh dấu cần rà soát* (mặc định) / *Hết hiệu lực* / *Giữ nguyên*.
4. Bấm **✅ Duyệt & cập nhật**. ĐTV và Điện lực nhận thông báo.
5. Mở trang Kiến thức / Ngân hàng tình huống kiểm tra 2-3 mục vừa đổi.
""",
        "🪄 Chuyển file": """
1. Tab **🪄 Chuyển file Excel bất kỳ** → chọn file Excel.
2. Kiểm tra ô **Mã bộ dữ liệu** (ví dụ `VBPL2025`, `GIA2026`).  
   👉 **Phiên bản sau của cùng tài liệu phải dùng lại đúng mã này.**
3. Xem cột **Cách đọc** của từng sheet, đổi nếu chương trình đoán chưa đúng:

| Sheet có... | Chọn |
|---|---|
| Cột Câu hỏi + Trả lời | Hỏi - đáp → Tình huống |
| Hai bên Điều/Nội dung mới - cũ | So sánh mới/cũ → Kiến thức |
| Cột Văn bản + Ngày hiệu lực | Danh mục văn bản → Văn bản |
| Bảng có STT, mỗi dòng 1 nội dung | Mỗi dòng 1 bài → Kiến thức |
| Biểu giá, bảng nhiều số | Bảng số liệu → 1 bài |
| Công cụ tính, chỉ có hình ảnh | Bỏ qua |

4. Đọc **⚠️ Điểm cần xem lại**, dùng **Xem thử 1 mục** để đọc vài bài.
5. Bấm **➡️ Đối chiếu & duyệt ngay** rồi mở tab 🔄 để duyệt  
   (hoặc **⬇️ Tải file đã chuyển** để sửa thêm trong Excel).

Màu chữ trong file gốc được giữ: xanh → **đậm** (mới), đỏ → ~~gạch~~ (bãi bỏ).
""",
        "🕘 Hoàn tác": """
1. Tab **🕘 Lịch sử cập nhật**.
2. Ở **đợt mới nhất**: tick *Tôi muốn trả dữ liệu về như trước đợt này*.
3. Bấm **↩️ Hoàn tác đợt này**.

Mục thêm mới bị xoá, mục bị sửa trở về nội dung cũ.  
Chỉ hoàn tác được đợt mới nhất, lần lượt từng đợt.
""",
        "❗ Lưu ý & lỗi": """
**Luôn nhớ**
- Giữ nguyên cột **Mã** giữa các phiên bản file → hệ thống nhận đúng mục *Thay đổi*.
- Mỗi tài liệu chỉ nạp theo **một cách** (file mẫu tự soạn *hoặc* file chuyển tự động).
- Không đưa thông tin khách hàng (tên, SĐT, mã KH) vào file.
- Số liệu nhập vào ô Excel, không dán ảnh.

| Gặp | Làm |
|---|---|
| Nạp lại mà tất cả thành *Thêm mới* | Mã / tiền tố bị đổi → dùng lại đúng mã cũ |
| Nhiều mục *Không còn trong file* bất thường | Chọn *Giữ nguyên*, kiểm tra lại mã bộ dữ liệu |
| Số hiệu "ký hiệu lạ" (vd `tTT-BCT`) | Sửa lỗi gõ trong file gốc |
| *Nhờ AI đọc* báo chưa bật AI | Nhờ IT cấu hình AI nội bộ, hoặc chọn cách đọc khác |
| Duyệt nhầm | Tab 🕘 → Hoàn tác |
""",
    },
}


def nut_huong_dan(hd, key):
    """Hiện nút ❓ Hướng dẫn canh phải; bấm mở hộp thoại có các tab nội dung."""
    @st.dialog(f"❓ Hướng dẫn: {hd['tieu_de']}", width="large")
    def _mo():
        tabs = st.tabs(list(hd["muc"]))
        for t, nd in zip(tabs, hd["muc"].values()):
            with t:
                st.markdown(nd)
        st.divider()
        toan_van = f"# Hướng dẫn: {hd['tieu_de']}\n\n" + "\n\n".join(
            f"## {k}\n{v}" for k, v in hd["muc"].items())
        st.download_button("⬇️ Tải hướng dẫn để in", toan_van.encode("utf-8"),
                           "huong_dan_nhap_du_lieu.md", key=f"{key}_tai")

    _, c = st.columns([5, 1])
    if c.button("❓ Hướng dẫn", key=key, width="stretch", help="Mở hướng dẫn nhanh cho trang này"):
        _mo()
