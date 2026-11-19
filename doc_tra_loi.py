# -*- coding: utf-8 -*-
"""
ĐỌC CÂU TRẢ LỜI THÀNH GIỌNG NÓI (TTS) cho Trợ lý tra cứu.

Cách B (chính): dùng lại engine của Callbot TTS_Doc_v2
  - Chuẩn hoá tiếng Việt: số, tiền "2.159,9037 đồng/kWh", ngày "01/11/2026", giờ "17h30",
    phần trăm, số điện thoại, viết tắt (KH, ĐL, QĐ, BCT, kWh...)  -> đọc đúng
  - Giọng vi-VN-HoaiMyNeural qua Edge TTS; dự phòng Azure Speech (nếu có key)
  - Cache MP3 theo nội dung: câu đã đọc phát lại ngay
Cách A (dự phòng): khi máy chủ không gọi được dịch vụ giọng nói -> trình duyệt tự đọc
  (Web Speech API speechSynthesis), vẫn dùng văn bản đã chuẩn hoá ở trên.

Nếu đặt file TTS_Doc_v2.py của Callbot cạnh chương trình, phần chuẩn hoá số sẽ dùng chính code đó.
"""
import asyncio
import hashlib
import json
import os
import re
from pathlib import Path
from xml.sax.saxutils import escape

from db import DATA_DIR

CACHE_DIR = Path(DATA_DIR) / "tts_cache"

TTS_DEFAULT = {
    "enabled": True,
    "voice": "vi-VN-HoaiMyNeural",
    "volume": "+0%",
    "timeout_sec": 20,
    "max_chars": 900,                 # câu trả lời dài: chỉ đọc phần đầu
    "azure": {"enabled": False, "key": "", "region": "southeastasia", "voice": "vi-VN-HoaiMyNeural"},
}
TOC_DO = {"Chậm": "-15%", "Vừa": "+0%", "Nhanh": "+15%"}

# Viết tắt: bộ của Callbot + văn bản pháp quy ngành điện
ABBR = {
    "EVNCPC": "e vê en xê pê xê", "EVN": "e vê en", "CSKH": "chăm sóc khách hàng", "MKH": "mã khách hàng",
    "SĐT": "số điện thoại", "ĐL": "Điện lực", "KH": "khách hàng", "TP.": "thành phố", "TX.": "thị xã",
    "kWh": "ki lô oát giờ", "KWh": "ki lô oát giờ", "kwh": "ki lô oát giờ", "kV": "ki lô vôn", "MVA": "mê ga vôn am pe",
    "QĐ-BCT": "quyết định Bộ Công Thương", "QĐ-TTg": "quyết định Thủ tướng", "QĐ-EVN": "quyết định e vê en",
    "TT-BCT": "thông tư Bộ Công Thương", "NĐ-CP": "nghị định Chính phủ", "QH15": "quốc hội khoá mười lăm",
    "HD-BVHTTDL": "hướng dẫn Bộ Văn hoá Thể thao và Du lịch", "VBHN-NĐ-BCT": "văn bản hợp nhất",
    "QĐ": "quyết định", "TT": "thông tư", "NĐ": "nghị định", "BCT": "Bộ Công Thương", "TTg": "Thủ tướng",
    "ĐTV": "điện thoại viên", "TT CSKH": "Trung tâm chăm sóc khách hàng", "LTDL": "lưu trú du lịch",
    "CSLTDL": "cơ sở lưu trú du lịch", "KDDV": "kinh doanh dịch vụ", "GCS": "ghi chỉ số", "SHBT": "sinh hoạt bậc thang",
    "VAT": "thuế giá trị gia tăng", "GTGT": "giá trị gia tăng", "HĐMBĐ": "hợp đồng mua bán điện",
    "PC": "công ty điện lực", "CTĐL": "công ty điện lực", "VB": "văn bản",
}

# ------------------------------------------------------------------ Đọc số (theo TTS_Doc_v2)
try:  # ưu tiên dùng đúng code Callbot nếu có file TTS_Doc_v2.py cạnh chương trình
    from TTS_Doc_v2 import number_to_vietnamese, spell_digits, month_words  # noqa: F401
