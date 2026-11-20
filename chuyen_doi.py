# -*- coding: utf-8 -*-
"""
CHUYỂN FILE EXCEL BẤT KỲ -> FILE MẪU 3 SHEET (VanBan / KienThuc / TinhHuong)

Cách làm (không cần AI, chạy offline):
  1. Đọc từng sheet: ô gộp, tiêu đề 2 tầng, nhóm dòng theo cột khoá (STT / Điều), dòng mục lớn (I, II...).
  2. Nhận dạng kiểu sheet:
       hoi_dap      : có cột Câu hỏi + Trả lời            -> Tình huống
       so_sanh      : 2 bên Điều/Nội dung (mới - cũ)       -> Kiến thức (mỗi Điều 1 bài)
       danh_muc_vb  : có cột Văn bản + Hiệu lực            -> Văn bản
       theo_dong    : bảng mô tả thông thường              -> Kiến thức (mỗi dòng / nhóm dòng 1 bài)
       bang_so_lieu : bảng số (biểu giá, công cụ tính...)  -> Kiến thức (cả sheet thành 1 bảng)
       ai           : nhờ AI đọc (khi đã cấu hình LLM)     -> kiểm tra số liệu với file gốc
       bo_qua
  3. Giữ màu chữ: xanh -> **đậm** (nội dung mới/điều chỉnh), đỏ -> ~~gạch~~ (bãi bỏ/thay đổi), tím -> *nghiêng*.
  4. Tạo Mã ổn định theo nội dung khoá (số hiệu, Điều, mục.STT), ghi Vị trí nguồn.

CLI: python chuyen_doi.py file_goc.xlsx [TIEN_TO] [file_ra.xlsx]
"""
import datetime as dt
import io
import json
import re
import sys
import unicodedata

import openpyxl
from openpyxl.cell.rich_text import CellRichText, TextBlock
from openpyxl.utils import get_column_letter

KIEU = {
    "hoi_dap": "Hỏi - đáp → Tình huống",
    "so_sanh": "So sánh mới/cũ → Kiến thức",
    "danh_muc_vb": "Danh mục văn bản → Văn bản",
    "theo_dong": "Mỗi dòng 1 bài → Kiến thức",
    "bang_so_lieu": "Bảng số liệu → 1 bài Kiến thức",
    "ai": "🤖 Nhờ AI đọc",
    "bo_qua": "Bỏ qua",
}
NGHIEP_VU_TU_KHOA = [
    ("Giá điện", ["gia ban dien", "gia dien", "bieu gia", "bac thang", "cong suat phan khang", "gio cao diem"]),
    ("Ngừng, giảm cung cấp điện", ["ngung, giam", "ngung giam", "ngung cap dien", "giam muc cung cap"]),
    ("Ghi chỉ số - Công tơ", ["ghi chi so", "cong to", "do dem", "thiet bi do"]),
    ("Hoá đơn - Thu tiền", ["thanh toan tien dien", "hoa don", "thu tien", "cham tra"]),
    ("Hợp đồng mua bán điện", ["hop dong mua ban dien", "giao ket hop dong", "hdmbd"]),
    ("Điện mặt trời áp mái", ["mat troi", "tu san xuat, tu tieu thu", "nang luong tai tao"]),
    ("Cấp điện mới", ["cap dien moi", "dau noi"]),
]
RE_SO_HIEU = re.compile(r"\b(\d{1,4}/\d{4}/[A-Za-zĐđ][A-Za-zĐđ0-9]*(?:-[A-Za-zĐđ0-9]+)*)")
LOAI_VB_HOP_LE = {"TT", "QĐ", "NĐ", "NQ", "CT", "HD", "CV", "TB", "TTLT", "BC", "KH"}
MAU = {"xanh": ("**", "**"), "do": ("~~", "~~"), "tim": ("*", "*")}


# ------------------------------------------------------------------ tiện ích chữ
def bo_dau(s):
    s = unicodedata.normalize("NFD", str(s or "")).replace("đ", "d").replace("Đ", "D")
    return "".join(ch for ch in s if unicodedata.category(ch) != "Mn").lower()


def _sach(s):
    s = str(s or "").replace("\xa0", " ").replace("\r", "")
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in s.split("\n")]
    out = []
    for ln in lines:
        if ln or (out and out[-1]):
            out.append(ln)
    return "\n".join(out).strip()


def _so_dep(v, fmt=""):
    if isinstance(v, bool):
        return str(v)
    if "%" in (fmt or "") and isinstance(v, (int, float)):
        return f"{v * 100:.2f}".rstrip("0").rstrip(".").replace(".", ",") + "%"
    if isinstance(v, int) or (isinstance(v, float) and v.is_integer()):
        return f"{int(v):,}".replace(",", ".")
    if isinstance(v, float):
        s = f"{v:,.4f}".rstrip("0").rstrip(".")
        return s.replace(",", "§").replace(".", ",").replace("§", ".")
    return str(v)


def _mau(font):
    try:
        c = font.color
        if c is None or c.type != "rgb" or not isinstance(c.rgb, str):
            return None
        rgb = c.rgb[-6:].upper()
    except Exception:
        return None
    r, g, b = int(rgb[0:2], 16), int(rgb[2:4], 16), int(rgb[4:6], 16)
    if r > 150 and g < 90 and b < 90:
        return "do"
    if b > 150 and r < 90:
        return "xanh"
    if r > 90 and b > 120 and g < 90:
        return "tim"
    return None


def _boc(text, kieu):
    """Bọc dấu markdown theo từng dòng (dấu ** không được vắt qua xuống dòng)."""
    if not kieu:
        return text
    a, b = MAU[kieu]
    out = []
    for ln in text.split("\n"):
        m = re.match(r"^(\s*)(.*?)(\s*)$", ln, re.S)
        out.append(f"{m.group(1)}{a}{m.group(2)}{b}{m.group(3)}" if m.group(2) else ln)
    return "\n".join(out)


