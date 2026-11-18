# -*- coding: utf-8 -*-
"""
TRỢ LÝ TRA CỨU (RAG đơn giản)
1. Truy xuất: BM25 trên tình huống, hỏi-đáp, kiến thức và nội dung văn bản CÒN HIỆU LỰC
   (tìm không dấu, mở rộng từ viết tắt ngành điện).
2. Sinh câu trả lời (tuỳ chọn): gọi LLM theo chuẩn OpenAI-compatible
   - On-premise: Ollama (http://localhost:11434/v1), vLLM, LM Studio...
   - Cloud có hợp đồng: bất kỳ dịch vụ có API tương thích
   Không cấu hình LLM -> chỉ hiển thị các đoạn tài liệu liên quan nhất (vẫn dùng được ngay).
Cấu hình trong config.json (tự tạo lần chạy đầu).
"""
import json
import math
import re
from collections import Counter
from datetime import date
from pathlib import Path

import requests

from db import BASE_DIR, bo_dau, query, trang_thai_hieu_luc, HL_HET

CONFIG_FILE = BASE_DIR / "config.json"
DEFAULT_CONFIG = {
    "llm": {
        "enabled": False,
        "base_url": "http://localhost:11434/v1",
        "model": "qwen2.5:7b-instruct",
        "api_key": "",
        "temperature": 0.1,
        "timeout_sec": 120,
    },
    "top_k": 6,
    # Từ viết tắt ngành điện - giống mục "abbreviations" của TTS_Doc_v2
    "abbreviations": {
        "hdmbd": "hop dong mua ban dien", "kh": "khach hang", "mkh": "ma khach hang",
        "dl": "dien luc", "cskh": "cham soc khach hang", "dtv": "dien thoai vien",
        "dmt": "dien mat troi", "dmtam": "dien mat troi mai nha", "ct": "cong to",
        "tba": "tram bien ap", "hd": "hoa don", "sh": "sinh hoat", "kd": "kinh doanh",
    },
}

STOPWORDS = set("la va cua co cac cho khi thi duoc nhung voi trong nay do de khong mot nhu ve tu se da bi".split())


def load_config():
    if not CONFIG_FILE.exists():
        CONFIG_FILE.write_text(json.dumps(DEFAULT_CONFIG, ensure_ascii=False, indent=2), encoding="utf-8")
        return DEFAULT_CONFIG
    cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8-sig"))
    merged = dict(DEFAULT_CONFIG)
    merged.update(cfg)
    merged["llm"] = {**DEFAULT_CONFIG["llm"], **cfg.get("llm", {})}
    return merged


def tokenize(text, abbr=None):
    words = re.findall(r"[a-z0-9]+", bo_dau(text))
    out = []
    for w in words:
        if abbr and w in abbr:
            out.extend(abbr[w].split())
        elif w not in STOPWORDS:
            out.append(w)
    # thêm cặp từ (tiếng Việt nhiều từ ghép: "hoa don", "cong to")
    return out + [f"{a}_{b}" for a, b in zip(out, out[1:])]


def chunk_text(text, size=900):
    """Cắt văn bản theo Điều; điều dài thì cắt tiếp theo đoạn."""
    parts = re.split(r"\n(?=\s*Điều\s+\d+)", text or "")
    chunks = []
    for p in parts:
        p = p.strip()
        while len(p) > size:
            cut = p.rfind("\n", 0, size)
            cut = cut if cut > size // 3 else size
            chunks.append(p[:cut])
            p = p[cut:].strip()
        if p:
            chunks.append(p)
    return chunks


