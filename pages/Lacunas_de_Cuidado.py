"""
Página: Lacunas de Cuidado
Indicadores agregados de qualidade terapêutica por território
+ lista nominal de pacientes com lacunas.
"""
import re
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from utils.bigquery_client import get_bigquery_client
from utils import theme as T
from components.cabecalho import renderizar_cabecalho
from utils.auth import get_contexto_territorial, get_perfil
import config
from utils.anonimizador import (
    anonimizar_ap, anonimizar_clinica, anonimizar_esf, mostrar_badge_anonimo, MODO_ANONIMO
)
st.set_page_config(
    page_title="Lacunas de Cuidado · Navegador Clínico",
    page_icon="⚠️",
    layout="wide"
)

renderizar_cabecalho("Lacunas")
ctx    = get_contexto_territorial()
perfil = get_perfil()

# ═══════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════
def _fqn(name: str) -> str:
    return f"{config.PROJECT_ID}.{config.DATASET_ID}.{name}"

def _ord_ap(ap: str) -> float:
    m = re.search(r'(\d+\.?\d*)', str(ap))
    return float(m.group(1)) if m else 999

@st.cache_data(ttl=3600, show_spinner=False)
def run_query(sql: str) -> pd.DataFrame:
    try:
        client = get_bigquery_client()
        return client.query(sql).result().to_dataframe(create_bqstorage_client=False)
    except Exception as e:
        st.error(f"❌ Erro na query: {e}")
        return pd.DataFrame()

# ═══════════════════════════════════════════════════════════════
# QUERIES
# ═══════════════════════════════════════════════════════════════
@st.cache_data(ttl=3600, show_spinner=False)
def carregar_lacunas_agregadas() -> pd.DataFrame:
    """MM_sumario_lacunas — 1 linha por lacuna × território."""
    sql = f"""
    SELECT
        categoria,
        lacuna,
        area_programatica_cadastro  AS ap,
        nome_clinica_cadastro       AS clinica,
        nome_esf_cadastro           AS esf,
        n_total_elegivel,
        n_com_lacuna,
        percentual_lacuna
    FROM `{_fqn("MM_sumario_lacunas")}`
    WHERE percentual_lacuna IS NOT NULL
    ORDER BY ap, clinica, esf
    """
    return run_query(sql)


@st.cache_data(ttl=3600, show_spinner=False)
def carregar_violin_charlson(ap=None, clinica=None, esf=None,
                              charlson_cats=None) -> pd.DataFrame:
    """
    Agrega por AP × clínica × Charlson:
    % de pacientes com cada lacuna.
    """
    clauses = [
        "area_programatica_cadastro IS NOT NULL",
        "nome_clinica_cadastro IS NOT NULL",
        "charlson_categoria IS NOT NULL",
        "charlson_categoria != 'Não Classificado'",
    ]
    if ap:      clauses.append(f"area_programatica_cadastro = '{ap}'")
    if clinica: clauses.append(f"nome_clinica_cadastro = '{clinica}'")
    if esf:     clauses.append(f"nome_esf_cadastro = '{esf}'")
    if charlson_cats:
        cats = "', '".join(charlson_cats)
        clauses.append(f"charlson_categoria IN ('{cats}')")
    where = "WHERE " + " AND ".join(clauses)

    sql = f"""
    SELECT
        area_programatica_cadastro  AS ap,
        nome_clinica_cadastro       AS clinica,
        nome_esf_cadastro           AS esf,
        charlson_categoria,
        COUNT(*)                    AS n_pacientes,

        ROUND(COUNTIF(lacuna_CI_sem_AAS = TRUE)
              * 100.0 / COUNT(*), 1)                          AS pct_CI_sem_AAS,
        ROUND(COUNTIF(lacuna_CI_sem_estatina_qualquer = TRUE)
              * 100.0 / COUNT(*), 1)                          AS pct_CI_sem_estatina,
        ROUND(COUNTIF(lacuna_FA_sem_anticoagulacao = TRUE)
              * 100.0 / COUNT(*), 1)                          AS pct_FA_sem_anticoag,
        ROUND(COUNTIF(lacuna_ICC_sem_SGLT2 = TRUE)
              * 100.0 / COUNT(*), 1)                          AS pct_ICC_sem_SGLT2,
        ROUND(COUNTIF(lacuna_ICC_sem_IECA_BRA = TRUE)
              * 100.0 / COUNT(*), 1)                          AS pct_ICC_sem_IECA_BRA,
        ROUND(COUNTIF(lacuna_IRC_sem_SGLT2 = TRUE)
              * 100.0 / COUNT(*), 1)                          AS pct_IRC_sem_SGLT2,
        ROUND(COUNTIF(lacuna_DM_sem_HbA1c_recente = TRUE)
              * 100.0 / COUNT(*), 1)                          AS pct_DM_sem_HbA1c,
        ROUND(COUNTIF(lacuna_DM_descontrolado = TRUE)
              * 100.0 / COUNT(*), 1)                          AS pct_DM_descontrolado,
        ROUND(COUNTIF(lacuna_HAS_descontrolado_menor80 = TRUE
                   OR lacuna_HAS_descontrolado_80mais = TRUE)
              * 100.0 / COUNT(*), 1)                          AS pct_HAS_descontrolado,
        ROUND(COUNTIF(lacuna_PA_hipertenso_180d = TRUE)
              * 100.0 / COUNT(*), 1)                          AS pct_HAS_sem_PA_180d,
        ROUND(COUNTIF(lacuna_creatinina_HAS_DM = TRUE)
              * 100.0 / COUNT(*), 1)                          AS pct_sem_creatinina,
        ROUND(COUNTIF(lacuna_colesterol_HAS_DM = TRUE)
              * 100.0 / COUNT(*), 1)                          AS pct_sem_colesterol,
        ROUND(COUNTIF(lacuna_DM_sem_exame_pe_365d = TRUE)
              * 100.0 / COUNT(*), 1)                          AS pct_DM_sem_exame_pe

    FROM `{_fqn(config.TABELA_FATO)}`
    {where}
    GROUP BY ap, clinica, esf, charlson_categoria
    HAVING COUNT(*) >= 5
    """
    return run_query(sql)


