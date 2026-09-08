from __future__ import annotations

from datetime import datetime
from html import escape, unescape
import math
import re

import pandas as pd
import streamlit as st

from services.wms_monitor import get_order_lines, load_wms_monitor
try:
    from services.wms_inventory import get_available_stock
except Exception:
    get_available_stock = None
from ui.components import render_html


PAGE_SIZE = 15
YELLOW = "#FFD21A"
BLACK = "#111111"
BG = "#F4F5F7"
BORDER = "#E2E5E9"
TEXT = "#17191C"
MUTED = "#707780"


# ============================================================
# ESTILOS · VISUAL MARITEX
# ============================================================

def _apply_styles() -> None:
    st.markdown(
        """
<style>
:root{
    --bg:#05090d;
    --bg2:#091018;
    --panel:#0b131a;
    --panel2:#101b24;
    --panel3:#14222d;
    --line:#243746;
    --line2:#304858;
    --text:#f7f9fb;
    --muted:#9aabb8;
    --muted2:#687b8a;
    --yellow:#ffd000;
    --yellow2:#ffbf00;
    --green:#1fc979;
    --red:#ef4452;
    --blue:#179ee8;
    --orange:#f28b21;
    --purple:#7a53d8;
}

/* APP */
[data-testid="stAppViewContainer"],
[data-testid="stAppViewContainer"] > .main,
.main{
    background:
        radial-gradient(circle at 92% 0%,rgba(37,69,90,.18),transparent 28%),
        linear-gradient(135deg,#071019 0%,#05090d 74%,#05080b 100%) !important;
    color:var(--text) !important;
}
[data-testid="stHeader"]{
    background:rgba(5,9,13,.96) !important;
    border-bottom:1px solid #1e303d !important;
}
.block-container{
    max-width:1880px !important;
    padding-top:1.15rem !important;
    padding-bottom:2.5rem !important;
}

/* HEADER */
.w9-top{
    display:flex;
    justify-content:space-between;
    align-items:flex-start;
    gap:18px;
    margin:0 0 15px 0;
}
.w9-title{
    margin:0;
    color:#fff !important;
    font-size:35px;
    font-weight:900;
    line-height:1.05;
    letter-spacing:-.85px;
}
.w9-sub{
    margin-top:7px;
    color:#b7c3cc;
    font-size:15px;
    line-height:1.35;
}
.w9-live{
    display:inline-flex;
    align-items:center;
    gap:8px;
    background:#071018;
    border:1px solid #294052;
    border-radius:11px;
    padding:10px 14px;
    color:#eaf0f4;
    font-size:12px;
    font-weight:800;
}
.w9-live i{
    display:inline-block;
    width:8px;height:8px;border-radius:50%;
    background:#2bd47e;
    box-shadow:0 0 0 4px rgba(43,212,126,.12);
}
.w9-source{
    margin:0;
    background:#071018;
    border:1px solid #263c4c;
    border-radius:10px;
    padding:10px 13px;
    color:#8fa2b1;
    font-size:10px;
}
.w9-source b{color:var(--yellow);}

/* KPI */
.w9-kpis{
    display:grid;
    grid-template-columns:repeat(6,minmax(0,1fr));
    gap:11px;
    margin:18px 0 18px 0;
}
.w9-kpi{
    min-height:103px;
    border:1px solid #263b4c;
    border-radius:11px;
    background:linear-gradient(145deg,#0c151d,#081018);
    padding:14px 14px 13px 14px;
    position:relative;
    overflow:hidden;
    box-shadow:0 8px 24px rgba(0,0,0,.13);
}
.w9-kpi:after{
    content:"";
    position:absolute;
    top:0;left:0;right:0;
    height:2px;
    background:#314757;
}
.w9-kpi.yellow:after{background:var(--yellow);}
.w9-kpi.red:after{background:var(--red);}
.w9-kpi.green:after{background:var(--green);}
.w9-kpi.blue:after{background:var(--blue);}
.w9-kpi.gray:after{background:#667987;}
.w9-kpi .kpi-top{
    display:flex;
    align-items:center;
    gap:10px;
}
.w9-kpi .kpi-icon{
    width:35px;height:35px;
    border-radius:50%;
    display:flex;align-items:center;justify-content:center;
    background:#182733;
    border:1px solid #2d4353;
    color:#dfe8ee;
    font-size:18px;
    flex:0 0 35px;
}
.w9-kpi.yellow .kpi-icon{background:#3b3100;color:var(--yellow);border-color:#675600;}
.w9-kpi.red .kpi-icon{background:#40191e;color:#ff7780;border-color:#692b32;}
.w9-kpi.green .kpi-icon{background:#123b29;color:#48e29a;border-color:#1c6241;}
.w9-kpi.blue .kpi-icon{background:#103957;color:#4bbaff;border-color:#205879;}
.w9-kpi .kpi-number{
    color:#fff;
    font-size:29px;
    font-weight:900;
    line-height:1;
}
.w9-kpi .kpi-label{
    color:#eef3f6;
    font-size:11px;
    font-weight:800;
    margin-top:5px;
}
.w9-kpi small{
    color:#8094a3;
    font-size:9px;
    margin-top:7px;
    display:block;
}

/* FILTERS */
[data-testid="stTextInput"] label,
[data-testid="stSelectbox"] label,
[data-testid="stRadio"] label{
    color:#dbe4ea !important;
    font-size:12px !important;
    font-weight:800 !important;
}
[data-testid="stTextInput"] input,
div[data-baseweb="select"] > div{
    min-height:47px !important;
    background:#0d1923 !important;
    border:1px solid #2b4254 !important;
    color:#f2f6f8 !important;
    box-shadow:none !important;
    font-size:13px !important;
}
div[data-baseweb="select"] span,
div[data-baseweb="select"] svg{
    color:#edf3f6 !important;
    fill:#edf3f6 !important;
}
div[role="radiogroup"]{
    gap:7px !important;
    flex-wrap:wrap !important;
}
div[role="radiogroup"] label{
    margin:0 !important;
    padding:7px 11px !important;
    border-radius:8px !important;
    background:#0c161e !important;
    border:1px solid #273b4b !important;
}
div[role="radiogroup"] label:has(input:checked){
    background:#141a1d !important;
    border-color:#7d6800 !important;
}
div[role="radiogroup"] label:has(input:checked) p{color:var(--yellow) !important;}
div[role="radiogroup"] p{
    color:#d7e1e7 !important;
    font-size:10px !important;
    font-weight:800 !important;
}

/* TABLE HEADER / ROWS */
div[data-testid="stHorizontalBlock"]:has(.w17-col-head){
    background:#071018;
    border:1px solid #263b4b;
    border-radius:10px 10px 0 0;
    padding:2px 8px;
}
.w17-col-head{
    color:#c9d5dd;
    font-size:9px;
    font-weight:900;
    text-transform:uppercase;
    letter-spacing:.35px;
    padding:8px 0;
}
.w17-cell{
    color:#edf2f5;
    font-size:11px;
    line-height:1.25;
    white-space:nowrap;
    overflow:hidden;
    text-overflow:ellipsis;
}
.w17-order{color:var(--yellow);font-weight:900;font-size:11px;}
.w17-progress{
    display:flex;
    align-items:center;
    gap:7px;
}
.w17-progress b{
    min-width:34px;
    color:#fff;
    font-size:10px;
}
.w17-track{
    flex:1;
    min-width:54px;
    height:7px;
    background:#203544;
    border-radius:999px;
    overflow:hidden;
}
.w17-fill{
    height:100%;
    background:linear-gradient(90deg,var(--yellow2),var(--yellow));
    border-radius:999px;
}
.w9-pill{
    display:inline-flex;
    align-items:center;
    justify-content:center;
    padding:5px 9px;
    border-radius:999px;
    font-size:9px;
    font-weight:850;
    white-space:nowrap;
    border:1px solid transparent;
}
.w9-pill.dark{background:#263441;color:#fff;border-color:#374b5a;}
.w9-pill.yellow{background:#6a5100;color:#fff1a6;border-color:#a97f00;}
.w9-pill.red{background:#7c2029;color:#fff;border-color:#a52e39;}
.w9-pill.green{background:#087546;color:#fff;border-color:#11945b;}
.w9-pill.blue{background:#0878b8;color:#fff;border-color:#1397de;}
.w9-pill.gray{background:#202c35;color:#bcc9d1;border-color:#344552;}

div[class*="st-key-w13_detail_"] .stButton > button{
    min-height:34px !important;
    height:34px !important;
    border-radius:999px !important;
    background:#071018 !important;
    border:1px solid #39566a !important;
    color:#eef4f7 !important;
    padding:0 12px !important;
    font-size:10px !important;
    font-weight:850 !important;
}
div[class*="st-key-w13_detail_"] .stButton > button:hover{
    background:var(--yellow) !important;
    border-color:var(--yellow) !important;
    color:#111 !important;
}

/* DETAIL PANEL */
.w17-detail-titlebar{
    display:flex;
    justify-content:space-between;
    align-items:center;
    gap:12px;
    border:1px solid #2a4253;
    border-bottom:none;
    background:#071018;
    border-radius:12px 12px 0 0;
    padding:14px 16px;
}
.w17-detail-title{
    color:#fff;
    font-size:22px;
    font-weight:900;
}
.w17-detail-title b{color:var(--yellow);}
.w17-client{
    color:#a8b8c3;
    font-size:11px;
    margin-top:4px;
}
.w9-detail{
    border:1px solid #2a4253;
    border-radius:0 0 12px 12px;
    overflow:hidden;
    background:#081119;
    box-shadow:0 14px 36px rgba(0,0,0,.22);
    position:relative;
}
.w9-detail:before{
    content:"";
    position:absolute;
    left:0;top:0;bottom:0;
    width:4px;
    background:var(--yellow);
}
.w17-summary{
    display:grid;
    grid-template-columns:repeat(6,minmax(0,1fr));
    gap:9px;
    padding:14px 16px;
}
.w17-summary-card{
    min-height:68px;
    border:1px solid #243a4b;
    border-radius:9px;
    background:linear-gradient(145deg,#0e1a24,#0b151d);
    padding:10px 11px;
}
.w17-summary-card.alert{
    background:linear-gradient(145deg,#34171d,#211217);
    border-color:#71303a;
}
.w17-summary-card span{
    color:#8296a5;
    font-size:8px;
    text-transform:uppercase;
    font-weight:850;
    letter-spacing:.4px;
}
.w17-summary-card strong{
    color:#fff;
    display:block;
    margin-top:5px;
    font-size:13px;
    font-weight:900;
}
.w17-summary-card.alert strong{color:#ff7e87;}
.w17-summary-card.stage strong{color:var(--yellow);}

/* FLOW */
.w9-flow{
    display:grid;
    grid-template-columns:repeat(5,minmax(0,1fr));
    gap:0;
    margin:0 16px 14px 16px;
    padding:13px 8px;
    background:#0b161f;
    border:1px solid #243a49;
    border-radius:10px;
}
.w9-step{
    min-height:76px;
    text-align:center;
    border-right:1px solid #243542;
    padding:4px 6px;
}
.w9-step:last-child{border-right:none;}
.w9-step .dot{
    margin:0 auto 7px auto;
    width:31px;height:31px;
    border-radius:50%;
    display:flex;align-items:center;justify-content:center;
    background:#243644;
    color:#9eb0bd;
    border:2px solid #405667;
    font-size:13px;
    font-weight:900;
}
.w9-step.done .dot{
    color:#fff;
    background:#0d8350;
    border-color:#20c778;
}
.w9-step.current .dot{
    color:#111;
    background:#10171d;
    border:3px solid var(--yellow);
}
.w9-step b{
    display:block;
    color:#edf3f6;
    font-size:10px;
}
.w9-step span{
    display:block;
    color:#8497a5;
    font-size:8px;
    margin-top:4px;
}
.w9-step.done span{color:#43d890;}
.w9-step.current b,.w9-step.current span{color:var(--yellow);}

/* PRODUCT METRICS */
.w9-mini-kpis{
    display:grid;
    grid-template-columns:repeat(5,minmax(0,1fr));
    gap:8px;
    padding:0 16px 12px 16px;
}
.w9-mini{
    border:1px solid #24394a;
    border-radius:8px;
    background:#0d1922;
    padding:10px;
    text-align:center;
}
.w9-mini span{display:block;color:#8294a2;font-size:8px;}
.w9-mini strong{display:block;color:#fff;font-size:19px;font-weight:900;margin-top:3px;}
.w9-mini.red{background:#31161b;border-color:#6b2d36;}
.w9-mini.red strong{color:#ff6874;}
.w9-product-head{
    padding:4px 16px 9px 16px;
}
.w9-product-head strong{color:#fff;font-size:16px;}
.w9-caption{color:#8fa1ae;font-size:9px;margin-top:3px;}

/* INCIDENT / ACTION */
.w17-bottom-alerts{
    display:grid;
    grid-template-columns:1.25fr 1fr;
    gap:10px;
    padding:12px 16px 16px 16px;
}
.w17-incident{
    border:1px solid #8e2934;
    background:linear-gradient(145deg,#41161d,#281218);
    border-radius:9px;
    padding:11px 13px;
}
.w17-action{
    border:1px solid #7d6700;
    background:linear-gradient(145deg,#282300,#181704);
    border-radius:9px;
    padding:11px 13px;
}
.w17-bottom-alerts b{display:block;font-size:11px;margin-bottom:4px;}
.w17-incident b{color:#ff828a;}
.w17-action b{color:var(--yellow);}
.w17-bottom-alerts span{color:#d8e0e5;font-size:9px;line-height:1.35;}

/* Streamlit components */
[data-testid="stDataFrame"]{
    background:#081119 !important;
    border:1px solid #263b4c !important;
    border-radius:8px !important;
}
.main .stButton > button,
.main .stDownloadButton > button,
.main a[data-testid="stLinkButton"]{
    background:#0b161f !important;
    color:#eef3f6 !important;
    border:1px solid #30495b !important;
    border-radius:8px !important;
    min-height:42px !important;
    font-size:12px !important;
    font-weight:800 !important;
}
.main .stButton > button:hover,
.main .stDownloadButton > button:hover,
.main a[data-testid="stLinkButton"]:hover{
    border-color:var(--yellow) !important;
}
.main .stButton > button[kind="primary"],
.main a[data-testid="stLinkButton"][kind="primary"]{
    background:var(--yellow) !important;
    border-color:var(--yellow) !important;
    color:#111 !important;
    font-weight:900 !important;
}
[data-testid="stExpander"]{
    background:#0b161f !important;
    border-color:#294151 !important;
}
[data-testid="stExpander"] summary,
[data-testid="stExpander"] summary *{color:#e8eff3 !important;}

@media(max-width:1250px){
    .w9-kpis{grid-template-columns:repeat(3,minmax(0,1fr));}
    .w17-summary{grid-template-columns:repeat(3,minmax(0,1fr));}
}
@media(max-width:760px){
    .w9-kpis{grid-template-columns:repeat(2,minmax(0,1fr));}
    .w17-summary{grid-template-columns:repeat(2,minmax(0,1fr));}
    .w9-flow{grid-template-columns:repeat(2,minmax(0,1fr));}
    .w9-mini-kpis{grid-template-columns:repeat(2,minmax(0,1fr));}
    .w17-bottom-alerts{grid-template-columns:1fr;}
    .w9-title{font-size:28px;}
}

/* =========================================================
   V18 · TABLA COMPACTA
   ========================================================= */
div[class*="st-key-w18_table_header"]{
    background:#071018;
    border:1px solid #263b4b;
    border-radius:10px 10px 0 0;
    padding:2px 8px 1px 8px;
    margin-bottom:0 !important;
}
div[class*="st-key-w18_table_header"] [data-testid="stHorizontalBlock"]{
    gap:.45rem !important;
}
div[class*="st-key-w18_table_header"] [data-testid="stMarkdownContainer"] p{
    margin:0 !important;
}

div[class*="st-key-w18_row_"]{
    background:#0c151d;
    border-left:1px solid #263b4b;
    border-right:1px solid #263b4b;
    border-bottom:1px solid #223543;
    padding:0 8px !important;
    margin:0 !important;
}
div[class*="st-key-w18_row_"]:hover{
    background:#101d27;
}
div[class*="st-key-w18_row_"] [data-testid="stHorizontalBlock"]{
    min-height:54px !important;
    gap:.45rem !important;
    align-items:center !important;
}
div[class*="st-key-w18_row_"] [data-testid="stColumn"]{
    padding-top:0 !important;
    padding-bottom:0 !important;
}
div[class*="st-key-w18_row_"] [data-testid="stElementContainer"]{
    margin-bottom:0 !important;
}
div[class*="st-key-w18_row_"] [data-testid="stMarkdownContainer"]{
    margin:0 !important;
}
div[class*="st-key-w18_row_"] [data-testid="stMarkdownContainer"] p{
    margin:0 !important;
}
div[class*="st-key-w18_row_"] .stButton{
    margin:0 !important;
}
div[class*="st-key-w18_row_"] .stButton > button{
    height:34px !important;
    min-height:34px !important;
    padding:0 12px !important;
    border-radius:999px !important;
    white-space:nowrap !important;
    font-size:10px !important;
    line-height:1 !important;
    font-weight:850 !important;
    background:#071018 !important;
    color:#eef4f7 !important;
    border:1px solid #39566a !important;
}
div[class*="st-key-w18_row_"] .stButton > button:hover{
    background:var(--yellow) !important;
    color:#111 !important;
    border-color:var(--yellow) !important;
}
.w17-cell,
.w17-order{
    font-size:10.5px !important;
    line-height:1.1 !important;
}
.w9-pill{
    padding:4px 8px !important;
    font-size:8.5px !important;
}
.w17-progress{
    gap:5px !important;
}
.w17-progress b{
    min-width:38px !important;
    font-size:9.5px !important;
}
.w17-track{
    min-width:48px !important;
    height:6px !important;
}


/* =========================================================
   V19 · DETALLE DE PRODUCTOS / QUIEBRES
   ========================================================= */
.w19-break-panel{
    margin:14px 0 12px 0;
    padding:14px;
    border:1px solid #6d2630;
    border-left:4px solid #ef4050;
    border-radius:12px;
    background:linear-gradient(180deg,rgba(91,20,29,.28),rgba(22,10,13,.62));
}
.w19-break-heading{
    display:flex;
    justify-content:space-between;
    align-items:center;
    gap:12px;
    margin-bottom:12px;
}
.w19-break-heading > div{
    display:flex;
    align-items:center;
    gap:8px;
}
.w19-break-heading strong{
    color:#fff;
    font-size:15px;
}
.w19-alert-icon{
    display:inline-flex;
    align-items:center;
    justify-content:center;
    width:24px;
    height:24px;
    border-radius:50%;
    background:#d52d3d;
    color:#fff;
    font-weight:950;
}
.w19-break-summary{
    color:#ffb4bc;
    font-size:11px;
    font-weight:800;
}
.w19-break-grid{
    display:grid;
    grid-template-columns:repeat(4,minmax(0,1fr));
    gap:9px;
}
.w19-break-card{
    min-width:0;
    padding:11px;
    border:1px solid #63303a;
    border-radius:10px;
    background:#0b0d10;
}
.w19-break-top{
    display:flex;
    align-items:center;
    justify-content:space-between;
    gap:8px;
}
.w19-break-top strong{
    color:#ffd400;
    font-size:11px;
}
.w19-break-badge{
    padding:3px 7px;
    border-radius:999px;
    background:#8f1f2c;
    color:#fff;
    font-size:8px;
    font-weight:950;
    letter-spacing:.04em;
}
.w19-break-name{
    min-height:31px;
    margin-top:8px;
    color:#f4f7f8;
    font-size:10.5px;
    line-height:1.35;
    font-weight:750;
}
.w19-break-meta{
    display:flex;
    flex-wrap:wrap;
    gap:8px 12px;
    margin-top:9px;
    color:#91a4b2;
    font-size:9px;
}
.w19-break-meta b{
    color:#fff;
}
.w19-break-meta .danger,
.w19-break-meta .danger b{
    color:#ff5d6b;
}
.w19-break-location{
    margin-top:8px;
    padding-top:7px;
    border-top:1px solid #252b31;
    color:#778a98;
    font-size:8.5px;
}
.w19-more{
    margin-top:9px;
    color:#aab6bf;
    font-size:9px;
}
.w19-ok-panel{
    display:flex;
    align-items:center;
    gap:10px;
    margin:14px 0 12px 0;
    padding:12px 14px;
    border:1px solid #175a3a;
    border-radius:11px;
    background:rgba(7,56,34,.30);
}
.w19-ok-icon{
    display:flex;
    align-items:center;
    justify-content:center;
    width:27px;
    height:27px;
    border-radius:50%;
    background:#0b8f55;
    color:#fff;
    font-weight:950;
}
.w19-ok-panel strong{
    display:block;
    color:#eafff3;
    font-size:12px;
}
.w19-ok-panel div span{
    display:block;
    margin-top:2px;
    color:#91b5a2;
    font-size:9px;
}
@media(max-width:1200px){
    .w19-break-grid{grid-template-columns:repeat(2,minmax(0,1fr));}
}
@media(max-width:700px){
    .w19-break-grid{grid-template-columns:1fr;}
    .w19-break-heading{align-items:flex-start;flex-direction:column;}
}


/* =========================================================
   V20 · CONSISTENCIA MONITOR WMS / DETALLE
   ========================================================= */
.w20-source-note{
    display:flex;
    justify-content:space-between;
    align-items:center;
    gap:14px;
    margin:14px 0 9px 0;
    padding:10px 12px;
    border:1px solid #34424d;
    border-left:4px solid #ffd400;
    border-radius:10px;
    background:#0b1116;
}
.w20-source-note strong{
    color:#ffd400;
    font-size:11px;
}
.w20-source-note span{
    color:#91a4b2;
    font-size:9.5px;
}
.w20-detail-summary{
    display:flex;
    justify-content:space-between;
    align-items:center;
    gap:15px;
    margin:16px 0 8px 0;
    padding:12px 13px;
    border:1px solid #26343e;
    border-radius:10px;
    background:#0a1015;
}
.w20-detail-summary strong{
    display:block;
    color:#fff;
    font-size:13px;
}
.w20-detail-summary div>span{
    display:block;
    margin-top:3px;
    color:#8da0ae;
    font-size:9px;
}
.w20-detail-badges{
    display:flex;
    flex-wrap:wrap;
    justify-content:flex-end;
    gap:6px;
}
.w20-detail-badges span{
    margin:0 !important;
    padding:4px 8px;
    border:1px solid #30414d;
    border-radius:999px;
    color:#c7d0d6 !important;
    background:#111a21;
    font-size:8.5px !important;
    font-weight:800;
}
.w20-detail-kpis{
    display:grid;
    grid-template-columns:repeat(4,minmax(0,1fr));
    gap:8px;
    margin-bottom:10px;
}
.w20-detail-kpis>div{
    padding:10px;
    border:1px solid #26343e;
    border-radius:9px;
    background:#0c1318;
}
.w20-detail-kpis span{
    display:block;
    color:#7f93a1;
    font-size:8px;
    text-transform:uppercase;
}
.w20-detail-kpis strong{
    display:block;
    margin-top:4px;
    color:#fff;
    font-size:15px;
}
.w20-pending-panel{
    margin:12px 0;
    padding:14px;
    border:1px solid #665015;
    border-left:4px solid #ffd400;
    border-radius:12px;
    background:linear-gradient(180deg,rgba(89,65,0,.25),rgba(18,15,8,.58));
}
.w20-pending-badge{
    padding:3px 7px;
    border-radius:999px;
    background:#6e5600;
    color:#ffd400;
    font-size:8px;
    font-weight:950;
    letter-spacing:.04em;
}
.w20-pending-summary{
    color:#efd86d;
    font-size:11px;
    font-weight:800;
}
.w20-caution{
    margin-top:10px;
    padding-top:9px;
    border-top:1px solid #5d4a16;
    color:#c8b96e;
    font-size:9px;
}
@media(max-width:850px){
    .w20-source-note,
    .w20-detail-summary{
        align-items:flex-start;
        flex-direction:column;
    }
    .w20-detail-badges{justify-content:flex-start;}
    .w20-detail-kpis{grid-template-columns:repeat(2,minmax(0,1fr));}
}


/* =========================================================
   V21 · ESPEJO DIRECTO DEL MONITOR WMS
   ========================================================= */
.w21-wms-mirror{
    margin:13px 0 10px 0;
    padding:12px;
    border:1px solid #304552;
    border-radius:11px;
    background:#071017;
}
.w21-mirror-title{
    display:flex;
    justify-content:space-between;
    align-items:center;
    gap:12px;
    margin-bottom:9px;
}
.w21-mirror-title strong{
    color:#ffd400;
    font-size:11px;
}
.w21-mirror-title span{
    color:#768b99;
    font-size:8.5px;
}
.w21-mirror-grid{
    display:grid;
    grid-template-columns:repeat(6,minmax(0,1fr));
    gap:7px;
}
.w21-mirror-grid>div{
    min-width:0;
    padding:9px 10px;
    border:1px solid #243945;
    border-radius:8px;
    background:#0b151c;
}
.w21-mirror-grid span{
    display:block;
    color:#7c95a5;
    font-size:7.5px;
    font-weight:800;
    text-transform:uppercase;
    letter-spacing:.04em;
}
.w21-mirror-grid strong{
    display:block;
    overflow:hidden;
    margin-top:4px;
    color:#f8fafb;
    font-size:10.5px;
    text-overflow:ellipsis;
    white-space:nowrap;
}
@media(max-width:1000px){
    .w21-mirror-grid{grid-template-columns:repeat(3,minmax(0,1fr));}
}
@media(max-width:620px){
    .w21-mirror-grid{grid-template-columns:repeat(2,minmax(0,1fr));}
}


/* =========================================================
   V22 · DETALLE ORDENADO Y JERARQUÍA VISUAL
   ========================================================= */
.w22-detail-shell{
    margin-top:12px;
    border:1px solid #263a46;
    border-radius:14px;
    overflow:hidden;
    background:#071017;
}
.w22-titlebar{
    display:flex;
    justify-content:space-between;
    align-items:center;
    gap:18px;
    padding:16px 18px;
    border-bottom:1px solid #20333f;
    background:#071017;
}
.w22-order{
    color:#fff;
    font-size:20px;
    font-weight:800;
}
.w22-order b{color:#ffd400;}
.w22-client{
    margin-top:4px;
    color:#9eb0bd;
    font-size:11px;
    font-weight:700;
}
.w22-title-right{
    display:flex;
    align-items:center;
    gap:10px;
}
.w22-title-right>span{
    color:#7f929f;
    font-size:9px;
}
.w22-main-grid{
    display:grid;
    grid-template-columns:1.25fr .8fr .85fr .9fr .9fr;
    gap:8px;
    padding:14px;
}
.w22-main-card{
    min-width:0;
    padding:12px 13px;
    border:1px solid #263a46;
    border-radius:10px;
    background:#0b151c;
}
.w22-main-card.danger{
    border-color:#74303a;
    background:#281217;
}
.w22-main-card span{
    display:block;
    color:#7390a2;
    font-size:8px;
    font-weight:800;
    text-transform:uppercase;
    letter-spacing:.05em;
}
.w22-main-card strong{
    display:block;
    margin-top:5px;
    color:#fff;
    font-size:12px;
    line-height:1.25;
}
.w22-main-card.danger strong{color:#ff6976;}
.w22-main-card small{
    display:block;
    margin-top:2px;
    color:#80929e;
    font-size:8px;
}
.w22-section-title{
    display:flex;
    justify-content:space-between;
    align-items:center;
    gap:12px;
    margin:17px 0 8px 0;
}
.w22-section-title strong{
    color:#fff;
    font-size:13px;
}
.w22-section-title span,
.w22-detail-note{
    color:#758b99;
    font-size:8.5px;
}
.w22-section-title.products{
    align-items:flex-end;
}
.w22-section-title.products>div:first-child span{
    display:block;
    margin-top:2px;
}
.w22-detail-note{
    max-width:520px;
    text-align:right;
}
.w22-flow{
    display:grid;
    grid-template-columns:repeat(5,minmax(0,1fr));
    gap:7px;
    padding:11px;
    border:1px solid #263a46;
    border-radius:11px;
    background:#081117;
}
.w22-step{
    position:relative;
    min-width:0;
    padding:10px;
    border-radius:8px;
    background:#0c171e;
    text-align:center;
}
.w22-step.done{background:rgba(10,62,41,.28);}
.w22-step.current{
    border:1px solid #8f7300;
    background:rgba(98,76,0,.24);
}
.w22-dot{
    display:flex;
    align-items:center;
    justify-content:center;
    width:24px;
    height:24px;
    margin:0 auto 6px auto;
    border:1px solid #3a4c57;
    border-radius:50%;
    color:#7f939f;
    font-size:11px;
    font-weight:900;
}
.w22-step.done .w22-dot{
    border-color:#19734a;
    background:#0c4d31;
    color:#d9ffeb;
}
.w22-step.current .w22-dot{
    border-color:#ffd400;
    color:#ffd400;
}
.w22-step b{
    display:block;
    color:#f7f9fa;
    font-size:10px;
}
.w22-step span{
    display:block;
    margin-top:3px;
    color:#778c99;
    font-size:8px;
}
.w22-step.current b,
.w22-step.current span{
    color:#ffd400;
}
.w22-wms-grid{
    display:grid;
    grid-template-columns:repeat(6,minmax(0,1fr));
    gap:7px;
    padding:11px;
    border:1px solid #263a46;
    border-radius:11px;
    background:#081117;
}
.w22-wms-grid>div{
    min-width:0;
    padding:9px 10px;
    border-right:1px solid #263a46;
}
.w22-wms-grid>div:last-child{border-right:0;}
.w22-wms-grid span{
    display:block;
    color:#708897;
    font-size:8px;
    font-weight:800;
    text-transform:uppercase;
}
.w22-wms-grid strong{
    display:block;
    overflow:hidden;
    margin-top:4px;
    color:#fff;
    font-size:10px;
    text-overflow:ellipsis;
    white-space:nowrap;
}
.w22-alert{
    display:flex;
    align-items:flex-start;
    gap:10px;
    margin:12px 0 14px 0;
    padding:12px 13px;
    border:1px solid #71313b;
    border-left:4px solid #e74352;
    border-radius:10px;
    background:#281217;
}
.w22-alert-icon{
    display:flex;
    flex:0 0 24px;
    align-items:center;
    justify-content:center;
    width:24px;
    height:24px;
    border-radius:50%;
    background:#c82f3e;
    color:#fff;
    font-weight:950;
}
.w22-alert strong{
    display:block;
    color:#ff7a86;
    font-size:11px;
}
.w22-alert span{
    display:block;
    margin-top:3px;
    color:#b9979b;
    font-size:9px;
    line-height:1.4;
}
@media(max-width:1100px){
    .w22-main-grid{grid-template-columns:repeat(3,minmax(0,1fr));}
    .w22-wms-grid{grid-template-columns:repeat(3,minmax(0,1fr));}
    .w22-wms-grid>div{border-right:0;}
}
@media(max-width:760px){
    .w22-titlebar,
    .w22-title-right,
    .w22-section-title{
        align-items:flex-start;
        flex-direction:column;
    }
    .w22-main-grid{grid-template-columns:repeat(2,minmax(0,1fr));}
    .w22-flow{grid-template-columns:1fr;}
    .w22-wms-grid{grid-template-columns:repeat(2,minmax(0,1fr));}
    .w22-detail-note{text-align:left;}
}


/* =========================================================
   V24 · DETALLE COMPACTO, LEGIBLE Y ORDENADO
   ========================================================= */
.w24-shell{
    margin-top:10px;
    border:1px solid #2c414e;
    border-radius:14px;
    overflow:hidden;
    background:#071017;
}
.w24-head{
    display:flex;
    justify-content:space-between;
    align-items:center;
    gap:16px;
    padding:14px 16px 12px;
    border-bottom:1px solid #223642;
}
.w24-order{color:#fff;font-size:20px;font-weight:850;}
.w24-order b{color:#ffd400;}
.w24-client{margin-top:3px;color:#9dafba;font-size:11px;font-weight:700;}
.w24-head-right{display:flex;align-items:center;gap:10px;}
.w24-head-right>span{color:#7f929f;font-size:9px;}

.w24-summary-grid{
    display:grid;
    grid-template-columns:1.3fr .75fr .8fr 1fr 1fr;
    gap:8px;
    padding:12px;
}
.w24-summary-card{
    min-width:0;
    padding:11px 12px;
    border:1px solid #263b47;
    border-radius:9px;
    background:#0b151c;
}
.w24-summary-card.danger{border-color:#77333d;background:#2b1218;}
.w24-summary-card span{
    display:block;
    color:#728b9a;
    font-size:8px;
    font-weight:850;
    text-transform:uppercase;
    letter-spacing:.05em;
}
.w24-summary-card strong{
    display:block;
    margin-top:4px;
    color:#fff;
    font-size:12px;
    line-height:1.25;
}
.w24-summary-card.danger strong{color:#ff707d;}
.w24-progress-line{
    display:flex;
    justify-content:space-between;
    align-items:center;
    margin-top:3px;
}
.w24-progress-line strong{margin:0;font-size:14px;}
.w24-progress-line em{color:#9aaab4;font-size:9px;font-style:normal;}
.w24-progressbar{
    height:5px;
    margin-top:7px;
    overflow:hidden;
    border-radius:999px;
    background:#1a2b35;
}
.w24-progressbar i{
    display:block;
    height:100%;
    border-radius:999px;
    background:#ffd400;
}

.w24-flow-wrap{
    margin-top:14px;
    padding:11px 12px;
    border:1px solid #263b47;
    border-radius:11px;
    background:#081117;
}
.w24-flow-title{
    margin-bottom:8px;
    color:#fff;
    font-size:11px;
    font-weight:850;
}
.w24-flow{
    display:grid;
    grid-template-columns:repeat(5,minmax(0,1fr));
    gap:6px;
}
.w24-step{
    display:flex;
    align-items:center;
    gap:8px;
    min-width:0;
    padding:8px 9px;
    border-radius:8px;
    background:#0c171e;
}
.w24-step.done{background:rgba(10,62,41,.26);}
.w24-step.current{
    border:1px solid #8d7000;
    background:rgba(97,76,0,.22);
}
.w24-step-dot{
    display:flex;
    flex:0 0 22px;
    align-items:center;
    justify-content:center;
    width:22px;
    height:22px;
    border:1px solid #3b4d57;
    border-radius:50%;
    color:#80939f;
    font-size:10px;
    font-weight:900;
}
.w24-step.done .w24-step-dot{
    border-color:#19734a;
    background:#0c4d31;
    color:#d9ffeb;
}
.w24-step.current .w24-step-dot{
    border-color:#ffd400;
    color:#ffd400;
}
.w24-step b{
    display:block;
    color:#fff;
    font-size:9.5px;
    line-height:1.15;
}
.w24-step span{
    display:block;
    margin-top:2px;
    color:#778c99;
    font-size:7.5px;
}
.w24-step.current b,.w24-step.current span{color:#ffd400;}

.w24-wms-block{
    margin-top:12px;
    border:1px solid #263b47;
    border-radius:11px;
    overflow:hidden;
    background:#081117;
}
.w24-block-head{
    display:flex;
    justify-content:space-between;
    align-items:center;
    gap:12px;
    padding:9px 12px;
    border-bottom:1px solid #223642;
}
.w24-block-head strong{color:#fff;font-size:11px;}
.w24-block-head span{color:#6f8796;font-size:8px;}
.w24-wms-strip{
    display:grid;
    grid-template-columns:repeat(6,minmax(0,1fr));
}
.w24-wms-strip>div{
    min-width:0;
    padding:10px 12px;
    border-right:1px solid #223642;
}
.w24-wms-strip>div:last-child{border-right:0;}
.w24-wms-strip span{
    display:block;
    color:#6f8999;
    font-size:7.5px;
    font-weight:850;
    text-transform:uppercase;
}
.w24-wms-strip strong{
    display:block;
    overflow:hidden;
    margin-top:4px;
    color:#f7fafb;
    font-size:10.5px;
    text-overflow:ellipsis;
    white-space:nowrap;
}

.w24-products-head{
    display:flex;
    justify-content:space-between;
    align-items:flex-end;
    gap:12px;
    margin:16px 0 7px;
}
.w24-products-head strong{display:block;color:#fff;font-size:13px;}
.w24-products-head>div:first-child span{
    display:block;
    margin-top:2px;
    color:#748b99;
    font-size:8px;
}
.w24-product-badges{
    display:flex;
    flex-wrap:wrap;
    justify-content:flex-end;
    gap:5px;
}
.w24-product-badges span{
    padding:4px 7px;
    border-radius:999px;
    font-size:8px;
    font-weight:850;
}
.w24-product-badges .ok{
    border:1px solid #215f42;
    background:#0c2d20;
    color:#85d9ac;
}
.w24-product-badges .warn{
    border:1px solid #705d16;
    background:#282109;
    color:#f2d45b;
}
.w24-note{
    margin:7px 0 11px;
    padding:8px 10px;
    border-left:3px solid #405663;
    background:#0a1218;
    color:#7f929e;
    font-size:8.5px;
}
.w24-note b{color:#dbe4e9;}

.w24-alert{
    display:flex;
    align-items:flex-start;
    gap:10px;
    margin:10px 0 13px;
    padding:10px 12px;
    border:1px solid #71313b;
    border-left:4px solid #e74352;
    border-radius:9px;
    background:#281217;
}
.w24-alert-icon{
    display:flex;
    flex:0 0 22px;
    align-items:center;
    justify-content:center;
    width:22px;height:22px;
    border-radius:50%;
    background:#c82f3e;
    color:#fff;
    font-weight:950;
}
.w24-alert strong{display:block;color:#ff7a86;font-size:10.5px;}
.w24-alert span{
    display:block;
    margin-top:2px;
    color:#b9979b;
    font-size:8.5px;
    line-height:1.35;
}

@media(max-width:1100px){
    .w24-summary-grid{grid-template-columns:repeat(3,minmax(0,1fr));}
    .w24-wms-strip{grid-template-columns:repeat(3,minmax(0,1fr));}
    .w24-wms-strip>div{border-bottom:1px solid #223642;}
}
@media(max-width:760px){
    .w24-head,.w24-head-right,.w24-products-head,.w24-block-head{
        align-items:flex-start;
        flex-direction:column;
    }
    .w24-summary-grid{grid-template-columns:repeat(2,minmax(0,1fr));}
    .w24-flow{grid-template-columns:1fr;}
    .w24-wms-strip{grid-template-columns:repeat(2,minmax(0,1fr));}
    .w24-product-badges{justify-content:flex-start;}
}


/* =========================================================
   V25 · PRODUCTOS SIMPLIFICADOS Y CONCORDANTES CON WMS
   ========================================================= */
.w25-products-head{
    display:flex;
    justify-content:space-between;
    align-items:center;
    gap:12px;
    margin:16px 0 8px;
}
.w25-products-head strong{
    display:block;
    color:#fff;
    font-size:13px;
}
.w25-products-head>div:first-child span{
    display:block;
    margin-top:2px;
    color:#718896;
    font-size:8px;
}
.w25-order-status{
    padding:6px 10px;
    border-radius:999px;
    font-size:9px;
    font-weight:900;
    white-space:nowrap;
}
.w25-order-status.ok{
    border:1px solid #1a754b;
    background:#0b3b27;
    color:#8be0b4;
}
.w25-order-status.warn{
    border:1px solid #766215;
    background:#2a2308;
    color:#f2d45b;
}
.w25-order-status.danger{
    border:1px solid #7a303b;
    background:#32141a;
    color:#ff7a86;
}
.w25-explain{
    margin-bottom:8px;
    padding:9px 11px;
    border-left:3px solid #ffd400;
    background:#0a1218;
    color:#8ca0ad;
    font-size:8.8px;
    line-height:1.4;
}
.w25-explain b{color:#dce4e9;}
@media(max-width:760px){
    .w25-products-head{
        align-items:flex-start;
        flex-direction:column;
    }
}


/* V27 · cantidades de nota de venta */
.w27-status-row{
    display:flex;
    flex-wrap:wrap;
    justify-content:flex-end;
    gap:6px;
}
@media(max-width:760px){
    .w27-status-row{justify-content:flex-start;}
}


/* V29 · resumen ejecutivo de productos */
.w29-product-kpis{
    display:grid;
    grid-template-columns:repeat(4,minmax(0,1fr));
    gap:7px;
    margin:8px 0;
}
.w29-product-kpis>div{
    padding:10px 12px;
    border:1px solid #29404c;
    border-radius:9px;
    background:#0b151c;
}
.w29-product-kpis>div.ok{
    border-color:#215f42;
    background:#0c2d20;
}
.w29-product-kpis>div.warn{
    border-color:#705d16;
    background:#282109;
}
.w29-product-kpis span{
    display:block;
    color:#758d9b;
    font-size:8px;
    font-weight:850;
    text-transform:uppercase;
}
.w29-product-kpis strong{
    display:block;
    margin-top:4px;
    color:#fff;
    font-size:16px;
}
.w29-product-kpis>div.ok strong{color:#8be0b4;}
.w29-product-kpis>div.warn strong{color:#f2d45b;}
@media(max-width:760px){
    .w29-product-kpis{grid-template-columns:repeat(2,minmax(0,1fr));}
}

</style>
        """,
        unsafe_allow_html=True,
    )