except Exception:
    DIGITS = ["không", "một", "hai", "ba", "bốn", "năm", "sáu", "bảy", "tám", "chín"]

    def _two(n):
        t, o = divmod(n, 10)
        if t == 0:
            return DIGITS[o]
        if t == 1:
            return "mười" if o == 0 else ("mười lăm" if o == 5 else "mười " + DIGITS[o])
        r = DIGITS[t] + " mươi"
        return r if o == 0 else r + " " + {1: "mốt", 5: "lăm"}.get(o, DIGITS[o])

    def _three(n, full):
        h, rest = divmod(n, 100)
        if h == 0 and not full:
            return _two(rest) if rest else ""
        r = DIGITS[h] + " trăm"
        if rest == 0:
            return r
        return r + (" lẻ " + DIGITS[rest] if rest < 10 else " " + _two(rest))

    def _below_billion(n, full):
        parts = []
        for v, unit in ((n // 1_000_000, "triệu"), ((n // 1000) % 1000, "ngàn"), (n % 1000, "")):
            if v:
                parts.append(f"{_three(v, full or bool(parts))} {unit}".strip())
        return " ".join(parts)

    def number_to_vietnamese(number):
        try:
            n = int(str(number).strip())
        except Exception:
            return str(number)
        if n == 0:
            return "không"
        if n < 0:
            return "âm " + number_to_vietnamese(-n)
        if n >= 1_000_000_000:
            hi, lo = divmod(n, 1_000_000_000)
            return number_to_vietnamese(hi) + " tỷ" + (" " + _below_billion(lo, True) if lo else "")
        return _below_billion(n, False)

    def spell_digits(digits, group=None):
        words = [DIGITS[int(c)] for c in digits if c.isdigit()]
        if not group:
            return " ".join(words)
        chunks, i = [], 0
        for size in group:
            if i >= len(words):
                break
            chunks.append(" ".join(words[i:i + size]))
            i += size
        if i < len(words):
            chunks.append(" ".join(words[i:]))
        return ", ".join(chunks)

    def month_words(m):
        return "tư" if m == 4 else number_to_vietnamese(m)


# ------------------------------------------------------------------ Làm sạch Markdown -> lời đọc
def lam_sach(md, max_chars=900):
    """Câu trả lời (Markdown) -> văn bản để đọc: bỏ định dạng, bảng, nguồn, danh sách liên quan."""
    text = str(md or "")
    text = re.split(r"\*\*Nội dung liên quan khác", text)[0]          # bỏ danh sách tham khảo
    text = re.sub(r"\*\*Nội dung phù hợp nhất\*\*\s*\([^)]*\):?", "", text)
    text = re.sub(r":gray\[[^\]]*\]", "", text)                        # dòng "Nguồn: ..."
    lines, in_table = [], False
    for ln in text.splitlines():
        s = ln.strip()
        if s.startswith("|"):
            if not in_table:
                lines.append("Phần bảng số liệu, mời xem trên màn hình.")
            in_table = True
            continue
        in_table = False
        if re.match(r"^\[\d+\]", s):
            continue
        s = re.sub(r"^#{1,6}\s*", "", s)                                 # tiêu đề
        s = re.sub(r"^[-*+]\s+", "", s)                                  # gạch đầu dòng
        s = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", s)                        # ảnh
        s = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", s)                   # link -> chữ
        s = re.sub(r"https?://\S+", "", s)
        s = s.replace("**", "").replace("__", "").replace("`", "").replace("*", "")
        s = re.sub(r":[a-z]+-badge\[([^\]]*)\]", r"\1", s)
        s = re.sub(r"[→⇒➔]", ", ", s)
        s = re.sub(r"[~|<>]", " ", s)
        if s:
            lines.append(s)
    text = "\n".join(lines).strip()
    if len(text) > max_chars:
        cut = text[:max_chars]
        end = max(cut.rfind(". "), cut.rfind(".\n"), cut.rfind("; "), cut.rfind("\n"))
        text = (cut[:end + 1] if end > max_chars // 2 else cut) + "\nPhần còn lại mời xem trên màn hình."
    return text


# ------------------------------------------------------------------ Chuẩn hoá (theo TextNormalizer của Callbot)
def _so_vn(raw):
    """'2.159,9037' -> 'hai ngàn một trăm năm mươi chín phẩy chín không ba bảy'."""
    nguyen, _, le = raw.partition(",")
    s = number_to_vietnamese(nguyen.replace(".", ""))
    return s + (" phẩy " + spell_digits(le) if le else "")


def chuan_hoa(text):
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in str(text).splitlines()]
    lines = [ln if ln[-1] in ".!?;:," else ln + "." for ln in lines if ln]
    t = " ".join(lines)
    # văn bản pháp quy: "2892/QĐ-BCT" -> "2892, quyết định Bộ Công Thương"; "61/2024/QH15"
    t = re.sub(r"\b(\d+)/(\d{4})/([A-ZĐa-z0-9-]+)", r"\1 năm \2 \3", t)
    t = re.sub(r"\b(\d+)/([A-ZĐ][A-ZĐa-z-]+)", r"\1, \2", t)
    t = re.sub(r"/(kWh|kwh|KWh)\b", " một ki lô oát giờ", t)
    t = re.sub(r"/(ngày|tháng|năm|hộ|người|kỳ|lần)\b", r" một \1", t)
    t = re.sub(r"(?<=\d)\s*-\s*(?=\d)", " đến ", t)                      # 17h30-22h30, 0-100
    t = re.sub(r"(?<![\w\d])-\s?(?=\d)", "âm ", t)
    for short, full in sorted(ABBR.items(), key=lambda kv: -len(kv[0])):
        t = re.sub(r"(?<!\w)" + re.escape(short) + r"(?!\w)", full, t)
    # số điện thoại, tổng đài
    t = re.sub(r"(?<![\d.,])(?:0\d{9,10}|1[89]00\d{4})(?!\d|[.,]\d)",
               lambda m: spell_digits(m.group(0), (4, 4) if m.group(0)[:2] in ("19", "18") else (4, 3, 3)), t)
    t = re.sub(r"(?<![\d.,])1558(?![\d.,])", "một năm năm tám", t)
    # ngày tháng
    def d3(m):
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return (f"ngày {number_to_vietnamese(d)} tháng {month_words(mo)} năm {number_to_vietnamese(y)}"
                if 1 <= d <= 31 and 1 <= mo <= 12 else m.group(0))
    t = re.sub(r"(?:ngày\s+)?\b(\d{1,2})/(\d{1,2})/(\d{4})\b", d3, t, flags=re.I)
    t = re.sub(r"(?:tháng\s+)?\b(\d{1,2})/(\d{4})\b",
               lambda m: f"tháng {month_words(int(m.group(1)))} năm {number_to_vietnamese(m.group(2))}"
               if 1 <= int(m.group(1)) <= 12 else m.group(0), t, flags=re.I)
    t = re.sub(r"(?:ngày\s+)?\b(\d{1,2})/(\d{1,2})\b",
               lambda m: f"ngày {number_to_vietnamese(m.group(1))} tháng {month_words(int(m.group(2)))}"
               if 1 <= int(m.group(1)) <= 31 and 1 <= int(m.group(2)) <= 12 else m.group(0), t, flags=re.I)
    # giờ
    def gio(m):
        h, mi = int(m.group(1)), int(m.group(2) or 0)
        if h > 24 or mi > 59:
            return m.group(0)
        return f"{number_to_vietnamese(h)} giờ" + (f" {number_to_vietnamese(mi)} phút" if mi else "")
    t = re.sub(r"\b(\d{1,2})\s?[hH](\d{2})?(?![\w])", gio, t)
    t = re.sub(r"\b(\d{1,2}):(\d{2})\b", gio, t)
    # số kiểu Việt Nam: 2.159,9037 ; 1.420.500 ; 0,97 ; phần trăm
    t = re.sub(r"(?<![\d.,])(\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+,\d+)\s?%",
               lambda m: _so_vn(m.group(1)) + " phần trăm", t)
    t = re.sub(r"(?<![\d.,])(\d+)\s?%", lambda m: number_to_vietnamese(m.group(1)) + " phần trăm", t)
    t = re.sub(r"(?<![\d.,])(\d{1,3}(?:\.\d{3})+(?:,\d+)?)(?![\d])", lambda m: _so_vn(m.group(1)), t)
    t = re.sub(r"(?<![\d.,])(\d+),(\d+)(?![\d])", lambda m: _so_vn(m.group(0)), t)
    t = re.sub(r"\bđ\b", "đồng", t)
    def so(m):
        s = m.group(0)
        if s.startswith("0") and 1 < len(s) <= 3:
            return number_to_vietnamese(s)                 # 05 giờ -> năm giờ
        return spell_digits(s) if (len(s) > 1 and s.startswith("0")) or len(s) > 15 else number_to_vietnamese(s)
    t = re.sub(r"\d+", so, t)
    t = t.replace("/", " trên ").replace("&", " và ")
    return re.sub(r"\s+", " ", t).strip()


# ------------------------------------------------------------------ Tạo MP3 (Edge TTS -> Azure)
def _cfg():
    from ai_assistant import load_config
    c = load_config().get("tts", {})
    merged = {**TTS_DEFAULT, **c}
    merged["azure"] = {**TTS_DEFAULT["azure"], **c.get("azure", {})}
    return merged


async def _edge(text, cfg, rate):
    import edge_tts
    com = edge_tts.Communicate(text=text, voice=cfg["voice"], rate=rate, volume=cfg["volume"])
    buf = bytearray()
    async for chunk in com.stream():
        if chunk.get("type") == "audio":
            buf.extend(chunk["data"])
    if len(buf) < 500:
        raise RuntimeError("Edge TTS trả về dữ liệu rỗng")
    return bytes(buf)


def _azure(text, cfg, rate):
    import requests
    az = cfg["azure"]
    key = az.get("key") or os.environ.get("AZURE_SPEECH_KEY", "")
    if not (az.get("enabled") and key):
        raise RuntimeError("Chưa bật Azure")
    ssml = (f"<speak version='1.0' xml:lang='vi-VN'><voice name='{az['voice']}'>"
            f"<prosody rate='{rate}'>{escape(text)}</prosody></voice></speak>")
    r = requests.post(f"https://{az['region']}.tts.speech.microsoft.com/cognitiveservices/v1",
                      data=ssml.encode("utf-8"), timeout=cfg["timeout_sec"],
                      headers={"Ocp-Apim-Subscription-Key": key, "Content-Type": "application/ssml+xml",
                               "X-Microsoft-OutputFormat": "audio-24khz-48kbitrate-mono-mp3"})
    if r.status_code != 200 or len(r.content) < 500:
        raise RuntimeError(f"Azure HTTP {r.status_code}")
    return r.content


def tao_giong_doc(answer_md, toc_do="Vừa"):
    """-> dict(spoken=văn bản đã chuẩn hoá, mp3=đường dẫn hoặc None, engine, loi)."""
    cfg = _cfg()
    spoken = chuan_hoa(lam_sach(answer_md, cfg["max_chars"]))
    rate = TOC_DO.get(toc_do, "+0%")
    out = {"spoken": spoken, "mp3": None, "engine": "", "loi": ""}
    if not spoken or not cfg.get("enabled", True):
        out["loi"] = "Đã tắt TTS máy chủ trong config.json" if spoken else "Không có nội dung để đọc"
        return out
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha1("|".join([spoken, cfg["voice"], rate, cfg["volume"]]).encode("utf-8")).hexdigest()
    path = CACHE_DIR / f"{key}.mp3"
    if path.exists() and path.stat().st_size > 500:
        return {**out, "mp3": str(path), "engine": "cache"}
    errors = []
    try:
        data = asyncio.run(asyncio.wait_for(_edge(spoken, cfg, rate), timeout=cfg["timeout_sec"]))
        engine = "edge"
    except Exception as e:
        msg = f"{type(e).__name__} {e}"
        if isinstance(e, ModuleNotFoundError):
            why = "chưa cài thư viện edge-tts (chạy: python -m pip install edge-tts)"
        elif "Application Control" in msg or "DLL load failed" in msg:
            why = "Windows chặn thư viện aiohttp của edge-tts (cần CNTT cho phép)"
        elif any(k in msg for k in ("DNS", "Cannot connect", "Timeout", "TimeoutError", "getaddrinfo")):
            why = "máy chủ không kết nối được Internet tới speech.platform.bing.com"
        elif "403" in msg:
            why = "dịch vụ từ chối (403): cập nhật edge-tts (pip install -U edge-tts) và đồng bộ giờ máy"
        else:
            why = msg[:120]
        errors.append(f"Edge TTS: {why}")
        try:
            data, engine = _azure(spoken, cfg, rate), "azure"
        except Exception as e2:
            if "Chưa bật Azure" not in str(e2):
                errors.append(f"Azure: {str(e2)[:120]}")
            return {**out, "loi": " | ".join(errors)}
    tmp = path.with_suffix(".part")
    tmp.write_bytes(data)
    os.replace(tmp, path)
    return {**out, "mp3": str(path), "engine": engine}


def html_giong_trinh_duyet(spoken, toc_do="Vừa"):
    """Cách A: trình duyệt tự đọc (speechSynthesis) văn bản đã chuẩn hoá.
    Chỉ đọc khi trình duyệt có giọng tiếng Việt: Edge có sẵn giọng online (HoaiMy, NamMinh);
    Chrome dùng giọng của Windows -> cần cài giọng tiếng Việt cho Windows."""
    rate = {"Chậm": 0.85, "Vừa": 1.0, "Nhanh": 1.15}.get(toc_do, 1.0)
    return """<!DOCTYPE html><html><body style="margin:0;font-family:'Source Sans Pro',system-ui,sans-serif;font-size:14px;color:#31333F">
<button id="b" style="font:inherit;font-weight:600;padding:.35rem .8rem;border-radius:6px;border:1px solid #ccc;background:#fff;cursor:pointer">▶ Đọc bằng giọng máy tính</button>
<button id="s" style="font:inherit;padding:.35rem .8rem;border-radius:6px;border:1px solid #ccc;background:#fff;cursor:pointer">■ Dừng</button>
<div id="m" style="margin-top:.35rem;color:#6b6f7b;font-size:13px"></div>
<script>
var T=%s, R=%s, m=document.getElementById('m');
function post(h){ window.parent.postMessage({isStreamlitMessage:true,type:"streamlit:setFrameHeight",height:h},"*"); }
function fit(){ post(document.documentElement.scrollHeight); }
function getVoices(cb){
  var v=speechSynthesis.getVoices(); if(v.length){ cb(v); return; }
  var done=false; speechSynthesis.onvoiceschanged=function(){ if(!done){ done=true; cb(speechSynthesis.getVoices()); } };
  setTimeout(function(){ if(!done){ done=true; cb(speechSynthesis.getVoices()); } }, 1500);
}
function pick(vs){
  var vi=vs.filter(function(x){ return /^vi([-_]|$)/i.test(x.lang); });
  return vi.find(function(x){ return /natural|online|hoaimy|namminh/i.test(x.name); }) || vi[0] || null;
}
function sentences(t){ return t.match(/[^.!?;:]+[.!?;:]*/g) || [t]; }
document.getElementById('b').onclick=function(){
  if(!window.speechSynthesis){ m.textContent='Trình duyệt này không hỗ trợ đọc văn bản.'; fit(); return; }
  speechSynthesis.cancel(); m.textContent='Đang tìm giọng tiếng Việt…';
  getVoices(function(vs){
    var v=pick(vs);
    if(!v){
      m.innerHTML='Máy này chưa có giọng đọc tiếng Việt nên không đọc được.<br>'
        + 'Cách 1: mở chương trình bằng trình duyệt <b>Microsoft Edge</b> (có sẵn giọng HoaiMy).<br>'
        + 'Cách 2: cài giọng cho Windows: Cài đặt → Thời gian và ngôn ngữ → Giọng nói → Thêm giọng nói → Tiếng Việt, rồi mở lại trình duyệt.';
      fit(); return;
    }
    m.textContent='Đang đọc bằng giọng: '+v.name; fit();
    sentences(T).forEach(function(p){ p=p.trim(); if(!p) return;
      var u=new SpeechSynthesisUtterance(p); u.voice=v; u.lang=v.lang; u.rate=R; speechSynthesis.speak(u); });
  });
};
document.getElementById('s').onclick=function(){ if(window.speechSynthesis) speechSynthesis.cancel(); m.textContent=''; fit(); };
fit();
</script></body></html>""" % (json.dumps(spoken, ensure_ascii=False), rate)
