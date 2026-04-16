"""
Page: Risco Cardiovascular
Panorama populacional do risco cardiovascular — Framingham+SBC e WHO 2019/HEARTS.
"""
import re
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from streamlit_option_menu import option_menu
from utils.bigquery_client import get_bigquery_client
from utils.data_loader import carregar_opcoes_filtros
from utils.anonimizador import (
    anonimizar_nome, anonimizar_ap, anonimizar_clinica,
    anonimizar_esf, mostrar_badge_anonimo, MODO_ANONIMO
)
import config
from utils import theme as T

st.set_page_config(
    page_title="Risco Cardiovascular · Navegador Clínico",
    page_icon="❤️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ═══════════════════════════════════════════════════════════════
# VERIFICAR LOGIN
# ═══════════════════════════════════════════════════════════════
if 'usuario_global' not in st.session_state or not st.session_state.usuario_global:
    st.warning("⚠️ Por favor, faça login na página inicial")
    st.stop()

usuario_logado = st.session_state['usuario_global']
if isinstance(usuario_logado, dict):
    nome    = usuario_logado.get('nome_completo', 'Usuário')
    esf     = usuario_logado.get('esf')     or 'N/A'
    clinica = usuario_logado.get('clinica') or 'N/A'
    ap      = usuario_logado.get('area_programatica') or 'N/A'
else:
    nome = str(usuario_logado)
    esf = clinica = ap = 'N/A'

ctx = {
    'ap':      None if ap      == 'N/A' else ap,
    'clinica': None if clinica == 'N/A' else clinica,
    'esf':     None if esf     == 'N/A' else esf,
}

# ═══════════════════════════════════════════════════════════════
# CABEÇALHO
# ═══════════════════════════════════════════════════════════════
st.markdown("""
<style>
    [data-testid="stSidebarNav"] {display: none;}
</style>
""", unsafe_allow_html=True)

col1, col2 = st.columns([3, 1])
with col1:
    st.markdown(f"""
    <h1 style='margin: 0; padding: 0; color: {T.TEXT};'>
        🏥 Navegador Clínico de Multimorbidade e Polifarmácia
    </h1>
    """, unsafe_allow_html=True)
with col2:
    info_lines = [f"<strong>{nome}</strong>"]
    if esf     != 'N/A': info_lines.append(f"ESF: {esf}")
    if clinica != 'N/A': info_lines.append(f"Clínica: {clinica}")
    if ap      != 'N/A': info_lines.append(f"AP: {ap}")
    st.markdown(f"""
    <div style='text-align: right; padding-top: 10px; color: {T.TEXT}; font-size: 0.9em;'>
        <span style='font-size: 1.3em;'>👤</span> {"<br>".join(info_lines)}
    </div>
    """, unsafe_allow_html=True)

st.markdown("---")

PAGINA_ATUAL = "Risco CV"
ROTAS = {
    "Home":          "Home.py",
    "População":     "pages/Minha_Populacao.py",
    "Pacientes":     "pages/Meus_Pacientes.py",
    "Lacunas":       "pages/Lacunas_de_Cuidado.py",
    "Continuidade":  "pages/Acesso_Continuidade.py",
    "Polifarmácia":  "pages/Polifarmacia_ACB.py",
    "Diabetes":      "pages/Diabetes.py",
    "Hipertensão":   "pages/Hipertensao.py",
    "Risco CV":      "pages/Risco_Cardiovascular.py",
}
ICONES = [
    "house-fill", "people-fill", "person-lines-fill",
    "exclamation-triangle-fill", "arrow-repeat", "capsule",
    "droplet-fill", "heart-pulse-fill", "heart-fill",
]
selected = option_menu(
    menu_title=None,
    options=list(ROTAS.keys()),
    icons=ICONES,
    default_index=list(ROTAS.keys()).index(PAGINA_ATUAL),
    orientation="horizontal",
    styles={
        "container":         {"padding": "0!important", "background-color": T.NAV_BG},
        "icon":              {"font-size": "22px", "color": T.TEXT, "display": "block", "margin-bottom": "4px"},
        "nav-link":          {"font-size": "11px", "text-align": "center", "margin": "0px",
                              "padding": "10px 18px", "color": T.NAV_LINK, "background-color": T.SECONDARY_BG,
                              "--hover-color": T.NAV_HOVER, "display": "flex", "flex-direction": "column",
                              "align-items": "center", "line-height": "1.2", "white-space": "nowrap"},
        "nav-link-selected": {"background-color": T.NAV_SELECTED_BG, "color": T.NAV_SELECTED_TEXT, "font-weight": "600"},
    }
)
if selected != PAGINA_ATUAL:
    st.switch_page(ROTAS[selected])

st.markdown("---")

# ═══════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════
def _fqn(name): return f"{config.PROJECT_ID}.{config.DATASET_ID}.{name}"
def _p(n, d):   return round(n / d * 100, 1) if d else 0.0

@st.cache_data(show_spinner=False, ttl=900)
def bq(sql):
    try:
        client = get_bigquery_client()
        return client.query(sql).result().to_dataframe(create_bqstorage_client=False)
    except Exception as e:
        st.error(f"❌ Erro na query: {e}")
        return pd.DataFrame()


# ═══════════════════════════════════════════════════════════════
# QUERIES
# ═══════════════════════════════════════════════════════════════

@st.cache_data(show_spinner=False, ttl=900)
def carregar_sumario_rcv(ap, clinica, esf):
    clauses = []
    if ap:      clauses.append(f"area_programatica_cadastro = '{ap}'")
    if clinica: clauses.append(f"nome_clinica_cadastro = '{clinica}'")
    if esf:     clauses.append(f"nome_esf_cadastro = '{esf}'")
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    sql = f"""
    SELECT
        COUNT(*) AS total_pop,

        -- Elegibilidade
        COUNTIF(idade >= 30 AND idade <= 74) AS n_elegivel_framingham,
        COUNTIF(idade >= 40 AND idade <= 80) AS n_elegivel_who,

        -- Framingham+SBC calculado (toda a população com categoria válida)
        -- Framingham+SBC restrito a elegíveis 30-74a
        COUNTIF(idade BETWEEN 30 AND 74 AND categoria_risco_final IN ('BAIXO','INTERMEDIÁRIO','ALTO','MUITO ALTO')) AS n_fram_calculado,
        COUNTIF(idade BETWEEN 30 AND 74 AND categoria_risco_final = 'MUITO ALTO') AS n_fram_muito_alto,
        COUNTIF(idade BETWEEN 30 AND 74 AND categoria_risco_final = 'ALTO') AS n_fram_alto,
        COUNTIF(idade BETWEEN 30 AND 74 AND categoria_risco_final = 'INTERMEDIÁRIO') AS n_fram_intermediario,
        COUNTIF(idade BETWEEN 30 AND 74 AND categoria_risco_final = 'BAIXO') AS n_fram_baixo,

        -- Framingham MUITO ALTO: por doença estabelecida vs por fatores de risco
        COUNTIF(idade BETWEEN 30 AND 74 AND categoria_risco_final = 'MUITO ALTO'
                AND (CI IS NOT NULL OR stroke IS NOT NULL OR vascular_periferica IS NOT NULL)) AS n_fram_ma_dcv,
        COUNTIF(idade BETWEEN 30 AND 74 AND categoria_risco_final = 'MUITO ALTO'
                AND CI IS NULL AND stroke IS NULL AND vascular_periferica IS NULL) AS n_fram_ma_fator,

        -- DCV estabelecida (toda a população)
        COUNTIF(CI IS NOT NULL) AS n_com_ci,
        COUNTIF(stroke IS NOT NULL) AS n_com_avc,
        COUNTIF(vascular_periferica IS NOT NULL) AS n_com_dap,
        COUNTIF(CI IS NOT NULL OR stroke IS NOT NULL OR vascular_periferica IS NOT NULL) AS n_dcv_estabelecida,

        -- WHO calculado (exclui 'não calculável')
        COUNTIF(who_categoria_risco IS NOT NULL
                AND who_categoria_risco != 'não calculável') AS n_who_calculado,
        COUNTIF(who_categoria_risco = '>=30%') AS n_who_gte30,
        COUNTIF(who_categoria_risco = '20-30%') AS n_who_20_30,
        COUNTIF(who_categoria_risco = '10-20%') AS n_who_10_20,
        COUNTIF(who_categoria_risco = '5-10%') AS n_who_5_10,
        COUNTIF(who_categoria_risco = '<5%') AS n_who_lt5,
        -- WHO >=30%: por doença estabelecida vs por fatores
        COUNTIF(who_categoria_risco = '>=30%'
                AND (CI IS NOT NULL OR stroke IS NOT NULL OR vascular_periferica IS NOT NULL)) AS n_who_gte30_dcv,
        COUNTIF(who_categoria_risco = '>=30%'
                AND CI IS NULL AND stroke IS NULL AND vascular_periferica IS NULL) AS n_who_gte30_fator,

        -- Variáveis disponíveis (para cards de cobertura)
        COUNTIF(pressao_sistolica IS NOT NULL AND dias_desde_ultima_pa <= 365) AS n_com_pa_recente,
        COUNTIF(colesterol_total IS NOT NULL) AS n_com_colesterol,
        COUNTIF(hdl IS NOT NULL) AS n_com_hdl,
        COUNTIF(ldl IS NOT NULL) AS n_com_ldl,
        COUNTIF(tabaco IS NOT NULL) AS n_com_tabaco,
        COUNTIF(IMC IS NOT NULL) AS n_com_imc,
        COUNTIF(egfr IS NOT NULL) AS n_com_egfr,
        COUNTIF(DM IS NOT NULL) AS n_com_dm,

        -- Variáveis ausentes em elegíveis Framingham (30-74)
        COUNTIF(idade BETWEEN 30 AND 74 AND colesterol_total IS NULL) AS n_fram_sem_colesterol,
        COUNTIF(idade BETWEEN 30 AND 74 AND hdl IS NULL) AS n_fram_sem_hdl,
        COUNTIF(idade BETWEEN 30 AND 74 AND (pressao_sistolica IS NULL OR dias_desde_ultima_pa > 365)) AS n_fram_sem_pa,
        COUNTIF(idade BETWEEN 30 AND 74 AND categoria_risco_final IS NULL) AS n_fram_nao_calculado,

        -- WHO modelo utilizado
        COUNTIF(who_modelo_utilizado = 'lab') AS n_who_lab,
        COUNTIF(who_modelo_utilizado = 'nonlab') AS n_who_nonlab

    FROM `{_fqn(config.TABELA_FATO)}`
    {where}
    """
    df = bq(sql)
    return df.iloc[0].to_dict() if not df.empty else {}


@st.cache_data(show_spinner=False, ttl=900)
def carregar_territorio_rcv(ap, clinica, esf):
    """Dados por território para gráfico stacked bar."""
    if clinica:
        grupo_col, label_col = "nome_esf_cadastro", "ESF"
    elif ap:
        grupo_col, label_col = "nome_clinica_cadastro", "Clínica"
    else:
        grupo_col, label_col = "area_programatica_cadastro", "AP"

    clauses = [f"{grupo_col} IS NOT NULL"]
    if ap:      clauses.append(f"area_programatica_cadastro = '{ap}'")
    if clinica: clauses.append(f"nome_clinica_cadastro = '{clinica}'")
    if esf:     clauses.append(f"nome_esf_cadastro = '{esf}'")
    where = "WHERE " + " AND ".join(clauses)

    sql = f"""
    SELECT
        {grupo_col} AS territorio,
        COUNT(*) AS total_pop,
        -- Framingham+SBC como % dos elegíveis (30-74a) do território
        ROUND(COUNTIF(categoria_risco_final = 'MUITO ALTO') * 100.0
              / NULLIF(COUNTIF(idade BETWEEN 30 AND 74), 0), 1) AS pct_fram_muito_alto,
        ROUND(COUNTIF(categoria_risco_final = 'ALTO') * 100.0
              / NULLIF(COUNTIF(idade BETWEEN 30 AND 74), 0), 1) AS pct_fram_alto,
        ROUND(COUNTIF(categoria_risco_final = 'INTERMEDIÁRIO') * 100.0
              / NULLIF(COUNTIF(idade BETWEEN 30 AND 74), 0), 1) AS pct_fram_intermediario,
        ROUND(COUNTIF(categoria_risco_final = 'BAIXO') * 100.0
              / NULLIF(COUNTIF(idade BETWEEN 30 AND 74), 0), 1) AS pct_fram_baixo,
        -- WHO como % dos elegíveis (40-80a) do território
        ROUND(COUNTIF(who_categoria_risco = '>=30%') * 100.0
              / NULLIF(COUNTIF(idade BETWEEN 40 AND 80), 0), 1) AS pct_who_gte30,
        ROUND(COUNTIF(who_categoria_risco = '20-30%') * 100.0
              / NULLIF(COUNTIF(idade BETWEEN 40 AND 80), 0), 1) AS pct_who_20_30,
        ROUND(COUNTIF(who_categoria_risco = '10-20%') * 100.0
              / NULLIF(COUNTIF(idade BETWEEN 40 AND 80), 0), 1) AS pct_who_10_20,
        ROUND(COUNTIF(who_categoria_risco = '5-10%') * 100.0
              / NULLIF(COUNTIF(idade BETWEEN 40 AND 80), 0), 1) AS pct_who_5_10,
        ROUND(COUNTIF(who_categoria_risco = '<5%') * 100.0
              / NULLIF(COUNTIF(idade BETWEEN 40 AND 80), 0), 1) AS pct_who_lt5,
        '{label_col}' AS label_col
    FROM `{_fqn(config.TABELA_FATO)}`
    {where}
    GROUP BY {grupo_col}
    ORDER BY {grupo_col}
    """
    df = bq(sql)
    df['label_col'] = label_col
    return df


# ═══════════════════════════════════════════════════════════════
# SIDEBAR — FILTROS
# ═══════════════════════════════════════════════════════════════
mostrar_badge_anonimo()
st.sidebar.title("Filtros")

_opcoes = carregar_opcoes_filtros()
_areas  = _opcoes.get('areas', [])

def _rcv_reset_cli_esf():
    st.session_state['rcv_cli'] = None
    st.session_state['rcv_esf'] = None

def _rcv_reset_esf():
    st.session_state['rcv_esf'] = None

if 'rcv_ap'  not in st.session_state: st.session_state['rcv_ap']  = ctx.get('ap')
if 'rcv_cli' not in st.session_state: st.session_state['rcv_cli'] = ctx.get('clinica')
if 'rcv_esf' not in st.session_state: st.session_state['rcv_esf'] = ctx.get('esf')

ap_sel = st.sidebar.selectbox(
    "Área Programática",
    options=[None] + _areas,
    format_func=lambda x: "Todas" if x is None else anonimizar_ap(str(x)),
    key="rcv_ap", on_change=_rcv_reset_cli_esf,
)
_clinicas = sorted(_opcoes['clinicas'].get(ap_sel, [])) if ap_sel else []
if st.session_state.get('rcv_cli') not in _clinicas:
    st.session_state['rcv_cli'] = None

cli_sel = st.sidebar.selectbox(
    "Clínica da Família",
    options=[None] + _clinicas,
    format_func=lambda x: "Todas" if x is None else anonimizar_clinica(x),
    key="rcv_cli", disabled=not ap_sel, on_change=_rcv_reset_esf,
)
_esfs = sorted(_opcoes['esf'].get(cli_sel, [])) if cli_sel else []
if st.session_state.get('rcv_esf') not in _esfs:
    st.session_state['rcv_esf'] = None

esf_sel = st.sidebar.selectbox(
    "Equipe ESF",
    options=[None] + _esfs,
    format_func=lambda x: "Todas" if x is None else anonimizar_esf(x),
    key="rcv_esf", disabled=not cli_sel,
)

territorio = {'ap': ap_sel, 'clinica': cli_sel, 'esf': esf_sel}

# ═══════════════════════════════════════════════════════════════
# CARREGAR DADOS
# ═══════════════════════════════════════════════════════════════
st.title("❤️ Risco Cardiovascular")
st.markdown("Panorama do risco cardiovascular na população — Framingham+SBC e WHO 2019/HEARTS.")
st.markdown("---")

with st.spinner("Carregando dados de risco cardiovascular..."):
    sumario = carregar_sumario_rcv(ap_sel, cli_sel, esf_sel)
    df_terr = carregar_territorio_rcv(ap_sel, cli_sel, esf_sel)

if not sumario:
    st.error("❌ Não foi possível carregar os dados.")
    st.stop()

# Anonimizar território
if MODO_ANONIMO and not df_terr.empty and 'territorio' in df_terr.columns:
    if cli_sel:
        df_terr['territorio'] = df_terr['territorio'].apply(anonimizar_esf)
    elif ap_sel:
        df_terr['territorio'] = df_terr['territorio'].apply(anonimizar_clinica)
    else:
        df_terr['territorio'] = df_terr['territorio'].apply(lambda x: anonimizar_ap(str(x)))

tot = int(sumario.get('total_pop', 0)) or 1

# ═══════════════════════════════════════════════════════════════
# BLOCO 1 — CARDS DE COBERTURA
# ═══════════════════════════════════════════════════════════════
st.markdown("#### 1️⃣ Cobertura e disponibilidade de dados")

n_eleg_fram = int(sumario.get('n_elegivel_framingham', 0) or 0)
n_eleg_who  = int(sumario.get('n_elegivel_who', 0) or 0)
n_fram_calc = int(sumario.get('n_fram_calculado', 0) or 0)
n_who_calc  = int(sumario.get('n_who_calculado', 0) or 0)

c1, c2, c3 = st.columns(3)
with c1:
    with st.container(border=True):
        st.metric("👥 População total", f"{tot:,}")
with c2:
    with st.container(border=True):
        st.metric("📊 Elegíveis Framingham (30-74a)", f"{n_eleg_fram:,}",
                  f"{_p(n_eleg_fram, tot):.0f}% da população")
with c3:
    with st.container(border=True):
        st.metric("🌍 Elegíveis WHO/HEARTS (40-80a)", f"{n_eleg_who:,}",
                  f"{_p(n_eleg_who, tot):.0f}% da população")

n_who_lab      = int(sumario.get('n_who_lab', 0) or 0)
n_who_nonlab   = int(sumario.get('n_who_nonlab', 0) or 0)

c4, c5 = st.columns(2)
with c4:
    with st.container(border=True):
        st.metric("📊 Framingham+SBC calculado", f"{n_fram_calc:,}",
                  f"{_p(n_fram_calc, n_eleg_fram):.0f}% dos elegíveis (30-74a)")
with c5:
    with st.container(border=True):
        st.metric("🌍 WHO/HEARTS calculado", f"{n_who_calc:,}",
                  f"{_p(n_who_calc, n_eleg_who):.0f}% dos elegíveis (40-80a)")
        st.caption(
            f"Lab-based: {n_who_lab:,} · "
            f"Non-lab: {n_who_nonlab:,}"
        )

# Variáveis mais ausentes
st.markdown("##### Disponibilidade de variáveis clínicas")
vars_disp = [
    ("PA recente (≤365d)", int(sumario.get('n_com_pa_recente', 0) or 0)),
    ("Colesterol total",   int(sumario.get('n_com_colesterol', 0) or 0)),
    ("HDL",                int(sumario.get('n_com_hdl', 0) or 0)),
    ("LDL",                int(sumario.get('n_com_ldl', 0) or 0)),
    ("IMC",                int(sumario.get('n_com_imc', 0) or 0)),
    ("eGFR",               int(sumario.get('n_com_egfr', 0) or 0)),
    ("Tabagismo",          int(sumario.get('n_com_tabaco', 0) or 0)),
]

vc = st.columns(len(vars_disp))
for i, (label, n) in enumerate(vars_disp):
    pct = _p(n, tot)
    cor = "🟢" if pct >= 50 else "🟡" if pct >= 20 else "🔴"
    with vc[i]:
        with st.container(border=True):
            st.markdown(f"{cor} **{label}**")
            st.metric("Disponível", f"{n:,}", f"{pct:.0f}%")

# Ranking de ausentes em elegíveis Framingham
n_fram_sem_col = int(sumario.get('n_fram_sem_colesterol', 0) or 0)
n_fram_sem_hdl = int(sumario.get('n_fram_sem_hdl', 0) or 0)
n_fram_sem_pa  = int(sumario.get('n_fram_sem_pa', 0) or 0)
n_fram_nao_calc = int(sumario.get('n_fram_nao_calculado', 0) or 0)

if n_fram_nao_calc > 0:
    st.warning(
        f"⚠️ **{n_fram_nao_calc:,} pacientes elegíveis (30-74a) sem Framingham calculado.** "
        f"Motivos: sem colesterol ({n_fram_sem_col:,}), sem HDL ({n_fram_sem_hdl:,}), "
        f"sem PA recente ({n_fram_sem_pa:,})."
    )

st.markdown("---")

# ═══════════════════════════════════════════════════════════════
# BLOCO 2 — DISTRIBUIÇÃO POR CATEGORIA DE RISCO
# ═══════════════════════════════════════════════════════════════
st.markdown("#### 2️⃣ Doença cardiovascular estabelecida")
st.caption("Pacientes com IAM prévio (CI), AVC prévio ou doença arterial periférica são classificados diretamente como muito alto risco, sem necessidade de cálculo de escore (recomendação OMS e SBC).")

n_dcv     = int(sumario.get('n_dcv_estabelecida', 0) or 0)
n_ci      = int(sumario.get('n_com_ci', 0) or 0)
n_avc     = int(sumario.get('n_com_avc', 0) or 0)
n_dap     = int(sumario.get('n_com_dap', 0) or 0)

dc1, dc2, dc3, dc4 = st.columns(4)
with dc1:
    with st.container(border=True):
        st.metric("🚨 DCV estabelecida", f"{n_dcv:,}",
                  f"{_p(n_dcv, tot):.1f}% da população")
with dc2:
    with st.container(border=True):
        st.metric("💔 Cardiopatia isquêmica", f"{n_ci:,}")
with dc3:
    with st.container(border=True):
        st.metric("🧠 AVC prévio", f"{n_avc:,}")
with dc4:
    with st.container(border=True):
        st.metric("🦵 Doença arterial periférica", f"{n_dap:,}")

st.markdown("---")

st.markdown("#### 3️⃣ Distribuição por categoria de risco")

n_fram_ma      = int(sumario.get('n_fram_muito_alto', 0) or 0)
n_fram_ma_dcv  = int(sumario.get('n_fram_ma_dcv', 0) or 0)
n_fram_ma_fat  = int(sumario.get('n_fram_ma_fator', 0) or 0)
n_who_gte30    = int(sumario.get('n_who_gte30', 0) or 0)
n_who_gte30_dcv = int(sumario.get('n_who_gte30_dcv', 0) or 0)
n_who_gte30_fat = int(sumario.get('n_who_gte30_fator', 0) or 0)

col_f, col_w = st.columns(2)

# Framingham+SBC
with col_f:
    st.markdown(f"**Framingham + SBC** (n={n_fram_calc:,})")
    cats_fram = [
        ("MUITO ALTO (>20%)", n_fram_ma, "#C0392B",
         f"DCV estabelecida: {n_fram_ma_dcv:,} · Por fatores: {n_fram_ma_fat:,}"),
        ("ALTO (10-20%)",     int(sumario.get('n_fram_alto', 0) or 0), "#E74C3C", None),
        ("INTERMEDIÁRIO (5-10%)", int(sumario.get('n_fram_intermediario', 0) or 0), "#F39C12", None),
        ("BAIXO (<5%)",       int(sumario.get('n_fram_baixo', 0) or 0), "#2ECC71", None),
    ]
    for label, n, cor, detalhe in cats_fram:
        pct = _p(n, n_fram_calc) if n_fram_calc else 0
        det_html = f"<br><span style='font-size:0.85em; color:#666;'>{detalhe}</span>" if detalhe else ""
        st.markdown(
            f"<div style='background:{cor}20; border-left:4px solid {cor}; "
            f"padding:8px 12px; margin:4px 0; border-radius:4px;'>"
            f"<strong>{label}</strong>: {n:,} ({pct:.0f}%){det_html}</div>",
            unsafe_allow_html=True
        )

# WHO
with col_w:
    st.markdown(f"**WHO 2019 / HEARTS** (n={n_who_calc:,})")
    cats_who = [
        ("≥30%", n_who_gte30, "#8E44AD",
         f"DCV estabelecida: {n_who_gte30_dcv:,} · Por fatores: {n_who_gte30_fat:,}"),
        ("20-30%",  int(sumario.get('n_who_20_30', 0) or 0),  "#C0392B", None),
        ("10-20%",  int(sumario.get('n_who_10_20', 0) or 0),  "#E74C3C", None),
        ("5-10%",   int(sumario.get('n_who_5_10', 0) or 0),   "#F39C12", None),
        ("<5%",     int(sumario.get('n_who_lt5', 0) or 0),     "#2ECC71", None),
    ]
    for label, n, cor, detalhe in cats_who:
        pct = _p(n, n_who_calc) if n_who_calc else 0
        det_html = f"<br><span style='font-size:0.85em; color:#666;'>{detalhe}</span>" if detalhe else ""
        st.markdown(
            f"<div style='background:{cor}20; border-left:4px solid {cor}; "
            f"padding:8px 12px; margin:4px 0; border-radius:4px;'>"
            f"<strong>{label}</strong>: {n:,} ({pct:.0f}%){det_html}</div>",
            unsafe_allow_html=True
        )


st.markdown("---")

# ═══════════════════════════════════════════════════════════════
# BLOCO 4 — DISTRIBUIÇÃO POR TERRITÓRIO
# ═══════════════════════════════════════════════════════════════
st.markdown("#### 4️⃣ Risco cardiovascular por território")

if df_terr.empty:
    st.info("Sem dados por território.")
else:
    lbl = df_terr['label_col'].iloc[0] if not df_terr.empty else 'Território'

    def _stacked_bar_rcv(df, cols, labels, cores, titulo):
        if df is None or df.empty: return
        def _ord(v):
            m = re.search(r"(\d+\.?\d*)", str(v))
            return float(m.group(1)) if m else 999
        df_s = df.copy()
        df_s['_ord'] = df_s['territorio'].apply(_ord)
        df_s = df_s.sort_values('_ord')
        terrs = [str(t) for t in df_s['territorio'].tolist()]

        fig = go.Figure()
        for col, label, cor in zip(cols, labels, cores):
            vals = df_s[col].tolist() if col in df_s.columns else [0]*len(terrs)
            fig.add_trace(go.Bar(
                name=label, x=terrs, y=vals,
                marker_color=cor,
                text=[f"{v:.1f}%" for v in vals],
                textposition='inside',
                textfont=dict(size=9, color=T.TEXT),
            ))
        fig.update_layout(
            barmode='stack', height=380, bargap=0.35,
            margin=dict(l=10, r=160, t=50, b=80),
            paper_bgcolor=T.PAPER_BG, plot_bgcolor=T.PLOT_BG,
            title=dict(text=titulo, font=dict(color=T.TEXT, size=13)),
            xaxis=dict(type='category', categoryorder='array', categoryarray=terrs,
                       tickfont=dict(color=T.TEXT, size=10), tickangle=-35),
            yaxis=dict(title='% da população', tickfont=dict(color=T.TEXT_MUTED, size=10),
                       gridcolor=T.GRID),
            legend=dict(orientation='v', xanchor='left', x=1.01, yanchor='middle', y=0.5,
                        font=dict(color=T.TEXT, size=11),
                        bgcolor=T.LEGEND_BG, bordercolor=T.LEGEND_BORDER, borderwidth=1),
        )
        st.plotly_chart(fig, use_container_width=True)

    t1, t2 = st.columns(2)
    with t1:
        _stacked_bar_rcv(
            df_terr,
            ['pct_fram_muito_alto', 'pct_fram_alto', 'pct_fram_intermediario', 'pct_fram_baixo'],
            ['Muito Alto', 'Alto', 'Intermediário', 'Baixo'],
            ['#C0392B', '#E74C3C', '#F39C12', '#2ECC71'],
            f'Framingham + SBC por {lbl}',
        )
    with t2:
        _stacked_bar_rcv(
            df_terr,
            ['pct_who_gte30', 'pct_who_20_30', 'pct_who_10_20', 'pct_who_5_10', 'pct_who_lt5'],
            ['≥30%', '20-30%', '10-20%', '5-10%', '<5%'],
            ['#8E44AD', '#C0392B', '#E74C3C', '#F39C12', '#2ECC71'],
            f'WHO 2019 / HEARTS por {lbl}',
        )

# ═══════════════════════════════════════════════════════════════
# RODAPÉ
# ═══════════════════════════════════════════════════════════════
st.markdown("---")
st.caption(
    "Framingham: D'Agostino et al., Circulation 2008. "
    "Reclassificação: Diretriz SBC 2019. "
    "WHO: Kaptoge et al., Lancet Global Health 2019 — região tropical_latin_america."
)