def _gia_tri(cell, giu_mau=True):
    """-> (chữ thuần, chữ có đánh dấu màu)."""
    v = cell.value
    if v is None:
        return "", ""
    if isinstance(v, CellRichText):
        runs = []
        for blk in v:
            if isinstance(blk, TextBlock):
                runs.append((blk.text, _mau(blk.font) if giu_mau else None))
            else:
                runs.append((str(blk), _mau(cell.font) if giu_mau else None))
        gop = []
        for t, k in runs:
            if gop and gop[-1][1] == k:
                gop[-1] = (gop[-1][0] + t, k)
            else:
                gop.append((t, k))
        thuan = "".join(t for t, _ in gop)
        co_mau = "".join(_boc(t, k) for t, k in gop)
        return _sach(thuan), _sach(co_mau)
    if isinstance(v, (dt.datetime, dt.date)):
        s = v.strftime("%d/%m/%Y")
        return s, s
    if isinstance(v, (int, float)):
        s = _so_dep(v, cell.number_format)
        return s, s
    s = _sach(v)
    return s, _sach(_boc(s, _mau(cell.font) if giu_mau else None))


def _so_hieu(text):
    out = []
    for m in RE_SO_HIEU.finditer(text or ""):
        sh = m.group(1).rstrip(".,;")
        out.append(sh)
    return out


def _chuan_so_hieu(sh):
    """Viết hoa phần chữ; trả (số hiệu, cảnh báo)."""
    so, nam, loai = sh.split("/", 2)
    loai_up = loai.upper()
    canh_bao = None
    dau = loai_up.split("-")[0]
    if not (re.fullmatch(r"QH\d+", loai_up) or dau in LOAI_VB_HOP_LE):
        canh_bao = f"số hiệu '{sh}' có ký hiệu lạ ('{loai}') - kiểm tra lại lỗi gõ"
    return f"{so}/{nam}/{loai_up}".replace("-TTG", "-TTg"), canh_bao


def _ngay(text, sau=r"(?:hiệu lực|từ ngày|kể từ)"):
    for m in re.finditer(sau + r"[^0-9]{0,40}(\d{1,2})/(\d{1,2})/(\d{4})", text or "", re.I):
        if re.search(r"hết\s*$", (text or "")[max(0, m.start() - 6):m.start()], re.I):
            continue                      # "hết hiệu lực từ ngày..." không phải ngày bắt đầu
        return f"{int(m.group(1)):02d}/{int(m.group(2)):02d}/{m.group(3)}"
    return ""


def _thuong(s):
    """'LUẬT ĐIỆN LỰC SỐ 61/2024/QH15 / (Có hiệu lực...)' -> 'Luật điện lực số 61/2024/QH15'."""
    s = re.split(r"\s+/\s+|\s*\(", (s or "").split("\n")[0])[0].strip()
    chu = [ch for ch in s if ch.isalpha()]
    if chu and sum(ch.isupper() for ch in chu) / len(chu) > 0.7:
        s = s.lower()
        s = s[:1].upper() + s[1:]
        s = RE_SO_HIEU.sub(lambda m: m.group(1).upper(), s)
        s = re.sub(r"\b(nđ|qđ|tt|bct|ttg|evn|cp|qh)\b", lambda m: m.group(1).upper(), s)
    return s


def _ngay_bh(text):
    m = re.search(r"ngày\s+(\d{1,2})/(\d{1,2})/(\d{4})", text or "", re.I)
    return f"{int(m.group(1)):02d}/{int(m.group(2)):02d}/{m.group(3)}" if m else ""


def _nghiep_vu(text, tieu=""):
    t, td = bo_dau(text), bo_dau(tieu)
    best, n = "Khác", 0
    for nv, kws in NGHIEP_VU_TU_KHOA:
        k = sum(t.count(w) + 3 * td.count(w) for w in kws)
        if k > n:
            best, n = nv, k
    return best


def _ma_sheet(name):
    w = re.findall(r"[A-Za-z0-9]+", bo_dau(name).upper())
    if not w:
        return "S"
    if len(w) <= 2 and sum(map(len, w)) <= 10:
        return "".join(w)
    return "".join(x[0] for x in w)[:8]


def tien_to_mac_dinh(ten_file):
    s = re.sub(r"\.xlsx?$", "", ten_file or "", flags=re.I)
    s = re.sub(r"(?i)^(ban[ _]goc[ _]*)", "", bo_dau(s).upper())
    w = [x for x in re.findall(r"[A-Z]+|\d{4}", s) if x not in ("NGAY", "V")]
    nam = next((x for x in w if x.isdigit()), "")
    chu = [x for x in w if not x.isdigit()]
    goc = chu[0][:10] if len(chu) == 1 else "".join(x[0] for x in chu)[:6]
    return (goc + nam) or "BO1"


def _vai_tro(label):
    t = bo_dau(label)
    if re.fullmatch(r"\s*(stt|tt)\s*", t):
        return "stt"
    if "cau hoi" in t or "tinh huong" in t:
        return "cau_hoi"
    if "tra loi" in t:
        return "tra_loi"
    if "ghi chu" in t or "luu y" in t:
        return "ghi_chu"
    if re.match(r"\s*dieu\b", t):
        return "dieu"
    if "hieu luc" in t:
        return "hieu_luc"
    if re.fullmatch(r"\s*van ban\s*", t):
        return "van_ban"
    if "noi dung" in t or "chi tiet" in t:
        return "noi_dung"
    return "khac"


def _la_nhan(s):
    s = (s or "").strip()
    return 0 < len(s) <= 60 and not s.endswith((".", ";", ":")) and s.count(" ") <= 9


ROMAN = re.compile(r"^(?=[IVXLC]+\.?$)[IVXLC]+\.?$")