@st.cache_data(ttl=3600, show_spinner=False)
def carregar_pacientes_com_lacunas(ap=None, clinica=None, esf=None,
                                    charlson_cats=None) -> pd.DataFrame:
    """Lista nominal — pacientes com pelo menos 1 lacuna."""
    clauses = [
        "area_programatica_cadastro IS NOT NULL",
        "nome_clinica_cadastro IS NOT NULL",
        """(
            lacuna_CI_sem_AAS = TRUE OR
            lacuna_CI_sem_estatina_qualquer = TRUE OR
            lacuna_FA_sem_anticoagulacao = TRUE OR
            lacuna_ICC_sem_SGLT2 = TRUE OR
            lacuna_ICC_sem_IECA_BRA = TRUE OR
            lacuna_IRC_sem_SGLT2 = TRUE OR
            lacuna_DM_sem_HbA1c_recente = TRUE OR
            lacuna_DM_descontrolado = TRUE OR
            lacuna_HAS_descontrolado_menor80 = TRUE OR
            lacuna_HAS_descontrolado_80mais = TRUE OR
            lacuna_PA_hipertenso_180d = TRUE OR
            lacuna_creatinina_HAS_DM = TRUE OR
            lacuna_colesterol_HAS_DM = TRUE OR
            lacuna_DM_sem_exame_pe_365d = TRUE
        )"""
    ]
    if ap:      clauses.append(f"area_programatica_cadastro = '{ap}'")
    if clinica: clauses.append(f"nome_clinica_cadastro = '{clinica}'")
    if esf:     clauses.append(f"nome_esf_cadastro = '{esf}'")
    if charlson_cats:
        cats = "', '".join(charlson_cats)
        clauses.append(f"charlson_categoria IN ('{cats}')")
    where = "WHERE " + " AND ".join(clauses)

    sql = f"""
    SELECT
        nome,
        idade,
        area_programatica_cadastro  AS ap,
        nome_clinica_cadastro       AS clinica,
        nome_esf_cadastro           AS esf,
        charlson_categoria          AS carga_morbidade,
        charlson_score,
        total_morbidades,
        dias_desde_ultima_medica,
        ARRAY_TO_STRING(ARRAY(SELECT m FROM UNNEST([
            IF(HAS IS NOT NULL,              'HAS', NULL),
            IF(DM IS NOT NULL,               'DM', NULL),
            IF(CI IS NOT NULL,               'CI', NULL),
            IF(ICC IS NOT NULL,              'ICC', NULL),
            IF(stroke IS NOT NULL,           'AVC', NULL),
            IF(IRC IS NOT NULL,              'IRC', NULL),
            IF(COPD IS NOT NULL,             'DPOC', NULL),
            IF(arritmia IS NOT NULL,         'Arritmia', NULL),
            IF(dementia IS NOT NULL,         'Demência', NULL),
            IF(depre_ansiedade IS NOT NULL,  'Depressão/Ans.', NULL),
            IF(psicoses IS NOT NULL,         'Psicose', NULL),
            IF(obesidade_consolidada IS NOT NULL, 'Obesidade', NULL),
            IF(HIV IS NOT NULL,              'HIV', NULL)
        ]) AS m WHERE m IS NOT NULL), ', ') AS morbidades,
        (
            IF(lacuna_CI_sem_AAS = TRUE, 1, 0) +
            IF(lacuna_CI_sem_estatina_qualquer = TRUE, 1, 0) +
            IF(lacuna_FA_sem_anticoagulacao = TRUE, 1, 0) +
            IF(lacuna_ICC_sem_SGLT2 = TRUE, 1, 0) +
            IF(lacuna_ICC_sem_IECA_BRA = TRUE, 1, 0) +
            IF(lacuna_IRC_sem_SGLT2 = TRUE, 1, 0) +
            IF(lacuna_DM_sem_HbA1c_recente = TRUE, 1, 0) +
            IF(lacuna_DM_descontrolado = TRUE, 1, 0) +
            IF(lacuna_HAS_descontrolado_menor80 = TRUE, 1, 0) +
            IF(lacuna_HAS_descontrolado_80mais = TRUE, 1, 0) +
            IF(lacuna_PA_hipertenso_180d = TRUE, 1, 0) +
            IF(lacuna_creatinina_HAS_DM = TRUE, 1, 0) +
            IF(lacuna_colesterol_HAS_DM = TRUE, 1, 0) +
            IF(lacuna_DM_sem_exame_pe_365d = TRUE, 1, 0)
        ) AS n_lacunas,
        ARRAY_TO_STRING(ARRAY(SELECT l FROM UNNEST([
            IF(lacuna_CI_sem_AAS = TRUE,               'CI sem AAS', NULL),
            IF(lacuna_CI_sem_estatina_qualquer = TRUE,  'CI sem estatina', NULL),
            IF(lacuna_FA_sem_anticoagulacao = TRUE,     'FA sem anticoag.', NULL),
            IF(lacuna_ICC_sem_SGLT2 = TRUE,             'ICC sem SGLT-2', NULL),
            IF(lacuna_ICC_sem_IECA_BRA = TRUE,          'ICC sem IECA/BRA', NULL),
            IF(lacuna_IRC_sem_SGLT2 = TRUE,             'IRC sem SGLT-2', NULL),
            IF(lacuna_DM_sem_HbA1c_recente = TRUE,      'DM sem HbA1c', NULL),
            IF(lacuna_DM_descontrolado = TRUE,          'DM descontrolado', NULL),
            IF(lacuna_HAS_descontrolado_menor80 = TRUE, 'HAS descontrolada', NULL),
            IF(lacuna_HAS_descontrolado_80mais = TRUE,  'HAS desc. ≥80a', NULL),
            IF(lacuna_PA_hipertenso_180d = TRUE,        'HAS sem PA 180d', NULL),
            IF(lacuna_creatinina_HAS_DM = TRUE,         'Sem creatinina', NULL),
            IF(lacuna_colesterol_HAS_DM = TRUE,         'Sem colesterol', NULL),
            IF(lacuna_DM_sem_exame_pe_365d = TRUE,      'DM sem exame pé', NULL)
        ]) AS l WHERE l IS NOT NULL), ' · ') AS lacunas_ativas
    FROM `{_fqn(config.TABELA_FATO)}`
    {where}
    ORDER BY charlson_score DESC, n_lacunas DESC
    LIMIT 5000
    """
    return run_query(sql)


