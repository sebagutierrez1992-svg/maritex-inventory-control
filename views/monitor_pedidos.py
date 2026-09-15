

from datetime import datetime
from html import escape, unescape
import math
import textwrap
import re

import pandas as pd
import streamlit as st

from services.wms_monitor import get_order_lines, load_wms_monitor
try:
    from services.wms_web_service import search_order, search_report_commands, search_inventory_available
except Exception:
    search_order = None
    search_report_commands = None
    search_inventory_available = None
try:
    from services.wms_inventory import get_alternative_stock
except Exception:
    get_alternative_stock = None
from ui.components import page_header, render_html


PAGE_SIZE = 10
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


/* =========================================================
   V32 · MOCKUP MARITEX WMS · VISUAL EJECUTIVA
   ========================================================= */
:root{--v32-yellow:#ffd000;--v32-green:#24d88a;--v32-blue:#159fe8;--v32-red:#ef4452;}
[data-testid="stAppViewContainer"],[data-testid="stAppViewContainer"]>.main,.main{
 background:radial-gradient(circle at 88% 0%,rgba(27,72,100,.16),transparent 28%),linear-gradient(135deg,#08131d 0%,#071019 54%,#060d13 100%) !important;
}
.block-container{max-width:1680px !important;padding:1.35rem 2.2rem 2.4rem !important;}
.v32-breadcrumb{color:#7890a0;font-size:11px;font-weight:750;letter-spacing:.06em;text-transform:uppercase;margin-bottom:9px;}
.v32-breadcrumb b{color:#9cb0bd;font-weight:850;}
.v32-head{display:flex;justify-content:space-between;align-items:flex-start;gap:22px;margin-bottom:18px;}
.v32-title{margin:0!important;color:#fff!important;font-size:42px!important;font-weight:900!important;letter-spacing:-1.4px!important;line-height:1.02!important;}
.v32-sub{margin-top:8px;color:#b7c6cf;font-size:15px;line-height:1.35;}
.v32-live{display:inline-flex;align-items:center;gap:9px;padding:10px 15px;background:#08141d;border:1px solid #315064;border-radius:999px;color:#eaf2f6;font-size:12px;font-weight:850;white-space:nowrap;}
.v32-live i{width:9px;height:9px;border-radius:50%;background:var(--v32-green);box-shadow:0 0 0 5px rgba(36,216,138,.10);}
div[class*="st-key-v32_refresh"] .stButton>button{min-height:46px!important;height:46px!important;background:linear-gradient(180deg,#ffda16,#ffc800)!important;border:1px solid #ffe55c!important;color:#101215!important;border-radius:10px!important;font-size:13px!important;font-weight:950!important;box-shadow:0 7px 22px rgba(255,208,0,.16)!important;}
div[class*="st-key-v32_refresh"] .stButton>button:hover{transform:translateY(-1px);background:#ffe04a!important;}
.v32-source{min-height:46px;display:flex;align-items:center;padding:0 14px;border:1px solid #263f50;border-radius:10px;background:#08131c;color:#78909f;font-size:10px;}
.v32-source b{color:#ffd000;}
.w9-kpis{grid-template-columns:repeat(6,minmax(0,1fr))!important;gap:14px!important;margin:20px 0 26px!important;}
.w9-kpi{min-height:120px!important;padding:16px!important;border:1px solid #2b4253!important;border-radius:11px!important;background:linear-gradient(145deg,#0d1923,#09131b)!important;box-shadow:none!important;}
.w9-kpi:after{display:none!important}.w9-kpi .kpi-top{gap:13px!important}.w9-kpi .kpi-icon{width:44px!important;height:44px!important;flex:0 0 44px!important;border-radius:11px!important;font-size:20px!important}.w9-kpi .kpi-number{font-size:26px!important}.w9-kpi .kpi-label{font-size:11px!important;margin-top:6px!important}.w9-kpi small{font-size:9px!important;margin-top:14px!important}
.w9-kpi .v32-bars{position:absolute;right:15px;bottom:12px;display:flex;align-items:flex-end;gap:4px;height:34px}.w9-kpi .v32-bars i{display:block;width:4px;border-radius:2px 2px 0 0;background:#294354}.w9-kpi.yellow .v32-bars i{background:#c99f00}.w9-kpi.blue .v32-bars i{background:#0b6091}.w9-kpi.green .v32-bars i{background:#118e5b}
.v32-filters-title{margin:3px 0 8px;color:#7d93a2;font-size:10px;font-weight:850;text-transform:uppercase;letter-spacing:.06em}
[data-testid="stTextInput"] label,[data-testid="stSelectbox"] label{color:#c6d2da!important;font-size:10px!important;font-weight:800!important}
[data-testid="stTextInput"] input,div[data-baseweb="select"]>div{min-height:48px!important;border:1px solid #2e4658!important;border-radius:9px!important;background:#0b1721!important;color:#f5f8fa!important}
[data-testid="stTextInput"] input::placeholder{color:#738896!important;opacity:1!important}
div[class*="st-key-w9_segment"] div[role="radiogroup"]{display:flex!important;gap:7px!important;margin:5px 0 17px!important}
div[class*="st-key-w9_segment"] div[role="radiogroup"] label{min-height:36px!important;display:flex!important;align-items:center!important;padding:0 15px!important;border:1px solid #253a49!important;border-radius:7px!important;background:#0e1a24!important}
div[class*="st-key-w9_segment"] div[role="radiogroup"] label:has(input:checked){background:linear-gradient(180deg,#ffda16,#ffc800)!important;border-color:#ffe259!important;box-shadow:0 5px 16px rgba(255,208,0,.14)!important}
div[class*="st-key-w9_segment"] div[role="radiogroup"] label p{color:#e8eef2!important;font-size:10px!important;font-weight:850!important}div[class*="st-key-w9_segment"] div[role="radiogroup"] label:has(input:checked) p{color:#111!important}
div[class*="st-key-w18_table_header"]{border:1px solid #2b4253!important;border-bottom:1px solid #2c4353!important;border-radius:9px 9px 0 0!important;background:linear-gradient(180deg,#142432,#10202c)!important;padding:0 12px!important}.w17-col-head{color:#aab9c4!important;font-size:8.5px!important;padding:11px 0!important}
div[class*="st-key-w18_row_"]{background:#0b151e!important;border-left:1px solid #263b4b!important;border-right:1px solid #263b4b!important;border-bottom:1px solid #203440!important;padding:0 12px!important}div[class*="st-key-w18_row_"]:hover{background:#0f1d28!important;box-shadow:inset 3px 0 0 #ffd000!important}div[class*="st-key-w18_row_"] [data-testid="stHorizontalBlock"]{min-height:57px!important}.w17-cell,.w17-order{font-size:10px!important}.w17-order{color:#ffd000!important;font-weight:950!important}.w17-progress b{color:#a8d9ff!important}.w17-track{height:7px!important;background:#162b38!important;border:1px solid #355165!important}.w17-fill{background:linear-gradient(90deg,#ffd000,#ffdc30)!important}.w9-pill{font-size:8.5px!important;font-weight:900!important;padding:5px 9px!important;border-radius:8px!important}.w9-pill.yellow{background:#816700!important;color:#fff4b2!important;border-color:#a98900!important}.w9-pill.blue{background:#0879b8!important;color:#fff!important;border-color:#159ade!important}.w9-pill.green{background:#087b49!important;color:#fff!important;border-color:#12a462!important}.w9-pill.red{background:#8b202c!important;color:#fff!important;border-color:#aa3440!important}.w9-pill.dark,.w9-pill.gray{background:#1b2b37!important;color:#d7e1e7!important;border-color:#314857!important}
div[class*="st-key-w18_row_"] .stButton>button{height:34px!important;min-height:34px!important;border-radius:999px!important;background:#08131b!important;border:1px solid #4b7088!important;color:#f4f8fa!important;font-size:9px!important;font-weight:900!important}div[class*="st-key-w18_row_"] .stButton>button:hover{background:#ffd000!important;color:#111!important;border-color:#ffd000!important}
div[class*="st-key-w9_prev"] .stButton>button,div[class*="st-key-w9_next"] .stButton>button{min-height:38px!important;border-radius:8px!important;background:#0c1821!important;border:1px solid #2d4759!important;color:#e7eef2!important}
.w24-shell,.w24-flow-wrap,.w24-wms-block{border-color:#2d4657!important;background:#08131b!important}.w24-head{background:linear-gradient(180deg,#0e1d28,#0a151e)!important}
@media(max-width:1400px){.w9-kpis{grid-template-columns:repeat(3,minmax(0,1fr))!important}.v32-title{font-size:36px!important}}
@media(max-width:800px){.block-container{padding:1rem!important}.v32-head{flex-direction:column}.w9-kpis{grid-template-columns:repeat(2,minmax(0,1fr))!important}.v32-title{font-size:30px!important}}


/* =========================================================
   V33 · DETALLE DE PEDIDO SIMPLIFICADO
   ========================================================= */
.w33-shell{
    margin-top:14px;
    border:1px solid #284151;
    border-radius:14px;
    overflow:hidden;
    background:#071018;
}
.w33-head{
    display:flex;
    justify-content:space-between;
    align-items:center;
    gap:18px;
    padding:16px 18px;
    border-bottom:1px solid #223744;
}
.w33-order{
    color:#fff;
    font-size:23px;
    font-weight:900;
    letter-spacing:-.35px;
}
.w33-order b{color:#ffd000;}
.w33-client{
    margin-top:4px;
    color:#9fb2bf;
    font-size:12px;
    font-weight:750;
}
.w33-head-right{
    display:flex;
    align-items:center;
    gap:9px;
    flex-wrap:wrap;
    justify-content:flex-end;
}
.w33-meta{
    display:flex;
    flex-wrap:wrap;
    gap:0;
    background:#0a151d;
}
.w33-meta>div{
    flex:1 1 170px;
    min-width:150px;
    padding:11px 16px;
    border-right:1px solid #223744;
}
.w33-meta>div:last-child{border-right:none;}
.w33-meta span{
    display:block;
    color:#6f8999;
    font-size:8px;
    font-weight:900;
    text-transform:uppercase;
    letter-spacing:.06em;
}
.w33-meta strong{
    display:block;
    margin-top:4px;
    color:#f5f8fa;
    font-size:11px;
    font-weight:850;
}
.w33-focus{
    margin-top:12px;
    padding:16px 18px;
    border:1px solid #665300;
    border-radius:12px;
    background:linear-gradient(135deg,rgba(88,67,0,.28),rgba(12,17,21,.96));
}
.w33-focus-top{
    display:flex;
    justify-content:space-between;
    align-items:flex-start;
    gap:16px;
}
.w33-focus-kicker{
    color:#ffd000;
    font-size:9px;
    font-weight:900;
    text-transform:uppercase;
    letter-spacing:.08em;
}
.w33-focus-title{
    margin-top:4px;
    color:#fff;
    font-size:19px;
    font-weight:900;
}
.w33-focus-copy{
    margin-top:5px;
    color:#9fb0ba;
    font-size:11px;
}
.w33-focus-copy b{color:#fff;}
.w33-progress-number{
    text-align:right;
    color:#fff;
    font-size:25px;
    font-weight:950;
    line-height:1;
}
.w33-progress-number span{
    display:block;
    margin-top:5px;
    color:#ffd000;
    font-size:11px;
    font-weight:850;
}
.w33-progressbar{
    height:9px;
    margin-top:13px;
    background:#1a2b35;
    border-radius:999px;
    overflow:hidden;
}
.w33-progressbar i{
    display:block;
    height:100%;
    border-radius:999px;
    background:linear-gradient(90deg,#ffbf00,#ffd000);
}
.w33-missing{
    display:flex;
    align-items:center;
    gap:9px;
    margin-top:11px;
    color:#f7f9fa;
    font-size:11px;
    font-weight:800;
}
.w33-missing .num{
    display:inline-flex;
    align-items:center;
    justify-content:center;
    min-width:27px;
    height:27px;
    padding:0 7px;
    border-radius:999px;
    background:#ffd000;
    color:#101214;
    font-weight:950;
}
.w33-section{
    margin-top:16px;
}
.w33-section-head{
    display:flex;
    justify-content:space-between;
    align-items:flex-end;
    gap:12px;
    margin-bottom:8px;
}
.w33-section-head strong{
    color:#fff;
    font-size:14px;
    font-weight:900;
}
.w33-section-head span{
    color:#768d9b;
    font-size:9px;
}
.w33-flow{
    display:grid;
    grid-template-columns:repeat(5,minmax(0,1fr));
    gap:7px;
    padding:11px;
    border:1px solid #28404f;
    border-radius:11px;
    background:#081117;
}
.w33-step{
    position:relative;
    display:flex;
    align-items:center;
    gap:9px;
    padding:10px;
    min-width:0;
    border-radius:9px;
    background:#0c171e;
}
.w33-step.done{background:#0a2c20;}
.w33-step.current{
    border:1px solid #9c7e00;
    background:#272100;
}
.w33-dot{
    display:flex;
    align-items:center;
    justify-content:center;
    flex:0 0 25px;
    width:25px;height:25px;
    border-radius:50%;
    border:1px solid #435a68;
    color:#8297a4;
    font-size:11px;
    font-weight:950;
}
.w33-step.done .w33-dot{
    border-color:#1a8554;
    background:#0e603c;
    color:#fff;
}
.w33-step.current .w33-dot{
    border-color:#ffd000;
    color:#ffd000;
}
.w33-step b{
    display:block;
    color:#f5f8fa;
    font-size:10px;
}
.w33-step span{
    display:block;
    margin-top:2px;
    color:#718995;
    font-size:8px;
}
.w33-step.current b,.w33-step.current span{color:#ffd000;}

.w33-products-summary{
    display:grid;
    grid-template-columns:repeat(3,minmax(0,1fr));
    gap:8px;
    margin-bottom:9px;
}
.w33-summary-card{
    padding:11px 13px;
    border:1px solid #28404f;
    border-radius:10px;
    background:#0b151c;
}
.w33-summary-card.warn{
    border-color:#786100;
    background:#2b2405;
}
.w33-summary-card span{
    display:block;
    color:#758d9b;
    font-size:8px;
    font-weight:900;
    text-transform:uppercase;
}
.w33-summary-card strong{
    display:block;
    margin-top:4px;
    color:#fff;
    font-size:18px;
}
.w33-summary-card.warn strong{color:#ffd000;}
.w33-note{
    margin:8px 0 10px;
    padding:9px 11px;
    border-left:3px solid #3d5665;
    background:#09131a;
    color:#8296a3;
    font-size:9px;
    line-height:1.45;
}
.w33-note b{color:#dfe8ed;}
.w33-stock-callout{
    display:flex;
    justify-content:space-between;
    align-items:center;
    gap:14px;
    margin:14px 0 8px;
    padding:12px 14px;
    border:1px solid #705b00;
    border-radius:10px;
    background:#211c04;
}
.w33-stock-callout strong{
    display:block;
    color:#ffd000;
    font-size:11px;
}
.w33-stock-callout span{
    display:block;
    margin-top:3px;
    color:#b6aa72;
    font-size:9px;
}
.w33-tech-row{
    display:grid;
    grid-template-columns:repeat(6,minmax(0,1fr));
    border:1px solid #28404f;
    border-radius:10px;
    overflow:hidden;
    background:#081117;
}
.w33-tech-row>div{
    padding:10px 12px;
    border-right:1px solid #223744;
}
.w33-tech-row>div:last-child{border-right:none;}
.w33-tech-row span{
    display:block;
    color:#708997;
    font-size:8px;
    font-weight:900;
    text-transform:uppercase;
}
.w33-tech-row strong{
    display:block;
    margin-top:4px;
    color:#f4f7f9;
    font-size:10px;
    overflow:hidden;
    text-overflow:ellipsis;
    white-space:nowrap;
}
@media(max-width:900px){
    .w33-head,.w33-focus-top,.w33-section-head,.w33-stock-callout{
        align-items:flex-start;
        flex-direction:column;
    }
    .w33-head-right{justify-content:flex-start;}
    .w33-progress-number{text-align:left;}
    .w33-flow{grid-template-columns:1fr;}
    .w33-products-summary{grid-template-columns:1fr;}
    .w33-tech-row{grid-template-columns:repeat(2,minmax(0,1fr));}
}


/* =========================================================
   V34 · DETALLE VISUAL TIPO MOCKUP
   ========================================================= */
.w34-detail{
    margin-top:14px;
}
.w34-hero{
    border:1px solid #294454;
    border-radius:16px;
    overflow:hidden;
    background:
        radial-gradient(circle at 95% 10%, rgba(255,208,0,.05), transparent 23%),
        linear-gradient(145deg,#071018,#09141c);
}
.w34-hero-top{
    display:flex;
    justify-content:space-between;
    align-items:center;
    gap:20px;
    padding:18px 20px;
    border-bottom:1px solid #223844;
}
.w34-order-wrap{
    display:flex;
    align-items:center;
    gap:13px;
}
.w34-doc-icon{
    display:flex;
    align-items:center;
    justify-content:center;
    width:48px;height:48px;
    flex:0 0 48px;
    border-radius:50%;
    background:#122432;
    border:1px solid #294556;
    color:#eaf2f6;
    font-size:23px;
}
.w34-order{
    color:#fff;
    font-size:24px;
    font-weight:950;
    letter-spacing:-.4px;
}
.w34-order b{color:#ffd000;}
.w34-client{
    margin-top:4px;
    color:#9eb1bd;
    font-size:12px;
    font-weight:800;
}
.w34-head-actions{
    display:flex;
    align-items:center;
    justify-content:flex-end;
    gap:10px;
    flex-wrap:wrap;
}
.w34-date{
    color:#78909f;
    font-size:9px;
}
.w34-cards{
    display:grid;
    grid-template-columns:1fr 1fr 1fr 1fr 1.65fr;
    gap:10px;
    padding:13px;
}
.w34-card{
    min-width:0;
    padding:12px 13px;
    border:1px solid #294453;
    border-radius:11px;
    background:#0a151d;
}
.w34-card span{
    display:block;
    color:#7290a3;
    font-size:8px;
    font-weight:900;
    text-transform:uppercase;
    letter-spacing:.055em;
}
.w34-card strong{
    display:block;
    margin-top:5px;
    color:#fff;
    font-size:12px;
    font-weight:900;
}
.w34-progress-card{
    display:grid;
    grid-template-columns:auto 1fr auto;
    gap:10px;
    align-items:center;
}
.w34-progress-icon{
    display:flex;
    align-items:center;
    justify-content:center;
    width:36px;height:36px;
    border-radius:50%;
    background:#342b00;
    border:1px solid #675600;
    color:#ffd000;
    font-size:17px;
}
.w34-progress-card .pct{
    color:#fff;
    font-size:11px;
    font-weight:900;
}
.w34-bar{
    height:7px;
    margin-top:7px;
    border-radius:999px;
    background:#1c303c;
    overflow:hidden;
}
.w34-bar i{
    display:block;
    height:100%;
    border-radius:999px;
    background:linear-gradient(90deg,#ffbd00,#ffd000);
}

/* FLOW */
.w34-flow{
    display:grid;
    grid-template-columns:repeat(5,minmax(0,1fr));
    gap:0;
    padding:18px 20px 13px;
    position:relative;
}
.w34-flow:before{
    content:"";
    position:absolute;
    left:8%;
    right:8%;
    top:31px;
    height:2px;
    background:#3a5667;
}
.w34-step{
    position:relative;
    z-index:1;
    text-align:center;
}
.w34-step .dot{
    display:flex;
    align-items:center;
    justify-content:center;
    width:29px;height:29px;
    margin:0 auto 8px;
    border-radius:50%;
    border:2px solid #4b6878;
    background:#0b1720;
    color:#78909d;
    font-size:11px;
    font-weight:950;
}
.w34-step.done .dot{
    border-color:#16d582;
    background:#08472f;
    color:#dffff0;
}
.w34-step.current .dot{
    border-color:#ffd000;
    box-shadow:0 0 0 5px rgba(255,208,0,.08);
    color:#ffd000;
}
.w34-step b{
    display:block;
    color:#eef4f7;
    font-size:10px;
}
.w34-step span{
    display:block;
    margin-top:3px;
    color:#788f9c;
    font-size:8px;
}
.w34-step.current b,.w34-step.current span{color:#ffd000;}

/* CURRENT STATE */
.w34-current{
    display:grid;
    grid-template-columns:1.1fr 1.25fr 1fr;
    gap:0;
    align-items:center;
    margin-top:13px;
    border:1px solid #897000;
    border-radius:11px;
    background:linear-gradient(90deg,#191704,#10170d 40%,#10191d);
    overflow:hidden;
}
.w34-current>div{
    padding:13px 16px;
    border-right:1px solid rgba(255,255,255,.08);
}
.w34-current>div:last-child{border-right:none;}
.w34-current-title{
    color:#ffd000;
    font-size:13px;
    font-weight:950;
}
.w34-current-sub{
    margin-top:3px;
    color:#b8c3ca;
    font-size:9px;
}
.w34-current-copy{
    color:#f4f7f9;
    font-size:10px;
    font-weight:800;
}
.w34-current-progress{
    display:grid;
    grid-template-columns:1fr auto;
    align-items:center;
    gap:11px;
}
.w34-current-progress b{
    color:#fff;
    font-size:12px;
}

/* PRODUCTS */
.w34-products{
    margin-top:14px;
    border:1px solid #294453;
    border-radius:13px;
    overflow:hidden;
    background:#071018;
}
.w34-products-head{
    display:flex;
    justify-content:space-between;
    align-items:center;
    gap:12px;
    padding:13px 16px;
    border-bottom:1px solid #263e4d;
}
.w34-products-head strong{
    color:#fff;
    font-size:15px;
    font-weight:950;
}
.w34-products-head span{
    margin-left:10px;
    color:#77909e;
    font-size:9px;
    font-weight:600;
}
.w34-product-table{
    width:100%;
    border-collapse:collapse;
    table-layout:fixed;
}
.w34-product-table th{
    padding:10px 11px;
    background:#0d1c26;
    border-right:1px solid #233d4c;
    border-bottom:1px solid #2a4656;
    color:#9eb0bb;
    font-size:8px;
    font-weight:850;
    text-align:left;
    text-transform:uppercase;
}
.w34-product-table td{
    padding:11px;
    border-right:1px solid #223945;
    border-bottom:1px solid #1d303a;
    color:#eaf0f3;
    font-size:9.5px;
    vertical-align:middle;
}
.w34-product-table th:last-child,
.w34-product-table td:last-child{border-right:none;}
.w34-product-table tr:last-child td{border-bottom:none;}
.w34-product-table tr.pending td{
    background:linear-gradient(90deg,rgba(113,22,31,.50),rgba(65,18,23,.40));
    border-top:1px solid #d24550;
    border-bottom:1px solid #d24550;
}
.w34-product-table tr.pending td:first-child{
    box-shadow:inset 3px 0 0 #ef4c58;
}
.w34-product-table .sku{
    color:#fff;
    font-weight:900;
}
.w34-product-table .product{
    color:#fff;
    font-weight:750;
}
.w34-product-table .num{
    text-align:right;
    font-variant-numeric:tabular-nums;
}
.w34-product-table .missing{
    color:#ff6975;
    font-weight:950;
}
.w34-sku-progress{
    display:flex;
    align-items:center;
    gap:8px;
}
.w34-sku-track{
    flex:1;
    min-width:55px;
    height:7px;
    border-radius:999px;
    background:#203541;
    overflow:hidden;
}
.w34-sku-fill{
    height:100%;
    border-radius:999px;
    background:#16d582;
}
.w34-sku-fill.warn{background:#ff616b;}
.w34-status{
    display:inline-flex;
    align-items:center;
    gap:6px;
    padding:5px 8px;
    border-radius:999px;
    font-size:8px;
    font-weight:900;
    white-space:nowrap;
}
.w34-status.ok{
    background:#075c39;
    border:1px solid #13875a;
    color:#dbfff0;
}
.w34-status.warn{
    background:#7d2029;
    border:1px solid #a4313c;
    color:#fff;
}
.w34-status i{
    display:block;
    width:7px;height:7px;
    border-radius:50%;
    background:currentColor;
}
.w34-actions{
    display:flex;
    align-items:center;
    justify-content:center;
    width:24px;height:24px;
    border:1px solid #324d5d;
    border-radius:7px;
    color:#c9d4da;
    font-weight:900;
}

/* BOTTOM ALERT */
.w34-bottom{
    display:grid;
    grid-template-columns:1fr auto;
    gap:10px;
    margin-top:10px;
}
.w34-alert{
    display:flex;
    align-items:center;
    gap:11px;
    padding:12px 14px;
    border:1px solid #762b35;
    border-radius:10px;
    background:#1d1115;
}
.w34-alert-icon{
    display:flex;
    align-items:center;
    justify-content:center;
    width:30px;height:30px;
    flex:0 0 30px;
    border-radius:50%;
    background:#ff5b67;
    color:#111;
    font-weight:950;
}
.w34-alert strong{
    display:block;
    color:#ff707b;
    font-size:11px;
}
.w34-alert span{
    display:block;
    margin-top:2px;
    color:#bda0a4;
    font-size:9px;
}
.w34-search-stock{
    display:flex;
    align-items:center;
    justify-content:center;
    min-width:235px;
    padding:0 18px;
    border-radius:10px;
    background:#ffd000;
    color:#111;
    font-size:11px;
    font-weight:950;
}
@media(max-width:1050px){
    .w34-cards{grid-template-columns:repeat(2,minmax(0,1fr));}
    .w34-progress-card{grid-column:span 2;}
}
@media(max-width:780px){
    .w34-hero-top,.w34-products-head{
        align-items:flex-start;
        flex-direction:column;
    }
    .w34-head-actions{justify-content:flex-start;}
    .w34-cards{grid-template-columns:1fr;}
    .w34-progress-card{grid-column:auto;}
    .w34-flow{grid-template-columns:1fr;gap:7px;}
    .w34-flow:before{display:none;}
    .w34-step{text-align:left;display:flex;align-items:center;gap:8px;}
    .w34-step .dot{margin:0;}
    .w34-current{grid-template-columns:1fr;}
    .w34-current>div{border-right:none;border-bottom:1px solid rgba(255,255,255,.08);}
    .w34-current>div:last-child{border-bottom:none;}
    .w34-bottom{grid-template-columns:1fr;}
    .w34-search-stock{min-height:46px;}
}


/* =========================================================
   V35 · TABLA FUNCIONAL + ACCIONES REALES
   ========================================================= */
.w35-products-shell{
    margin-top:14px;
    border:1px solid #294453;
    border-radius:13px;
    overflow:hidden;
    background:#071018;
}
.w35-products-title{
    display:flex;
    align-items:center;
    justify-content:space-between;
    gap:12px;
    padding:14px 16px;
    border-bottom:1px solid #263e4d;
}
.w35-products-title strong{
    color:#fff;
    font-size:15px;
    font-weight:950;
}
.w35-products-title span{
    margin-left:9px;
    color:#78909e;
    font-size:9px;
}
.w35-head-cell{
    color:#88a0ae;
    font-size:8px;
    font-weight:900;
    text-transform:uppercase;
    letter-spacing:.04em;
    padding:3px 0;
}
.w35-cell{
    color:#eef3f6;
    font-size:10px;
    line-height:1.25;
    white-space:nowrap;
    overflow:hidden;
    text-overflow:ellipsis;
}
.w35-cell.sku{font-weight:950;color:#fff;}
.w35-cell.product{font-weight:800;color:#fff;}
.w35-cell.num{text-align:right;font-variant-numeric:tabular-nums;}
.w35-cell.missing{color:#ff6772;font-weight:950;}
.w35-cell.muted{color:#8298a6;}
.w35-state{
    display:inline-flex;
    align-items:center;
    gap:6px;
    padding:5px 9px;
    border-radius:999px;
    font-size:8px;
    font-weight:900;
}
.w35-state.ok{
    color:#dffff0;
    border:1px solid #118355;
    background:#075d3a;
}
.w35-state.warn{
    color:#fff;
    border:1px solid #ad3340;
    background:#7e202a;
}
.w35-state i{
    width:7px;height:7px;border-radius:50%;
    background:currentColor;display:block;
}
.w35-prog{
    display:flex;
    align-items:center;
    gap:8px;
}
.w35-track{
    flex:1;
    min-width:60px;
    height:7px;
    border-radius:999px;
    overflow:hidden;
    background:#203541;
}
.w35-fill{
    height:100%;
    border-radius:999px;
    background:#16d582;
}
.w35-fill.warn{background:#ff616b;}
.w35-prog b{
    min-width:34px;
    color:#fff;
    font-size:9px;
}
div[class*="st-key-w35_products_header"]{
    background:#0d1c26;
    border-left:1px solid #294453;
    border-right:1px solid #294453;
    padding:8px 12px !important;
    margin:0 !important;
}
div[class*="st-key-w35_product_row_"]{
    background:#09141c;
    border-left:1px solid #294453;
    border-right:1px solid #294453;
    border-bottom:1px solid #203642;
    padding:9px 12px !important;
    margin:0 !important;
}
div[class*="st-key-w35_product_row_"]:hover{
    background:#0d1a23;
}
div[class*="st-key-w35_product_pending_"]{
    background:linear-gradient(90deg,rgba(107,23,32,.56),rgba(57,17,22,.42)) !important;
    border-left:4px solid #ff5966 !important;
    border-top:1px solid #bf3944 !important;
    border-bottom:1px solid #bf3944 !important;
}
div[class*="st-key-w35_product_row_"] [data-testid="stHorizontalBlock"],
div[class*="st-key-w35_product_pending_"] [data-testid="stHorizontalBlock"]{
    align-items:center !important;
    gap:.55rem !important;
    min-height:38px !important;
}
div[class*="st-key-w35_product_row_"] .stButton > button,
div[class*="st-key-w35_product_pending_"] .stButton > button{
    height:30px !important;
    min-height:30px !important;
    width:30px !important;
    min-width:30px !important;
    padding:0 !important;
    border-radius:7px !important;
    background:#0a151d !important;
    border:1px solid #375263 !important;
    color:#f3f6f8 !important;
    font-size:16px !important;
}
div[class*="st-key-w35_stock_action"] .stButton > button{
    min-height:56px !important;
    background:#ffd000 !important;
    color:#111 !important;
    border:1px solid #ffd000 !important;
    border-radius:11px !important;
    font-size:12px !important;
    font-weight:950 !important;
}
div[class*="st-key-w35_stock_action"] .stButton > button:hover{
    background:#ffdf3b !important;
    color:#111 !important;
}
.w35-alert{
    display:flex;
    align-items:center;
    gap:12px;
    min-height:56px;
    padding:11px 14px;
    border:1px solid #7a2d37;
    border-radius:11px;
    background:#1c1115;
}
.w35-alert .icon{
    display:flex;align-items:center;justify-content:center;
    width:31px;height:31px;border-radius:50%;
    background:#ff5966;color:#111;font-weight:950;
}
.w35-alert strong{
    display:block;color:#ff707b;font-size:11px;
}
.w35-alert span{
    display:block;margin-top:3px;color:#bca1a6;font-size:9px;
}
.w35-sku-detail{
    margin:8px 0 12px;
    padding:10px 12px;
    border:1px solid #304958;
    border-radius:9px;
    background:#0a151d;
}
.w35-sku-detail strong{color:#ffd000;font-size:11px;}
.w35-sku-detail span{display:block;color:#94a6b1;font-size:9px;margin-top:3px;}


/* V55 · diagnóstico visual de stock + ayuda contextual */
.w55-stock-grid{
    display:grid;
    grid-template-columns:1.15fr repeat(3,minmax(0,1fr));
    gap:10px;
    margin:8px 0 12px;
}
.w55-stock-card{
    min-width:0;
    min-height:72px;
    display:flex;
    align-items:center;
    gap:11px;
    padding:11px 13px;
    border:1px solid #294656;
    border-radius:10px;
    background:linear-gradient(145deg,#0b1922,#08131b);
}
.w55-stock-card.diag{border-left:4px solid #24d57f;}
.w55-stock-icon{
    width:35px;height:35px;flex:0 0 35px;
    display:flex;align-items:center;justify-content:center;
    border-radius:8px;
    background:#123247;
    color:#ccefff;
    font-size:16px;
    font-weight:900;
}
.w55-stock-card.diag .w55-stock-icon{background:#073b27;color:#56e895;}
.w55-stock-card.pick .w55-stock-icon{background:#073b27;color:#56e895;}
.w55-stock-card.ra .w55-stock-icon{background:#403400;color:#ffd000;}
.w55-stock-card.cd .w55-stock-icon{background:#173247;color:#91c9e8;}
.w55-stock-body{min-width:0;}
.w55-stock-label{
    display:flex;
    align-items:center;
    gap:6px;
    color:#a9bfcc;
    font-size:8.5px;
    font-weight:850;
    text-transform:uppercase;
    letter-spacing:.35px;
}
.w55-stock-value{
    margin-top:4px;
    color:#fff;
    font-size:14px;
    font-weight:900;
    white-space:nowrap;
    overflow:hidden;
    text-overflow:ellipsis;
}
.w55-help{
    width:16px;height:16px;flex:0 0 16px;
    display:inline-flex;
    align-items:center;
    justify-content:center;
    border:1px solid #607b8b;
    border-radius:50%;
    background:#0b1c27;
    color:#d6e5ed;
    font-size:9px;
    font-weight:950;
    line-height:1;
    cursor:help;
    transition:all .15s ease;
}
.w55-help:hover{
    background:#ffd000;
    border-color:#ffd000;
    color:#071018;
    transform:translateY(-1px);
}
.w55-stock-action{
    margin:-3px 0 12px;
    padding:8px 11px;
    border:1px solid #665315;
    border-radius:8px;
    background:#211c06;
    color:#e8d36d;
    font-size:9px;
    font-weight:800;
}
.w55-stock-action b{color:#ffd000;}
@media(max-width:1050px){
    .w55-stock-grid{grid-template-columns:repeat(2,minmax(0,1fr));}
}
@media(max-width:650px){
    .w55-stock-grid{grid-template-columns:1fr;}
}


/* V36 · estado SKU no concluyente */
.w35-state.progress{
    color:#ffe985;
    border:1px solid #7c6914;
    background:#2c2509;
}
.w35-fill.progress{background:#ffd000;}


/* =========================================================
   V38 · BLOQUES SIMPLIFICADOS
   ========================================================= */
.w38-stock{
    margin-top:12px;
    border:1px solid #2b4352;
    border-radius:12px;
    background:#081119;
    overflow:hidden;
}
.w38-stock-head{
    display:flex;
    justify-content:space-between;
    align-items:center;
    gap:12px;
    padding:13px 15px;
    border-bottom:1px solid #213743;
}
.w38-stock-head strong{
    color:#fff;
    font-size:13px;
    font-weight:950;
}
.w38-stock-head span{
    color:#7d929f;
    font-size:9px;
}
.w38-stock-body{
    padding:12px 14px 14px;
}
.w38-stock-summary{
    display:flex;
    flex-wrap:wrap;
    gap:8px;
    margin-bottom:10px;
}
.w38-chip{
    display:inline-flex;
    align-items:center;
    gap:6px;
    padding:6px 9px;
    border-radius:999px;
    border:1px solid #304b5b;
    background:#0d1922;
    color:#dce6eb;
    font-size:9px;
    font-weight:800;
}
.w38-chip.warn{
    border-color:#7e6820;
    background:#2a2308;
    color:#ffe071;
}
.w38-actions{
    margin-top:12px;
    padding:12px;
    border:1px solid #2b4352;
    border-radius:12px;
    background:#081119;
}
div[class*="st-key-w38_stock_button_"] .stButton > button{
    background:#ffd000 !important;
    border-color:#ffd000 !important;
    color:#111 !important;
    font-weight:950 !important;
}
div[class*="st-key-w38_stock_button_"] .stButton > button:hover{
    background:#ffe04b !important;
    color:#111 !important;
}
.w38-note{
    margin-top:10px;
    padding:9px 11px;
    border-left:3px solid #385465;
    background:#0a141b;
    color:#8297a4;
    font-size:8.5px;
    line-height:1.4;
}
.w38-note b{color:#dfe8ed;}


/* V40 · detalle expandible debajo de la fila */
div[class*="st-key-w40_inline_detail_"]{
    margin:-3px 0 14px 0 !important;
    padding:12px 14px 16px !important;
    border:1px solid #385565 !important;
    border-top:3px solid #ffd000 !important;
    border-radius:0 0 14px 14px !important;
    background:#050d13 !important;
    box-shadow:0 12px 24px rgba(0,0,0,.18);
}
div[class*="st-key-w40_inline_detail_"] .w34-detail{
    margin-top:0 !important;
}


/* =========================================================
   V44 · CABECERA DEL DETALLE DEL PEDIDO
   ========================================================= */
.w44-detail-card{
    border:1px solid #294758;
    border-radius:16px;
    background:#061018;
    padding:18px 20px;
    margin:4px 0 14px 0;
}
.w44-detail-top{
    display:flex;
    align-items:flex-start;
    justify-content:space-between;
    gap:18px;
    flex-wrap:wrap;
}
.w44-order-kicker{
    color:#84a9bd;
    font-size:11px;
    font-weight:800;
    letter-spacing:.08em;
    text-transform:uppercase;
    margin-bottom:5px;
}
.w44-order-title{
    color:#ffffff;
    font-size:22px;
    line-height:1.15;
    font-weight:900;
    margin:0;
}
.w44-client{
    color:#d9e7ee;
    font-size:14px;
    margin-top:7px;
}
.w44-stage-badge{
    display:inline-flex;
    align-items:center;
    gap:7px;
    border:1px solid #7a6500;
    border-radius:999px;
    background:#2b2500;
    color:#ffd400;
    font-size:12px;
    font-weight:850;
    padding:7px 11px;
    white-space:nowrap;
}
.w44-meta-grid{
    display:grid;
    grid-template-columns:repeat(6,minmax(120px,1fr));
    gap:9px;
    margin-top:16px;
}
.w44-meta{
    border:1px solid #1c3441;
    border-radius:11px;
    background:#09151e;
    padding:10px 12px;
}
.w44-meta-label{
    color:#6f95a9;
    font-size:10px;
    font-weight:800;
    letter-spacing:.05em;
    text-transform:uppercase;
}
.w44-meta-value{
    color:#f4f8fa;
    font-size:13px;
    font-weight:750;
    margin-top:3px;
}
.w56-context-row{display:flex;align-items:flex-start;gap:10px;margin-top:12px;padding:10px 12px;border:1px solid #1c3441;border-radius:10px;background:#08141c;}
.w56-context-icon{width:20px;height:20px;flex:0 0 20px;display:flex;align-items:center;justify-content:center;border:1px solid #526c7a;border-radius:50%;color:#b9cfda;font-size:11px;font-weight:900;}
.w56-context-text{color:#9fb8c5;font-size:11px;line-height:1.45;}
.w56-context-text b{color:#e9f2f6;}
.w56-incidence-value{color:#ff6b78!important;}
.w44-progress-wrap{
    margin-top:15px;
    border-top:1px solid #1c3441;
    padding-top:14px;
}
.w44-progress-line{
    display:flex;
    align-items:center;
    justify-content:space-between;
    gap:12px;
    margin-bottom:8px;
}
.w44-progress-title{
    color:#f7fafc;
    font-size:13px;
    font-weight:850;
}
.w44-progress-numbers{
    color:#d6e2e8;
    font-size:12px;
    font-weight:700;
}
.w44-progress-track{
    height:10px;
    border-radius:999px;
    overflow:hidden;
    background:#1a2b35;
}
.w44-progress-fill{
    height:100%;
    border-radius:999px;
    background:#ffd000;
}
.w44-progress-foot{
    display:flex;
    gap:18px;
    flex-wrap:wrap;
    margin-top:9px;
    color:#9fb8c5;
    font-size:11px;
}
.w44-progress-foot b{
    color:#ffffff;
}
@media (max-width: 900px){
    .w44-meta-grid{
        grid-template-columns:repeat(2,minmax(120px,1fr));
    }
}


<style>
.w35-state.picking{background:#103653!important;border-color:#1f628b!important;color:#5fc0ff!important;}
.w35-state.packing{background:#3a3100!important;border-color:#7a6500!important;color:#ffe34d!important;}
.w35-state.repo{background:#2e1b4f!important;border-color:#6940a5!important;color:#c997ff!important;}
.w35-state.invoice{background:#103b28!important;border-color:#1b6844!important;color:#70e5a9!important;}
.w35-state.check{background:#24313a!important;border-color:#455967!important;color:#d0dae0!important;}
</style>
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

    # Un valor histórico en `quiebre` no debe bloquear indefinidamente
    # la etapa final cuando el WMS ya cerró operacionalmente el pedido.
    # Si Pick + Pack + Check están completos y las unidades están 100%,
    # el pedido queda listo para facturar aunque `quiebre` conserve texto.
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
    df["_ready_invoice"] = df.apply(_ready_to_invoice, axis=1)
    df["_stage"] = df.apply(_stage, axis=1)

    # `quiebre` puede quedar informado como antecedente histórico aun cuando
    # el pedido ya terminó Pick + Pack + Check y está 100% procesado.
    # Para filtros/KPI/incidencia visual contamos solo quiebres activos.
    _historical_break = df["quiebre"].fillna("").astype(str).str.strip().ne("")
    # V58: conservar por separado la incidencia original informada por WMS.
    # `_quiebre` se reemplaza más adelante por el quiebre REAL confirmado
    # contra avance por SKU + PICK CM + RA CM + CD_LO_BOZA.
    df["_quiebre_wms"] = _historical_break & ~df["_ready_invoice"]
    df["_quiebre"] = df["_quiebre_wms"]
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


@st.cache_data(ttl=30, show_spinner=False)
def _order_product_progress(order: str) -> dict:
    """Carga Reporte Comandos Picking y agrupa la cantidad por SKU."""
    if search_report_commands is None:
        return {
            "ok": False,
            "order": str(order).strip(),
            "rows": [],
            "grouped": [],
            "total_quantity": 0,
            "error": "search_report_commands no está disponible.",
        }

    return search_report_commands(
        order=str(order).strip(),
        save_html=False,
        debug=False,
    )


@st.cache_data(ttl=60, show_spinner=False)
def _sku_operational_stock(sku: str, pending_qty: int) -> dict:
    """Diagnóstico operacional por SKU: PICK -> RA -> CD -> Quiebre.

    Bodega 25 queda excluida por search_inventory_available. CD_LO_BOZA
    solo se consulta cuando CASA_MATRIZ no alcanza.
    """
    sku = str(sku or "").strip()
    pending = max(0, int(pending_qty or 0))

    base = {
        "ok": False, "sku": sku, "pending": pending,
        "pick": 0, "ra": 0, "cm_total": 0, "cd": 0,
        "estado": "Sin diagnóstico", "accion_qty": 0, "deficit": 0,
        "error": None,
    }

    if pending <= 0:
        return {**base, "ok": True, "estado": "Procesado"}

    if search_inventory_available is None:
        return {**base, "error": "search_inventory_available no está disponible."}

    try:
        cm = search_inventory_available(sku, site="CASA_MATRIZ", debug=False)
        if not cm.get("ok"):
            return {**base, "error": cm.get("error") or "Error consultando CASA_MATRIZ."}

        by_cm = cm.get("by_warehouse") or {}
        pick = int(float(by_cm.get("PICK UN") or 0))
        ra = int(float(by_cm.get("RA") or 0))
        cm_total = pick + ra

        if pick >= pending:
            return {**base, "ok": True, "pick": pick, "ra": ra,
                    "cm_total": cm_total, "estado": "Picking"}

        if cm_total >= pending:
            return {**base, "ok": True, "pick": pick, "ra": ra,
                    "cm_total": cm_total, "estado": "Reposición",
                    "accion_qty": max(0, pending - pick)}

        cd_result = search_inventory_available(sku, site="CD_LO_BOZA", debug=False)
        if not cd_result.get("ok"):
            return {**base, "pick": pick, "ra": ra, "cm_total": cm_total,
                    "error": cd_result.get("error") or "Error consultando CD_LO_BOZA."}

        cd = int(float(cd_result.get("total_operational") or 0))
        total_operativo = cm_total + cd

        if total_operativo >= pending:
            return {**base, "ok": True, "pick": pick, "ra": ra,
                    "cm_total": cm_total, "cd": cd,
                    "estado": "Abastecimiento CD",
                    "accion_qty": max(0, pending - cm_total)}

        return {**base, "ok": True, "pick": pick, "ra": ra,
                "cm_total": cm_total, "cd": cd, "estado": "Quiebre",
                "deficit": max(0, pending - total_operativo)}
    except Exception as exc:
        return {**base, "error": str(exc)}


@st.cache_data(ttl=120, show_spinner=False)
def _order_real_break_status(
    order: str,
    ob_type: str,
    sitio: str,
    cliente: str,
    dest: str,
    official_completed: int,
    official_requested: int,
) -> dict:
    """Confirma si un pedido tiene al menos un SKU en quiebre operacional real.

    Solo considera un SKU como Quiebre cuando:
      pendiente SKU > PICK CM + RA CM + CD_LO_BOZA.

    El pendiente por SKU se usa únicamente si Reporte Comandos Picking
    reconcilia exactamente con cmp_qty_total y el detalle solicitado reconcilia
    con ord_qty_total. Bodega 25 ya queda excluida por
    search_inventory_available().
    """
    base = {
        "ok": False,
        "real_break": False,
        "status": "Sin validar",
        "break_skus": [],
        "checked_skus": 0,
        "error": None,
    }

    try:
        official_completed = max(0, int(official_completed or 0))
        official_requested = max(0, int(official_requested or 0))

        if official_requested <= 0:
            return {**base, "status": "Sin cantidad solicitada"}

        if official_completed >= official_requested:
            return {**base, "ok": True, "status": "Sin quiebre real"}

        detail = _order_lines(
            str(order).strip(),
            str(ob_type).strip(),
            str(sitio).strip(),
            str(cliente).strip(),
            str(dest).strip() or "ALL",
        )
        if not detail.get("ok"):
            return {**base, "error": detail.get("error") or "No fue posible cargar detalle WMS."}

        rows = detail.get("rows") or []
        if not rows:
            return {**base, "error": "El pedido no devolvió líneas de producto."}

        data = pd.DataFrame(rows)

        def _col(*names):
            for name in names:
                if name in data.columns:
                    return data[name]
            return pd.Series([""] * len(data), index=data.index)

        raw = pd.DataFrame({
            "ObOid": _col("ObOid", "ob_oid", "obOid").astype(str).str.strip(),
            "ObType": _col("ObType", "ob_type", "obType").astype(str).str.strip(),
            "SKU": _col("Codigo", "codigo", "SKU", "sku").astype(str).str.strip(),
            "CantidadPedido": pd.to_numeric(
                _col("CantidadPedido", "cantidadPedido"), errors="coerce"
            ).fillna(0).astype(int),
        })

        def _norm_order(value):
            digits = re.sub(r"[^0-9]", "", str(value or "").strip())
            return digits.lstrip("0") or "0"

        same_order = raw["ObOid"].map(_norm_order) == _norm_order(order)
        if same_order.any():
            raw = raw.loc[same_order].copy()

        norm_type = re.sub(r"\s+", " ", str(ob_type or "").strip()).upper()
        same_type = raw["ObType"].map(
            lambda x: re.sub(r"\s+", " ", str(x or "").strip()).upper()
        ) == norm_type
        if same_type.any():
            raw = raw.loc[same_type].copy()

        raw = raw.loc[raw["CantidadPedido"] > 0].copy()
        raw = raw.loc[raw["SKU"].astype(str).str.strip() != ""].copy()
        if raw.empty:
            return {**base, "error": "No hay SKU solicitados utilizables para validar."}

        requested = (
            raw.groupby("SKU", dropna=False)["CantidadPedido"]
            .max()
            .astype(int)
            .to_dict()
        )
        requested_total = int(sum(requested.values()))
        if requested_total != official_requested:
            return {
                **base,
                "status": "No conciliado",
                "error": f"Detalle solicitado {requested_total} != monitor {official_requested}.",
            }

        report = _order_product_progress(str(order).strip())
        if not report.get("ok"):
            return {**base, "status": "No conciliado", "error": report.get("error") or "Reporte Comandos Picking no disponible."}

        try:
            report_total = int(float(report.get("total_quantity") or 0))
        except Exception:
            report_total = 0

        if report_total != official_completed:
            return {
                **base,
                "status": "No conciliado",
                "error": f"Reporte comandos {report_total} != monitor {official_completed}.",
            }

        processed = {}
        for item in report.get("grouped") or []:
            sku = str(item.get("Producto") or "").strip()
            if not sku:
                continue
            try:
                qty = max(0, int(float(item.get("Cantidad") or 0)))
            except Exception:
                qty = 0
            processed[sku] = qty

        checked = 0
        break_skus = []
        for sku, qty_requested in requested.items():
            qty_processed = min(max(0, int(processed.get(sku, 0))), max(0, int(qty_requested)))
            pending = max(0, int(qty_requested) - qty_processed)
            if pending <= 0:
                continue

            diag = _sku_operational_stock(str(sku), pending)
            if not diag.get("ok"):
                return {
                    **base,
                    "status": "Sin validar",
                    "checked_skus": checked,
                    "error": diag.get("error") or f"No fue posible validar stock de {sku}.",
                }

            checked += 1
            if str(diag.get("estado") or "").strip() == "Quiebre":
                break_skus.append({
                    "sku": str(sku),
                    "pending": pending,
                    "pick": int(diag.get("pick") or 0),
                    "ra": int(diag.get("ra") or 0),
                    "cd": int(diag.get("cd") or 0),
                    "deficit": int(diag.get("deficit") or 0),
                })
                # Para incidencia a nivel pedido basta confirmar un SKU real.
                return {
                    **base,
                    "ok": True,
                    "real_break": True,
                    "status": "Quiebre real",
                    "break_skus": break_skus,
                    "checked_skus": checked,
                }

        return {
            **base,
            "ok": True,
            "real_break": False,
            "status": "Sin quiebre real",
            "break_skus": [],
            "checked_skus": checked,
        }

    except Exception as exc:
        return {**base, "error": str(exc)}


def _attach_real_breaks(df: pd.DataFrame) -> pd.DataFrame:
    """V58 · Reemplaza la incidencia operativa por quiebres realmente confirmados.

    Para no castigar al WMS con consultas innecesarias, solo valida pedidos que
    vienen con señal de quiebre desde WMS. Una señal WMS no confirmada NO se
    cuenta como quiebre real; queda disponible en `_quiebre_wms`.
    """
    if df.empty:
        return df

    out = df.copy()
    out["_quiebre_real"] = False
    out["_quiebre_checked"] = False
    out["_quiebre_diag_status"] = "No aplica"

    candidate_mask = out.get("_quiebre_wms", pd.Series(False, index=out.index)).fillna(False).astype(bool)

    for idx in out.index[candidate_mask]:
        row = out.loc[idx]
        completed, requested = _progress(row)
        diag = _order_real_break_status(
            _safe(row.get("ob_oid")),
            _safe(row.get("ob_type")),
            _safe(row.get("sitio")),
            _safe(row.get("cod_cliente")),
            _safe(row.get("dest"), "ALL"),
            completed,
            requested,
        )
        out.at[idx, "_quiebre_checked"] = bool(diag.get("ok"))
        out.at[idx, "_quiebre_real"] = bool(diag.get("ok") and diag.get("real_break"))
        out.at[idx, "_quiebre_diag_status"] = str(diag.get("status") or "Sin validar")

    # Desde V58, `_quiebre` significa exclusivamente QUIEBRE REAL CONFIRMADO.
    out["_quiebre"] = out["_quiebre_real"].astype(bool)
    return out


@st.cache_data(ttl=60, show_spinner=False)
def _alternative_stock(sku: str, missing_qty: int) -> dict:
    if get_alternative_stock is None:
        return {
            "ok": False,
            "sku": str(sku).strip(),
            "faltan": int(missing_qty or 0),
            "bodegas": [],
            "recomendacion": None,
            "error": "No está disponible services.wms_inventory.get_alternative_stock.",
        }

    return get_alternative_stock(
        str(sku).strip(),
        missing_qty=max(0, int(missing_qty or 0)),
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
        ("▤", total, "Pedidos totales", "gray", "Monitor activo"),
        ("◷", repos, "Reposición", "yellow", "Preparación inicial"),
        ("➜", picking, "Picking", "blue", "Preparación de pedido"),
        ("⬡", packing, "Packing", "yellow", "Empaque"),
        ("✓", check, "Check", "gray", "Control"),
        ("▣", ready, "Listo p/facturar", "green", "Etapa final"),
    ]
    heights = [9, 16, 23, 31, 38]
    html = '<div class="w9-kpis">'
    for icon, value, label, css, note in cards:
        bars = "".join(f'<i style="height:{h}px"></i>' for h in heights)
        html += (f'<div class="w9-kpi {css}">'
                 f'<div class="kpi-top"><div class="kpi-icon">{escape(icon)}</div><div>'
                 f'<div class="kpi-number">{value:,}</div><div class="kpi-label">{escape(label)}</div></div></div>'
                 f'<small>{escape(note)}</small><div class="v32-bars">{bars}</div></div>')
    html += '</div>'
    render_html(html)
    if incidents:
        render_html(f'<div style="margin:-12px 0 18px;color:#ff707b;font-size:10px;font-weight:850">⚠ {incidents:,} pedido(s) con quiebre real confirmado por stock operacional</div>')


# ============================================================
# TABLA DE PEDIDOS
# ============================================================

def _orders_table(df: pd.DataFrame, selected_order: str) -> None:
    """Tabla principal estilo mockup, manteniendo la lógica WMS."""
    widths = [1.0, 1.75, 1.05, .95, 1.15, .95, .88, 1.10, .95]
    header_wrap = st.container(key="w18_table_header")
    with header_wrap:
        header_cols = st.columns(widths, gap="small")
        headers = ["N° PEDIDO", "CLIENTE", "RUT / CÓDIGO", "FECHA PEDIDO", "ETAPA WMS", "TIPO", "QUIEBRE REAL", "% AVANCE", "ACCIONES"]
        for col, label in zip(header_cols, headers):
            with col:
                st.markdown(f'<div class="w17-col-head">{escape(label)}</div>', unsafe_allow_html=True)
    for row_index, row in df.reset_index(drop=True).iterrows():
        order = _safe(row.get("ob_oid"))
        client = _safe(row.get("bill_name"))
        customer_code = _safe(row.get("cod_cliente"))
        typ = _safe(row.get("ob_type"))
        stage = _safe(row.get("_stage"))
        has_break = bool(row.get("_quiebre"))
        completed, total = _progress(row)
        dt = row.get("_date")
        date_text = dt.strftime("%d/%m/%Y") if pd.notna(dt) else _safe(row.get("fecha_creacion"))
        percent = max(0, min(100, round((completed / total) * 100))) if total > 0 else 0
        row_wrap = st.container(key=f"w18_row_{row_index}_{order}")
        with row_wrap:
            cols = st.columns(widths, gap="small", vertical_alignment="center")
            with cols[0]: st.markdown(f'<div class="w17-order">{escape(order)}</div>', unsafe_allow_html=True)
            with cols[1]: st.markdown(f'<div class="w17-cell" title="{escape(client)}">{escape(client)}</div>', unsafe_allow_html=True)
            with cols[2]: st.markdown(f'<div class="w17-cell">{escape(customer_code)}</div>', unsafe_allow_html=True)
            with cols[3]: st.markdown(f'<div class="w17-cell">{escape(date_text)}</div>', unsafe_allow_html=True)
            with cols[4]: st.markdown(_pill(stage, _stage_kind(stage)), unsafe_allow_html=True)
            with cols[5]: st.markdown(f'<div class="w17-cell" title="{escape(typ)}">{escape(typ)}</div>', unsafe_allow_html=True)
            with cols[6]: st.markdown(_pill("Quiebre real", "red") if has_break else _pill("Sin quiebre", "dark"), unsafe_allow_html=True)
            with cols[7]:
                fill_color = "#24d88a" if percent >= 100 else "#ffd000"
                progress_html = (f'<div class="w17-progress"><div class="w17-track">'
                                 f'<div class="w17-fill" style="width:{percent}%;background:{fill_color} !important"></div>'
                                 f'</div><b>{percent}%</b></div>')
                st.markdown(
        textwrap.dedent(progress_html).strip(),
        unsafe_allow_html=True,
    )
            with cols[8]:
                is_open = str(st.session_state.get("w12_selected_order", "")) == str(order)
                detail_label = "◉  Ocultar" if is_open else "◉  Ver detalle"

                if st.button(
                    detail_label,
                    key=f"w18_detail_{order}_{row_index}",
                    use_container_width=True,
                ):
                    if is_open:
                        st.session_state.pop("w12_selected_order", None)
                    else:
                        st.session_state["w12_selected_order"] = order
                    st.rerun()

        # V40: detalle expandible inmediatamente debajo del pedido.
        if str(st.session_state.get("w12_selected_order", "")) == str(order):
            inline_wrap = st.container(key=f"w40_inline_detail_{row_index}_{order}")
            with inline_wrap:
                _render_detail(row)


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
    """
    V34 · Detalle visual tipo mockup.

    Mantiene el avance oficial del pedido desde cmp_qty_total / ord_qty_total.
    El detalle por SKU se muestra completo y solo se resalta un faltante cuando
    existe evidencia compatible con el faltante oficial del pedido.
    """
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
    # V44 · RESUMEN PRINCIPAL DEL PEDIDO
    # ------------------------------------------------------------
    # Esta información proviene de la fila oficial del monitor y se muestra
    # antes de cargar las líneas del pedido, por lo que sigue visible incluso
    # si el endpoint de detalle de productos falla.
    client_label = client if client and client != "—" else "Cliente no informado"
    stage_label = stage if stage and stage != "—" else (status if status and status != "—" else "Sin estado")
    status_label = status if status and status != "—" else stage_label
    type_label = typ if typ and typ != "—" else "—"
    dest_label = dest if dest and dest != "—" else "—"
    site_label = site if site and site != "—" else "Casa Matriz"
    created_label = created_text if created_text and created_text != "—" else "—"
    incidence_wms_label = "Quiebre" if has_break else "Sin incidencia"

    # V47 · HTML compacto. Evita que Markdown interprete los <div>
    # internos como un bloque de código por indentación.
    progress_html = (
        f'<div class="w44-detail-card">'
        f'<div class="w44-detail-top">'
        f'<div>'
        f'<div class="w44-order-kicker">Detalle del pedido WMS</div>'
        f'<div class="w44-order-title">Pedido {escape(order)}</div>'
        f'<div class="w44-client">Cliente: <b>{escape(client_label)}</b></div>'
        f'</div>'
        f'<div class="w44-stage-badge">● Etapa WMS: {escape(stage_label)}</div>'
        f'</div>'
        f'<div class="w44-meta-grid">'
        f'<div class="w44-meta"><div class="w44-meta-label">Estado WMS</div>'
        f'<div class="w44-meta-value">{escape(status_label)}</div></div>'
        f'<div class="w44-meta"><div class="w44-meta-label">Tipo</div>'
        f'<div class="w44-meta-value">{escape(type_label)}</div></div>'
        f'<div class="w44-meta"><div class="w44-meta-label">Destino</div>'
        f'<div class="w44-meta-value">{escape(dest_label)}</div></div>'
        f'<div class="w44-meta"><div class="w44-meta-label">Sitio</div>'
        f'<div class="w44-meta-value">{escape(site_label)}</div></div>'
        f'<div class="w44-meta"><div class="w44-meta-label">Fecha</div>'
        f'<div class="w44-meta-value">{escape(created_label)}</div></div>'
        f'<div class="w44-meta"><div class="w44-meta-label">Incidencia WMS</div>'
        f'<div class="w44-meta-value">{escape(incidence_wms_label)}</div></div>'
        f'</div>'
        f'<div class="w56-context-row">'
        f'<div class="w56-context-icon">?</div>'
        f'<div class="w56-context-text"><b>Estado WMS:</b> refleja la etapa e incidencia informadas por el flujo WMS. '
        f'<b>Diagnóstico actual:</b> se calcula por SKU con su avance reconciliado y el stock operacional disponible en PICK CM, RA CM y CD Lo Boza.</div>'
        f'</div>'
        f'<div class="w44-progress-wrap">'
        f'<div class="w44-progress-line">'
        f'<div class="w44-progress-title">Avance general del pedido</div>'
        f'<div class="w44-progress-numbers"><b>{official_completed}/{official_requested}</b> · {percent}%</div>'
        f'</div>'
        f'<div class="w44-progress-track">'
        f'<div class="w44-progress-fill" style="width:{percent}%"></div>'
        f'</div>'
        f'<div class="w44-progress-foot">'
        f'<span>Procesadas: <b>{official_completed}</b></span>'
        f'<span>Pendientes: <b>{official_pending}</b></span>'
        f'<span>Picking: <b>{escape(wms_pick)}</b></span>'
        f'<span>Packing: <b>{escape(wms_pack)}</b></span>'
        f'<span>Check: <b>{escape(wms_check)}</b></span>'
        f'</div>'
        f'</div>'
        f'</div>'
    )
    st.markdown(progress_html, unsafe_allow_html=True)

    # ------------------------------------------------------------
    # 1) CARGA DETALLE PRODUCTOS
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

    raw = pd.DataFrame(
        {
            "ObOid": col("ObOid", "ob_oid", "obOid").astype(str).str.strip(),
            "ObType": col("ObType", "ob_type", "obType").astype(str).str.strip(),
            "SKU": col("Codigo", "codigo", "SKU", "sku").astype(str).str.strip(),
            "Producto": col("Articulo", "articulo", "Producto", "producto").astype(str).str.strip(),
            "Talla": col("Talla", "talla", "Size", "size").astype(str).str.strip(),
            "Color": col("Color", "color").astype(str).str.strip(),
            "Ubicación": col("Ubicacion", "ubicacion").astype(str).str.strip(),
            "Contenedor": col("Contenedor", "contenedor").astype(str).str.strip(),
            "Línea WMS": col("ObLno", "ob_lno", "Linea", "linea").astype(str).str.strip(),

            # Estado operacional REAL de la línea/producto en WMS.
            # Se aceptan varios nombres porque la respuesta puede variar
            # según el endpoint / versión del WMS.
            "Estado WMS": col(
                "Estado",
                "estado",
                "EstadoProducto",
                "estadoProducto",
                "EstadoLinea",
                "estadoLinea",
                "EstadoProceso",
                "estadoProceso",
                "Status",
                "status",
            ).astype(str).str.strip(),

            "CantidadPedido": pd.to_numeric(
                col("CantidadPedido", "cantidadPedido"), errors="coerce"
            ).fillna(0).astype(int),
            "Cantidad": pd.to_numeric(
                col("Cantidad", "cantidad"), errors="coerce"
            ).fillna(0).astype(int),
        }
    )

    def _norm_order_id(value):
        s = str(value or "").strip()
        digits = re.sub(r"[^0-9]", "", s)
        return digits.lstrip("0") or "0"

    selected_order_id = _norm_order_id(order)
    same_order = raw["ObOid"].map(_norm_order_id) == selected_order_id
    if same_order.any():
        raw = raw.loc[same_order].copy()

    def _norm_type(value):
        return re.sub(r"\s+", " ", str(value or "").strip()).upper()

    selected_type = _norm_type(typ)
    same_type = raw["ObType"].map(_norm_type) == selected_type
    if same_type.any():
        raw = raw.loc[same_type].copy()

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

    product_view = (
        raw.groupby(["SKU", "Producto"], dropna=False)
        .agg(
            Talla=("Talla", join_unique),
            Color=("Color", join_unique),
            Cantidad_NV=("CantidadPedido", "max"),
            Registro_Detalle_WMS=("Cantidad", "sum"),
            Ubicaciones=("Ubicación", join_unique),
            Contenedores=("Contenedor", join_unique),
            Estado_WMS=("Estado WMS", join_unique),
            Registros_WMS=("SKU", "size"),
        )
        .reset_index()
        .rename(
            columns={
                "Cantidad_NV": "Cantidad NV",
                "Registro_Detalle_WMS": "Cantidad detalle WMS",
                "Estado_WMS": "Estado WMS",
                "Registros_WMS": "Registros WMS",
            }
        )
    )

    product_view = product_view[
        (product_view["SKU"].astype(str).str.strip() != "") |
        (product_view["Producto"].astype(str).str.strip() != "")
    ].reset_index(drop=True)

    for c in ("Cantidad NV", "Cantidad detalle WMS"):
        product_view[c] = pd.to_numeric(
            product_view[c], errors="coerce"
        ).fillna(0).astype(int)

    product_view["Talla / Color"] = product_view.apply(
        lambda r: " / ".join(
            x for x in (str(r["Talla"]).strip(), str(r["Color"]).strip())
            if x and x not in {"—", "-", "nan"}
        ) or "—",
        axis=1,
    )

    sku_count = int(product_view["SKU"].replace("", pd.NA).dropna().nunique())
    nv_units = int(product_view["Cantidad NV"].sum())
    raw_count = len(raw)
    # El diagnóstico de stock por SKU exige además que el detalle solicitado
    # reconcilie con ord_qty_total; evita clasificar tipos/órdenes con unidades
    # incompatibles entre cabecera y detalle.
    detail_reconciles = (nv_units == official_requested)

    # ------------------------------------------------------------
    # 2) AVANCE REAL POR SKU · REPORTE COMANDOS PICKING
    # ------------------------------------------------------------
    # Fuente:
    # ReporteComandosShipunit2020.aspx
    #
    # La cantidad del reporte se agrupa por SKU y se usa como avance SOLO
    # cuando la suma total del reporte concilia exactamente con
    # cmp_qty_total del monitor oficial. Si no concilia, no inventamos
    # porcentajes por producto y mostramos "—".
    report_result = _order_product_progress(order)
    report_grouped = report_result.get("grouped") or []

    report_qty_by_sku = {}
    for item in report_grouped:
        sku_key = str(item.get("Producto") or "").strip()
        if not sku_key:
            continue
        try:
            qty_value = int(float(item.get("Cantidad") or 0))
        except Exception:
            qty_value = 0
        report_qty_by_sku[sku_key] = max(0, qty_value)

    try:
        report_total = int(float(report_result.get("total_quantity") or 0))
    except Exception:
        report_total = 0

    report_ok = bool(report_result.get("ok"))
    sku_reconciles = (
        report_ok
        and report_total == official_completed
    )

    product_view["Procesado SKU"] = product_view["SKU"].map(
        lambda sku: report_qty_by_sku.get(str(sku).strip(), 0)
    ).astype(int)

    # Nunca permitir que un valor de reporte supere lo solicitado visualmente.
    product_view["Procesado SKU"] = product_view.apply(
        lambda r: min(
            max(0, int(r["Procesado SKU"])),
            max(0, int(r["Cantidad NV"])),
        ),
        axis=1,
    )

    if sku_reconciles:
        product_view["Faltante oficial"] = (
            product_view["Cantidad NV"] - product_view["Procesado SKU"]
        ).clip(lower=0).astype(int)

        product_view["Avance %"] = product_view.apply(
            lambda r: (
                max(
                    0,
                    min(
                        100,
                        round(
                            (int(r["Procesado SKU"]) / int(r["Cantidad NV"])) * 100
                        ),
                    ),
                )
                if int(r["Cantidad NV"]) > 0
                else 0
            ),
            axis=1,
        ).astype(int)
    else:
        product_view["Faltante oficial"] = pd.NA
        product_view["Avance %"] = pd.NA

    # ------------------------------------------------------------
    # ESTADO OPERACIONAL REAL POR PRODUCTO
    # ------------------------------------------------------------
    def _normalize_product_wms_status(value: str) -> str:
        raw_status = re.sub(r"\s+", " ", str(value or "").strip())

        if not raw_status or raw_status.lower() in {"nan", "none", "—", "-"}:
            return ""

        upper = raw_status.upper()

        if "QUIEBRE" in upper:
            return "Quiebre"
        if "REPOS" in upper:
            return "Reposición"
        if "PACKING" in upper or "PACK" in upper:
            return "Packing"
        if "PICKING" in upper or "PICK" in upper or "RECOG" in upper:
            return "Picking"
        if "FACTUR" in upper:
            return "Facturar"
        if "CHECK" in upper or "CONTROL" in upper:
            return "Check"
        if "PEND" in upper:
            return "Pendiente"
        if "PROCES" in upper or "PROC." in upper or "PROC " in upper:
            return "En proceso"

        return raw_status

    def _normalize_order_stage_for_product(value: str) -> str:
        stage_value = re.sub(r"\s+", " ", str(value or "").strip())
        upper = stage_value.upper()

        if "QUIEBRE" in upper:
            return "Quiebre"
        if "REPOS" in upper:
            return "Reposición"
        if "PACK" in upper:
            return "Packing"
        if "PICK" in upper or "RECOG" in upper:
            return "Picking"
        if "FACTUR" in upper or "LISTO" in upper:
            return "Facturar"
        if "CHECK" in upper or "CONTROL" in upper:
            return "Check"

        return stage_value or "Pendiente"

    fallback_stage = _normalize_order_stage_for_product(stage)

    def _trusted_line_stage(value: str) -> str:
        normalized = _normalize_product_wms_status(value)
        if normalized in {
            "Picking",
            "Packing",
            "Check",
            "Facturar",
            "Quiebre",
            "Reposición",
        }:
            return normalized
        return ""

    def _sku_status(r: pd.Series) -> str:
        """
        Determina el proceso visible por SKU sin propagar un Quiebre/Reposición
        global a productos que ya están completamente procesados.

        Reglas:
        1. Si existe un estado operacional confiable a nivel línea, se respeta.
        2. Si el avance por SKU está conciliado:
           - SKU incompleto: conserva Quiebre/Reposición cuando corresponda.
           - SKU completo y el pedido completo (0 pendientes): Facturar.
           - SKU completo con pedido aún parcial: conserva la etapa general,
             salvo Quiebre/Reposición, que no se hereda al SKU completo.
        3. Si no existe conciliación por SKU, se mantiene la etapa general.
        """
        line_stage = _trusted_line_stage(r.get("Estado WMS", ""))
        if line_stage:
            return line_stage

        if not sku_reconciles:
            return fallback_stage

        requested_sku = max(0, int(r.get("Cantidad NV", 0) or 0))
        processed_sku = max(0, int(r.get("Procesado SKU", 0) or 0))

        sku_complete = (
            requested_sku > 0
            and processed_sku >= requested_sku
        )

        order_complete = (
            official_requested > 0
            and official_completed >= official_requested
            and official_pending == 0
        )

        # Un producto ya completo no debe verse como "Quiebre" solo porque
        # el pedido arrastre una bandera general de revisión.
        if sku_complete:
            if order_complete:
                return "Facturar"

            if fallback_stage in {"Quiebre", "Reposición"}:
                return "Picking"

            return fallback_stage

        # Solo los SKU realmente incompletos heredan Quiebre/Reposición.
        if fallback_stage in {"Quiebre", "Reposición"}:
            return fallback_stage

        return fallback_stage

    product_view["Estado"] = product_view.apply(_sku_status, axis=1)
    product_view["Estado fuente"] = product_view["Estado WMS"].apply(
        lambda x: "WMS línea" if _trusted_line_stage(x) else "Etapa pedido"
    )

    # Ya no intentamos reconciliar el faltante global asignándolo artificialmente
    # a SKU individuales. Cada línea se calcula solamente con sus propias cantidades.
    detail_mode = "reporte_comandos" if sku_reconciles else "estado_operacional"
    calculated_pending = int(official_pending)

    # V53 · resumen por SKU calculado directamente desde las cantidades.
    if sku_reconciles:
        missing_sku_count = int(
            (pd.to_numeric(product_view["Faltante oficial"], errors="coerce").fillna(0) > 0).sum()
        )
        missing_units = int(
            pd.to_numeric(product_view["Faltante oficial"], errors="coerce").fillna(0).sum()
        )
    else:
        missing_sku_count = 0
        missing_units = int(official_pending)

    # Paginación propia del detalle.
    detail_page_key = f"w42_product_page_{order}"
    if detail_page_key not in st.session_state:
        st.session_state[detail_page_key] = 0

    detail_page_size = 10

    detail_pages = max(1, math.ceil(len(product_view) / detail_page_size))
    st.session_state[detail_page_key] = min(
        max(int(st.session_state[detail_page_key]), 0),
        detail_pages - 1,
    )

    detail_start = st.session_state[detail_page_key] * detail_page_size
    detail_end = min(detail_start + detail_page_size, len(product_view))
    detail_page_df = product_view.iloc[detail_start:detail_end].copy()

    widths = [0.9, 3.0, 1.2, .9, 1.35, 1.55, .45]

    head_wrap = st.container(key=f"w35_products_header_{order}")
    with head_wrap:
        hcols = st.columns(widths, gap="small")
        headers = [
            "SKU","Producto","Talla / Color","Cantidad","Proceso","Avance","Acc."
        ]
        for c, label in zip(hcols, headers):
            with c:
                st.markdown(
                    f'<div class="w35-head-cell">{escape(label)}</div>',
                    unsafe_allow_html=True,
                )

    selected_sku_key = f"w35_selected_sku_{order}"
    if selected_sku_key not in st.session_state:
        st.session_state[selected_sku_key] = ""

    # V54 · diagnóstico de stock actual solo para los SKU visibles.
    # Esto evita consultar decenas de SKU innecesariamente al abrir el pedido.
    stock_diagnostics = {}
    stock_diagnosis_valid = sku_reconciles and detail_reconciles

    for _, visible_row in detail_page_df.iterrows():
        sku_visible = str(visible_row.get("SKU", "")).strip()
        if not sku_visible:
            continue
        missing_visible_raw = visible_row.get("Faltante oficial")
        if stock_diagnosis_valid and not pd.isna(missing_visible_raw):
            stock_diagnostics[sku_visible] = _sku_operational_stock(
                sku_visible, int(missing_visible_raw)
            )

    for ridx, p in detail_page_df.reset_index(drop=True).iterrows():
        absolute_idx = detail_start + ridx
        missing_raw = p["Faltante oficial"]
        missing = None if pd.isna(missing_raw) else int(missing_raw)
        progress_raw = p["Avance %"]
        progress = None if pd.isna(progress_raw) else int(progress_raw)
        sku_diag = stock_diagnostics.get(str(p["SKU"]).strip())
        if sku_diag and sku_diag.get("ok"):
            state_text = str(sku_diag.get("estado") or p["Estado"])
        else:
            state_text = str(p["Estado"])
        is_pending = missing is not None and missing > 0
        is_progress = state_text == "En proceso"

        row_key = (
            f"w35_product_pending_{absolute_idx}_{p['SKU']}"
            if is_pending else
            f"w35_product_row_{absolute_idx}_{p['SKU']}"
        )

        wrap = st.container(key=row_key)
        with wrap:
            cols = st.columns(widths, gap="small", vertical_alignment="center")

            cells = [
                ("sku", str(p["SKU"])),
                ("product", str(p["Producto"])),
                ("", str(p["Talla / Color"])),
                ("num", str(int(p["Cantidad NV"]))),
            ]

            for ci, (klass, cell_text) in enumerate(cells):
                with cols[ci]:
                    st.markdown(
                        f'<div class="w35-cell {klass}" title="{escape(cell_text)}">{escape(cell_text)}</div>',
                        unsafe_allow_html=True,
                    )

            # Proceso operacional.
            with cols[4]:
                normalized_state = str(state_text or "").strip()
                state_lower = normalized_state.lower()

                if "quiebre" in state_lower:
                    label, state_class = "Quiebre", "warn"
                elif "abaste" in state_lower or "traslado" in state_lower:
                    label, state_class = "Abastecimiento CD", "picking"
                elif "procesado" in state_lower or "completo" in state_lower:
                    label, state_class = "Procesado", "invoice"
                elif "repos" in state_lower:
                    label, state_class = "Reposición", "repo"
                elif "packing" in state_lower:
                    label, state_class = "Packing", "packing"
                elif "picking" in state_lower:
                    label, state_class = "Picking", "picking"
                elif "factur" in state_lower:
                    label, state_class = "Facturar", "invoice"
                elif "check" in state_lower or "control" in state_lower:
                    label, state_class = "Check", "check"
                elif normalized_state:
                    label, state_class = normalized_state, "progress"
                else:
                    label, state_class = "Pendiente", "progress"

                st.markdown(
                    f'<span class="w35-state {state_class}"><i></i>{escape(label)}</span>',
                    unsafe_allow_html=True,
                )

            # Avance por SKU validado contra el total oficial del pedido.
            with cols[5]:
                if sku_reconciles and progress is not None:
                    processed_sku = int(p["Procesado SKU"])
                    requested_sku = int(p["Cantidad NV"])
                    st.markdown(
                        f"""
<div class="w35-prog">
    <div class="w35-track">
        <div class="w35-fill progress" style="width:{int(progress)}%"></div>
    </div>
    <b>{processed_sku}/{requested_sku} · {int(progress)}%</b>
</div>
""",
                        unsafe_allow_html=True,
                    )
                else:
                    st.markdown(
                        '<div class="w35-prog"><div class="w35-track"></div><b>—</b></div>',
                        unsafe_allow_html=True,
                    )

            with cols[6]:
                if st.button(
                    "⋮",
                    key=f"w35_sku_action_{order}_{absolute_idx}_{p['SKU']}",
                    help="Ver detalle de este SKU",
                ):
                    st.session_state[selected_sku_key] = str(p["SKU"])
                    st.rerun()

    # Navegación del listado del pedido.
    nav1, nav2, nav3, nav4 = st.columns([1.3, 3.2, .8, .8], vertical_alignment="center")

    with nav1:
        st.caption(
            f"Mostrando {detail_start + 1 if len(product_view) else 0}–{detail_end} "
            f"de {len(product_view)} productos"
        )

    with nav2:
        if sku_reconciles:
            if missing_sku_count:
                st.caption(
                    f"Avance por SKU validado · {missing_sku_count} producto(s) pendientes · "
                    f"{missing_units} unidad(es)"
                )
            else:
                st.caption(
                    f"Avance por SKU validado con Reporte Comandos Picking · "
                    f"{report_total}/{official_requested}"
                )
        else:
            report_note = (
                f"reporte {report_total} vs. monitor {official_completed}"
                if report_ok else
                "reporte no disponible"
            )
            st.caption(
                f"Avance por SKU no mostrado: {report_note}. "
                f"Se mantiene el avance oficial {official_completed}/{official_requested}."
            )

    with nav3:
        if st.button(
            "‹",
            key=f"w37_prev_products_{order}",
            disabled=st.session_state[detail_page_key] <= 0,
            use_container_width=True,
        ):
            st.session_state[detail_page_key] -= 1
            st.rerun()

    with nav4:
        if st.button(
            "›",
            key=f"w37_next_products_{order}",
            disabled=st.session_state[detail_page_key] >= detail_pages - 1,
            use_container_width=True,
        ):
            st.session_state[detail_page_key] += 1
            st.rerun()

    selected_sku = st.session_state.get(selected_sku_key, "")
    if selected_sku:
        selected_product_rows = product_view[
            product_view["SKU"].astype(str) == str(selected_sku)
        ]
        if not selected_product_rows.empty:
            sp = selected_product_rows.iloc[0]
            render_html(
                f"""
<div class="w35-sku-detail">
    <strong>{escape(str(sp["SKU"]))} · {escape(str(sp["Producto"]))}</strong>
    <span>
        Cantidad NV: {int(sp["Cantidad NV"])} ·
        Procesadas SKU: {int(sp["Procesado SKU"]) if sku_reconciles else "—"} ·
        Faltante oficial: {("—" if pd.isna(sp["Faltante oficial"]) else str(int(sp["Faltante oficial"])))} ·
        Avance SKU: {("—" if pd.isna(sp["Avance %"]) else str(int(sp["Avance %"])) + "%")}
    </span>
</div>
"""
            )

            selected_diag = stock_diagnostics.get(str(sp["SKU"]).strip())
            if selected_diag and selected_diag.get("ok"):
                estado_diag = str(selected_diag.get("estado") or "—")
                accion = int(selected_diag.get("accion_qty") or 0)
                deficit = int(selected_diag.get("deficit") or 0)
                extra = ""
                if estado_diag == "Reposición":
                    extra = f" · Reponer: <b>{accion}</b> UN"
                elif estado_diag == "Abastecimiento CD":
                    extra = f" · Trasladar desde CD: <b>{accion}</b> UN"
                elif estado_diag == "Quiebre":
                    extra = f" · Déficit: <b>{deficit}</b> UN"

                pick_diag = int(selected_diag.get("pick") or 0)
                ra_diag = int(selected_diag.get("ra") or 0)
                cd_diag = int(selected_diag.get("cd") or 0)

                render_html(
                    f"""
<div class="w55-stock-grid">
    <div class="w55-stock-card diag">
        <div class="w55-stock-icon">✓</div>
        <div class="w55-stock-body">
            <div class="w55-stock-label">Diagnóstico de stock actual</div>
            <div class="w55-stock-value">{escape(estado_diag)}</div>
        </div>
    </div>

    <div class="w55-stock-card pick">
        <div class="w55-stock-icon">▣</div>
        <div class="w55-stock-body">
            <div class="w55-stock-label">
                PICK CM
                <span class="w55-help" title="Stock disponible directamente en las ubicaciones de Picking de CASA MATRIZ. Si alcanza para cubrir el faltante del SKU, el producto puede continuar directamente a Picking.">?</span>
            </div>
            <div class="w55-stock-value">{pick_diag} unidades</div>
        </div>
    </div>

    <div class="w55-stock-card ra">
        <div class="w55-stock-icon">▤</div>
        <div class="w55-stock-body">
            <div class="w55-stock-label">
                RA CM
                <span class="w55-help" title="Stock de reserva disponible en CASA MATRIZ. Se usa para Reposición cuando PICK CM no alcanza; las unidades necesarias se trasladan desde reserva hacia Picking.">?</span>
            </div>
            <div class="w55-stock-value">{ra_diag} unidades</div>
        </div>
    </div>

    <div class="w55-stock-card cd">
        <div class="w55-stock-icon">▦</div>
        <div class="w55-stock-body">
            <div class="w55-stock-label">
                CD Lo Boza
                <span class="w55-help" title="Stock operacional disponible en CD LO BOZA. Se usa como alternativa de abastecimiento cuando PICK CM y RA CM no alcanzan para completar el faltante del SKU.">?</span>
            </div>
            <div class="w55-stock-value">{cd_diag} unidades</div>
        </div>
    </div>
</div>
"""
                )

                if extra:
                    render_html(
                        f'<div class="w55-stock-action">Acción sugerida:{extra}</div>'
                    )

    # ------------------------------------------------------------
    # 7) STOCK ALTERNATIVO · BLOQUE ÚNICO
    # ------------------------------------------------------------
    _missing_num = pd.to_numeric(product_view["Faltante oficial"], errors="coerce").fillna(0)
    missing_products = product_view[_missing_num > 0].copy()

    render_html(
        f"""
<div class="w38-stock">
    <div class="w38-stock-head">
        <strong>Stock alternativo</strong>
        <span>Consulta directa al WMS</span>
    </div>
    <div class="w38-stock-body">
        <div class="w38-stock-summary">
            <span class="w38-chip">Avance global {official_completed}/{official_requested}</span>
            <span class="w38-chip warn">{official_pending} unidad(es) pendientes</span>
            <span class="w38-chip">{missing_sku_count} SKU con faltante identificado</span>
        </div>
    </div>
</div>
"""
    )

    stock_candidates = product_view[
        ["SKU", "Producto", "Cantidad NV", "Cantidad detalle WMS", "Faltante oficial"]
    ].copy()

    # No atribuimos el faltante global a un SKU específico si WMS no lo informa.
    # El stock alternativo por SKU solo debe activarse cuando exista un faltante
    # explícito de línea.

    # Si el detalle concilia, consultamos primero solo SKU con faltante.
    if sku_reconciles and missing_sku_count > 0:
        selectable = stock_candidates[
            stock_candidates["Faltante oficial"].fillna(0) > 0
        ].copy()
    else:
        selectable = stock_candidates.copy()

    selectable = selectable[
        selectable["SKU"].astype(str).str.strip() != ""
    ].drop_duplicates(subset=["SKU"]).reset_index(drop=True)

    selected_sku = ""
    if not selectable.empty:
        option_map = {}
        options = []

        for _, r in selectable.iterrows():
            sku_val = str(r["SKU"]).strip()
            prod_val = str(r["Producto"]).strip()
            falt_raw = r["Faltante oficial"]
            falt = None if pd.isna(falt_raw) else int(falt_raw)
            label = f"{sku_val} · {prod_val}"
            if falt is not None and falt > 0:
                label += f" · faltan {falt}"
            option_map[label] = r.to_dict()
            options.append(label)

        chosen = st.selectbox(
            "SKU a consultar",
            options,
            key=f"w38_stock_select_{order}",
        )
        selected = option_map[chosen]
        selected_sku = str(selected["SKU"]).strip()
        selected_missing_raw = selected["Faltante oficial"]
        selected_missing = (
            int(selected_missing_raw)
            if not pd.isna(selected_missing_raw)
            else int(official_pending)
        )

        stock_btn_wrap = st.container(key=f"w38_stock_button_{order}_{selected_sku}")
        with stock_btn_wrap:
            consult = st.button(
                "Buscar stock WMS",
                use_container_width=True,
                key=f"w38_stock_query_{order}_{selected_sku}",
            )

        state_key = f"w38_stock_result_{order}"

        if consult:
            with st.spinner(f"Consultando stock alternativo WMS de {selected_sku}..."):
                result_stock = _alternative_stock(
                    selected_sku,
                    selected_missing,
                )

            st.session_state[state_key] = {
                "sku": selected_sku,
                "required": selected_missing,
                "result": result_stock,
            }

        stock_state = st.session_state.get(state_key)

        if stock_state and stock_state.get("sku") == selected_sku:
            result_stock = stock_state.get("result") or {}
            required_qty = max(0, int(stock_state.get("required") or 0))

            if result_stock.get("ok"):
                wh_rows = []
                for item in result_stock.get("bodegas") or []:
                    stock_value = item.get("stock_disponible")
                    available = (
                        int(float(stock_value))
                        if stock_value is not None else None
                    )

                    state = str(item.get("estado") or "")
                    if state == "cubre_completo":
                        result_label = "✅ Cubre completo"
                    elif state == "cubre_parcial":
                        result_label = "🟡 Cubre parcial"
                    elif state == "sin_stock":
                        result_label = "🔴 Sin stock"
                    elif state == "con_stock":
                        result_label = "Stock disponible"
                    else:
                        result_label = "⚠️ Error"

                    wh_rows.append(
                        {
                            "Bodega alternativa": item.get("bodega") or item.get("site") or "—",
                            "Stock disponible": available if available is not None else "—",
                            "Faltan CM": required_qty,
                            "Resultado": result_label,
                        }
                    )

                if wh_rows:
                    st.dataframe(
                        pd.DataFrame(wh_rows),
                        hide_index=True,
                        use_container_width=True,
                        height=min(250, 42 + len(wh_rows) * 38),
                    )

                recommendation = result_stock.get("recomendacion")
                if recommendation:
                    message = str(recommendation.get("mensaje") or "").strip()
                    if message:
                        if recommendation.get("tipo") in {"completo", "combinado"}:
                            st.success(message)
                        else:
                            st.warning(message)
                elif wh_rows:
                    total_alt = sum(
                        int(float(x.get("stock_disponible") or 0))
                        for x in (result_stock.get("bodegas") or [])
                        if x.get("stock_disponible") is not None
                    )
                    if required_qty > 0 and total_alt <= 0:
                        st.warning(
                            f"No se encontró stock alternativo para cubrir "
                            f"{required_qty} unidad(es) del SKU {selected_sku}."
                        )

                # Solo mostramos errores técnicos si alguna bodega falló.
                technical_errors = [
                    f"{x.get('bodega') or x.get('site')}: {x.get('error')}"
                    for x in (result_stock.get("bodegas") or [])
                    if x.get("estado") == "error" and x.get("error")
                ]
                if technical_errors:
                    with st.expander("Diagnóstico técnico WMS", expanded=False):
                        for err in technical_errors:
                            st.write(f"• {err}")

            else:
                # Mensaje de operación limpio; el detalle técnico queda colapsado.
                st.error("No fue posible consultar stock alternativo WMS.")
                tech_error = str(result_stock.get("error") or "").strip()
                if tech_error:
                    with st.expander("Diagnóstico técnico WMS", expanded=False):
                        st.write(tech_error)

    else:
        st.info("No hay SKU disponibles para consultar.")

    # ------------------------------------------------------------
    # 8) ACCIONES DEL PEDIDO
    # ------------------------------------------------------------
    render_html('<div class="w38-actions">')

    export_view = product_view[
        ["SKU", "Producto", "Talla / Color", "Cantidad NV",
         "Cantidad detalle WMS", "Faltante oficial", "Avance %", "Estado"]
    ].copy()

    csv = export_view.to_csv(index=False).encode("utf-8-sig")

    b1, b2, b3 = st.columns([1, 1, 1.2])

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

    render_html("</div>")

    # ------------------------------------------------------------
    # 9) INFORMACIÓN TÉCNICA WMS · ÚNICO ACORDEÓN
    # ------------------------------------------------------------
    with st.expander("Información técnica WMS", expanded=False):
        render_html(
            f"""
<div class="w33-tech-row">
    <div><span>Pick</span><strong>{escape(wms_pick)}</strong></div>
    <div><span>Pack</span><strong>{escape(wms_pack)}</strong></div>
    <div><span>Check</span><strong>{escape(wms_check)}</strong></div>
    <div><span>P/B C.</span><strong>{escape(wms_pb)}</strong></div>
    <div><span>Estado</span><strong>{escape(status)}</strong></div>
    <div><span>Tiempo</span><strong>{escape(wms_time)}</strong></div>
</div>
"""
        )

        st.caption(
            "El avance general del pedido se obtiene exclusivamente desde cmp_qty_total / ord_qty_total. "
            "El detalle por SKU se usa solo como apoyo operativo y se concilia contra el total global."
        )

        technical_view = raw[
            ["ObOid", "ObType", "SKU", "Producto", "Talla", "Color",
             "Ubicación", "Contenedor", "Línea WMS", "Estado WMS", "CantidadPedido", "Cantidad"]
        ].copy()

        st.dataframe(
            technical_view,
            hide_index=True,
            use_container_width=True,
            height=min(360, 42 + len(technical_view) * 35),
        )

        st.write(
            {
                "pedido": order,
                "avance_oficial": f"{official_completed}/{official_requested}",
                "faltante_oficial": official_pending,
                "detalle_sku_concilia": sku_reconciles,
                "interpretacion_registro_detalle": detail_mode,
                "faltante_calculado_desde_detalle": calculated_pending,
                "detalle_concilia_con_global": sku_reconciles,
                "sku_unicos": sku_count,
                "registros_operativos": raw_count,
            }
        )

    render_html(
        f"""
<div class="w38-note">
    <b>Importante:</b> el faltante oficial del pedido es {official_pending} unidad(es),
    calculado desde el avance global WMS {official_completed}/{official_requested}.
</div>
"""
    )

# ============================================================
# RENDER
# ============================================================


# ============================================================
# REDISEÑO FINAL · MONITOR PEDIDOS MARITEX
# ============================================================

def _apply_redesign_overrides() -> None:
    st.markdown(
        """
<style>
:root{
    --mx-bg:#09131b;
    --mx-bg2:#0b1620;
    --mx-panel:#0f1a23;
    --mx-panel2:#13212c;
    --mx-line:#28404f;
    --mx-line2:#314b5c;
    --mx-text:#f6f8fa;
    --mx-muted:#8da2b0;
    --mx-yellow:#ffd000;
    --mx-green:#24d88a;
    --mx-red:#ef4452;
    --mx-blue:#159fe8;
    --mx-purple:#8a4fff;
    --mx-soft:#d7e2ea;
}

/* APP */
[data-testid="stAppViewContainer"],
[data-testid="stAppViewContainer"]>.main,
.main{
    background:
        radial-gradient(circle at 90% 0%,rgba(23,78,108,.16),transparent 28%),
        linear-gradient(180deg,#0a141c 0%,#081119 100%) !important;
    color:var(--mx-text) !important;
}
[data-testid="stHeader"]{
    background:#081119 !important;
    border-bottom:1px solid #203441 !important;
}
.block-container{
    max-width:1720px !important;
    padding:1.15rem 1.6rem 2.2rem !important;
}

/* HEADER */
.w9-title,.v32-title,.w33-title,.w34-title,.w35-title{
    color:#fff !important;
    font-size:34px !important;
    font-weight:900 !important;
    letter-spacing:-.6px !important;
}
.w9-sub,.v32-sub,.w33-sub,.w34-sub,.w35-sub{
    color:#9db0bd !important;
}
.w9-source,.v32-source{
    background:#071018 !important;
    border:1px solid #274151 !important;
    border-radius:12px !important;
    color:#7f95a4 !important;
}

/* KPI */
.w9-kpis{
    grid-template-columns:repeat(6,minmax(0,1fr)) !important;
    gap:16px !important;
    margin:18px 0 20px !important;
}
.w9-kpi{
    min-height:116px !important;
    padding:18px 20px !important;
    border:1px solid #29404f !important;
    border-radius:14px !important;
    background:linear-gradient(145deg,#101c26,#0b151d) !important;
    box-shadow:0 8px 24px rgba(0,0,0,.18) !important;
}
.w9-kpi:after{display:none !important;}
.w9-kpi .kpi-top{
    align-items:center !important;
    gap:14px !important;
}
.w9-kpi .kpi-icon{
    display:flex !important;
    width:42px !important;
    height:42px !important;
    flex:0 0 42px !important;
    border-radius:12px !important;
    background:#162633 !important;
    border:1px solid #2c4657 !important;
    color:#dce7ed !important;
}
.w9-kpi.yellow .kpi-icon{background:#3a3100 !important;color:#ffd000 !important;border-color:#6a5900 !important;}
.w9-kpi.blue .kpi-icon{background:#103553 !important;color:#3fb3ff !important;border-color:#1d577c !important;}
.w9-kpi.green .kpi-icon{background:#103b28 !important;color:#42e497 !important;border-color:#1c6844 !important;}
.w9-kpi.red .kpi-icon{background:#411a20 !important;color:#ff7280 !important;border-color:#6d2e37 !important;}
.w9-kpi .kpi-number{
    color:#fff !important;
    font-size:31px !important;
    font-weight:900 !important;
}
.w9-kpi .kpi-label{
    color:#eef4f7 !important;
    font-size:12px !important;
    font-weight:850 !important;
}
.w9-kpi .kpi-label:before{display:none !important;}
.w9-kpi small{
    display:block !important;
    color:#708795 !important;
    font-size:8.5px !important;
}
.v32-bars{
    display:flex !important;
}
.v32-bars i{
    background:#263c4b !important;
}
.w9-kpi.yellow .v32-bars i:last-child{background:#ffd000 !important;}
.w9-kpi.blue .v32-bars i:last-child{background:#159fe8 !important;}
.w9-kpi.green .v32-bars i:last-child{background:#24d88a !important;}
.w9-kpi.red .v32-bars i:last-child{background:#ef4452 !important;}

/* ALERT */
.w17-bottom-alerts,
.w19-break-panel{
    background:#181217 !important;
    border-color:#76313a !important;
}
.w19-break-summary,
.w17-incident b{
    color:#ff6a76 !important;
}

/* FILTER AREA */
[data-testid="stTextInput"] label,
[data-testid="stSelectbox"] label{
    color:#dfe8ed !important;
    font-size:12px !important;
    font-weight:850 !important;
}
[data-testid="stTextInput"] input,
div[data-baseweb="select"]>div{
    min-height:50px !important;
    background:#101b24 !important;
    border:1px solid #2b4556 !important;
    border-radius:10px !important;
    color:#fff !important;
}
[data-testid="stTextInput"] input::placeholder{
    color:#78909f !important;
}

/* FILTER CHIPS */
div[role="radiogroup"] label{
    background:#0e1821 !important;
    border:1px solid #2d4656 !important;
    border-radius:10px !important;
    padding:9px 14px !important;
}
div[role="radiogroup"] label:has(input:checked){
    background:#ffd000 !important;
    border-color:#ffd000 !important;
    box-shadow:0 0 0 1px rgba(255,208,0,.15),0 8px 20px rgba(255,208,0,.10) !important;
}
div[role="radiogroup"] label:has(input:checked) p{
    color:#111 !important;
}
div[role="radiogroup"] p{
    color:#f0f4f6 !important;
    font-size:10px !important;
    font-weight:850 !important;
}

/* TABLE HEADER */
div[class*="st-key-w18_table_header"],
div[data-testid="stHorizontalBlock"]:has(.w17-col-head){
    background:#12212c !important;
    border:1px solid #294351 !important;
    border-radius:12px 12px 0 0 !important;
    padding:4px 12px !important;
}
.w17-col-head{
    color:#dce7ed !important;
    font-size:9px !important;
    font-weight:900 !important;
}

/* TABLE ROWS */
div[class*="st-key-w18_row_"]{
    background:#0e1820 !important;
    border-left:1px solid #243b49 !important;
    border-right:1px solid #243b49 !important;
    border-bottom:1px solid #223642 !important;
    padding:0 12px !important;
}
div[class*="st-key-w18_row_"]:hover{
    background:#13222d !important;
}
div[class*="st-key-w18_row_"] [data-testid="stHorizontalBlock"]{
    min-height:58px !important;
}
.w17-cell{
    color:#eef3f6 !important;
    font-size:11px !important;
}
.w17-order{
    color:#fff !important;
    font-size:11px !important;
    font-weight:900 !important;
}
.w17-progress b{
    color:#e9f0f4 !important;
}
.w17-track{
    background:#c9d7e0 !important;
    height:8px !important;
}
.w17-fill{
    background:#ffd000 !important;
}

/* STATUS PILLS */
.w9-pill{
    padding:7px 12px !important;
    font-size:9px !important;
    font-weight:900 !important;
    color:#fff !important;
    border-radius:9px !important;
}
.w9-pill.yellow{background:#ffd000 !important;border-color:#ffd000 !important;color:#111 !important;}
.w9-pill.blue{background:#189cea !important;border-color:#189cea !important;}
.w9-pill.green{background:#17a863 !important;border-color:#17a863 !important;}
.w9-pill.red{background:#ef4452 !important;border-color:#ef4452 !important;}
.w9-pill.gray{background:#223746 !important;border-color:#355064 !important;}
.w9-pill.purple{background:#8748ee !important;border-color:#8748ee !important;}

/* DETAIL BUTTONS */
div[class*="st-key-w18_row_"] .stButton>button{
    background:#0d1820 !important;
    border:1px solid #3a5a6e !important;
    color:#fff !important;
    border-radius:10px !important;
    min-height:42px !important;
    height:42px !important;
}
div[class*="st-key-w18_row_"] .stButton>button:hover{
    background:#ffd000 !important;
    border-color:#ffd000 !important;
    color:#111 !important;
}

/* DETAIL SHELL - DARK */
.w24-shell,.w22-detail-shell,.w9-detail{
    background:#0b151d !important;
    border:1px solid #29404f !important;
    border-radius:14px !important;
    box-shadow:none !important;
}
.w24-head,.w22-titlebar,.w17-detail-titlebar{
    background:#0b151d !important;
    border-bottom:1px solid #243947 !important;
    padding:18px 20px 14px !important;
}
.w24-order,.w22-order,.w17-detail-title{
    color:#fff !important;
    font-size:26px !important;
    font-weight:900 !important;
}
.w24-client,.w22-client,.w17-client{
    color:#9dafba !important;
}
.w24-summary-card,.w22-main-card,.w17-summary-card{
    background:#101d26 !important;
    border:1px solid #29404f !important;
    border-radius:10px !important;
}
.w24-summary-card span,.w22-main-card span,.w17-summary-card span{
    color:#7991a0 !important;
}
.w24-summary-card strong,.w22-main-card strong,.w17-summary-card strong{
    color:#fff !important;
}
.w24-summary-card.danger,.w22-main-card.danger,.w17-summary-card.alert{
    background:#2b1419 !important;
    border-color:#74303a !important;
}
.w24-summary-card.danger strong,.w22-main-card.danger strong,.w17-summary-card.alert strong{
    color:#ff7581 !important;
}

/* FLOW */
.w24-flow-wrap,.w24-wms-block,.w22-flow,.w22-wms-grid,.w9-flow{
    background:#0c171f !important;
    border-color:#29404f !important;
}
.w24-flow-title,.w24-block-head strong,.w22-section-title strong,.w9-product-head strong{
    color:#fff !important;
}
.w24-step,.w22-step,.w9-step{
    background:#101b24 !important;
}
.w24-step b,.w22-step b,.w9-step b{
    color:#eef4f7 !important;
}
.w24-step span,.w22-step span,.w9-step span{
    color:#748a98 !important;
}
.w24-step.current,.w22-step.current,.w9-step.current{
    background:#302800 !important;
    border-color:#8d7300 !important;
}
.w24-step.done,.w22-step.done,.w9-step.done{
    background:#0e3a28 !important;
}

/* PRODUCT TABLE */
[data-testid="stDataFrame"]{
    background:#0d171f !important;
    border:1px solid #29404f !important;
    border-radius:10px !important;
}

/* GENERIC BUTTONS */
.main .stButton>button,
.main .stDownloadButton>button,
.main a[data-testid="stLinkButton"]{
    background:#0d1820 !important;
    color:#fff !important;
    border:1px solid #345064 !important;
    border-radius:10px !important;
}
.main .stButton>button[kind="primary"]{
    background:#ffd000 !important;
    border-color:#ffd000 !important;
    color:#111 !important;
}

/* RESPONSIVE */
@media(max-width:1200px){
    .w9-kpis{grid-template-columns:repeat(3,minmax(0,1fr)) !important;}
}
@media(max-width:760px){
    .w9-kpis{grid-template-columns:repeat(2,minmax(0,1fr)) !important;}
}
</style>
        """,
        unsafe_allow_html=True,
    )


@st.cache_data(ttl=45, show_spinner=False)
def _wms_web_order_cached(order_id: str) -> dict:
    if search_order is None:
        return {}
    try:
        result = search_order(str(order_id), debug=False)
        return result or {}
    except Exception:
        return {}


@st.fragment(run_every="30s")
def render(ctx: dict | None = None) -> None:
    _apply_styles()
    _apply_redesign_overrides()

    page_header(
        title="MONITOR DE PEDIDOS WMS",
        subtitle=(
            "Seguimiento operativo en línea de pedidos "
            "comerciales y eCommerce."
        ),
        status="WMS Online",
    )

    refresh_col, source_col = st.columns([1.25, 6.75], vertical_alignment="center")
    with refresh_col:
        refresh_box = st.container(key="v32_refresh")
        with refresh_box:
            if st.button("Actualizar", icon=":material/refresh:", use_container_width=True):
                _load_live.clear()
                _order_lines.clear()
                _order_product_progress.clear()
                _sku_operational_stock.clear()
                _order_real_break_status.clear()
                _alternative_stock.clear()
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

    if not df.empty:
        # V58 · La señal [Q] del WMS es antecedente; el filtro/contador de
        # quiebre se basa en stock real reconciliado por SKU.
        with st.spinner("Validando quiebres reales contra stock operacional..."):
            df = _attach_real_breaks(df)

    if df.empty:
        st.warning("El WMS respondió, pero no entregó pedidos.")
        return

    with source_col:
        render_html(
            f"""
<div class="v32-source">
    Fuente: <b>{escape(str(result.get("source") or "ScoresHub"))}</b>
    · última actualización {datetime.now().strftime("%d-%m-%Y %H:%M:%S")}
    · autoactualización cada 30 s
</div>
"""
        )

    _render_kpis(df)

    # --------------------------------------------------------
    # FILTROS
    # --------------------------------------------------------
    render_html('<div class="v32-filters-title">Buscar y filtrar pedidos</div>')
    f1, f2, f3, f4, f5 = st.columns([2.25,1,1,1,1.2], gap="small")

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
            "Quiebre real",
            ["Todos", "Con quiebre real", "Sin quiebre real"],
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
            f"Quiebre real ({breaks})",
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

    if incidence == "Con quiebre real":
        filtered = filtered[filtered["_quiebre"]]
    elif incidence == "Sin quiebre real":
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
    elif segment.startswith("Quiebre real"):
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

