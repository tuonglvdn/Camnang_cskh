# -*- coding: utf-8 -*-
"""NHẬP DỮ LIỆU HÀNG LOẠT (User quản lý): văn bản + kiến thức + tình huống trong 1 file Excel."""
import pandas as pd
import streamlit as st

from auth import require_role
from common import page_header
from nhap_du_lieu import import_data, read_workbook, template_workbook

user = require_role("quan_ly")
page_header("📥 Nhập dữ liệu hàng loạt",
            "Một file Excel gồm các sheet VanBan, KienThuc, TinhHuong (có sheet nào nhập sheet đó)")

st.download_button("⬇️ Tải file mẫu (3 sheet)", template_workbook(), "mau_nhap_du_lieu.xlsx")
st.markdown("- Thứ tự nhập tự động: **Văn bản → Kiến thức → Tình huống**, để cột *Số hiệu văn bản* liên kết đúng.\n"
            "- Mục đã có (trùng số hiệu văn bản, trùng tiêu đề + ngày hiệu lực, trùng câu hỏi) sẽ được **bỏ qua**.\n"
            "- Văn bản có *Quan hệ* = Thay thế và *Số hiệu văn bản gốc*: văn bản gốc tự hết hiệu lực "
            "trước ngày hiệu lực của văn bản mới; nội dung dẫn chiếu văn bản gốc được đánh dấu cần rà soát.")

up = st.file_uploader("Chọn file Excel", type=["xlsx"])
if up:
    data, errors = read_workbook(up)
    for e in errors:
        st.warning(e)
    labels = {"van_ban": "Văn bản", "kien_thuc": "Kiến thức", "tinh_huong": "Tình huống"}
    if data:
        tabs = st.tabs([f"{labels[k]} ({len(v)})" for k, v in data.items()])
        for tab, (k, rows) in zip(tabs, data.items()):
            with tab:
                st.dataframe(pd.DataFrame(rows).drop(columns="_dong", errors="ignore"),
                             use_container_width=True, hide_index=True)
        stats, notes = import_data(data, user["id"], dry_run=True)
        st.info("Kiểm tra trước: " + " · ".join(
            f"{labels[k]}: thêm {v['them']}, bỏ qua {v['bo_qua']}" for k, v in stats.items() if k in data))
        for n in notes:
            st.caption(n)
        if st.button("📥 Nhập vào hệ thống", type="primary"):
            stats, notes = import_data(data, user["id"])
            st.success("Đã nhập: " + " · ".join(
                f"{labels[k]} {v['them']}" for k, v in stats.items() if k in data))
            for n in notes:
                st.caption(n)