# ═══════════════════════════════════════════════════════════════
# SIDEBAR — apenas território
# ═══════════════════════════════════════════════════════════════
st.sidebar.title("Filtros")

with st.spinner("Carregando opções..."):
    df_lac = carregar_lacunas_agregadas()

if df_lac.empty:
    st.error("❌ Não foi possível carregar os dados de lacunas.")
    st.stop()

st.sidebar.markdown("### 📍 Território")

# ── Callbacks para reset hierárquico ─────────────────────────
def _lac_reset_cli_esf():
    st.session_state['lac_cli'] = 'Todas'
    st.session_state['lac_esf'] = 'Todas'

def _lac_reset_esf():
    st.session_state['lac_esf'] = 'Todas'

# Inicializar session_state
if 'lac_ap' not in st.session_state:
    ap_init = ctx.get('ap')
    aps_init = ['Todas'] + sorted(df_lac['ap'].dropna().unique().tolist(), key=_ord_ap)
    st.session_state['lac_ap'] = ap_init if ap_init in aps_init else 'Todas'
if 'lac_cli' not in st.session_state:
    st.session_state['lac_cli'] = ctx.get('clinica') or 'Todas'
if 'lac_esf' not in st.session_state:
    st.session_state['lac_esf'] = ctx.get('esf') or 'Todas'

