# Cẩm nang CSKH – Trao đổi nghiệp vụ (bản MVP)

Ứng dụng web nội bộ cho TT CSKH và các Điện lực, viết bằng Python (Streamlit + SQLite).
Bám theo 2 tài liệu: *Chương trình Cẩm nang CSKH* và *Chương trình Trao đổi nghiệp vụ CSKH*.

## 1. Cài đặt (máy chủ Windows nội bộ hoặc máy cá nhân để thử)

**Cách nhanh nhất:** cài Python 3.11+ (tick *Add Python to PATH*), giải nén, **nhấp đúp `chay.bat`**.
File này tự cài thư viện, tạo tài khoản demo và mở chương trình.

> Lưu ý: phải chạy bằng `streamlit run app.py` (không phải `python app.py`).
> Tài khoản demo `dtv1`, `dl1` chỉ có sau khi chạy `python seed_demo.py`; chạy lại lúc nào cũng được,
> không cần tắt chương trình.

Cài tay:

```bat
:: Cài Python 3.11+ (tick "Add Python to PATH"), rồi trong thư mục camnang_cskh:
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

:: (Tuỳ chọn) dữ liệu mẫu để chạy thử - KHÔNG chạy trên hệ thống thật
python seed_demo.py

:: Chạy
streamlit run app.py --server.port 8501 --server.address 0.0.0.0
```

Mở trình duyệt: `http://<IP-máy-chủ>:8501`. Tài khoản đầu tiên: **admin / admin123** (đổi ngay sau khi đăng nhập).
Demo: `dtv1 / 123456` (ĐTV), `dl1 / 123456` (Điện lực).

Chạy như dịch vụ Windows (tự khởi động): dùng NSSM
`nssm install CamNangCSKH "C:\camnang_cskh\.venv\Scripts\streamlit.exe" run app.py --server.port 8501 --server.headless true`
và đặt *Startup directory* = `C:\camnang_cskh`.

## 2. Cấu trúc mã nguồn

| File | Nội dung |
| --- | --- |
| `app.py` | Điểm vào: đăng nhập, menu theo vai trò, đổi mật khẩu |
| `db.py` | Lược đồ CSDL SQLite, tìm kiếm không dấu, trạng thái hiệu lực |
| `auth.py` | Mật khẩu (PBKDF2), vai trò: `quan_ly`, `dtv`, `dl` |
| `common.py` | Thông báo + theo dõi đã đọc, file đính kèm, nhập Excel mẫu, trích chữ Word/PDF, điểm thi đua |
| `ai_assistant.py` | Trợ lý tra cứu: BM25 + (tuỳ chọn) LLM on-premise/cloud |
| `seed_demo.py` | Dữ liệu ví dụ |
| `views/trang_chu.py` | Trang chủ, thông báo chưa đọc |
| `views/hoi_dap.py` | Chuyên mục hỏi-đáp: tìm, like, bình luận, chốt (chữ đỏ), thêm câu hỏi + đính kèm |
| `views/hd_quan_ly.py` | Xử lý câu hỏi, đánh giá (hay / chuẩn / tương đối), theo dõi bình luận, gửi thông báo + ai chưa đọc |
| `views/hd_soan_thao.py` | Soạn thảo hỏi-đáp (tự điền từ câu hỏi ĐTV), rà soát, chuyển sang ngân hàng, nhập Excel |
| `views/thong_ke.py` | 3 bảng thống kê theo tài liệu + bảng điểm thi đua + câu hỏi gửi Trợ lý |
| `views/ngan_hang.py` | Ngân hàng tình huống: lọc từ khoá / nghiệp vụ / hiệu lực, "Thêm" để xem nhiều tình huống, bình chọn thường gặp |
| `views/nh_soan_thao.py` | Soạn thảo tình huống, gắn tag hết hiệu lực, nhập Excel, xuất "thường gặp" cho web CSKH |
| `views/van_ban.py` | Văn bản: tra cứu theo nội dung, lược đồ thay thế; khai báo văn bản thay thế ⇒ tự đánh dấu nội dung cần rà soát |
| `views/kien_thuc.py` | Kiến thức tổng hợp theo nghiệp vụ, đơn vị, **tra cứu tại thời điểm** (giai đoạn cũ) |
| `views/tro_ly.py` | Hỏi đáp kiểu chat, trích nguồn, đánh giá 👍/👎 |
| `views/nguoi_dung.py` | Người dùng, phân quyền, nhập Excel, danh mục nghiệp vụ / đơn vị |

## 3. Bật mô hình AI (khi sẵn sàng)

Lần chạy đầu tạo `config.json`. Ví dụ dùng Ollama trên máy chủ nội bộ có GPU:

```bat
ollama pull qwen2.5:7b-instruct
```
```json
{ "llm": { "enabled": true, "base_url": "http://localhost:11434/v1", "model": "qwen2.5:7b-instruct" } }
```
Bất kỳ dịch vụ tương thích OpenAI (vLLM, LM Studio, API cloud có hợp đồng) đều dùng được, thêm `api_key` nếu cần.
Chưa bật AI thì Trợ lý vẫn hoạt động ở chế độ tìm kiếm.

## 4. Sao lưu

Toàn bộ dữ liệu nằm trong thư mục `data/` (`camnang.db` + `uploads/`). Sao lưu thư mục này hằng ngày.
Đổi vị trí dữ liệu: đặt biến môi trường `CAMNANG_DATA=D:\CamNangData`.

## 5. Ghi chú mở rộng

- Đăng nhập AD/LDAP của đơn vị: thay hàm `login_page()` trong `auth.py`.
- Nhiều người dùng đồng thời (> 200): chuyển sang PostgreSQL / SQL Server (sửa `get_conn()` trong `db.py`).
- Dùng lại `TTS_Doc_v2.py`: đặt chung thư mục, `common.extract_text()` sẽ tự dùng bộ đọc Word của Callbot.
