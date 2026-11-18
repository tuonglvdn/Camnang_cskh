# -*- coding: utf-8 -*-
"""
TRỢ LÝ TRA CỨU - hỏi bằng tiếng Việt, trả lời từ tài liệu đã duyệt, có trích dẫn nguồn.
Không cấu hình LLM: hiển thị các đoạn tài liệu liên quan nhất.
"""
import streamlit as st

from ai_assistant import BM25, build_corpus, ask_llm, load_config
from giong_noi import giong_noi
from auth import current_user
from common import page_header
from db import execute, query_one

user = current_user()
cfg = load_config()
page_header("🤖 Trợ lý tra cứu nghiệp vụ")


@st.cache_resource(ttl=300, show_spinner="Đang nạp chỉ mục tài liệu...")
def get_index(stamp):
    return BM25(build_corpus(), cfg.get("abbreviations", {}))


# Chỉ mục được làm mới khi dữ liệu thay đổi (hoặc sau 5 phút)
stamp = query_one("""SELECT (SELECT COUNT(*)||MAX(updated_at) FROM nh_tinh_huong) ||
                            (SELECT COUNT(*)||MAX(updated_at) FROM hd_bai) ||
                            (SELECT COUNT(*)||MAX(updated_at) FROM kt_bai) ||
                            (SELECT COUNT(*) FROM van_ban) AS s""")["s"]
index = get_index(stamp)

with st.sidebar:
    st.caption(f"Chỉ mục: {len(index.docs)} đoạn tài liệu")
    st.caption("LLM: " + (f"✅ {cfg['llm']['model']}" if cfg["llm"]["enabled"] else "⏸️ chưa bật (chỉ tìm kiếm)"))
    if st.button("Xoá hội thoại"):
        st.session_state["chat"] = []
        st.rerun()

chat = st.session_state.setdefault("chat", [])


def show_sources(passages):
    with st.expander(f"📑 Nguồn tham khảo ({len(passages)})"):
        for i, p in enumerate(passages, 1):
            st.markdown(f"**[{i}] {p['kind']}:** {p['title']}  \n:gray[{p['source']}]")
            st.text(p["text"][:600] + ("…" if len(p["text"]) > 600 else ""))
            if p.get("link"):
                st.markdown(f"[Mở văn bản]({p['link']})")


def tra_loi(q):
    """Tìm tài liệu + soạn câu trả lời; lưu nhật ký. Trả về (answer, passages, log_id)."""
    passages = index.search(q, cfg.get("top_k", 6))
    if not passages:
        answer = ("Không tìm thấy nội dung liên quan trong tài liệu. Bạn có thể gửi câu hỏi lên "
                  "**Chuyên mục hỏi-đáp** để P.CSKH giải đáp.")
    elif cfg["llm"]["enabled"]:
        try:
            answer = ask_llm(q, passages, cfg)
        except Exception as e:
            answer = (f"⚠️ Không gọi được mô hình AI ({e}). Dưới đây là các nội dung liên quan nhất:\n\n"
                      + "\n".join(f"- [{i}] {p['title']}" for i, p in enumerate(passages, 1)))
    else:
        best = passages[0]
        body = (f"**{best['title']}**\n\n{best['answer']}" if best.get("answer") else best["text"])[:1500]
        answer = (f"**Nội dung phù hợp nhất** ({best['kind']}):\n\n{body}\n\n"
                  f":gray[Nguồn: {best['source']}]")
        seen, items = {best["title"]}, []
        for i, p in enumerate(passages[1:], 2):
            if p["title"] not in seen:
                seen.add(p["title"])
                items.append(f"- [{i}] {p['title']}")
        if items:
            answer += "\n\n**Nội dung liên quan khác:**\n" + "\n".join(items)
    log_id = execute("INSERT INTO tl_nhat_ky(user_id, cau_hoi, tra_loi) VALUES (?,?,?)",
                     (user["id"], q, answer[:4000]))
    return answer, passages, log_id


# ---- Ô hỏi đặt ở TRÊN CÙNG; câu hỏi - trả lời mới nhất hiện ngay bên dưới ----
q = giong_noi(
    "o_hoi_tro_ly",
    placeholder="Hỏi như hỏi đồng nghiệp: gõ hoặc bấm 🎤 để nói…",
    ghi_chu="VD: Khách thuê nhà cần giấy tờ gì để tính giá điện theo định mức? · Trả lời từ ngân hàng tình huống, "
            "hỏi-đáp, kiến thức và văn bản còn hiệu lực · Enter để gửi",
)

if q:
    with st.spinner("Đang tra cứu..."):
        answer, passages, log_id = tra_loi(q)
    # lưu theo cặp (hỏi, đáp); cặp mới nhất đứng đầu danh sách
    chat.insert(0, {"q": q, "a": answer, "passages": passages, "log_id": log_id})

for n, m in enumerate(chat):
    if "q" not in m:  # bỏ dữ liệu hội thoại dạng cũ trong phiên
        continue
    if n == 1:
        st.markdown("##### Các câu hỏi trước")
    with st.container(border=(n == 0)):
        with st.chat_message("user"):
            st.markdown(m["q"])
        with st.chat_message("assistant"):
            st.markdown(m["a"])
            if m.get("passages"):
                show_sources(m["passages"])
            fb = st.feedback("thumbs", key=f"fb_{m['log_id']}")
            if fb is not None and m.get("fb") != fb:
                m["fb"] = fb
                execute("UPDATE tl_nhat_ky SET danh_gia=? WHERE id=?", (1 if fb == 1 else -1, m["log_id"]))