# ============================================================
# HELPERS
# ============================================================

def _safe(value, default="-") -> str:
    if value is None:
        return default
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "nat"}:
        return default
    return text


def _yes(value) -> bool:
    return _safe(value, "").upper() in {"SI", "SÍ", "YES", "1", "TRUE"}


def _num(value) -> int:
    try:
        return int(float(value))
    except Exception:
        return 0


def _channel(row: pd.Series) -> str:
    typ = _safe(row.get("ob_type"), "").upper()
    dest = _safe(row.get("dest"), "").upper()
    ecommerce_tokens = ("ECOM", "E-COMMERCE", "B2C", "NOLK", "MARKETPLACE", "MERCADO LIBRE", "FALABELLA", "PARIS")
    return "eCommerce" if any(t in typ for t in ecommerce_tokens) or dest.startswith("ECOM") else "Ejecutivos"


def _has_invoice(row: pd.Series) -> bool:
    raw = _safe(row.get("num_factura") or row.get("numfactura"), "")
    if not raw:
        return False
    try:
        return float(raw) > 0
    except Exception:
        return raw not in {"0", "-"}


def _progress(row: pd.Series) -> tuple[int, int]:
    completed = _num(row.get("cmp_qty_total"))
    total = _num(row.get("ord_qty_total"))
    return completed, total