# ------------------------------------------------------------------ đọc 1 sheet
class Sheet:
    def __init__(self, ws, cong_thuc=0):
        self.cong_thuc = cong_thuc
        self.ten = ws.title
        self.ws = ws
        nr, nc = ws.max_row, ws.max_column
        self.raw = [[("", "")] * (nc + 1) for _ in range(nr + 1)]   # 1-based
        self.fill = [[""] * (nc + 1) for _ in range(nr + 1)]
        self.so = 0
        self.tong = 0
        for row in ws.iter_rows(min_row=1, max_row=nr, max_col=nc):
            for c in row:
                if c.value is None or not hasattr(c, "column"):
                    continue
                t, m = _gia_tri(c)
                if not t:
                    continue
                self.raw[c.row][c.column] = (t, m)
                self.fill[c.row][c.column] = t
                self.tong += 1
                if isinstance(c.value, (int, float)) and not isinstance(c.value, bool):
                    self.so += 1
        self.gop = {}            # (r,c) -> range
        for rg in ws.merged_cells.ranges:
            t = self.raw[rg.min_row][rg.min_col][0] if rg.min_row <= nr and rg.min_col <= nc else ""
            for r in range(rg.min_row, min(rg.max_row, nr) + 1):
                for c in range(rg.min_col, min(rg.max_col, nc) + 1):
                    self.gop[(r, c)] = rg
                    if t:
                        self.fill[r][c] = t
        self.nr, self.nc = nr, nc
        self._tieu_de()

    def o(self, r, c, mau=True):
        return self.raw[r][c][1 if mau else 0]

    def hang(self, r):
        return [c for c in range(1, self.nc + 1) if self.raw[r][c][0]]

    def _tieu_de(self):
        # dòng tiêu đề cột: dòng có nhiều nhãn ngắn nhất trong 15 dòng đầu
        best, h = 1, None
        for r in range(1, min(self.nr, 15) + 1):
            k = sum(1 for c in self.hang(r) if _la_nhan(self.raw[r][c][0]))
            if k >= 2 and k > best:
                best, h = k, r
        self.h = h
        self.dau = (h or 0) + 1
        self.nhan = {}
        self.nhom = {}
        if not h:
            return
        sub = False
        if h + 1 <= self.nr:
            doc = sum(1 for c in self.hang(h) if (h, c) in self.gop and self.gop[(h, c)].max_row > h)
            if doc >= 2:
                sub = True
        for c in range(1, self.nc + 1):
            phan = []
            if h > 1 and (h - 1, c) in self.gop:
                rg = self.gop[(h - 1, c)]
                rong = max(self.hang(h)) - min(self.hang(h)) + 1
                if rg.max_col > rg.min_col and rg.max_row == h - 1 and (rg.max_col - rg.min_col + 1) < 0.8 * rong:
                    self.nhom[c] = self.fill[h - 1][c]
            if not self.fill[h][c] and h > 1 and (h - 1, c) in self.gop and self.gop[(h - 1, c)].max_row >= h:
                phan.append(self.fill[h - 1][c])
            if self.fill[h][c]:
                phan.append(self.fill[h][c])
            if sub and self.raw[h + 1][c][0] and not ((h + 1, c) in self.gop and self.gop[(h + 1, c)].min_row <= h):
                phan.append(self.raw[h + 1][c][0])
            if phan:
                self.nhan[c] = " / ".join(dict.fromkeys(p.replace("\n", " ") for p in phan))
        self.dau = h + (2 if sub else 1)
        self.tieu_de_tren = []
        for r in range(1, h):
            for c in self.hang(r):
                if c in self.nhom and r == h - 1:
                    continue
                self.tieu_de_tren.append(self.raw[r][c][0])

    @property
    def tieu_de(self):
        if self.h:
            t = [x for x in self.tieu_de_tren if not bo_dau(x).startswith("ghi chu")]
            return t[0].replace("\n", " ") if t else self.ten
        for r in range(1, self.nr + 1):
            if self.hang(r):
                return self.raw[r][self.hang(r)[0]][0].replace("\n", " ")
        return self.ten

    def vai_tro(self):
        out = {}
        for c, lb in self.nhan.items():
            out.setdefault(_vai_tro(lb), []).append(c)
        return out

    def ty_le_so(self):
        return self.so / self.tong if self.tong else 0

    def doan_kieu(self):
        if self.tong < 2:
            return "bo_qua", "sheet gần như trống (có thể chỉ chứa hình ảnh)"
        vt = self.vai_tro()
        if "cau_hoi" in vt and "tra_loi" in vt:
            return "hoi_dap", ""
        nhan_nd = [bo_dau(self.nhan[c]).strip() for k in ("noi_dung", "dieu") for c in vt.get(k, [])]
        if len(vt.get("dieu", [])) >= 2 or len(nhan_nd) > len(set(nhan_nd)):
            return "so_sanh", ""
        if "van_ban" in vt and "hieu_luc" in vt:
            return "danh_muc_vb", ""
        if self.cong_thuc > 0.3 * max(self.so, 1) and any(
                "nhap " in bo_dau(self.raw[r][c][0]) for r in range(1, min(self.nr, 12) + 1) for c in self.hang(r)):
            return "bo_qua", "sheet công cụ tính (ô nhập + công thức) - ĐTV dùng trực tiếp file Excel"
        if not self.h or self.ty_le_so() > 0.3 or len(self.nhan) > 10:
            return "bang_so_lieu", "nhiều số / nhiều cột"
        return "theo_dong", ""

    # ---- nhóm dòng thành mục
    def cot_khoa(self):
        vt = self.vai_tro()
        for k in ("stt", "dieu", "cau_hoi"):
            if k in vt:
                return min(vt[k])
        return min(self.nhan) if self.nhan else 1

    def muc(self):
        """-> list[{dong_dau, dong_cuoi, nhom, ghi_chu_nhom}]"""
        k = self.cot_khoa()
        cot = sorted(self.nhan)
        out, nhom, ghi_nhom = [], "", ""
        for r in range(self.dau, self.nr + 1):
            co = self.hang(r)
            if not co:
                continue
            kv = self.raw[r][k][0]
            khac = [c for c in co if c != k]
            if kv and ROMAN.match(kv.strip()) and len(khac) <= 1:
                nhom, ghi_nhom = kv.strip().rstrip("."), (self.raw[r][khac[0]][0] if khac else "")
                continue
            if kv and not khac and len(kv) > 12:          # dòng ghi chú gộp ngang
                ghi_nhom = (ghi_nhom + "\n" + kv).strip()
                continue
            if kv and (r, k) in self.gop and self.gop[(r, k)].min_row < r:
                kv = ""
            if kv or not out:
                out.append({"dau": r, "cuoi": r, "nhom": nhom, "ghi_nhom": ghi_nhom})
            else:
                out[-1]["cuoi"] = r
        _ = cot
        return out

    def chu_cot(self, m, c, mau=True, sep="\n"):
        vals = []
        for r in range(m["dau"], m["cuoi"] + 1):
            if (r, c) in self.gop and self.gop[(r, c)].min_row < r:
                continue
            v = self.o(r, c, mau)
            if v:
                vals.append(v)
        return sep.join(vals)

    def vi_tri(self, m, c=None):
        c = c or min(self.nhan or {1: 0})
        a = f"{get_column_letter(c)}{m['dau']}"
        return f"{self.ten}!{a}" + (f":{get_column_letter(self.nc)}{m['cuoi']}" if m["cuoi"] > m["dau"] else "")