aps_disp = ['Todas'] + sorted(df_lac['ap'].dropna().unique().tolist(), key=_ord_ap)
ap_sel = st.sidebar.selectbox(
    "🗺️ Área Programática", options=aps_disp,
    format_func=lambda x: "Todas" if x == 'Todas' else anonimizar_ap(str(x)),
    key="lac_ap", on_change=_lac_reset_cli_esf,
)

df_ap_f = df_lac if ap_sel == 'Todas' else df_lac[df_lac['ap'] == ap_sel]
clis_disp = ['Todas'] + sorted(df_ap_f['clinica'].dropna().unique().tolist())

# Garantir que o valor em session_state é válido para a AP atual
if st.session_state.get('lac_cli') not in clis_disp:
    st.session_state['lac_cli'] = 'Todas'

cli_sel = st.sidebar.selectbox(
    "🏥 Clínica", options=clis_disp,
    format_func=lambda x: "Todas" if x == 'Todas' else anonimizar_clinica(x),
    key="lac_cli", on_change=_lac_reset_esf,
)

df_cli_f = df_ap_f if cli_sel == 'Todas' else df_ap_f[df_ap_f['clinica'] == cli_sel]
esfs_disp = ['Todas'] + sorted(df_cli_f['esf'].dropna().unique().tolist())

# Garantir que o valor em session_state é válido para a clínica atual
if st.session_state.get('lac_esf') not in esfs_disp:
    st.session_state['lac_esf'] = 'Todas'

esf_sel = st.sidebar.selectbox(
    "👥 ESF", options=esfs_disp,
    format_func=lambda x: "Todas" if x == 'Todas' else anonimizar_esf(x),
    key="lac_esf",
)

# Navegação
st.sidebar.markdown("---")
st.sidebar.markdown("### 📑 Navegar para")
NOMES_ABAS = ["🎻 Distribuição por Território", "📋 Tabela de Lacunas", "👤 Lista de Pacientes"]
if 'lac_aba' not in st.session_state:
    st.session_state['lac_aba'] = 0
aba_sel = st.sidebar.radio(
    "", options=range(len(NOMES_ABAS)),
    format_func=lambda i: NOMES_ABAS[i],
    index=st.session_state['lac_aba'],
    key="lac_nav", label_visibility="collapsed",
)
st.session_state['lac_aba'] = aba_sel

# ═══════════════════════════════════════════════════════════════
# FILTRAR TABELA AGREGADA — só por território
# ═══════════════════════════════════════════════════════════════
df_f = df_lac.copy()
if ap_sel  != 'Todas': df_f = df_f[df_f['ap']      == ap_sel]
if cli_sel != 'Todas': df_f = df_f[df_f['clinica'] == cli_sel]
if esf_sel != 'Todas': df_f = df_f[df_f['esf']     == esf_sel]

# ═══════════════════════════════════════════════════════════════
# TÍTULO E MÉTRICAS
# ═══════════════════════════════════════════════════════════════
st.title("⚠️ Lacunas de Cuidado")
st.markdown(
    "Identifica onde há oportunidades de melhoria no cuidado clínico — "
    "pacientes elegíveis que não estão recebendo o tratamento ou monitoramento recomendado."
)
st.markdown("---")

c1, c2, c3, c4 = st.columns(4)
c1.metric("📝 Território × Lacuna", f"{len(df_f):,}")
c2.metric("📋 Tipos de lacuna", df_f['lacuna'].nunique())
media_lac = df_f['percentual_lacuna'].mean() if len(df_f) else 0
c3.metric("📊 % Lacuna médio", f"{media_lac:.1f}%")
n_crit = (df_f['percentual_lacuna'] > 50).sum()
c4.metric("🚨 Situações críticas (>50%)", f"{n_crit:,}", delta_color="inverse")

st.markdown("---")