def _field_has_value(row: pd.Series, field: str) -> bool:
    value = _safe(row.get(field), "")
    return bool(value and value not in {"-", "0", "[]", "[ ]"})


def _check_completed(row: pd.Series) -> bool:
    """
    Replica la evidencia visible de la columna Check del WMS original.

    El visor dibuja Check desde por_04_consolidar_symbol y su color.
    El valor crudo por_04_consolidar=NO, por sí solo, NO prueba que exista
    un check terminado (lo comprobamos en el pedido 0000119651).
    """
    symbol = _safe(row.get("por_04_consolidar_symbol"), "").strip()
    if symbol and symbol not in {"_", "____", "-", "0"}:
        return True

    color = _safe(row.get("por_04_consolidar_color"), "").lower()
    if any(token in color for token in ("green", "verde", "ok", "positivo")):
        return True

    return False


def _pick_completed(row: pd.Series) -> bool:
    """
    En el WMS original la columna Pick muestra opr_pick y toma el color desde
    por_01_rpck_color. Operador informado + estado no rojo = Pick completado.
    """
    if not _field_has_value(row, "opr_pick"):
        return False

    color = _safe(row.get("por_01_rpck_color"), "").lower()
    if any(token in color for token in ("red", "rojo", "negativo")):
        return False

    return True