def _md(text):
    """Xuống dòng trong ô -> xuống dòng markdown."""
    return "  \n".join((text or "").split("\n"))


def _co_mau(s):
    return "**" in s or "~~" in s


# ------------------------------------------------------------------ chuyển từng kiểu
def _hoi_dap(sh, P, ctx):
    vt = sh.vai_tro()
    cq, ca = vt["cau_hoi"][0], vt["tra_loi"][0]
    ghi = vt.get("ghi_chu", [])
    ngoai = [c for c in range(1, sh.nc + 1) if c not in sh.nhan]
    ma_s = "" if ctx["so_sheet_hd"] == 1 else _ma_sheet(sh.ten) + "-"
    out, dem = [], {}
    k = sh.cot_khoa()
    for m in sh.muc():
        q = sh.chu_cot(m, cq, mau=False, sep=" ")
        if not q:
            continue
        a = _md(sh.chu_cot(m, ca))
        for c in ghi + ngoai:
            t = sh.chu_cot(m, c)
            if t:
                a += f"\n\n**{sh.nhan.get(c, 'Ghi chú thêm')}:** " + _md(t)
        stt = sh.raw[m["dau"]][k][0].strip().rstrip(".") if k != cq else ""
        dem[m["nhom"]] = dem.get(m["nhom"], 0) + 1
        so = stt if stt.isdigit() else str(dem[m["nhom"]])
        key = (f"{m['nhom']}." if m["nhom"] else "") + so.zfill(2)
        out.append({"ma": f"{P}-TH-{ma_s}{key}", "cau_hoi": q.strip(), "tra_loi": a.strip(),
                    "tu_goi_y": m["ghi_nhom"].replace("\n", " ")[:120], "nghiep_vu": _nghiep_vu(a, q),
                    "nguon_tai_lieu": f"{ctx['ten_tai_lieu']} - sheet {sh.ten}", "so_hieu": "",
                    "nguon_vi_tri": sh.vi_tri(m, cq)})
    return {"tinh_huong": out}


def _ben(sh):
    """Chia cột thành bên mới (0) / bên cũ (1) theo lần xuất hiện vai trò."""
    vt_cot = {c: _vai_tro(lb) for c, lb in sh.nhan.items()}
    ben, dem = {}, {}
    for c in sorted(vt_cot):
        v = vt_cot[c]
        if v == "stt":
            continue
        dem[v] = dem.get(v, 0) + 1
        ben[c] = 0 if dem[v] == 1 else 1
    # cột ghi chú đứng sau cột nội dung bên cũ thuộc bên cũ
    noi_dung = [c for c in sorted(vt_cot) if vt_cot[c] == "noi_dung"]
    if len(noi_dung) >= 2:
        for c in ben:
            ben[c] = 0 if c < noi_dung[1] - (1 if vt_cot.get(noi_dung[1] - 1) == "dieu" else 0) else 1
    return ben, vt_cot


def _ten_ben(sh, cols):
    for c in cols:
        if c in sh.nhom:
            return sh.nhom[c].replace("\n", " ")
    return ""