# ═══════════════════════════════════════════════════════════════
# ABAS
# ═══════════════════════════════════════════════════════════════
tab1, tab2, tab3 = st.tabs(NOMES_ABAS)

# ──────────────────────────────────────────────────────────────
# ABA 1 — VIOLINO
# ──────────────────────────────────────────────────────────────
with tab1:
    st.markdown("### 🎻 Distribuição por Território")
    st.caption(
        "Cada ponto = uma clínica da família. "
        "Selecione a lacuna e a carga de morbidade para análises específicas. "
        "Ao filtrar por clínica, os pontos passam a representar as ESFs."
    )

    # Mapeamento lacuna → coluna na tabela fato
    MAPA_LAC_COL = {
        'CI sem AAS':                 'pct_CI_sem_AAS',
        'CI sem estatina alta intensidade': 'pct_CI_sem_estatina',
        'CI sem estatina qualquer':   'pct_CI_sem_estatina',
        'FA sem anticoagulação':      'pct_FA_sem_anticoag',
        'ICC sem SGLT-2':             'pct_ICC_sem_SGLT2',
        'ICC sem IECA/BRA':           'pct_ICC_sem_IECA_BRA',
        'IRC sem SGLT-2':             'pct_IRC_sem_SGLT2',
        'DM sem HbA1c recente':       'pct_DM_sem_HbA1c',
        'DM descontrolado':           'pct_DM_descontrolado',
        'HAS descontrolada':          'pct_HAS_descontrolado',
        'HAS sem aferição de PA em 180 dias': 'pct_HAS_sem_PA_180d',
        'Sem creatinina':             'pct_sem_creatinina',
        'Sem colesterol':             'pct_sem_colesterol',
        'DM sem exame do pé':         'pct_DM_sem_exame_pe',
    }

    # Filtros inline — mesmo padrão da tabela
    vf1, vf2 = st.columns(2)
    with vf1:
        cats_vio = ['Todas'] + sorted({
            k.split(' sem ')[0].split(' des')[0].strip()
            for k in MAPA_LAC_COL.keys()
        })
        # Categorias reais da MM_sumario_lacunas
        cats_vio = ['Todas'] + sorted(df_lac['categoria'].dropna().unique().tolist())
        cat_vio_sel = st.selectbox("📋 Categoria", options=cats_vio, key="vio_cat")
    with vf2:
        df_lac_vio = df_lac if cat_vio_sel == 'Todas' else df_lac[df_lac['categoria'] == cat_vio_sel]
        # Filtrar lacunas disponíveis no MAPA_LAC_COL
        lacs_vio_disp = sorted(MAPA_LAC_COL.keys())
        lac_violin_sel = st.selectbox(
            "🏷️ Lacuna", options=lacs_vio_disp, key="lac_violin_sel",
        )
    col_v = MAPA_LAC_COL[lac_violin_sel]

    charlson_opts = ['Muito Alto', 'Alto', 'Moderado', 'Baixo']
    charlson_sel = st.multiselect(
        "🏥 Carga de morbidade",
        options=charlson_opts,
        default=charlson_opts,
        key="vio_charlson",
        help="Filtra quais pacientes entram no cálculo de cada unidade.",
    )

    ap_v  = None if ap_sel  == 'Todas' else ap_sel
    cli_v = None if cli_sel == 'Todas' else cli_sel
    esf_v = None if esf_sel == 'Todas' else esf_sel
    ch_v  = charlson_sel if charlson_sel else None

    with st.spinner("Carregando dados do violino..."):
        df_ch = carregar_violin_charlson(ap=ap_v, clinica=cli_v, esf=esf_v,
                                          charlson_cats=ch_v)

    if df_ch.empty or col_v not in df_ch.columns:
        st.info("Sem dados suficientes para os filtros selecionados.")
    else:
        # Drill-down progressivo:
        # Sem filtro       → APs (violin, 1 ponto = clínica)
        # AP filtrada      → Clínicas daquela AP (strip, 1 ponto = clínica)
        # Clínica filtrada → ESFs daquela clínica (strip, 1 ponto = ESF)
        # ESF filtrada     → Só a ESF (strip)

        if esf_v is not None:
            # Nível ESF — mostra só a equipe
            df_plot = (
                df_ch.groupby(['esf'])[col_v]
                .mean().reset_index()
                .rename(columns={'esf': 'unidade', col_v: 'valor'})
            )
            df_plot['valor'] = df_plot['valor'].round(1)
            fig_v = px.strip(
                df_plot, x='unidade', y='valor', color='unidade',
                labels={'valor': '% com lacuna', 'unidade': 'ESF'},
                title=f"{lac_violin_sel} · % de pacientes com lacuna — ESF selecionada",
                color_discrete_sequence=px.colors.qualitative.Bold,
                height=440,
            )
            fig_v.update_traces(
                marker=dict(size=14, opacity=0.85, line=dict(width=1, color=T.BORDER)),
                jitter=0,
            )
            fig_v.update_xaxes(tickangle=-30, tickfont=dict(size=11), title_text='ESF')
            nivel_txt = 'ESF'

        elif cli_v is not None:
            # Nível Clínica — mostra ESFs da clínica
            df_plot = (
                df_ch.groupby(['clinica', 'esf'])[col_v]
                .mean().reset_index()
                .rename(columns={'esf': 'unidade', col_v: 'valor'})
            )
            df_plot['valor'] = df_plot['valor'].round(1)
            fig_v = px.strip(
                df_plot, x='unidade', y='valor', color='unidade',
                labels={'valor': '% com lacuna', 'unidade': 'ESF'},
                title=f"{lac_violin_sel} · % de pacientes com lacuna por ESF",
                color_discrete_sequence=px.colors.qualitative.Bold,
                height=440,
            )
            fig_v.update_traces(
                marker=dict(size=14, opacity=0.85, line=dict(width=1, color=T.BORDER)),
                jitter=0,
            )
            fig_v.update_xaxes(tickangle=-30, tickfont=dict(size=11), title_text='ESF')
            nivel_txt = 'ESF'

        elif ap_v is not None:
            # Nível AP — mostra clínicas daquela AP
            df_plot = (
                df_ch.groupby(['ap', 'clinica'])[col_v]
                .mean().reset_index()
                .rename(columns={'clinica': 'unidade', col_v: 'valor'})
            )
            df_plot['valor'] = df_plot['valor'].round(1)
            fig_v = px.strip(
                df_plot, x='unidade', y='valor', color='unidade',
                labels={'valor': '% com lacuna', 'unidade': 'Clínica'},
                title=f"{lac_violin_sel} · % de pacientes com lacuna por Clínica da Família",
                color_discrete_sequence=px.colors.qualitative.Bold,
                height=440,
            )
            fig_v.update_traces(
                marker=dict(size=14, opacity=0.85, line=dict(width=1, color=T.BORDER)),
                jitter=0,
            )
            fig_v.update_xaxes(tickangle=-30, tickfont=dict(size=11), title_text='Clínica')
            nivel_txt = 'clínica da família'

        else:
            # Sem filtro — mostra APs (violin, 1 ponto = clínica)
            df_plot = (
                df_ch.groupby(['ap', 'clinica'])[col_v]
                .mean().reset_index()
                .rename(columns={'ap': 'categoria', 'clinica': 'unidade',
                                 col_v: 'valor'})
            )
            df_plot['valor'] = df_plot['valor'].round(1)
            ap_ord = sorted(df_plot['categoria'].unique().tolist(), key=_ord_ap)
            fig_v = px.violin(
                df_plot, x='categoria', y='valor', color='categoria',
                box=True, points='all',
                hover_data={'unidade': True, 'valor': True, 'categoria': False},
                labels={'valor': '% com lacuna', 'categoria': 'Área Programática',
                        'unidade': 'Clínica'},
                title=f"{lac_violin_sel} · % de pacientes com lacuna por Área Programática",
                category_orders={'categoria': ap_ord},
                color_discrete_sequence=px.colors.qualitative.Bold,
                height=540,
            )
            fig_v.update_traces(
                meanline_visible=True,
                marker=dict(size=8, opacity=0.65, line=dict(width=0)),
                spanmode='hard',
            )
            fig_v.update_xaxes(
                type='category', categoryorder='array', categoryarray=ap_ord,
                tickangle=-30, tickfont=dict(size=11),
            )
            nivel_txt = 'clínica da família'

        fig_v.update_yaxes(ticksuffix='%', gridcolor=T.GRID,
                            rangemode='tozero', tickfont=dict(size=11))
        fig_v.update_layout(
            showlegend=False,
            paper_bgcolor=T.PAPER_BG,
            plot_bgcolor=T.PLOT_BG,
            font=dict(color=T.TEXT),
            title_font=dict(size=13, color=T.TEXT),
            margin=dict(l=60, r=20, t=60, b=80),
        )
        st.plotly_chart(fig_v, use_container_width=True)

        ch_txt = ', '.join(charlson_sel) if charlson_sel else 'todas as categorias'
        st.caption(
            f"Lacuna: **{lac_violin_sel}** · "
            f"Carga de morbidade: **{ch_txt}** · "
            f"Cada ponto = uma {nivel_txt}."
        )