def _pack_completed(row: pd.Series) -> bool:
    """
    En el WMS original la columna Pack muestra opr_pack y usa
    por_02_pick_color. Si el operador está vacío o el color es rojo,
    Packing todavía no está completo.
    """
    if not _field_has_value(row, "opr_pack"):
        return False

    color = _safe(row.get("por_02_pick_color"), "").lower()
    if any(token in color for token in ("red", "rojo", "negativo")):
        return False

    return True


def _ready_to_invoice(row: pd.Series) -> bool:
    """
    Regla operacional alineada con el visor WMS original.

    'Avance x/x' es solo avance de unidades; NO basta para facturar.
    Se exige además Pick + Pack + Check completados, sin factura,
    sin despacho y sin quiebre activo.
    """
    completed, total = _progress(row)

    if total <= 0 or completed < total:
        return False

    if not _pick_completed(row):
        return False

    if not _pack_completed(row):
        return False

    if not _check_completed(row):
        return False

    if _has_invoice(row):
        return False

    if _safe(row.get("quiebre"), ""):
        return False

    return True


def _stage(row: pd.Series) -> str:
    """
    Etapa estrictamente secuencial:
    Reposición -> Picking -> Packing -> Check -> Listo p/facturar.

    Importante:
    - Tener operador de Pick significa que el pedido está en Picking; NO que
      Picking haya terminado.
    - Nunca se muestra Packing si no existe evidencia visible de Pack.
    - Nunca se muestra Check si no existe evidencia de que Packing ocurrió.
    """
    if _ready_to_invoice(row):
        return "Listo p/facturar"

    # El alcance visual del monitor termina en Listo p/facturar, pero
    # conservamos estados históricos si ya existe factura.
    if _has_invoice(row):
        if _yes(row.get("por_07_despachar")):
            return "Despacho"
        return "Facturado"

    has_pick_operator = _field_has_value(row, "opr_pick")
    has_pack_operator = _field_has_value(row, "opr_pack")
    check_started = _yes(row.get("por_04_consolidar"))
    check_done = _check_completed(row)
    has_break = bool(_safe(row.get("quiebre"), ""))

    # 1. Reposición explícita, siempre antes de Picking.
    if _yes(row.get("por_01_rpck")) and not has_pick_operator:
        return "Reposición"

    # 2. Si hay operador de Pick y todavía no aparece operador de Pack,
    #    el pedido sigue en Picking.
    if has_pick_operator and not has_pack_operator:
        return "Picking"

    # 3. Packing solo existe cuando el WMS ya muestra evidencia real de Pack.
    if has_pack_operator and not check_started and not check_done:
        return "Packing"

    # 4. Check solo puede venir después de Packing.
    if has_pack_operator and (check_started or check_done):
        if check_done:
            if has_break:
                return "Quiebre / revisión"
            # Si el check terminó pero aún no cumple la regla estricta de
            # listo para facturar, mantenerlo en Check.
            return "Check"
        return "Check"

    # 5. Sin operador de Pack nunca saltamos a Packing/Check.
    if has_pick_operator:
        return "Picking"

    # Si aún no existe operador visible, se considera pendiente de Picking,
    # salvo reposición explícita.
    if _yes(row.get("por_01_rpck")):
        return "Reposición"

    return "Picking"