def _so_sanh(sh, P, ctx):
    ben, vt = _ben(sh)
    moi = [c for c in sorted(ben) if ben[c] == 0]
    cu = [c for c in sorted(ben) if ben[c] == 1]
    ten_moi = _ten_ben(sh, moi) or sh.tieu_de
    ten_cu = _ten_ben(sh, cu)
    shs = _so_hieu(ten_moi) or _so_hieu(sh.tieu_de)
    so_hieu = _chuan_so_hieu(shs[0])[0] if shs else ""
    hl = _ngay(ten_moi) or _ngay(sh.tieu_de) or ctx["hieu_luc_vb"].get(bo_dau(so_hieu), "")
    ten_ngan = _thuong(ten_moi) if ten_moi else sh.ten
    out, dung = [], set()
    for m in sh.muc():
        dieu_m = next((sh.chu_cot(m, c, mau=False, sep=" ") for c in moi if vt[c] == "dieu"), "")
        nd_m = "\n".join(t for t in (sh.chu_cot(m, c) for c in moi if vt[c] == "noi_dung") if t)
        gc_m = "\n".join(t for t in (sh.chu_cot(m, c) for c in moi if vt[c] in ("ghi_chu", "khac")) if t)
        dieu_c = next((sh.chu_cot(m, c, mau=False, sep=" ") for c in cu if vt[c] == "dieu"), "")
        nd_c = "\n".join(t for t in (sh.chu_cot(m, c) for c in cu if vt[c] == "noi_dung") if t)
        gc_c = "\n".join(t for t in (sh.chu_cot(m, c) for c in cu if vt[c] in ("ghi_chu", "khac")) if t)
        if not (dieu_m or nd_m):
            continue
        dau = (dieu_m or re.sub(r"[*~]", "", nd_m).split("\n")[0])[:150]
        md = []
        if _co_mau(nd_m + nd_c + gc_m + gc_c):
            md.append("_Chữ **đậm**: nội dung mới / điều chỉnh · ~~gạch ngang~~: nội dung cũ bị bãi bỏ, thay đổi "
                      "(theo màu chữ trong file gốc)._")
        md.append(f"#### Quy định mới - {ten_ngan}" + (f": {dieu_m}" if dieu_m else ""))
        md.append(_md(nd_m))
        if gc_m:
            md += ["#### Điểm mới / ghi chú", _md(gc_m)]
        if nd_c or dieu_c:
            md.append("#### Quy định cũ" + (f" - {_thuong(ten_cu)}" if ten_cu else "")
                      + (f": {dieu_c}" if dieu_c else ""))
            md.append(_md(nd_c or "_(không có)_"))
        if gc_c:
            md += ["#### Ghi chú về quy định cũ", _md(gc_c)]
        so_d = re.match(r"\s*Điều\s+(\d+[a-z]?)", dieu_m or "", re.I)
        key = f"D{so_d.group(1)}" if so_d else f"R{m['dau']}"
        ma = f"{P}-KT-{_ma_sheet(sh.ten)}-{key}"
        if ma in dung:
            ma += f"-R{m['dau']}"
        dung.add(ma)
        out.append({"ma": ma, "tieu_de": f"{so_hieu or ten_ngan} - {dau}", "noi_dung": "\n\n".join(md),
                    "nghiep_vu": _nghiep_vu(nd_m, dieu_m), "so_hieu": so_hieu, "hieu_luc_tu": hl,
                    "nguon_vi_tri": sh.vi_tri(m)})
    return {"kien_thuc": out}


def _danh_muc_vb(sh, P, ctx):
    vt = sh.vai_tro()
    cvb, chl = vt["van_ban"][0], vt["hieu_luc"][0]
    khac = [c for c in sorted(sh.nhan) if c not in (cvb, chl) and _vai_tro(sh.nhan[c]) != "stt"]
    out = []
    for m in sh.muc():
        t = sh.chu_cot(m, cvb, mau=False)
        shs = _so_hieu(t)
        if not shs:
            ctx["canh_bao"].append(f"{sh.ten} dòng {m['dau']}: không tìm thấy số hiệu văn bản trong '{t[:60]}'.")
            continue
        so_hieu, cb = _chuan_so_hieu(shs[0])
        if cb:
            ctx["canh_bao"].append(f"{sh.ten} dòng {m['dau']}: {cb}; đã ghi tạm là {so_hieu}.")
        nd = []
        for c in khac:
            v = sh.chu_cot(m, c, mau=False)
            if v:
                nd.append(f"**{sh.nhan[c].capitalize()}:**  \n" + _md(v))
        ten = " ".join(t.split())
        hl = sh.chu_cot(m, chl, mau=False, sep=" ")
        loai = so_hieu.split("/")[2]
        cap = "EVN" if "EVN" in loai or "CPC" in loai else "QPPL"
        out.append({"ma": f"{P}-VB-" + re.sub(r"[^A-Z0-9]", "", so_hieu.upper().replace("Đ", "D")),
                    "so_hieu": so_hieu, "ten": ten, "cap": cap, "nghiep_vu": _nghiep_vu(t),
                    "ngay_ban_hanh": _ngay_bh(t), "hieu_luc_tu": hl, "noi_dung": "\n\n".join(nd),
                    "nguon_vi_tri": sh.vi_tri(m, cvb)})
        ctx["hieu_luc_vb"][bo_dau(so_hieu)] = hl
    return {"van_ban": out}