def build_corpus():
    """Danh sách đoạn tài liệu còn hiệu lực: dict(title, text, source, kind)."""
    docs = []
    for t in query("SELECT * FROM nh_tinh_huong"):
        if trang_thai_hieu_luc(t["hieu_luc_tu"], t["hieu_luc_den"], t["het_hieu_luc"]) == HL_HET:
            continue
        docs.append({"kind": "Tình huống", "title": t["cau_hoi"],
                     "text": f"{t['cau_hoi']}\n{t['tu_goi_y']}\n{t['tra_loi']}",
                     "source": t["nguon_tai_lieu"] or "Ngân hàng tình huống", "link": t["link_wiki"],
                     "answer": t["tra_loi"]})
    for b in query("SELECT * FROM hd_bai WHERE an=0"):
        docs.append({"kind": "Hỏi-đáp", "title": b["cau_hoi"],
                     "text": f"{b['cau_hoi']}\n{b['tu_goi_y']}\n{b['tra_loi']}",
                     "source": b["nguon_tai_lieu"] or "Chuyên mục hỏi-đáp", "link": b["link_wiki"],
                     "answer": b["tra_loi"]})
    today = date.today().isoformat()
    for k in query("SELECT * FROM kt_bai WHERE (hieu_luc_tu IS NULL OR hieu_luc_tu<=?) "
                   "AND (hieu_luc_den IS NULL OR hieu_luc_den>=?)", (today, today)):
        for ch in chunk_text(k["noi_dung"]):
            docs.append({"kind": "Kiến thức", "title": k["tieu_de"], "text": f"{k['tieu_de']}\n{ch}",
                         "source": f"Kiến thức tổng hợp - {k['ap_dung']}", "link": ""})
    for v in query("SELECT * FROM van_ban WHERE noi_dung<>''"):
        if trang_thai_hieu_luc(v["hieu_luc_tu"], v["hieu_luc_den"]) == HL_HET:
            continue
        for ch in chunk_text(v["noi_dung"]):
            first = ch.splitlines()[0][:80] if ch else ""
            docs.append({"kind": "Văn bản", "title": f"{v['so_hieu']} - {first}", "text": ch,
                         "source": f"{v['so_hieu']} ({v['ten'][:60]})", "link": v["link_wiki"]})
    return docs


class BM25:
    def __init__(self, docs, abbr, k1=1.5, b=0.75):
        self.docs, self.abbr, self.k1, self.b = docs, abbr, k1, b
        self.toks = [Counter(tokenize(d["text"], abbr)) for d in docs]
        self.lens = [sum(t.values()) for t in self.toks]
        self.avg = (sum(self.lens) / len(self.lens)) if self.lens else 1
        df = Counter()
        for t in self.toks:
            df.update(t.keys())
        n = len(docs)
        self.idf = {w: math.log(1 + (n - f + 0.5) / (f + 0.5)) for w, f in df.items()}

    def search(self, q, k=6):
        qt = set(tokenize(q, self.abbr))
        scores = []
        for i, tf in enumerate(self.toks):
            s = 0.0
            for w in qt:
                if w in tf:
                    f = tf[w]
                    s += self.idf[w] * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * self.lens[i] / self.avg))
            if s > 0:
                scores.append((s, i))
        scores.sort(reverse=True)
        return [dict(self.docs[i], score=round(s, 2)) for s, i in scores[:k]]


SYSTEM_PROMPT = """Bạn là trợ lý nghiệp vụ cho Điện thoại viên và nhân viên Điện lực của EVNCPC.
Quy tắc bắt buộc:
- CHỈ trả lời dựa trên các đoạn tài liệu được cung cấp. Không dùng kiến thức bên ngoài.
- Nếu tài liệu không đủ để trả lời, nói rõ: "Không tìm thấy trong tài liệu, vui lòng liên hệ P.CSKH."
- Trả lời ngắn gọn, đúng trình tự xử lý, dùng gạch đầu dòng khi có nhiều bước.
- Ghi nguồn sau mỗi ý bằng số trong ngoặc vuông, ví dụ [1], [2]."""


def ask_llm(question, passages, cfg):
    llm = cfg["llm"]
    context = "\n\n".join(f"[{i}] ({p['kind']} - {p['source']})\n{p['text'][:1500]}"
                          for i, p in enumerate(passages, 1))
    payload = {
        "model": llm["model"], "temperature": llm["temperature"],
        "messages": [{"role": "system", "content": SYSTEM_PROMPT},
                     {"role": "user", "content": f"Tài liệu:\n{context}\n\nCâu hỏi: {question}"}],
    }
    headers = {"Content-Type": "application/json"}
    if llm.get("api_key"):
        headers["Authorization"] = f"Bearer {llm['api_key']}"
    r = requests.post(llm["base_url"].rstrip("/") + "/chat/completions", json=payload, headers=headers,
                      timeout=llm["timeout_sec"])
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]