def _prepare(payload: dict) -> pd.DataFrame:
    rows = payload.get("PICK", [])
    if not isinstance(rows, list) or not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows).copy()

    for col in [
        "ob_oid","bill_name","cod_cliente","bill_po","ob_type","dest","sitio",
        "ob_ord_stt","quiebre","crea_date","fecha_creacion","cmp_qty_total",
        "ord_qty_total","num_factura","numfactura","opr_pick","opr_pack",
        "por_01_rpck","por_01_rpck_color",
        "por_02_pick","por_02_pick_color",
        "por_04_consolidar","por_04_consolidar_color","por_04_consolidar_symbol",
        "estado_paletizado_contenedores_P","estado_paletizado_contenedores",
        "tiempo_fin_packing","por_facturar","por_06_enrutar","por_07_despachar",
    ]:
        if col not in df.columns:
            df[col] = ""

    df["_date"] = pd.to_datetime(df["crea_date"], errors="coerce")
    if df["_date"].isna().all():
        df["_date"] = pd.to_datetime(df["fecha_creacion"], errors="coerce", dayfirst=True)

    df["_channel"] = df.apply(_channel, axis=1)
    df["_stage"] = df.apply(_stage, axis=1)
    df["_quiebre"] = df["quiebre"].fillna("").astype(str).str.strip().ne("")
    df["_ready_invoice"] = df.apply(_ready_to_invoice, axis=1)
    df["_search"] = (
        df["ob_oid"].astype(str) + " " +
        df["bill_name"].astype(str) + " " +
        df["cod_cliente"].astype(str) + " " +
        df["bill_po"].astype(str) + " " +
        df["ob_type"].astype(str)
    ).str.lower()

    return df.sort_values("_date", ascending=False, na_position="last").reset_index(drop=True)


def _pill(text: str, kind: str = "gray") -> str:
    return f'<span class="w9-pill {kind}">{escape(_safe(text))}</span>'


def _stage_kind(stage: str) -> str:
    if stage == "Listo p/facturar":
        return "green"
    if stage == "Quiebre / revisión":
        return "red"
    if stage in {"Reposición", "Picking", "Packing", "Check", "Consolidación", "Bajada"}:
        return "yellow"
    return "gray"


def _query_order() -> str:
    try:
        value = st.query_params.get("pedido_wms", "")
    except Exception:
        return ""
    if isinstance(value, list):
        value = value[0] if value else ""
    return _safe(value, "")


def _set_query_order(order_id: str) -> None:
    try:
        st.query_params["pedido_wms"] = order_id
    except Exception:
        pass


# ============================================================
# WMS LIVE
# ============================================================

@st.cache_data(ttl=5, show_spinner=False)
def _load_live() -> dict:
    return load_wms_monitor(timeout=8.0, max_polls=5)


@st.cache_data(ttl=20, show_spinner=False)
def _order_lines(ob_oid: str, ob_type: str, sitio: str, cliente: str, dest: str) -> dict:
    return get_order_lines(
        ob_oid=ob_oid,
        ob_type=ob_type,
        sitio=sitio,
        cliente=cliente,
        dest=dest or "ALL",
    )


WMS_STOCK_SITES = (
    "CASA_MATRIZ",
    "CD_LO_BOZA",
    "PATRONATO",
    "CONCEPCION",
)


@st.cache_data(ttl=60, show_spinner=False)
def _available_stock_site(sku: str, site: str) -> dict:
    if get_available_stock is None:
        return {
            "ok": False,
            "rows": [],
            "summary": {},
            "error": "No está disponible services.wms_inventory.",
        }
    return get_available_stock(
        str(sku).strip(),
        site=site,
        timeout=20.0,
    )


# ============================================================
# KPIs
# ============================================================

def _render_kpis(df: pd.DataFrame) -> None:
    total = len(df)
    repos = int((df["_stage"] == "Reposición").sum())
    picking = int((df["_stage"] == "Picking").sum())
    packing = int((df["_stage"] == "Packing").sum())
    check = int((df["_stage"] == "Check").sum())
    ready = int(df["_ready_invoice"].sum())
    incidents = int(df["_quiebre"].sum())

    cards = [
        ("▤", total, "Pedidos totales", "gray", "Monitor WMS"),
        ("◆", repos, "Reposición", "yellow", "Preparación inicial"),
        ("➜", picking, "Picking", "blue", "Preparación de pedido"),
        ("⬡", packing, "Packing", "yellow", "Empaque"),
        ("✓", check, "Check", "gray", "Control"),
        ("▣", ready, "Listo p/facturar", "green", "Etapa final"),
    ]

    html = '<div class="w9-kpis">'
    for icon, value, label, css, note in cards:
        html += f"""
<div class="w9-kpi {css}">
    <div class="kpi-top">
        <div class="kpi-icon">{escape(icon)}</div>
        <div>
            <div class="kpi-number">{value:,}</div>
            <div class="kpi-label">{escape(label)}</div>
        </div>
    </div>
    <small>{escape(note)}</small>
</div>
"""
    html += "</div>"

    render_html(html)

    if incidents:
        render_html(
            f"""
<div style="margin:-7px 0 16px 0;color:#ff7c85;font-size:10px;font-weight:800">
    ⚠ {incidents:,} pedido(s) con incidencia/quiebre reportado por WMS
</div>
"""
        )


# ============================================================
# TABLA DE PEDIDOS
# ============================================================

def _orders_table(df: pd.DataFrame, selected_order: str) -> None:
    """
    Tabla compacta con botón Ver detalles dentro de Acciones.
    Cada pedido ocupa una sola línea visual.
    """
    widths = [1.0, 1.75, 1.25, .82, .92, 1.10, .58, .82, 1.08, 1.12]

    # Cabecera
    header_wrap = st.container(key="w18_table_header")
    with header_wrap:
        header_cols = st.columns(widths, gap="small")
        headers = [
            "PEDIDO", "CLIENTE", "TIPO", "DESTINO", "CREACIÓN",
            "ETAPA ACTUAL", "WMS", "INCIDENCIA", "AVANCE", "ACCIONES",
        ]
        for col, label in zip(header_cols, headers):
            with col:
                st.markdown(
                    f'<div class="w17-col-head">{escape(label)}</div>',
                    unsafe_allow_html=True,
                )

    for row_index, row in df.reset_index(drop=True).iterrows():
        order = _safe(row.get("ob_oid"))
        typ = _safe(row.get("ob_type"))
        client = _safe(row.get("bill_name"))
        dest = _safe(row.get("dest"))
        stage = _safe(row.get("_stage"))
        status = _safe(row.get("ob_ord_stt"))
        has_break = bool(row.get("_quiebre"))
        completed, total = _progress(row)

        dt = row.get("_date")
        date_text = (
            dt.strftime("%d-%m %H:%M")
            if pd.notna(dt)
            else _safe(row.get("fecha_creacion"))
        )

        percent = 0
        if total > 0:
            percent = max(0, min(100, round((completed / total) * 100)))

        row_wrap = st.container(key=f"w18_row_{row_index}_{order}")
        with row_wrap:
            cols = st.columns(widths, gap="small", vertical_alignment="center")

            with cols[0]:
                st.markdown(
                    f'<div class="w17-order">{escape(order)}</div>',
                    unsafe_allow_html=True,
                )

            with cols[1]:
                st.markdown(
                    f'<div class="w17-cell" title="{escape(client)}">{escape(client)}</div>',
                    unsafe_allow_html=True,
                )

            with cols[2]:
                st.markdown(
                    f'<div class="w17-cell" title="{escape(typ)}">{escape(typ)}</div>',
                    unsafe_allow_html=True,
                )

            with cols[3]:
                st.markdown(
                    f'<div class="w17-cell">{escape(dest)}</div>',
                    unsafe_allow_html=True,
                )

            with cols[4]:
                st.markdown(
                    f'<div class="w17-cell">{escape(date_text)}</div>',
                    unsafe_allow_html=True,
                )

            with cols[5]:
                st.markdown(
                    _pill(stage, _stage_kind(stage)),
                    unsafe_allow_html=True,
                )

            with cols[6]:
                st.markdown(
                    _pill(status, "dark"),
                    unsafe_allow_html=True,
                )

            with cols[7]:
                st.markdown(
                    _pill("Quiebre", "red") if has_break else _pill("—", "gray"),
                    unsafe_allow_html=True,
                )

            with cols[8]:
                st.markdown(
                    f"""
<div class="w17-progress">
    <b>{completed}/{total}</b>
    <div class="w17-track">
        <div class="w17-fill" style="width:{percent}%"></div>
    </div>
</div>
""",
                    unsafe_allow_html=True,
                )

            with cols[9]:
                if st.button(
                    "Ver detalles",
                    key=f"w18_detail_{order}_{row_index}",
                    use_container_width=True,
                ):
                    st.session_state["w12_selected_order"] = order
                    st.rerun()