def _theo_dong(sh, P, ctx):
    cot = sorted(sh.nhan)
    k = sh.cot_khoa()
    vt = {c: _vai_tro(sh.nhan[c]) for c in cot}
    cot_ten = next((c for c in cot if vt[c] in ("noi_dung", "khac", "dieu") and c != k), cot[0])
    out, dung = [], set()
    for m in sh.muc():
        ten = sh.chu_cot(m, cot_ten, mau=False, sep=" ")
        if not ten:
            continue
        md, nhieu = [], []
        for c in cot:
            if c in (k, cot_ten):
                continue
            so_dong = sum(1 for r in range(m["dau"], m["cuoi"] + 1)
                          if sh.raw[r][c][0] and not ((r, c) in sh.gop and sh.gop[(r, c)].min_row < r))
            if so_dong > 1:
                nhieu.append(c)
            else:
                v = sh.chu_cot(m, c)
                if v:
                    md.append(f"**{sh.nhan[c].capitalize()}:**  \n" + _md(v))
        if nhieu:
            dong = []
            for r in range(m["dau"], m["cuoi"] + 1):
                cs = [sh.o(r, c) for c in nhieu if sh.o(r, c) and not ((r, c) in sh.gop and sh.gop[(r, c)].min_row < r)]
                if cs:
                    dong.append("- " + " — ".join(_md(x) for x in cs))
            lb = " / ".join(dict.fromkeys(sh.nhan[c] for c in nhieu))
            md.append(f"**{lb.capitalize()}:**\n\n" + "\n".join(dong))
        if m["ghi_nhom"] and m["nhom"]:
            md.insert(0, f"_Thuộc mục {m['nhom']}: {m['ghi_nhom'].split(chr(10))[0]}_")
        stt = sh.raw[m["dau"]][k][0].strip().rstrip(".") if k != cot_ten else ""
        key = (f"{m['nhom']}." if m["nhom"] else "") + (stt if re.fullmatch(r"[\w.]{1,8}", stt) else f"R{m['dau']}")
        ma = f"{P}-KT-{_ma_sheet(sh.ten)}-{key}"
        if ma in dung:
            ma += f"-R{m['dau']}"
        dung.add(ma)
        shs = _so_hieu(m["ghi_nhom"] + " " + " ".join(sh.chu_cot(m, c, mau=False) for c in cot))
        so_hieu = _chuan_so_hieu(shs[0])[0] if shs else ""
        if so_hieu and bo_dau(so_hieu) not in ctx["hieu_luc_vb"] and bo_dau(so_hieu) not in ctx["vb_db"]:
            so_hieu = ""
        nhom_sh = _so_hieu(m["ghi_nhom"])
        tieu = ten.replace("\n", " ").strip()
        if nhom_sh:
            tieu += f" ({_chuan_so_hieu(nhom_sh[0])[0]})"
        out.append({"ma": ma, "tieu_de": f"{tieu[:160]}", "noi_dung": "\n\n".join(md) or ten,
                    "nghiep_vu": _nghiep_vu(" ".join(md), ten), "so_hieu": so_hieu,
                    "hieu_luc_tu": _ngay(sh.tieu_de), "nguon_vi_tri": sh.vi_tri(m)})
    if out:
        ctx["ghi_chu"].append(f"{sh.ten}: tiêu đề bài lấy từ cột '{sh.nhan[cot_ten]}'.")
    return {"kien_thuc": out}


def _bang_so_lieu(sh, P, ctx, max_dong=250):
    dong = [r for r in range(1, sh.nr + 1) if sh.hang(r)]
    if sh.h:
        dong = [r for r in dong if r >= sh.h]
    dem = {c: sum(1 for r in dong if sh.raw[r][c][0]) for c in range(1, sh.nc + 1)}
    cot = [c for c in range(1, sh.nc + 1) if dem[c] >= 2]
    if not cot or not dong:
        return {}
    bang = []
    cot_stt = {c for c in cot if _vai_tro(sh.nhan.get(c, "")) == "stt"}
    for r in dong[:max_dong]:
        hang = [sh.fill[r][c] if (r, c) in sh.gop and sh.gop[(r, c)].min_col < c and sh.gop[(r, c)].min_row == r
                else sh.raw[r][c][0] for c in cot]
        hang = [x.replace("\n", " · ").replace("|", "/") for x in hang]
        hang = [x.replace(",", ".") if c in cot_stt else x for x, c in zip(hang, cot)]
        if any(hang) and (not bang or hang != bang[-1]):
            bang.append(hang)
    tren = [x.replace("\n", " ") for x in getattr(sh, "tieu_de_tren", [])]
    tieu = " / ".join(tren[:2])[:160] if len(tren) >= 2 and sh.h else sh.tieu_de[:160]
    md = [f"_{x}_" for x in tren[2:5]]
    md.append("| " + " | ".join(bang[0]) + " |")
    md.append("|" + "---|" * len(cot))
    md += ["| " + " | ".join(h) + " |" for h in bang[1:]]
    if len(dong) > max_dong:
        ctx["canh_bao"].append(f"{sh.ten}: bảng dài {len(dong)} dòng, chỉ lấy {max_dong} dòng đầu.")
    ctx["canh_bao"].append(f"{sh.ten}: chuyển cả sheet thành 1 bảng ({len(bang)} dòng × {len(cot)} cột) - "
                           "nên xem lại tiêu đề cột và bỏ phần không cần cho ĐTV.")
    return {"kien_thuc": [{"ma": f"{P}-KT-{_ma_sheet(sh.ten)}", "tieu_de": tieu,
                           "noi_dung": "\n".join(md), "nghiep_vu": _nghiep_vu(" ".join(bang[0]), tieu),
                           "so_hieu": "", "hieu_luc_tu": "" if len(tren) >= 2 else _ngay(sh.tieu_de),
                           "nguon_vi_tri": f"{sh.ten}!{get_column_letter(cot[0])}{dong[0]}:"
                                           f"{get_column_letter(cot[-1])}{dong[-1]}"}]}


# ------------------------------------------------------------------ AI (tuỳ chọn)
AI_PROMPT = """Bạn chuyển nội dung một sheet Excel nghiệp vụ điện lực thành dữ liệu tra cứu cho điện thoại viên.
Chỉ dùng thông tin có trong sheet, KHÔNG thêm số liệu mới, giữ nguyên mọi con số.
Trả về DUY NHẤT một JSON: {"kien_thuc":[{"tieu_de":"","noi_dung":"(markdown)","vi_tri":"ô bắt đầu, vd B5"}],
"tinh_huong":[{"cau_hoi":"","tra_loi":"","vi_tri":""}]}"""


def _so_trong(text):
    return {re.sub(r"[.,]", "", m) for m in re.findall(r"\d[\d.,]*\d|\d", text or "") if len(re.sub(r"\D", "", m)) >= 3}


