# -*- coding: utf-8 -*-
"""
THỐNG KÊ - THI ĐUA (User quản lý) - mục 2.5.3
- Thống kê phản hồi theo tình huống (like, like trong 30 ngày đầu, bình luận, bình luận hay)
- Thống kê tương tác theo user (+ xem chi tiết)
- Thống kê đề xuất theo user (+ xem chi tiết)
- Bảng điểm thi đua tổng hợp
"""
import io
from datetime import date, timedelta

import pandas as pd
import streamlit as st

from auth import require_role
from common import DIEM, fmt_dt, page_header
from db import query

require_role("quan_ly")
page_header("📊 Thống kê - thi đua")

c1, c2, _ = st.columns([1, 1, 2])
tu = c1.date_input("Từ ngày", date.today() - timedelta(days=90), format="DD/MM/YYYY")
den = c2.date_input("Đến ngày", date.today(), format="DD/MM/YYYY")
rng = (tu.isoformat(), (den + timedelta(days=1)).isoformat())


def excel_button(df, name, key):
    buf = io.BytesIO()
    df.to_excel(buf, index=False)
    st.download_button("⬇️ Xuất Excel", buf.getvalue(), f"{name}_{tu:%Y%m%d}_{den:%Y%m%d}.xlsx", key=key)


t1, t2, t3, t4, t5 = st.tabs(["Phản hồi theo tình huống", "Tương tác theo user", "Đề xuất theo user",
                              "🏆 Bảng điểm thi đua", "🤖 Câu hỏi gửi Trợ lý"])

with t1:
    rows = query("""
        SELECT b.cau_hoi AS "Tình huống", COALESCE(u.full_name, '') AS "User gửi",
               (SELECT COUNT(*) FROM hd_like l WHERE l.bai_id=b.id) AS "Tổng lượt like",
               (SELECT COUNT(*) FROM hd_like l WHERE l.bai_id=b.id
                    AND l.created_at < datetime(b.created_at, '+30 days')) AS "Lượt like trong 30 ngày đầu",
               (SELECT COUNT(*) FROM hd_binh_luan c WHERE c.bai_id=b.id) AS "Tổng bình luận",
               (SELECT COUNT(*) FROM hd_binh_luan c WHERE c.bai_id=b.id AND c.la_hay=1) AS "Tổng bình luận hay"
        FROM hd_bai b LEFT JOIN users u ON u.id = b.nguoi_gui
        WHERE b.an=0 AND b.created_at >= ? AND b.created_at < ?
        ORDER BY "Tổng lượt like" DESC""", rng)
    df = pd.DataFrame(rows)
    if df.empty:
        st.info("Không có dữ liệu trong khoảng thời gian này.")
    else:
        st.dataframe(df, hide_index=True, width="stretch")
        excel_button(df, "phan_hoi_tinh_huong", "x1")

with t2:
    rows = query("""
        SELECT u.id, u.full_name AS "User", u.don_vi AS "Đơn vị",
          (SELECT COUNT(*) FROM hd_like l WHERE l.user_id=u.id AND l.created_at>=? AND l.created_at<?) AS "Tổng lượt like",
          (SELECT COUNT(*) FROM hd_binh_luan c WHERE c.user_id=u.id AND c.created_at>=? AND c.created_at<?) AS "Tổng bình luận",
          (SELECT COUNT(*) FROM hd_binh_luan c WHERE c.user_id=u.id AND c.la_hay=1 AND c.created_at>=? AND c.created_at<?) AS "Bình luận hay"
        FROM users u WHERE u.role='dtv' AND u.active=1 ORDER BY "Tổng bình luận" DESC, "Tổng lượt like" DESC""",
                 rng * 3)
    df = pd.DataFrame(rows)
    if not df.empty:
        ev = st.dataframe(df.drop(columns="id"), hide_index=True, width="stretch",
                          on_select="rerun", selection_mode="single-row", key="tk_tt")
        excel_button(df.drop(columns="id"), "tuong_tac_user", "x2")
        if ev.selection.rows:
            u = rows[ev.selection.rows[0]]
            st.markdown(f"**Chi tiết: {u['User']}**")
            detail = query("""
                SELECT b.cau_hoi AS "Tình huống",
                       CASE WHEN EXISTS (SELECT 1 FROM hd_like l WHERE l.bai_id=b.id AND l.user_id=?
                                          AND l.created_at>=? AND l.created_at<?) THEN 'Có' ELSE '' END AS "Like",
                       COALESCE(c.noi_dung, '') AS "Nội dung bình luận",
                       CASE WHEN c.la_hay=1 THEN 'Có' ELSE '' END AS "Bình luận hay"
                FROM hd_bai b
                LEFT JOIN hd_binh_luan c ON c.bai_id=b.id AND c.user_id=? AND c.created_at>=? AND c.created_at<?
                WHERE EXISTS (SELECT 1 FROM hd_like l WHERE l.bai_id=b.id AND l.user_id=? AND l.created_at>=? AND l.created_at<?)
                   OR c.id IS NOT NULL
                ORDER BY b.id""", (u["id"], *rng, u["id"], *rng, u["id"], *rng))
            st.dataframe(pd.DataFrame(detail), hide_index=True, width="stretch")
        else:
            st.caption("Chọn một dòng để xem chi tiết.")