# ──────────────────────────────────────────────────────────────
# ABA 2 — TABELA INTERATIVA
# ──────────────────────────────────────────────────────────────
with tab2:
    st.markdown("### 📋 Tabela de Lacunas por Território")
    st.caption(
        "Clique no cabeçalho de qualquer coluna para ordenar. "
        "A barra de progresso em '% Lacuna' facilita a comparação visual."
    )

    # Filtros inline — categoria, lacuna e carga de morbidade
    tf1, tf2 = st.columns(2)
    with tf1:
        cats_disp_t = ['Todas'] + sorted(df_f['categoria'].dropna().unique().tolist())
        cat_sel_t = st.selectbox("📋 Categoria", options=cats_disp_t, key="tab_cat")
    with tf2:
        df_temp_t = df_f if cat_sel_t == 'Todas' else df_f[df_f['categoria'] == cat_sel_t]
        lacs_disp_t = ['Todas'] + sorted(df_temp_t['lacuna'].dropna().unique().tolist())
        lac_sel_t = st.selectbox("🏷️ Lacuna específica", options=lacs_disp_t, key="tab_lac")

    charlson_opts = ['Muito Alto', 'Alto', 'Moderado', 'Baixo']
    charlson_sel_t = st.multiselect(
        "🏥 Carga de morbidade",
        options=charlson_opts,
        default=charlson_opts,
        key="tab_charlson",
        help="Filtra quais pacientes entram no cálculo de cada unidade.",
    )

    # Aplicar filtros adicionais
    df_tab_f = df_f.copy()
    if cat_sel_t != 'Todas': df_tab_f = df_tab_f[df_tab_f['categoria'] == cat_sel_t]
    if lac_sel_t != 'Todas': df_tab_f = df_tab_f[df_tab_f['lacuna']    == lac_sel_t]

    st.markdown("---")

    if df_tab_f.empty:
        st.info("Nenhum dado para os filtros selecionados.")
    else:
        df_tab = df_tab_f.sort_values('percentual_lacuna', ascending=False).copy()
        df_tab = df_tab.rename(columns={
            'categoria':         'Categoria',
            'lacuna':            'Lacuna',
            'ap':                'AP',
            'clinica':           'Clínica',
            'esf':               'ESF',
            'n_total_elegivel':  'Elegíveis',
            'n_com_lacuna':      'Com lacuna',
            'percentual_lacuna': '% Lacuna',
        })

        st.dataframe(
            df_tab[['Categoria','Lacuna','AP','Clínica','ESF',
                    'Elegíveis','Com lacuna','% Lacuna']],
            use_container_width=True,
            height=520,
            hide_index=True,
            column_config={
                '% Lacuna': st.column_config.ProgressColumn(
                    '% Lacuna', min_value=0, max_value=100, format="%.1f%%",
                ),
                'Clínica': st.column_config.TextColumn(width='medium'),
                'Lacuna':  st.column_config.TextColumn(width='medium'),
            }
        )

        st.markdown(
            f"**{len(df_tab):,} registros** · "
            f"**{(df_tab['% Lacuna'] > 50).sum():,}** situações críticas (>50%)"
        )
        csv = df_tab.to_csv(index=False, sep=';', encoding='utf-8-sig')
        st.download_button("⬇️ Baixar tabela (.csv)", csv,
                           "lacunas_territorio.csv", "text/csv")