def _ai(sh, P, ctx):
    from ai_assistant import load_config
    import requests
    cfg = load_config()
    llm = cfg.get("llm", {})
    if not llm.get("enabled"):
        ctx["canh_bao"].append(f"{sh.ten}: chưa bật AI (config.json → llm.enabled) nên không đọc được bằng AI.")
        return {}
    dong = []
    for r in range(1, sh.nr + 1):
        cs = [f"{get_column_letter(c)}{r}: {sh.raw[r][c][0]}" for c in sh.hang(r)]
        if cs:
            dong.append(" | ".join(cs))
    goc = "\n".join(dong)[:12000]
    headers = {"Content-Type": "application/json"}
    if llm.get("api_key"):
        headers["Authorization"] = f"Bearer {llm['api_key']}"
    try:
        r = requests.post(llm["base_url"].rstrip("/") + "/chat/completions", headers=headers,
                          timeout=max(60, llm.get("timeout_sec", 60)),
                          json={"model": llm["model"], "temperature": 0,
                                "messages": [{"role": "system", "content": AI_PROMPT},
                                             {"role": "user", "content": f"Sheet '{sh.ten}':\n{goc}"}]})
        r.raise_for_status()
        txt = r.json()["choices"][0]["message"]["content"]
        js = json.loads(txt[txt.find("{"): txt.rfind("}") + 1])
    except Exception as e:
        ctx["canh_bao"].append(f"{sh.ten}: gọi AI không thành công ({type(e).__name__}: {str(e)[:120]}).")
        return {}
    so_goc = _so_trong("\n".join(sh.raw[r][c][0] for r in range(1, sh.nr + 1) for c in sh.hang(r)))
    ms = _ma_sheet(sh.ten)
    kt, th = [], []
    for i, d in enumerate(js.get("kien_thuc", []), 1):
        la = _so_trong(d.get("noi_dung", "") + " " + d.get("tieu_de", "")) - so_goc
        if la:
            ctx["loi_ai"].append(f"{sh.ten} - bài '{d.get('tieu_de', '')[:50]}': AI ghi số không có trong file gốc: "
                                 + ", ".join(sorted(la)[:6]))
        kt.append({"ma": f"{P}-KT-{ms}-AI{i:02d}", "tieu_de": d.get("tieu_de", "")[:160],
                   "noi_dung": d.get("noi_dung", ""), "nghiep_vu": _nghiep_vu(d.get("noi_dung", "")),
                   "so_hieu": "", "hieu_luc_tu": "", "nguon_vi_tri": f"{sh.ten}!{d.get('vi_tri', '')}"})
    for i, d in enumerate(js.get("tinh_huong", []), 1):
        la = _so_trong(d.get("tra_loi", "") + " " + d.get("cau_hoi", "")) - so_goc
        if la:
            ctx["loi_ai"].append(f"{sh.ten} - câu '{d.get('cau_hoi', '')[:50]}': AI ghi số không có trong file gốc: "
                                 + ", ".join(sorted(la)[:6]))
        th.append({"ma": f"{P}-TH-{ms}-AI{i:02d}", "cau_hoi": d.get("cau_hoi", ""), "tra_loi": d.get("tra_loi", ""),
                   "tu_goi_y": "", "nghiep_vu": _nghiep_vu(d.get("cau_hoi", "") + d.get("tra_loi", "")),
                   "nguon_tai_lieu": f"{ctx['ten_tai_lieu']} - sheet {sh.ten} (AI đọc)", "so_hieu": "",
                   "nguon_vi_tri": f"{sh.ten}!{d.get('vi_tri', '')}"})
    ctx["ghi_chu"].append(f"{sh.ten}: AI đọc {len(kt)} bài kiến thức, {len(th)} tình huống - cần người duyệt kỹ.")
    return {"kien_thuc": kt, "tinh_huong": th}


HAM = {"hoi_dap": _hoi_dap, "so_sanh": _so_sanh, "danh_muc_vb": _danh_muc_vb, "theo_dong": _theo_dong,
       "bang_so_lieu": _bang_so_lieu, "ai": _ai}


# ------------------------------------------------------------------ API chính
def doc_file(data):
    """bytes -> list[Sheet] (giữ màu chữ)."""
    wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True, rich_text=True)
    ct = {}
    try:
        wf = openpyxl.load_workbook(io.BytesIO(data), read_only=True)
        for ws in wf.worksheets:
            ct[ws.title] = sum(1 for row in ws.iter_rows(values_only=True) for v in row
                               if isinstance(v, str) and v.startswith("="))
    except Exception:
        pass
    return [Sheet(ws, ct.get(ws.title, 0)) for ws in wb.worksheets if ws.sheet_state == "visible"]


def nhan_dang(sheets):
    out = []
    for s in sheets:
        k, ly_do = s.doan_kieu()
        out.append({"sheet": s.ten, "kieu": k, "tieu_de": s.tieu_de[:90], "ghi_chu": ly_do,
                    "kich_thuoc": f"{s.nr}×{s.nc}"})
    return out


def chuyen(sheets, kieu, tien_to, ten_file=""):
    """kieu: {tên sheet: kiểu}. -> {"data": {van_ban, kien_thuc, tinh_huong}, "canh_bao", "loi_ai", "ghi_chu", "bao_cao"}"""
    try:
        from db import query, bo_dau as _bd
        vb_db = {_bd(r["so_hieu"]) for r in query("SELECT so_hieu FROM van_ban")}
    except Exception:
        vb_db = set()
    P = re.sub(r"[^A-Z0-9]", "", bo_dau(tien_to).upper()) or "BO1"
    import os
    ten_tl = re.sub(r"\.xlsx?$", "", os.path.basename(ten_file or ""), flags=re.I)
    ctx = {"ten_file": ten_file, "ten_tai_lieu": ten_tl, "canh_bao": [], "loi_ai": [], "ghi_chu": [], "hieu_luc_vb": {}, "vb_db": vb_db,
           "so_sheet_hd": sum(1 for s in sheets if kieu.get(s.ten) == "hoi_dap")}
    data = {"van_ban": [], "kien_thuc": [], "tinh_huong": []}
    bao_cao = []
    # danh mục văn bản trước để các bài khác lấy ngày hiệu lực / số hiệu
    thu_tu = sorted(sheets, key=lambda s: 0 if kieu.get(s.ten) == "danh_muc_vb" else 1)
    for s in thu_tu:
        k = kieu.get(s.ten, "bo_qua")
        if k == "bo_qua" or k not in HAM:
            bao_cao.append({"sheet": s.ten, "kieu": KIEU.get(k, k), "so_muc": 0})
            continue
        try:
            kq = HAM[k](s, P, ctx)
        except Exception as e:
            ctx["canh_bao"].append(f"{s.ten}: không chuyển được theo kiểu '{KIEU[k]}' ({type(e).__name__}: {e}). "
                                   "Thử chọn kiểu khác.")
            kq = {}
        n = 0
        for loai, rows in kq.items():
            data[loai] += rows
            n += len(rows)
        bao_cao.append({"sheet": s.ten, "kieu": KIEU[k], "so_muc": n})
    thu = {s.ten: i for i, s in enumerate(sheets)}
    bao_cao.sort(key=lambda b: thu.get(b["sheet"], 0))
    return {"data": data, "canh_bao": ctx["canh_bao"], "loi_ai": ctx["loi_ai"], "ghi_chu": ctx["ghi_chu"],
            "bao_cao": bao_cao, "tien_to": P}