with t3:
    rows = query("""
        SELECT u.id, u.full_name AS "User",
          SUM(CASE WHEN COALESCE(d.tra_loi_de_xuat,'')='' THEN 1 ELSE 0 END) AS "Tổng câu hỏi (không kèm câu trả lời)",
          SUM(CASE WHEN COALESCE(d.tra_loi_de_xuat,'')<>'' THEN 1 ELSE 0 END) AS "Tổng câu hỏi kèm câu trả lời",
          SUM(d.cau_hoi_hay) AS "Câu hỏi hay", SUM(d.tl_chuan) AS "Câu trả lời chuẩn",
          SUM(d.tl_tuong_doi) AS "Câu trả lời tương đối chuẩn"
        FROM de_xuat d JOIN users u ON u.id = d.nguoi_gui
        WHERE d.created_at >= ? AND d.created_at < ?
        GROUP BY u.id ORDER BY "Câu hỏi hay" DESC""", rng)
    df = pd.DataFrame(rows)
    if df.empty:
        st.info("Chưa có đề xuất trong khoảng thời gian này.")
    else:
        ev = st.dataframe(df.drop(columns="id"), hide_index=True, width="stretch",
                          on_select="rerun", selection_mode="single-row", key="tk_dx")
        excel_button(df.drop(columns="id"), "de_xuat_user", "x3")
        if ev.selection.rows:
            u = rows[ev.selection.rows[0]]
            st.markdown(f"**Chi tiết: {u['User']}**")
            detail = query("""
                SELECT cau_hoi AS "Câu hỏi", tra_loi_de_xuat AS "Câu trả lời",
                       CASE WHEN cau_hoi_hay=1 THEN 'Có' ELSE '' END AS "Câu hỏi hay",
                       CASE WHEN tl_chuan=1 THEN 'Có' ELSE '' END AS "Câu trả lời chuẩn",
                       CASE WHEN tl_tuong_doi=1 THEN 'Có' ELSE '' END AS "Câu trả lời tương đối chuẩn",
                       created_at AS "Ngày gửi"
                FROM de_xuat WHERE nguoi_gui=? AND created_at>=? AND created_at<? ORDER BY created_at""",
                           (u["id"], *rng))
            for d in detail:
                d["Ngày gửi"] = fmt_dt(d["Ngày gửi"])
            st.dataframe(pd.DataFrame(detail), hide_index=True, width="stretch")

with t4:
    st.caption(f"Cách tính: câu hỏi hay {DIEM['cau_hoi_hay']}đ · trả lời chuẩn {DIEM['tl_chuan']}đ · "
               f"tương đối chuẩn {DIEM['tl_tuong_doi']}đ · bình luận hay {DIEM['binh_luan_hay']}đ "
               "(chỉnh trong common.py → DIEM)")
    rows = query("""
        SELECT u.full_name AS "User", u.don_vi AS "Đơn vị",
          COALESCE((SELECT SUM(cau_hoi_hay) FROM de_xuat d WHERE d.nguoi_gui=u.id AND d.created_at>=? AND d.created_at<?),0) AS hay,
          COALESCE((SELECT SUM(tl_chuan) FROM de_xuat d WHERE d.nguoi_gui=u.id AND d.created_at>=? AND d.created_at<?),0) AS chuan,
          COALESCE((SELECT SUM(tl_tuong_doi) FROM de_xuat d WHERE d.nguoi_gui=u.id AND d.created_at>=? AND d.created_at<?),0) AS td,
          (SELECT COUNT(*) FROM hd_binh_luan c WHERE c.user_id=u.id AND c.la_hay=1 AND c.created_at>=? AND c.created_at<?) AS blh
        FROM users u WHERE u.role='dtv' AND u.active=1""", rng * 4)
    for r in rows:
        r["Điểm"] = (r["hay"] * DIEM["cau_hoi_hay"] + r["chuan"] * DIEM["tl_chuan"]
                     + r["td"] * DIEM["tl_tuong_doi"] + r["blh"] * DIEM["binh_luan_hay"])
    df = pd.DataFrame(rows).rename(columns={"hay": "Câu hỏi hay", "chuan": "Trả lời chuẩn",
                                            "td": "Tương đối chuẩn", "blh": "Bình luận hay"})
    if not df.empty:
        df = df.sort_values("Điểm", ascending=False)
        st.dataframe(df, hide_index=True, width="stretch",
                     column_config={"Điểm": st.column_config.ProgressColumn(
                         "Điểm", min_value=0, max_value=max(1, int(df["Điểm"].max())), format="%d")})
        excel_button(df, "diem_thi_dua", "x4")

with t5:
    st.caption("Câu hỏi ĐTV/ĐL gửi Trợ lý tra cứu. Câu bị đánh giá 'Sai' cho thấy chỗ tài liệu còn thiếu.")
    rows = query("""SELECT n.created_at AS "Thời gian", u.full_name AS "Người hỏi", n.cau_hoi AS "Câu hỏi",
                           CASE n.danh_gia WHEN 1 THEN '👍 Đúng' WHEN -1 THEN '👎 Sai' ELSE '' END AS "Đánh giá"
                    FROM tl_nhat_ky n LEFT JOIN users u ON u.id=n.user_id
                    WHERE n.created_at>=? AND n.created_at<? ORDER BY COALESCE(n.danh_gia, 0), n.created_at DESC""", rng)
    df = pd.DataFrame(rows)
    if df.empty:
        st.info("Chưa có câu hỏi.")
    else:
        st.dataframe(df, hide_index=True, width="stretch")
        excel_button(df, "cau_hoi_tro_ly", "x5")