# ============================================================
# DETALLE DEL PEDIDO
# ============================================================

def _flow_states(row: pd.Series) -> list[tuple[str, str, str]]:
    """
    Representación visual estrictamente secuencial del flujo:
    Reposición -> Picking -> Packing -> Check -> Listo p/facturar.
    """
    stage = _stage(row)
    labels = ["Reposición", "Picking", "Packing", "Check", "Listo p/facturar"]

    # Reposición puede no ser necesaria.
    repo_required = _yes(row.get("por_01_rpck"))

    if stage == "Listo p/facturar":
        return [
            ("Reposición", "Completado" if repo_required else "No requerida", "done"),
            ("Picking", "Completado", "done"),
            ("Packing", "Completado", "done"),
            ("Check", "Completado", "done"),
            ("Listo p/facturar", "Listo", "current"),
        ]

    if stage in {"Facturado", "Despacho"}:
        return [
            ("Reposición", "Completado" if repo_required else "No requerida", "done"),
            ("Picking", "Completado", "done"),
            ("Packing", "Completado", "done"),
            ("Check", "Completado", "done"),
            ("Listo p/facturar", "Completado", "done"),
        ]

    if stage == "Quiebre / revisión":
        return [
            ("Reposición", "Completado" if repo_required else "No requerida", "done"),
            ("Picking", "Completado", "done"),
            ("Packing", "Completado", "done"),
            ("Check", "Revisión", "current"),
            ("Listo p/facturar", "Pendiente", ""),
        ]

    current_idx = {
        "Reposición": 0,
        "Picking": 1,
        "Packing": 2,
        "Check": 3,
    }.get(stage, 1)

    out = []
    for idx, label in enumerate(labels):
        if label == "Reposición" and not repo_required:
            out.append((label, "No requerida", "done" if current_idx > 0 else ""))
        elif idx < current_idx:
            out.append((label, "Completado", "done"))
        elif idx == current_idx:
            out.append((label, "En curso", "current"))
        else:
            out.append((label, "Pendiente", ""))
    return out


