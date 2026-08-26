
import pandas as pd
import streamlit as st
import altair as alt

from analytics.sales_metrics import calculate_commercial_totals, filter_sales
from ui.components import render_html
from utils.dates import available_months, month_bounds, month_label_es
from utils.numbers import format_clp


def render(ctx):
    df=ctx.get("sales_df")

    render_html("""
    <div class="exec-v60-head">
      <div>
        <div class="exec-v60-eyebrow">MARITEX ADMIN / RESUMEN</div>
        <div class="exec-v60-title">Resumen Ejecutivo</div>
        <div class="exec-v60-subtitle">Performance comercial, cumplimiento de meta y proyección de cierre.</div>
      </div>
      <div class="exec-v60-rule">Selecciona análisis con IVA o sin IVA</div>
    </div>
    """)

    if df is None or df.empty:
        st.info("Carga ERP Ventas desde Plantillas.")
        return

    base=df[df["Grupo comercial"].isin(["Factura","Boleta","Nota de crédito"])].copy()
    months=available_months(base,"Fecha_dt")
    labels=[month_label_es(m) for m in months]
    mm=dict(zip(labels,months))

    sellers=sorted(base["Vendedor"].fillna("Sin vendedor").astype(str).str.strip().unique().tolist())
    whs=sorted(base["Bodega"].fillna("Sin bodega").astype(str).str.strip().unique().tolist()) if "Bodega" in base.columns else []
    types=sorted(base["TipoDocto"].dropna().astype(str).unique().tolist())

    st.markdown("##### Filtros de performance")
    a,b,c,d,e=st.columns([1.05,1.1,.9,1.05,1.05],gap="small")
    with a:
        lab=st.selectbox("Mes",labels,index=0,key="exec_month_v617")
        month=mm[lab]
        mstart,mend=month_bounds(month)
        mr=base[(base["Fecha_dt"].dt.date>=mstart)&(base["Fecha_dt"].dt.date<=mend)]
        realmax=mr["Fecha_dt"].max().date() if not mr.empty else mstart
        dend=min(mend,realmax)
        days=st.date_input("Días",value=(mstart,dend),min_value=mstart,max_value=mend,key=f"exec_days_v617_{month}")
    with b:
        fs=st.multiselect("Vendedor",sellers,placeholder="Todos los vendedores",key="exec_seller_v617")
    with c:
        fw=st.multiselect("Bodega",whs,placeholder="Todas",key="exec_wh_v617")
    with d:
        ft=st.multiselect("Tipo de documento",types,placeholder="Facturas + Boletas + NC",key="exec_type_v617")
    with e:
        base_mode=st.selectbox("Base de análisis",["Venta final con IVA","Venta final sin IVA"],key="exec_base_v617")

    g1,g2=st.columns(2)
    with g1:
        goal=st.number_input("Meta de venta",min_value=0,value=100_000_000,step=100_000,key="exec_goal_v617")
    with g2:
        projection_mode=st.selectbox("Método de proyección",["Ritmo diario del período","Ritmo por días hábiles (lun-vie)"],key="exec_proj_v617")

    sdate,edate=mstart,dend
    if isinstance(days,(tuple,list)) and len(days)==2:
        sdate,edate=days

    filtered=filter_sales(base,sellers=fs,warehouses=fw,document_types=ft)
    actual_rows=filtered[(filtered["Fecha_dt"].dt.date>=sdate)&(filtered["Fecha_dt"].dt.date<=edate)]
    actual_end=actual_rows["Fecha_dt"].max().date() if not actual_rows.empty else sdate
    actual_view=actual_rows[actual_rows["Fecha_dt"].dt.date<=actual_end]

    totals=calculate_commercial_totals(actual_view,.19)
    no_vat=base_mode=="Venta final sin IVA"
    actual=float(totals["venta_neta_sin_iva"] if no_vat else totals["venta_neta_con_iva"])
    gross=float(totals["ventas_brutas_sin_iva"] if no_vat else totals["ventas_brutas_con_iva"])
    credits=float(totals["notas_credito_sin_iva"] if no_vat else totals["notas_credito_con_iva"])
    opposite=float(totals["venta_neta_con_iva"] if no_vat else totals["venta_neta_sin_iva"])

    def cd(a,b): return max((pd.Timestamp(b)-pd.Timestamp(a)).days+1,0)
    def bd(a,b): return len(pd.bdate_range(a,b)) if b>=a else 0
    counter=bd if "hábiles" in projection_mode else cd
    elapsed=counter(sdate,actual_end)
    target=counter(sdate,edate)
    rate=actual/elapsed if elapsed else 0
    projected=actual if edate<=actual_end else rate*target

    compliance=actual/goal*100 if goal else 0
    projected_compliance=projected/goal*100 if goal else 0
    missing=max(goal-actual,0)
    gap=goal-projected

    sales_only=actual_view[actual_view["Grupo comercial"].isin(["Factura","Boleta"])]
    docs=sales_only["Numero"].nunique() if "Numero" in sales_only.columns else len(sales_only)
    ticket=gross/docs if docs else 0

    plen=cd(sdate,actual_end)
    prev_end=pd.Timestamp(sdate)-pd.Timedelta(days=1)
    prev_start=prev_end-pd.Timedelta(days=max(plen-1,0))
    prev=filtered[(filtered["Fecha_dt"]>=prev_start.normalize())&(filtered["Fecha_dt"]<=prev_end.normalize()+pd.Timedelta(days=1)-pd.Timedelta(seconds=1))]
    prev_tot=calculate_commercial_totals(prev,.19)
    previous=float(prev_tot["venta_neta_sin_iva"] if no_vat else prev_tot["venta_neta_con_iva"])
    variation=((actual-previous)/previous*100) if previous else (100 if actual>0 else 0)
    coverage=min(elapsed/target*100,100) if target else 0

    render_html(f"""
    <div class="exec-v60-strip">
      <div><span>Datos ERP hasta</span><strong>{pd.Timestamp(actual_end).strftime("%d/%m/%Y")}</strong></div>
      <div><span>Mes analizado</span><strong>{lab}</strong></div>
      <div><span>Días seleccionados</span><strong>{pd.Timestamp(sdate).strftime("%d/%m")} – {pd.Timestamp(edate).strftime("%d/%m/%Y")}</strong></div>
      <div><span>Cobertura temporal</span><strong>{coverage:.1f}%</strong></div>
      <div class="exec-v60-note">{"El ERP aún no cubre todo el período; la venta faltante se proyecta con el ritmo observado." if actual_end < edate else "El ERP cubre completamente el período seleccionado."}</div>
    </div>
    """)

    short="Sin IVA" if no_vat else "Con IVA"
    other="Con IVA" if no_vat else "Sin IVA"
    render_html(f"""
    <div class="exec-v60-kpis">
      <div class="exec-v60-kpi"><span>Venta actual · {short}</span><strong>{format_clp(actual)}</strong><small>{other}: {format_clp(opposite)}</small></div>
      <div class="exec-v60-kpi"><span>Meta · {short}</span><strong>{format_clp(goal)}</strong><small>{compliance:.1f}% cumplido</small></div>
      <div class="exec-v60-kpi focus"><span>Proyección cierre · {short}</span><strong>{format_clp(projected)}</strong><small>{projected_compliance:.1f}% de la meta</small></div>
      <div class="exec-v60-kpi"><span>Variación</span><strong>{variation:+.1f}%</strong><small>vs. período anterior equivalente</small></div>
      <div class="exec-v60-kpi"><span>Ticket promedio</span><strong>{format_clp(ticket)}</strong><small>{docs:,} documentos de venta</small></div>
    </div>
    """)

    current_w=min(max(compliance,0),100)
    projected_w=min(max(projected_compliance,0),100)
    message=f"Proyección supera la meta en {format_clp(abs(gap))}" if gap<0 else f"Proyección queda bajo la meta en {format_clp(gap)}"

    render_html(f"""
    <div class="exec-v60-goal">
      <div class="exec-v60-goal-head">
        <div><div class="gm-card-title">Cumplimiento y proyección · {short}</div><div class="gm-card-subtitle">Ritmo promedio: {format_clp(rate)} por {"día hábil" if "hábiles" in projection_mode else "día"}.</div></div>
        <div class="exec-v60-note">{message}</div>
      </div>
      <div class="exec-v60-progress-label"><span>Venta actual</span><strong>{compliance:.1f}%</strong></div>
      <div class="exec-v60-progress-track"><div class="exec-v60-progress-fill current" style="width:{current_w:.2f}%"></div></div>
      <div class="exec-v60-progress-label" style="margin-top:12px"><span>Proyección al cierre</span><strong>{projected_compliance:.1f}%</strong></div>
      <div class="exec-v60-progress-track"><div class="exec-v60-progress-fill projected" style="width:{projected_w:.2f}%"></div></div>
      <div class="exec-v60-goal-foot"><span>Faltante actual: <strong>{format_clp(missing)}</strong></span><span>Venta bruta: <strong>{format_clp(gross)}</strong></span><span>NC: <strong>{format_clp(credits)}</strong></span></div>
    </div>
    """)

    monthly=filtered.copy()
    monthly["_Mes"]=monthly["Fecha_dt"].dt.to_period("M")
    monthly["_Monto"]=pd.to_numeric(monthly["VentaMonto_num"],errors="coerce").fillna(0)
    if no_vat: monthly["_Monto"]=monthly["_Monto"]/1.19
    monthly["_Firmada"]=monthly.apply(lambda r:-abs(r["_Monto"]) if r["Grupo comercial"]=="Nota de crédito" else r["_Monto"],axis=1)
    monthly=monthly.groupby("_Mes",as_index=False).agg(Venta=("_Firmada","sum")).sort_values("_Mes")
    monthly["Mes"]=monthly["_Mes"].apply(month_label_es)

    render_html(f'<div class="gm-section-title">Evolución mensual · {short}</div>')
    chart=alt.Chart(monthly).mark_bar(cornerRadiusTopLeft=4,cornerRadiusTopRight=4,color="#4F7CD7").encode(
        x=alt.X("Mes:N",sort=list(monthly["Mes"]),title=None,axis=alt.Axis(labelAngle=-25)),
        y=alt.Y("Venta:Q",title="Venta neta"),
        tooltip=["Mes",alt.Tooltip("Venta:Q",format=",")]
    ).properties(height=285)
    st.altair_chart(chart,use_container_width=True)