COT_RA = {
    "VanBan": [("Mã", "ma"), ("Số hiệu", "so_hieu"), ("Tên văn bản", "ten"), ("Cấp ban hành", "cap"),
               ("Đơn vị áp dụng", "ap_dung"), ("Nghiệp vụ", "nghiep_vu"), ("Ngày ban hành", "ngay_ban_hanh"),
               ("Hiệu lực từ", "hieu_luc_tu"), ("Hiệu lực đến", "hieu_luc_den"), ("Quan hệ", "quan_he"),
               ("Số hiệu văn bản gốc", "so_hieu_goc"), ("Link", "link_wiki"), ("Nội dung tóm tắt", "noi_dung"),
               ("Vị trí nguồn", "nguon_vi_tri")],
    "KienThuc": [("Mã", "ma"), ("Tiêu đề", "tieu_de"), ("Nghiệp vụ", "nghiep_vu"), ("Đơn vị áp dụng", "ap_dung"),
                 ("Nội dung", "noi_dung"), ("Số hiệu văn bản", "so_hieu"), ("Hiệu lực từ", "hieu_luc_tu"),
                 ("Hiệu lực đến", "hieu_luc_den"), ("Vị trí nguồn", "nguon_vi_tri")],
    "TinhHuong": [("Mã", "ma"), ("Câu hỏi", "cau_hoi"), ("Từ gợi ý", "tu_goi_y"), ("Nghiệp vụ", "nghiep_vu"),
                  ("Câu trả lời", "tra_loi"), ("Nguồn tài liệu", "nguon_tai_lieu"), ("Số hiệu văn bản", "so_hieu"),
                  ("Link wiki", "link_wiki"), ("Hiệu lực từ", "hieu_luc_tu"), ("Hiệu lực đến", "hieu_luc_den"),
                  ("Nguồn tình huống", "nguon"), ("Link video", "video_link"), ("Vị trí nguồn", "nguon_vi_tri")],
}
SHEET_LOAI = {"VanBan": "van_ban", "KienThuc": "kien_thuc", "TinhHuong": "tinh_huong"}


def xuat_excel(kq, ten_file=""):
    from openpyxl.styles import Alignment, Font, PatternFill
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    dam = Font(bold=True, color="FFFFFF")
    nen = PatternFill("solid", fgColor="0054A6")
    for ten, cols in COT_RA.items():
        ws = wb.create_sheet(ten)
        ws.append([c[0] for c in cols])
        for r in kq["data"][SHEET_LOAI[ten]]:
            ws.append([r.get(k, "") or "" for _, k in cols])
        for i, (lb, k) in enumerate(cols, 1):
            ws.cell(1, i).font, ws.cell(1, i).fill = dam, nen
            ws.column_dimensions[get_column_letter(i)].width = {"noi_dung": 80, "tra_loi": 80, "ten": 50,
                                                                 "tieu_de": 45, "cau_hoi": 45}.get(k, 18)
        for row in ws.iter_rows(min_row=2):
            for c in row:
                c.alignment = Alignment(wrap_text=True, vertical="top")
        ws.freeze_panes = "C2"
    ws = wb.create_sheet("BaoCaoChuyenDoi")
    import os
    ws.append([f"Chuyển từ file: {os.path.basename(ten_file or '')}", "", f"Tiền tố mã: {kq['tien_to']}",
               f"Lúc {dt.datetime.now():%d/%m/%Y %H:%M}"])
    ws.append(["Sheet gốc", "Cách đọc", "Số mục tạo ra"])
    for b in kq["bao_cao"]:
        ws.append([b["sheet"], b["kieu"], b["so_muc"]])
    ws.append([])
    for lb, ds in (("LỖI AI", kq["loi_ai"]), ("Cảnh báo", kq["canh_bao"]), ("Ghi chú", kq["ghi_chu"])):
        for x in ds:
            ws.append([lb, x])
    ws.column_dimensions["A"].width, ws.column_dimensions["B"].width = 28, 110
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
    f = sys.argv[1]
    P = sys.argv[2] if len(sys.argv) > 2 else tien_to_mac_dinh(f)
    ra = sys.argv[3] if len(sys.argv) > 3 else re.sub(r"\.xlsx$", "", f, flags=re.I) + "_DA_CHUYEN.xlsx"
    shs = doc_file(open(f, "rb").read())
    nd = nhan_dang(shs)
    for x in nd:
        print(f"{x['sheet']:32s} {KIEU[x['kieu']]:36s} {x['ghi_chu']}")
    kq = chuyen(shs, {x["sheet"]: x["kieu"] for x in nd}, P, f)
    open(ra, "wb").write(xuat_excel(kq, f))
    print({k: len(v) for k, v in kq["data"].items()}, "->", ra)
    for x in kq["canh_bao"]:
        print("  !", x)