def _render_detail(row: pd.Series) -> None:
    order = _safe(row.get("ob_oid"))
    stage = _safe(row.get("_stage"))
    client = _safe(row.get("bill_name"))
    typ = _safe(row.get("ob_type"))
    dest = _safe(row.get("dest"))
    site = _safe(row.get("sitio"))
    status = _safe(row.get("ob_ord_stt"))
    has_break = bool(_safe(row.get("quiebre"), ""))
    completed, total = _progress(row)

    created = row.get("_date")
    created_text = (
        created.strftime("%d-%m-%Y %H:%M")
        if pd.notna(created)
        else _safe(row.get("fecha_creacion"))
    )

    official_requested = max(0, int(total))
    official_completed = max(0, int(completed))
    official_pending = max(0, official_requested - official_completed)
    percent = (
        max(0, min(100, round((official_completed / official_requested) * 100)))
        if official_requested > 0 else 0
    )

    def clean_wms_value(value, default="—"):
        s = _safe(value, "").strip()
        if not s:
            return default
        s = unescape(s)
        s = re.sub(r"<[^>]+>", "", s).strip()
        low = s.lower().replace(" ", "")
        if low in {"", "nbsp;", "_", "____", "-", "0"}:
            return default
        if s in {"✓", "✔"}:
            return "✓"
        return s

    wms_pick = clean_wms_value(row.get("opr_pick"))
    wms_pack = clean_wms_value(row.get("opr_pack"))
    wms_check = clean_wms_value(row.get("por_04_consolidar_symbol"))
    pb_left = clean_wms_value(row.get("estado_paletizado_contenedores_P"), "")
    pb_right = clean_wms_value(row.get("estado_paletizado_contenedores"), "")
    wms_pb = " ".join(x for x in (pb_left, pb_right) if x).strip() or "—"
    wms_time = clean_wms_value(row.get("tiempo_fin_packing"))

    # ------------------------------------------------------------
    # 1) RESUMEN OFICIAL DEL PEDIDO
    # ------------------------------------------------------------
    render_html(
        f"""
<div class="w24-shell">
    <div class="w24-head">
        <div>
            <div class="w24-order">Pedido <b>{escape(order)}</b></div>
            <div class="w24-client">{escape(client)}</div>
        </div>
        <div class="w24-head-right">
            {_pill("Quiebre", "red") if has_break else _pill(stage, _stage_kind(stage))}
            <span>{escape(created_text)}</span>
        </div>
    </div>

    <div class="w24-summary-grid">
        <div class="w24-summary-card">
            <span>Tipo</span>
            <strong>{escape(typ)}</strong>
        </div>
        <div class="w24-summary-card">
            <span>Destino</span>
            <strong>{escape(dest)}</strong>
        </div>
        <div class="w24-summary-card">
            <span>Etapa</span>
            <strong>{escape(stage)}</strong>
        </div>
        <div class="w24-summary-card progress">
            <span>Avance WMS</span>
            <div class="w24-progress-line">
                <strong>{official_completed}/{official_requested}</strong>
                <em>{percent}%</em>
            </div>
            <div class="w24-progressbar"><i style="width:{percent}%"></i></div>
        </div>
        <div class="w24-summary-card {'danger' if has_break else ''}">
            <span>Incidencia</span>
            <strong>{'Pedido con quiebre' if has_break else 'Sin incidencia'}</strong>
        </div>
    </div>
</div>
"""
    )

    # ------------------------------------------------------------
    # 2) FLUJO
    # ------------------------------------------------------------
    flow = '<div class="w24-flow-wrap"><div class="w24-flow-title">Flujo del pedido</div><div class="w24-flow">'
    for label, state, css in _flow_states(row):
        symbol = "✓" if css == "done" else "●" if css == "current" else "·"
        flow += f"""
<div class="w24-step {css}">
    <div class="w24-step-dot">{symbol}</div>
    <div>
        <b>{escape(label)}</b>
        <span>{escape(state)}</span>
    </div>
</div>
"""
    flow += "</div></div>"
    render_html(flow)

    # ------------------------------------------------------------
    # 3) ESTADO OPERATIVO WMS
    # ------------------------------------------------------------
    render_html(
        f"""
<div class="w24-wms-block">
    <div class="w24-block-head">
        <strong>Estado operativo WMS</strong>
        <span>Lectura directa del monitor original</span>
    </div>
    <div class="w24-wms-strip">
        <div><span>Pick</span><strong>{escape(wms_pick)}</strong></div>
        <div><span>Pack</span><strong>{escape(wms_pack)}</strong></div>
        <div><span>Check</span><strong>{escape(wms_check)}</strong></div>
        <div><span>P/B C.</span><strong>{escape(wms_pb)}</strong></div>
        <div><span>Estado</span><strong>{escape(status)}</strong></div>
        <div><span>Tiempo</span><strong>{escape(wms_time)}</strong></div>
    </div>
</div>
"""
    )

    # ------------------------------------------------------------
    # 4) PRODUCTOS: UNA FILA POR SKU, SIN SUMAS ENGAÑOSAS
    # ------------------------------------------------------------
    result = _order_lines(
        order,
        typ,
        site,
        _safe(row.get("cod_cliente")),
        dest or "ALL",
    )

    if not result.get("ok"):
        st.warning(
            f"No se pudo cargar el detalle de productos: "
            f"{result.get('error') or 'sin respuesta'}"
        )
        return

    rows = result.get("rows") or []
    data = pd.DataFrame(rows)

    if data.empty:
        st.info("El WMS no devolvió productos para este pedido.")
        return

    def col(*names):
        for name in names:
            if name in data.columns:
                return data[name]
        return pd.Series([""] * len(data), index=data.index)

    # Construimos primero el detalle crudo incluyendo identificadores de pedido.
    raw = pd.DataFrame(
        {
            "ObOid": col("ObOid", "ob_oid", "obOid").astype(str).str.strip(),
            "ObType": col("ObType", "ob_type", "obType").astype(str).str.strip(),
            "SKU": col("Codigo", "codigo", "SKU", "sku").astype(str).str.strip(),
            "Producto": col("Articulo", "articulo", "Producto", "producto").astype(str).str.strip(),
            "Ubicación": col("Ubicacion", "ubicacion").astype(str).str.strip(),
            "Contenedor": col("Contenedor", "contenedor").astype(str).str.strip(),
            "Línea WMS": col("ObLno", "ob_lno", "Linea", "linea").astype(str).str.strip(),
            "CantidadPedido": pd.to_numeric(
                col("CantidadPedido", "cantidadPedido"), errors="coerce"
            ).fillna(0).astype(int),
            "Cantidad": pd.to_numeric(
                col("Cantidad", "cantidad"), errors="coerce"
            ).fillna(0).astype(int),
        }
    )

    # El webservice puede devolver registros operativos adicionales.
    # Para "Productos del pedido" solo aceptamos filas que correspondan
    # explícitamente al ObOid seleccionado.
    def _norm_order_id(value):
        s = str(value or "").strip()
        digits = re.sub(r"[^0-9]", "", s)
        return digits.lstrip("0") or "0"

    selected_order_id = _norm_order_id(order)

    if "ObOid" in raw.columns:
        same_order = raw["ObOid"].map(_norm_order_id) == selected_order_id
        # Aplicamos el filtro solo si el servicio devolvió al menos una
        # coincidencia exacta; así evitamos vaciar la tabla por un cambio
        # de nombre/formato del backend.
        if same_order.any():
            raw = raw.loc[same_order].copy()

    # El webservice puede devolver, bajo el mismo ObOid, líneas pertenecientes
    # a OTRO tipo de documento. El monitor principal ya nos entrega el ObType
    # correcto del pedido seleccionado, por lo que la nota de venta debe
    # conciliar usando ObOid + ObType.
    def _norm_type(value):
        return re.sub(r"\s+", " ", str(value or "").strip()).upper()

    selected_type = _norm_type(typ)

    if "ObType" in raw.columns and selected_type:
        same_type = raw["ObType"].map(_norm_type) == selected_type
        if same_type.any():
            raw = raw.loc[same_type].copy()

    # Una línea con CantidadPedido <= 0 no representa un producto solicitado
    # por el pedido y no debe entrar en la lista ejecutiva de productos.
    requested_rows = raw["CantidadPedido"] > 0
    if requested_rows.any():
        raw = raw.loc[requested_rows].copy()

    raw = raw.reset_index(drop=True)

    def join_unique(values):
        vals = []
        for v in values:
            s = str(v).strip()
            if s and s.lower() not in {"nan", "none"} and s not in vals:
                vals.append(s)
        return " · ".join(vals) if vals else "—"

    # Para reconstruir la cantidad de la nota de venta por SKU no se deben
    # sumar las filas operativas: el WMS puede repetir el mismo SKU en varias
    # ubicaciones/contenedores. CantidadPedido se repite en esos registros.
    # Por eso tomamos una sola cantidad solicitada por SKU (máximo observado).
    product_view = (
        raw.groupby(["SKU", "Producto"], dropna=False)
        .agg(
            Cantidad_NV=("CantidadPedido", "max"),
            Procesado_WMS=("Cantidad", "sum"),
            Ubicaciones=("Ubicación", join_unique),
            Contenedores=("Contenedor", join_unique),
            Registros_WMS=("SKU", "size"),
        )
        .reset_index()
        .rename(
            columns={
                "Cantidad_NV": "Cantidad NV",
                "Procesado_WMS": "Procesado WMS",
                "Registros_WMS": "Registros WMS",
            }
        )
    )

    # Eliminamos filas sin SKU/producto útil después del filtrado.
    product_view = product_view[
        (product_view["SKU"].astype(str).str.strip() != "") |
        (product_view["Producto"].astype(str).str.strip() != "")
    ].reset_index(drop=True)

    for c in ("Cantidad NV", "Procesado WMS"):
        product_view[c] = pd.to_numeric(
            product_view[c], errors="coerce"
        ).fillna(0).astype(int)

    # El pendiente por SKU se calcula sobre el resumen agrupado.
    product_view["Pendiente"] = (
        product_view["Cantidad NV"] - product_view["Procesado WMS"]
    ).clip(lower=0).astype(int)

    product_view["Estado"] = product_view["Pendiente"].apply(
        lambda n: "COMPLETO" if int(n) == 0 else f"PENDIENTE · {int(n)}"
    )

    sku_count = int(product_view["SKU"].replace("", pd.NA).dropna().nunique())
    nv_units = int(product_view["Cantidad NV"].sum())
    processed_units = int(product_view["Procesado WMS"].sum())
    pending_units = int(product_view["Pendiente"].sum())
    pending_skus = int((product_view["Pendiente"] > 0).sum())
    raw_count = len(raw)
    reconciles = official_requested > 0 and nv_units == official_requested

    if stage == "Listo p/facturar":
        status_text = f"Pedido completo según WMS · {official_completed}/{official_requested}"
        status_class = "ok"
    elif has_break:
        status_text = f"Pedido con quiebre · avance {official_completed}/{official_requested}"
        status_class = "danger"
    else:
        status_text = f"Avance oficial WMS · {official_completed}/{official_requested}"
        status_class = "warn"

    qty_status_class = "ok" if reconciles else "warn"
    qty_status_text = (
        f"Cantidad NV conciliada · {nv_units} uds."
        if reconciles
        else f"Cantidad NV detalle · {nv_units} uds. / WMS oficial {official_requested}"
    )

    render_html(
        f"""
<div class="w25-products-head">
    <div>
        <strong>Productos de la nota de venta</strong>
        <span>{sku_count} SKU · {nv_units} unidades NV</span>
    </div>
    <div class="w27-status-row">
        <div class="w25-order-status {status_class}">{escape(status_text)}</div>
        <div class="w25-order-status {qty_status_class}">{escape(qty_status_text)}</div>
    </div>
</div>
<div class="w29-product-kpis">
    <div><span>Unidades NV</span><strong>{nv_units}</strong></div>
    <div><span>Procesado WMS</span><strong>{processed_units}</strong></div>
    <div class="{'warn' if pending_units else 'ok'}"><span>Pendiente</span><strong>{pending_units}</strong></div>
    <div class="{'warn' if pending_skus else 'ok'}"><span>SKU pendientes</span><strong>{pending_skus}</strong></div>
</div>
<div class="w25-explain">
    <b>Cómo se calcula:</b> Cantidad NV se toma una sola vez por SKU desde <b>CantidadPedido</b>. 
    Procesado WMS suma las fracciones operativas de <b>Cantidad</b> para ese SKU. 
    Pendiente = Cantidad NV − Procesado WMS.
</div>
"""
    )

    executive_view = product_view[
        ["SKU", "Producto", "Cantidad NV", "Procesado WMS", "Pendiente", "Estado"]
    ].copy()

    def _style_exec_row(r):
        if int(r["Pendiente"]) > 0:
            return [
                "background-color: rgba(126, 91, 0, 0.22); color: #ffffff;"
            ] * len(r)
        return [
            "background-color: rgba(10, 43, 31, 0.18); color: #eef8f2;"
        ] * len(r)

    styled_exec = executive_view.style.apply(_style_exec_row, axis=1)

    st.dataframe(
        styled_exec,
        hide_index=True,
        use_container_width=True,
        height=min(420, 42 + len(executive_view) * 38),
        column_config={
            "SKU": st.column_config.TextColumn("SKU", width="small"),
            "Producto": st.column_config.TextColumn("Producto", width="large"),
            "Cantidad NV": st.column_config.NumberColumn("Cantidad NV", format="%d"),
            "Procesado WMS": st.column_config.NumberColumn("Procesado WMS", format="%d"),
            "Pendiente": st.column_config.NumberColumn("Pendiente", format="%d"),
            "Estado": st.column_config.TextColumn("Estado", width="medium"),
        },
    )

    # ------------------------------------------------------------
    # 4.1) STOCK WMS ALTERNATIVO · CONSULTA BAJO DEMANDA
    # ------------------------------------------------------------
    pending_view = product_view.loc[
        product_view["Pendiente"] > 0,
        ["SKU", "Producto", "Cantidad NV", "Procesado WMS", "Pendiente"],
    ].copy()

    # Cuando existe quiebre a nivel pedido pero el detalle operativo no permite
    # señalar un SKU específico, dejamos disponibles todos los SKU del pedido
    # para que el usuario consulte uno de forma explícita.
    stock_candidates = pending_view if not pending_view.empty else product_view[
        ["SKU", "Producto", "Cantidad NV", "Procesado WMS", "Pendiente"]
    ].copy()

    stock_candidates = stock_candidates[
        stock_candidates["SKU"].astype(str).str.strip() != ""
    ].drop_duplicates(subset=["SKU"]).reset_index(drop=True)

    if (has_break or not pending_view.empty) and not stock_candidates.empty:
        render_html(
            """
<div class="w24-wms-block" style="margin-top:14px;">
    <div class="w24-block-head">
        <strong>Stock WMS alternativo</strong>
        <span>Consulta directa a ReporteInventario2020</span>
    </div>
</div>
"""
        )

        option_map = {}
        options = []
        for _, p in stock_candidates.iterrows():
            sku_value = str(p["SKU"]).strip()
            product_name = str(p["Producto"]).strip()
            pending_value = int(p["Pendiente"])
            label = (
                f"{sku_value} · {product_name}"
                + (f" · pendiente {pending_value}" if pending_value > 0 else "")
            )
            option_map[label] = p.to_dict()
            options.append(label)

        selected_label = st.selectbox(
            "SKU a consultar",
            options,
            key=f"stock_sku_{order}",
        )
        selected_product = option_map[selected_label]
        selected_sku = str(selected_product["SKU"]).strip()

        c_stock_1, c_stock_2 = st.columns([1.25, 3.75])
        with c_stock_1:
            consult_stock = st.button(
                "Consultar stock WMS",
                use_container_width=True,
                key=f"stock_query_{order}_{selected_sku}",
            )
        with c_stock_2:
            st.caption(
                "Consulta el SKU en Casa Matriz, CD Lo Boza, Patronato y Concepción. "
                "La cantidad mostrada es la disponibilidad reportada por el WMS."
            )

        state_key = f"wms_stock_lookup_{order}"
        if consult_stock:
            site_results = []
            errors = []

            with st.spinner(f"Consultando stock WMS de {selected_sku}..."):
                for stock_site in WMS_STOCK_SITES:
                    result_stock = _available_stock_site(selected_sku, stock_site)

                    if not result_stock.get("ok"):
                        errors.append(
                            f"{stock_site}: {result_stock.get('error') or 'sin respuesta'}"
                        )
                        continue

                    sku_summary = (
                        (result_stock.get("summary") or {}).get("por_sku") or []
                    )

                    if sku_summary:
                        for item in sku_summary:
                            available_qty = item.get("cantidad_disponible", 0) or 0
                            physical_qty = item.get("cantidad_fisica", 0) or 0
                            reserved_qty = item.get("cantidad_reservada", 0) or 0
                            site_results.append(
                                {
                                    "Sitio": item.get("sitio") or stock_site,
                                    "Bodega": item.get("bodega") or "—",
                                    "Disponible WMS": int(float(available_qty)),
                                    "Físico": int(float(physical_qty)),
                                    "Reservado": int(float(reserved_qty)),
                                    "Ubicaciones": " · ".join(item.get("ubicaciones") or []) or "—",
                                    "Contenedores": " · ".join(item.get("contenedores") or []) or "—",
                                }
                            )

            st.session_state[state_key] = {
                "sku": selected_sku,
                "product": str(selected_product["Producto"]),
                "pending": int(selected_product["Pendiente"]),
                "rows": site_results,
                "errors": errors,
            }

        stock_state = st.session_state.get(state_key)
        if stock_state and stock_state.get("sku") == selected_sku:
            stock_rows = stock_state.get("rows") or []
            stock_errors = stock_state.get("errors") or []

            if stock_rows:
                stock_df = pd.DataFrame(stock_rows)
                stock_df["Disponible WMS"] = pd.to_numeric(
                    stock_df["Disponible WMS"], errors="coerce"
                ).fillna(0).astype(int)
                stock_df = stock_df.sort_values(
                    ["Disponible WMS", "Sitio", "Bodega"],
                    ascending=[False, True, True],
                ).reset_index(drop=True)

                required_qty = max(0, int(stock_state.get("pending") or 0))
                total_available = int(stock_df["Disponible WMS"].sum())

                if required_qty > 0:
                    enough_text = (
                        f"Hay {total_available} uds. disponibles para cubrir "
                        f"{required_qty} uds. pendientes."
                        if total_available >= required_qty
                        else f"Hay {total_available} uds. disponibles y faltan "
                             f"{max(0, required_qty - total_available)} uds. para cubrir el pendiente."
                    )
                else:
                    enough_text = f"Disponibilidad total encontrada: {total_available} uds."

                st.caption(enough_text)

                st.dataframe(
                    stock_df,
                    hide_index=True,
                    use_container_width=True,
                    height=min(340, 42 + len(stock_df) * 38),
                    column_config={
                        "Sitio": st.column_config.TextColumn("Sitio", width="medium"),
                        "Bodega": st.column_config.TextColumn("Bodega", width="medium"),
                        "Disponible WMS": st.column_config.NumberColumn(
                            "Disponible WMS", format="%d"
                        ),
                        "Físico": st.column_config.NumberColumn("Físico", format="%d"),
                        "Reservado": st.column_config.NumberColumn("Reservado", format="%d"),
                        "Ubicaciones": st.column_config.TextColumn(
                            "Ubicaciones", width="large"
                        ),
                        "Contenedores": st.column_config.TextColumn(
                            "Contenedores", width="large"
                        ),
                    },
                )
            elif not stock_errors:
                st.info(
                    f"El WMS no devolvió stock disponible para el SKU {selected_sku} "
                    "en los sitios consultados."
                )

            if stock_errors:
                with st.expander("Errores de consulta de stock WMS", expanded=False):
                    for err in stock_errors:
                        st.write(f"• {err}")

    if has_break:
        render_html(
            """
<div class="w24-alert">
    <div class="w24-alert-icon">!</div>
    <div>
        <strong>Pedido con quiebre reportado por WMS</strong>
        <span>El quiebre está confirmado a nivel del pedido. Con la información disponible no se puede asignar de forma confiable a un SKU específico.</span>
    </div>
</div>
"""
        )

    # El detalle crudo queda disponible, pero fuera de la vista principal.
    with st.expander("Detalle técnico WMS", expanded=False):
        st.caption(
            "Aquí se muestran las líneas operativas que componen el resumen anterior. "
            "Un SKU puede aparecer varias veces por ubicación o contenedor."
        )
        technical_view = raw[
            ["ObOid", "ObType", "SKU", "Producto", "Ubicación", "Contenedor",
             "Línea WMS", "CantidadPedido", "Cantidad"]
        ].copy()
        st.dataframe(
            technical_view,
            hide_index=True,
            use_container_width=True,
            height=min(360, 42 + len(technical_view) * 35),
        )

    # ------------------------------------------------------------
    # 5) ACCIONES
    # ------------------------------------------------------------
    csv = executive_view.to_csv(index=False).encode("utf-8-sig")

    b1, b2, b3 = st.columns([1, 1, 1.25])
    with b1:
        if st.button(
            "Cerrar detalle",
            use_container_width=True,
            key=f"close_{order}",
        ):
            st.session_state.pop("w12_selected_order", None)
            st.rerun()

    with b2:
        st.download_button(
            "Exportar productos",
            data=csv,
            file_name=f"pedido_{order}_productos.csv",
            mime="text/csv",
            use_container_width=True,
        )

    with b3:
        st.link_button(
            "Ver en WMS ↗",
            "http://104.45.239.215/wms/form_monitor_visor_online_especial_operadores_detalle.aspx",
            use_container_width=True,
            type="primary",
        )

    with st.expander("Información técnica", expanded=False):
        st.write(
            {
                "pedido": order,
                "estado_wms": status,
                "sitio": site,
                "destino": dest,
                "avance_oficial": f"{official_completed}/{official_requested}",
                "pendientes_oficiales": official_pending,
                "quiebre_pedido": _safe(row.get("quiebre"), "Sin incidencia"),
                "tipo_documento_filtrado": typ,
                "sku_unicos": sku_count,
                "unidades_nv_detalle": nv_units,
                "procesado_wms_por_sku": processed_units,
                "pendiente_por_sku": pending_units,
                "unidades_wms_oficial": official_requested,
                "cantidad_nv_concilia": reconciles,
                "registros_operativos": raw_count,
            }
        )