# ──────────────────────────────────────────────────────────────
# ABA 3 — LISTA NOMINAL
# ──────────────────────────────────────────────────────────────
with tab3:
    st.markdown("### 👤 Pacientes com Lacunas de Cuidado")
    st.caption(
        "Lista nominal de pacientes com pelo menos uma lacuna identificada, "
        "ordenados por carga de morbidade e número de lacunas. "
        "Permite identificar quem priorizar para intervenção clínica."
    )

    # Filtros inline — mesmo padrão das outras abas
    pf1, pf2 = st.columns(2)
    with pf1:
        cats_pac = ['Todas'] + sorted(df_lac['categoria'].dropna().unique().tolist())
        cat_pac_sel = st.selectbox("📋 Categoria", options=cats_pac, key="pac_cat")
    with pf2:
        df_lac_pac = df_lac if cat_pac_sel == 'Todas' else df_lac[df_lac['categoria'] == cat_pac_sel]
        lacs_pac = ['Todas'] + sorted(df_lac_pac['lacuna'].dropna().unique().tolist())
        lac_pac_sel = st.selectbox("🏷️ Lacuna específica", options=lacs_pac, key="pac_lac")

    pf3, pf4, pf5 = st.columns(3)
    with pf3:
        charlson_opts = ['Muito Alto', 'Alto', 'Moderado', 'Baixo']
        charlson_sel = st.multiselect(
            "🏥 Carga de morbidade",
            options=charlson_opts,
            default=charlson_opts,
            key="pac_charlson",
        )
    with pf4:
        ordenar_por = st.selectbox(
            "Ordenar por",
            options=[
                'N° de lacunas (maior primeiro)',
                'Carga de morbidade (maior primeiro)',
                'Dias sem médico (maior primeiro)',
            ],
            key="pac_ordem",
        )
    with pf5:
        n_exibir = st.selectbox(
            "Exibir até",
            options=[50, 100, 250, 500, 1000, 5000],
            index=1,
            key="pac_n",
        )
    ap_p  = None if ap_sel  == 'Todas' else ap_sel
    cli_p = None if cli_sel == 'Todas' else cli_sel
    esf_p = None if esf_sel == 'Todas' else esf_sel
    ch_p  = charlson_sel if charlson_sel else None

    with st.spinner("Carregando lista de pacientes..."):
        df_pac = carregar_pacientes_com_lacunas(
            ap=ap_p, clinica=cli_p, esf=esf_p, charlson_cats=ch_p
        )

    if df_pac.empty:
        st.info("Nenhum paciente encontrado para os filtros selecionados.")
    else:
        # Filtrar por lacuna específica se selecionada
        if lac_pac_sel != 'Todas':
            # Filtrar pacientes que têm esta lacuna na lista
            df_pac = df_pac[df_pac['lacunas_ativas'].str.contains(
                lac_pac_sel[:15], case=False, na=False
            )]

        # Ordenar conforme seleção
        ordem_map = {
            'N° de lacunas (maior primeiro)':        ('n_lacunas', False),
            'Carga de morbidade (maior primeiro)':   ('charlson_score', False),
            'Dias sem médico (maior primeiro)':      ('dias_desde_ultima_medica', False),
        }
        col_ord, asc_ord = ordem_map[ordenar_por]
        df_pac = df_pac.sort_values(col_ord, ascending=asc_ord)

        media_lac_pac = df_pac['n_lacunas'].mean()
        st.markdown(
            f"**{len(df_pac):,} pacientes** com pelo menos 1 lacuna · "
            f"média de **{media_lac_pac:.1f} lacunas** por paciente"
        )

        df_exib = df_pac.head(n_exibir).rename(columns={
            'nome':               'Paciente',
            'idade':              'Idade',
            'ap':                 'AP',
            'clinica':            'Clínica',
            'esf':                'ESF',
            'carga_morbidade':    'Carga de Morbidade',
            'charlson_score':     'Score',
            'total_morbidades':   'N° Morb.',
            'dias_desde_ultima_medica': 'Dias s/ médico',
            'morbidades':         'Morbidades',
            'n_lacunas':          'N° Lacunas',
            'lacunas_ativas':     'Lacunas',
        })

        st.dataframe(
            df_exib[[
                'Paciente', 'Idade', 'AP', 'Clínica', 'ESF',
                'Carga de Morbidade', 'Score', 'N° Morb.',
                'Dias s/ médico', 'Morbidades', 'N° Lacunas', 'Lacunas',
            ]],
            use_container_width=True,
            height=560,
            hide_index=True,
            column_config={
                'Morbidades': st.column_config.TextColumn(width='medium'),
                'Lacunas':    st.column_config.TextColumn(width='large'),
                'Clínica':    st.column_config.TextColumn(width='medium'),
                'N° Lacunas': st.column_config.NumberColumn(width='small'),
            }
        )

        csv_p = df_pac.to_csv(index=False, sep=';', encoding='utf-8-sig')
        st.download_button("⬇️ Baixar lista (.csv)", csv_p,
                           "pacientes_lacunas.csv", "text/csv")

# ═══════════════════════════════════════════════════════════════
# RODAPÉ
# ═══════════════════════════════════════════════════════════════
st.markdown("---")
st.caption("SMS-RJ · Superintendência de Atenção Primária · Lacunas de Cuidado")