# ============================================================
# RENDER
# ============================================================

def render(ctx: dict | None = None) -> None:
    _apply_styles()

    render_html(
        """
<div class="w9-top">
    <div>
        <h1 class="w9-title">Monitor de Pedidos WMS</h1>
        <div class="w9-sub">Seguimiento operativo WMS de pedidos comerciales y eCommerce.</div>
    </div>
    <div class="w9-live"><i></i> WMS Online</div>
</div>
"""
    )

    refresh_col, source_col = st.columns([1, 7], vertical_alignment="center")
    with refresh_col:
        if st.button("Actualizar", icon=":material/refresh:", use_container_width=True):
            _load_live.clear()
            _order_lines.clear()
            st.rerun()

    with st.spinner("Consultando WMS..."):
        result = _load_live()

    if not result.get("ok"):
        st.error("No fue posible obtener datos del monitor WMS.")
        with st.expander("Detalle técnico"):
            st.code(str(result.get("error") or "Sin detalle"))
        return

    detail_payload = result.get("detail") or {}
    df = _prepare(detail_payload)

    if df.empty:
        st.warning("El WMS respondió, pero no entregó pedidos.")
        return

    with source_col:
        render_html(
            f"""
<div class="w9-source">
    Fuente: <b>{escape(str(result.get("source") or "ScoresHub"))}</b>
    · actualización local {datetime.now().strftime("%d-%m-%Y %H:%M:%S")}
    · caché 5 s
</div>
"""
        )

    _render_kpis(df)

    # --------------------------------------------------------
    # FILTROS
    # --------------------------------------------------------
    f1, f2, f3, f4, f5 = st.columns([2.1,1,1,1,1.2], gap="small")

    with f1:
        search = st.text_input(
            "Buscar pedido / cliente",
            placeholder="N° pedido, cliente, RUT, OC o tipo...",
            key="w9_search",
        )

    with f2:
        stage_options = ["Todas"] + sorted(df["_stage"].dropna().astype(str).unique().tolist())
        stage_filter = st.selectbox("Etapa", stage_options, key="w9_stage")

    with f3:
        incidence = st.selectbox(
            "Incidencia",
            ["Todas", "Con quiebre", "Sin incidencia"],
            key="w9_incidence",
        )

    with f4:
        channel = st.selectbox(
            "Tipo de cliente",
            ["Todos", "Ejecutivos", "eCommerce"],
            key="w9_channel",
        )

    destinations = ["Todos"] + sorted(
        [_safe(x) for x in df["dest"].dropna().unique().tolist() if _safe(x) != "-"]
    )
    with f5:
        destination = st.selectbox("Destino", destinations, key="w9_dest")

    total = len(df)
    repos = int((df["_stage"] == "Reposición").sum())
    picking = int((df["_stage"] == "Picking").sum())
    packing = int((df["_stage"] == "Packing").sum())
    ready = int(df["_ready_invoice"].sum())
    breaks = int(df["_quiebre"].sum())

    segment = st.radio(
        "Vista rápida",
        [
            f"Todos ({total})",
            f"Reposición ({repos})",
            f"Picking ({picking})",
            f"Packing ({packing})",
            f"Listos para facturar ({ready})",
            f"Con quiebre ({breaks})",
        ],
        horizontal=True,
        label_visibility="collapsed",
        key="w9_segment",
    )

    filtered = df.copy()

    q = (search or "").strip().lower()
    if q:
        filtered = filtered[filtered["_search"].str.contains(q, regex=False, na=False)]

    if stage_filter != "Todas":
        filtered = filtered[filtered["_stage"] == stage_filter]

    if incidence == "Con quiebre":
        filtered = filtered[filtered["_quiebre"]]
    elif incidence == "Sin incidencia":
        filtered = filtered[~filtered["_quiebre"]]

    if channel != "Todos":
        filtered = filtered[filtered["_channel"] == channel]

    if destination != "Todos":
        filtered = filtered[filtered["dest"].astype(str) == destination]

    if segment.startswith("Reposición"):
        filtered = filtered[filtered["_stage"] == "Reposición"]
    elif segment.startswith("Picking"):
        filtered = filtered[filtered["_stage"] == "Picking"]
    elif segment.startswith("Packing"):
        filtered = filtered[filtered["_stage"] == "Packing"]
    elif segment.startswith("Listos"):
        filtered = filtered[filtered["_ready_invoice"]]
    elif segment.startswith("Con quiebre"):
        filtered = filtered[filtered["_quiebre"]]

    filtered = filtered.reset_index(drop=True)

    # --------------------------------------------------------
    # SELECCIÓN Y PAGINACIÓN
    # --------------------------------------------------------
    selected_order = st.session_state.get("w12_selected_order", "")
    if selected_order and selected_order not in set(df["ob_oid"].astype(str)):
        selected_order = ""

    page_key = "w9_page"
    if page_key not in st.session_state:
        st.session_state[page_key] = 0

    pages = max(1, math.ceil(len(filtered) / PAGE_SIZE))
    st.session_state[page_key] = min(max(int(st.session_state[page_key]), 0), pages - 1)

    start = st.session_state[page_key] * PAGE_SIZE
    end = min(start + PAGE_SIZE, len(filtered))
    page_df = filtered.iloc[start:end].copy()

    # --------------------------------------------------------
    # TABLA PRINCIPAL · ANCHO COMPLETO
    # --------------------------------------------------------
    if page_df.empty:
        st.info("No hay pedidos para los filtros seleccionados.")
    else:
        _orders_table(page_df, selected_order)

    p1, p2, p3 = st.columns([1,3,1], vertical_alignment="center")
    with p1:
        if st.button(
            "Anterior",
            icon=":material/chevron_left:",
            disabled=st.session_state[page_key] <= 0,
            use_container_width=True,
            key="w9_prev",
        ):
            st.session_state[page_key] -= 1
            st.rerun()

    with p2:
        st.caption(
            f"Mostrando {start + 1 if len(filtered) else 0}–{end} de {len(filtered)} pedidos · "
            f"Página {st.session_state[page_key] + 1} de {pages}"
        )

    with p3:
        if st.button(
            "Siguiente",
            icon=":material/chevron_right:",
            disabled=st.session_state[page_key] >= pages - 1,
            use_container_width=True,
            key="w9_next",
        ):
            st.session_state[page_key] += 1
            st.rerun()

    # --------------------------------------------------------
    # DETALLE BAJO DEMANDA · MISMA PÁGINA
    # --------------------------------------------------------
    selected_order = st.session_state.get("w12_selected_order", "")

    if selected_order:
        selected = df[df["ob_oid"].astype(str) == str(selected_order)]

        if not selected.empty:
            st.markdown(
                "<div style='height:12px'></div>",
                unsafe_allow_html=True,
            )

            detail_wrap = st.container(key="w12_detail_area")
            with detail_wrap:
                _render_detail(selected.iloc[0])