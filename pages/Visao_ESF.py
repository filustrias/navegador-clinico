"""
Page: Visão ESF
Hub operacional para a equipe de Saúde da Família — KPIs da equipe,
top-N pacientes mais críticos via IPC, e análise de colinearidade
entre as dimensões do índice.
"""
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go

from utils.bigquery_client import get_bigquery_client
from utils import theme as T
from components.cabecalho import renderizar_cabecalho
from utils.anonimizador import (
    anonimizar_ap, anonimizar_clinica, anonimizar_esf, anonimizar_nome,
    mostrar_badge_anonimo, MODO_ANONIMO
)
from utils.ipc import (
    calcular_ipc, gerar_sql_total_lacunas, explicar_ipc_paciente,
    PESOS_DEFAULT, BONUS_DCV_SEM_PREV, CORES_IPC,
)
from utils.morbidades import gerar_sql_morbidades_lista
from utils.lacunas_config import LACUNAS, GRUPOS_LACUNAS
import config

st.set_page_config(
    page_title="Visão ESF · Navegador Clínico",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="expanded",
)

renderizar_cabecalho("Visão ESF")

# ═══════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════
def _fqn(name):
    return f"{config.PROJECT_ID}.{config.DATASET_ID}.{name}"


@st.cache_data(show_spinner=False, ttl=900)
def bq(sql: str) -> pd.DataFrame:
    try:
        client = get_bigquery_client()
        return client.query(sql).result().to_dataframe(create_bqstorage_client=False)
    except Exception as e:
        st.error(f"❌ Erro na query: {e}")
        return pd.DataFrame()


@st.cache_data(show_spinner=False, ttl=900)
def carregar_territorios() -> pd.DataFrame:
    """Tuplas únicas (AP, clínica, ESF) para alimentar os selectboxes."""
    sql = f"""
    SELECT DISTINCT
        area_programatica_cadastro,
        nome_clinica_cadastro,
        nome_esf_cadastro
    FROM `{_fqn(config.TABELA_FATO)}`
    WHERE area_programatica_cadastro IS NOT NULL
      AND nome_clinica_cadastro IS NOT NULL
      AND nome_esf_cadastro IS NOT NULL
    ORDER BY area_programatica_cadastro, nome_clinica_cadastro, nome_esf_cadastro
    """
    return bq(sql)


@st.cache_data(show_spinner=False, ttl=900)
def carregar_pacientes_ipc(ap: str, clinica: str, esf: str) -> pd.DataFrame:
    """Carrega colunas necessárias para o IPC + identificação do paciente."""
    sql_total_lac   = gerar_sql_total_lacunas("total_lacunas")
    sql_morb_lista  = gerar_sql_morbidades_lista("morbidades_lista")
    sql = f"""
    WITH stopp AS (
        SELECT cpf, COALESCE(total_criterios_stopp, 0) AS total_criterios_stopp
        FROM `rj-sms-sandbox.sub_pav_us.MM_stopp_start`
    )
    SELECT
        f.cpf, f.nome, f.idade, f.genero,
        f.area_programatica_cadastro,
        f.nome_clinica_cadastro AS clinica,
        f.nome_esf_cadastro     AS esf,
        f.charlson_score,
        f.charlson_categoria,
        f.acb_score_total,
        f.categoria_acb,
        f.dias_desde_ultima_medica,
        f.consultas_medicas_365d,
        f.total_morbidades,
        f.polifarmacia,
        f.hiperpolifarmacia,
        f.nucleo_cronico_atual         AS medicamentos_lista,
        f.dose_NPH_ui_kg,
        -- DCV estabelecida
        f.CI, f.stroke, f.vascular_periferica,
        -- Lacunas individuais usadas no bônus
        f.lacuna_CI_sem_AAS,
        f.lacuna_CI_sem_estatina_qualquer,
        -- Total de lacunas (soma dos 41 booleanos)
        {sql_total_lac},
        -- Lista textual de morbidades ativas
        {sql_morb_lista},
        -- Total de critérios STOPP (JOIN com MM_stopp_start)
        COALESCE(s.total_criterios_stopp, 0) AS total_criterios_stopp
    FROM `{_fqn(config.TABELA_FATO)}` AS f
    LEFT JOIN stopp s ON f.cpf = s.cpf
    WHERE f.area_programatica_cadastro = '{ap}'
      AND f.nome_clinica_cadastro     = '{clinica}'
      AND f.nome_esf_cadastro         = '{esf}'
    """
    return bq(sql)


@st.cache_data(show_spinner=False, ttl=900)
def carregar_lacunas_agregado(ap: str = None, clinica: str = None,
                              esf: str = None) -> pd.DataFrame:
    """
    Para um escopo (equipe = AP+clínica+ESF, ou município = sem filtro),
    devolve um DataFrame com uma linha por lacuna contendo:
      lacuna, grupo, numerador, denominador, pct
    A fórmula segue exatamente o denominador_sql definido em
    utils/lacunas_config.py (população elegível para a lacuna).
    """
    clauses = []
    if ap:      clauses.append(f"area_programatica_cadastro = '{ap}'")
    if clinica: clauses.append(f"nome_clinica_cadastro     = '{clinica}'")
    if esf:     clauses.append(f"nome_esf_cadastro         = '{esf}'")
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""

    selects = []
    for nome, info in LACUNAS.items():
        col   = info['coluna_fato']
        den   = info['denominador_sql']
        alias_n = "n_num__" + info['alias_pct'][len('pct_'):]
        alias_d = "n_den__" + info['alias_pct'][len('pct_'):]
        selects.append(f"COUNTIF({col} = TRUE) AS {alias_n}")
        selects.append(f"{den}                AS {alias_d}")

    sql = f"""
    SELECT
        {', '.join(selects)}
    FROM `{_fqn(config.TABELA_FATO)}`
    {where}
    """
    df = bq(sql)
    if df.empty:
        return pd.DataFrame(columns=['lacuna', 'grupo', 'numerador',
                                     'denominador', 'pct'])

    row = df.iloc[0]
    linhas = []
    for nome, info in LACUNAS.items():
        sufixo = info['alias_pct'][len('pct_'):]
        num = row.get(f"n_num__{sufixo}")
        den = row.get(f"n_den__{sufixo}")
        try:
            num_f = float(num) if pd.notna(num) else 0.0
            den_f = float(den) if pd.notna(den) and den else 0.0
        except (TypeError, ValueError):
            num_f, den_f = 0.0, 0.0
        pct = (num_f / den_f * 100.0) if den_f > 0 else None
        grupo = info['grupo']
        if isinstance(grupo, list):
            grupo = grupo[0]
        linhas.append({
            'lacuna':      nome,
            'grupo':       grupo,
            'numerador':   int(num_f),
            'denominador': int(den_f),
            'pct':         round(pct, 1) if pct is not None else None,
        })
    return pd.DataFrame(linhas)


def _kpi(col, label, valor, delta=None, ajuda=None):
    with col:
        with st.container(border=True):
            st.metric(label, valor, delta, help=ajuda)


# ═══════════════════════════════════════════════════════════════
# SIDEBAR — SELEÇÃO OBRIGATÓRIA AP / CLÍNICA / ESF
# ═══════════════════════════════════════════════════════════════
st.sidebar.header("🎯 Equipe selecionada")
mostrar_badge_anonimo()
st.sidebar.info("⚠️ Selecione AP, Clínica e ESF para carregar a visão da equipe.")

df_opts = carregar_territorios()
if df_opts.empty:
    st.sidebar.error("Sem opções de filtro disponíveis.")
    st.stop()

aps = sorted(df_opts['area_programatica_cadastro'].dropna().unique().tolist())
ap_sel = st.sidebar.selectbox(
    "Área Programática: *",
    options=[None] + aps,
    format_func=lambda x: "Selecione..." if x is None else anonimizar_ap(str(x)),
    key="ve_ap",
)

if ap_sel:
    clinicas = sorted(df_opts[df_opts['area_programatica_cadastro'] == ap_sel]
                      ['nome_clinica_cadastro'].dropna().unique().tolist())
else:
    clinicas = []

cli_sel = st.sidebar.selectbox(
    "Clínica da Família: *",
    options=[None] + clinicas,
    format_func=lambda x: "Selecione..." if x is None else anonimizar_clinica(x),
    disabled=not ap_sel, key="ve_cli",
)

if ap_sel and cli_sel:
    esfs = sorted(df_opts[(df_opts['area_programatica_cadastro'] == ap_sel)
                          & (df_opts['nome_clinica_cadastro'] == cli_sel)]
                  ['nome_esf_cadastro'].dropna().unique().tolist())
else:
    esfs = []

esf_sel = st.sidebar.selectbox(
    "ESF: *",
    options=[None] + esfs,
    format_func=lambda x: "Selecione..." if x is None else anonimizar_esf(x),
    disabled=not cli_sel, key="ve_esf",
)

# Bloqueia até que a equipe esteja selecionada
if not ap_sel:
    st.warning("⚠️ Selecione uma Área Programática na barra lateral.")
    st.stop()
if not cli_sel:
    st.warning("⚠️ Selecione uma Clínica da Família na barra lateral.")
    st.stop()
if not esf_sel:
    st.warning("⚠️ Selecione uma ESF na barra lateral.")
    st.stop()

# ═══════════════════════════════════════════════════════════════
# TÍTULO + EXPLICAÇÃO DO IPC
# ═══════════════════════════════════════════════════════════════
st.title("📋 Visão da ESF")
st.caption(
    f"AP **{anonimizar_ap(ap_sel)}** · Clínica **{anonimizar_clinica(cli_sel)}** "
    f"· ESF **{anonimizar_esf(esf_sel)}**"
)

# ═══════════════════════════════════════════════════════════════
# CARREGAMENTO DE DADOS
# ═══════════════════════════════════════════════════════════════
with st.spinner("Carregando pacientes da equipe..."):
    df_raw = carregar_pacientes_ipc(ap_sel, cli_sel, esf_sel)

if df_raw.empty:
    st.warning("⚠️ Nenhum paciente encontrado para a equipe selecionada.")
    st.stop()

df = calcular_ipc(df_raw)

# Anonimização para exibição
if MODO_ANONIMO:
    df['nome_exib'] = df.apply(
        lambda r: anonimizar_nome(str(r.get('cpf') or r.get('nome', '')),
                                  r.get('genero', '')),
        axis=1,
    )
else:
    df['nome_exib'] = df['nome']

# ═══════════════════════════════════════════════════════════════
# ABAS
# ═══════════════════════════════════════════════════════════════
tab_resumo, tab_lacunas, tab_analise = st.tabs([
    "📊 Resumo da equipe",
    "⚠️ Lacunas",
    "🔬 Análise do IPC",
])

# ─────────────────────────────────────────────────────────────
# ABA 1 — RESUMO DA EQUIPE
# ─────────────────────────────────────────────────────────────
with tab_resumo:
    n_total = len(df)

    # ─────────────────────────────────────────────────────────
    # 3️⃣ Top-10 mais críticos (PRIMEIRA INFORMAÇÃO)
    # ─────────────────────────────────────────────────────────
    st.markdown("#### 1️⃣ Aqui estão os 10 pacientes mais críticos da sua equipe (pacientes com maior IPC)")
    st.caption(
        "Ranking pelo IPC. Empates são desempatados pela Carga de "
        "Morbidade. Use como ponto de partida para discussão "
        "clínica em equipe."
    )
    top = df.sort_values(['ipc', 'charlson_score'],
                        ascending=[False, False]).head(10).copy()

    if top.empty:
        st.info("Sem pacientes para listar.")
    else:
        def _fmt_int_or_dash(v):
            return f"{int(v)}" if pd.notna(v) else "—"

        def _fmt_nph(v):
            if pd.isna(v) or v is None or v == 0:
                return "—"
            return f"{float(v):.2f}"

        top_show = pd.DataFrame({
            '#': range(1, len(top) + 1),
            'Paciente': top['nome_exib'].values,
            'Idade': top['idade'].astype('Int64').values,
            'IPC': top['ipc'].round(2).values,
            'Categoria': top['ipc_categoria'].values,
            'Carga de Morbidade': top['charlson_score'].astype('Int64').values,
            'Morbidades': top['morbidades_lista'].fillna('—').values,
            'ACB': top['acb_score_total'].astype('Int64').values,
            'STOPP': top['total_criterios_stopp'].astype('Int64').values,
            'Dias s/ médico': top['dias_desde_ultima_medica'].apply(
                _fmt_int_or_dash
            ).values,
            'Lacunas': top['total_lacunas'].astype('Int64').values,
            'Medicamentos (última prescrição)': top['medicamentos_lista'].fillna('—').values,
            'NPH (UI/kg)': top['dose_NPH_ui_kg'].apply(_fmt_nph).values,
            'DCV s/ prev': top['ipc_dcv_sem_prev'].apply(
                lambda v: '⚠️' if v else ''
            ).values,
        })
        st.dataframe(
            top_show, hide_index=True, use_container_width=True,
            column_config={
                'Morbidades':   st.column_config.TextColumn('Morbidades',   width='large'),
                'Medicamentos (última prescrição)':
                    st.column_config.TextColumn('Medicamentos (última prescrição)',
                                                width='large'),
                'IPC':          st.column_config.NumberColumn('IPC', format='%.2f'),
                'Carga de Morbidade':
                    st.column_config.NumberColumn('Carga de Morbidade', width='small'),
                'ACB':          st.column_config.NumberColumn('ACB',     width='small'),
                'STOPP':        st.column_config.NumberColumn('STOPP',   width='small'),
                'Lacunas':      st.column_config.NumberColumn('Lacunas', width='small'),
                'Dias s/ médico': st.column_config.TextColumn('Dias s/ médico', width='small'),
                'NPH (UI/kg)':  st.column_config.TextColumn('NPH (UI/kg)', width='small'),
                'DCV s/ prev':  st.column_config.TextColumn('DCV s/ prev', width='small'),
            },
        )

        # Detalhe expandido por paciente
        with st.expander("Ver decomposição do IPC por paciente"):
            for _, row in top.iterrows():
                cor = CORES_IPC.get(row['ipc_categoria'], '#999')
                st.markdown(
                    f"<div style='border-left:4px solid {cor}; padding:6px 12px; "
                    f"margin:4px 0; background:{cor}10; border-radius:4px;'>"
                    f"<strong>{row['nome_exib']}</strong> — IPC {row['ipc']:.2f} "
                    f"(<span style='color:{cor};'>{row['ipc_categoria']}</span>)<br>"
                    f"<span style='color:{T.TEXT_MUTED}; font-size:0.88em;'>"
                    f"{explicar_ipc_paciente(row)}</span>"
                    f"</div>",
                    unsafe_allow_html=True,
                )

    st.markdown("---")

    # ─────────────────────────────────────────────────────────
    # Sobre o IPC — sem sanfona, sem "Diferença para o ICA"
    # ─────────────────────────────────────────────────────────
    st.markdown("### ℹ️ Sobre o IPC — Índice de Priorização de Cuidado")
    st.markdown(f"""
**O IPC é um índice composto que ordena pacientes por necessidade de
atenção da equipe.** Combina cinco dimensões clínicas em uma única
escala de 0 a 1, com bandas absolutas (independentes da amostra),
permitindo comparar pacientes entre ESFs, clínicas e APs.

#### Dimensões e pesos

| Dimensão | Peso | Bandas |
|---|---|---|
| 🦠 **Carga de Morbidade** (Charlson) | {PESOS_DEFAULT['charlson']:.0%} | 0–3 → 0 · 4–6 → 0,33 · 7–9 → 0,67 · ≥10 → 1 |
| ⚠️ **Total de lacunas de cuidado** | {PESOS_DEFAULT['lacunas']:.0%} | 0 → 0 · 1–3 → 0,33 · 4–7 → 0,67 · ≥8 → 1 |
| ⏳ **Dias sem consulta médica** | {PESOS_DEFAULT['acesso']:.0%} | 0–180 → 0 · 181–365 → 0,5 · 366–730 → 0,85 · >730 ou nunca → 1 |
| 💊 **ACB** (carga anticolinérgica) | {PESOS_DEFAULT['acb']:.0%} | 0 → 0 · 1 → 0,33 · 2 → 0,67 · ≥3 → 1 |
| 🚫 **STOPP** (prescrições inapropriadas) | {PESOS_DEFAULT['stopp']:.0%} | 0 → 0 · 1 → 0,33 · 2 → 0,67 · ≥3 → 1 |

**Bônus de +{BONUS_DCV_SEM_PREV:.2f}** quando o paciente tem DCV estabelecida
(CI, AVC ou doença arterial periférica) **e** mantém lacunas de prevenção
secundária pendentes (sem AAS ou sem estatina). O resultado final é
cortado em 1,0.

#### Como interpretar

| Faixa de IPC | Categoria |
|---|---|
| ≥ 0,75 | 🔴 Crítico |
| 0,50 – 0,74 | 🟠 Alto |
| 0,25 – 0,49 | 🟡 Moderado |
| < 0,25 | 🟢 Baixo |
""")

    st.markdown("---")

    # ─────────────────────────────────────────────────────────
    # 1️⃣ Indicadores da equipe (KPIs)
    # ─────────────────────────────────────────────────────────
    st.markdown("#### 2️⃣ Indicadores da equipe")
    k1, k2, k3, k4 = st.columns(4)
    n_multi = int((df['total_morbidades'] >= 2).sum()) if 'total_morbidades' in df.columns else 0
    n_poli  = int(df['polifarmacia'].fillna(False).astype(bool).sum()) if 'polifarmacia' in df.columns else 0
    n_dcv   = int(((df['CI'].notna()) | (df['stroke'].notna())
                   | (df['vascular_periferica'].notna())).sum())
    _kpi(k1, "👥 Pacientes da equipe", f"{n_total:,}")
    _kpi(k2, "🦠 Multimórbidos (≥2)", f"{n_multi:,}",
         f"{n_multi/n_total*100:.0f}%" if n_total else None)
    _kpi(k3, "💊 Em polifarmácia", f"{n_poli:,}",
         f"{n_poli/n_total*100:.0f}%" if n_total else None)
    _kpi(k4, "❤️ DCV estabelecida", f"{n_dcv:,}",
         f"{n_dcv/n_total*100:.0f}%" if n_total else None)

    # ─────────────────────────────────────────────────────────
    # 2️⃣ Distribuição do IPC — caixas alinhadas com o histograma
    # (Baixo → Crítico, ordem visual da esquerda para a direita)
    # ─────────────────────────────────────────────────────────
    st.markdown("#### 3️⃣ Distribuição do IPC (Índice de Priorização de Cuidado)")
    dist = df['ipc_categoria'].value_counts().reindex(
        ['Baixo', 'Moderado', 'Alto', 'Crítico']
    ).fillna(0).astype(int)

    cd1, cd2, cd3, cd4 = st.columns(4)
    for col_w, cat in zip([cd1, cd2, cd3, cd4], ['Baixo', 'Moderado', 'Alto', 'Crítico']):
        n = int(dist.get(cat, 0))
        cor = CORES_IPC[cat]
        with col_w:
            st.markdown(
                f"<div style='background:{cor}20; border-left:6px solid {cor}; "
                f"padding:14px 16px; border-radius:8px;'>"
                f"<div style='color:{cor}; font-weight:600; font-size:0.9em;'>{cat}</div>"
                f"<div style='font-size:1.8em; font-weight:600; color:{T.TEXT};'>{n:,}</div>"
                f"<div style='color:{T.TEXT_MUTED}; font-size:0.85em;'>"
                f"{n/n_total*100:.1f}% da equipe</div>"
                f"</div>",
                unsafe_allow_html=True,
            )

    # Histograma do IPC — bins curtos coloridos pela faixa de IPC
    st.markdown("##### Histograma do IPC (Índice de Priorização de Cuidado)")
    n_bins = 80
    bins = np.linspace(0, 1.0, n_bins + 1)
    counts, edges = np.histogram(df['ipc'].clip(0, 1.0), bins=bins)
    centros = (edges[:-1] + edges[1:]) / 2

    def _cor_para_centro(c):
        if c >= 0.75: return CORES_IPC['Crítico']
        if c >= 0.50: return CORES_IPC['Alto']
        if c >= 0.25: return CORES_IPC['Moderado']
        return CORES_IPC['Baixo']

    cores_bins = [_cor_para_centro(c) for c in centros]

    fig_hist = go.Figure(
        go.Bar(
            x=centros, y=counts,
            marker=dict(color=cores_bins, line=dict(width=0)),
            width=(1.0 / n_bins) * 0.95,
            hovertemplate='IPC %{x:.2f}<br>%{y} pacientes<extra></extra>',
        )
    )
    for limiar in (0.25, 0.50, 0.75):
        fig_hist.add_vline(x=limiar, line_dash='dash', line_color='#888888')
    fig_hist.update_layout(
        height=320, bargap=0.0,
        margin=dict(l=10, r=10, t=20, b=40),
        paper_bgcolor=T.PAPER_BG, plot_bgcolor=T.PLOT_BG,
        xaxis=dict(range=[0, 1.05], title='IPC',
                   tickfont=dict(color=T.TEXT_MUTED), gridcolor=T.GRID),
        yaxis=dict(title='Pacientes',
                   tickfont=dict(color=T.TEXT_MUTED), gridcolor=T.GRID),
    )
    st.plotly_chart(fig_hist, use_container_width=True)

# ─────────────────────────────────────────────────────────────
# ABA 2 — LACUNAS DA EQUIPE × MUNICÍPIO
# ─────────────────────────────────────────────────────────────
with tab_lacunas:
    st.markdown(
        "#### Lacunas de cuidado da sua equipe — comparado ao município"
    )
    st.caption(
        "Cada lacuna é calculada apenas sobre a população elegível "
        "(ex.: 'CI sem AAS' usa pacientes com CI como denominador). "
        "Município = todos os pacientes da base. Lacunas ordenadas "
        "da mais prevalente à menos prevalente na sua equipe."
    )

    with st.spinner("Calculando lacunas da equipe e do município..."):
        df_eq  = carregar_lacunas_agregado(ap_sel, cli_sel, esf_sel)
        df_mun = carregar_lacunas_agregado(None, None, None)

    if df_eq.empty:
        st.warning("Sem dados de lacunas para a equipe selecionada.")
    else:
        df_lac = df_eq.merge(
            df_mun[['lacuna', 'numerador', 'denominador', 'pct']]
                .rename(columns={'numerador':   'numerador_mun',
                                 'denominador': 'denominador_mun',
                                 'pct':         'pct_mun'}),
            on='lacuna', how='left',
        )
        df_lac['delta'] = df_lac['pct'] - df_lac['pct_mun']
        df_lac = df_lac.sort_values('pct', ascending=False, na_position='last')

        # ── Tabela com gradiente de cor + setas ─────────────────
        df_tab = pd.DataFrame({
            'Grupo':       df_lac['grupo'].values,
            'Lacuna':      df_lac['lacuna'].values,
            'n / N':       df_lac.apply(
                lambda r: f"{int(r['numerador'])} / {int(r['denominador'])}"
                          if r['denominador'] else "—",
                axis=1,
            ).values,
            '% Equipe':    df_lac['pct'].astype(float).values,
            '% Município': df_lac['pct_mun'].astype(float).values,
            'Variação':    df_lac['delta'].astype(float).values,
        })

        def _fmt_variacao(v):
            if pd.isna(v):
                return '—'
            if v > 0:
                return f'↑ +{v:.1f}%'   # equipe pior que município
            if v < 0:
                return f'↓ {v:.1f}%'    # equipe melhor (v já negativo)
            return '↔ 0,0%'

        def _cor_variacao(v):
            if pd.isna(v):
                return ''
            if v > 0:
                return 'color: #C0392B; font-weight: 600;'   # vermelho
            if v < 0:
                return 'color: #27AE60; font-weight: 600;'   # verde
            return 'color: #6B7280;'

        # Gradiente manual verde→amarelo→vermelho (sem matplotlib)
        def _gradiente_pct(v, vmin=0.0, vmax=100.0):
            if pd.isna(v):
                return ''
            norm = max(0.0, min(1.0, (float(v) - vmin) / (vmax - vmin)))
            if norm <= 0.5:                       # verde → amarelo
                t = norm * 2
                r = int(round(76  + (255 - 76)  * t))
                g = int(round(175 + (235 - 175) * t))
                b = int(round( 80 + ( 59 -  80) * t))
            else:                                  # amarelo → vermelho
                t = (norm - 0.5) * 2
                r = int(round(255 + (231 - 255) * t))
                g = int(round(235 + ( 76 - 235) * t))
                b = int(round( 59 + ( 60 -  59) * t))
            return f'background-color: rgba({r},{g},{b},0.55);'

        styled = (
            df_tab.style
            .applymap(_gradiente_pct, subset=['% Equipe', '% Município'])
            .format({
                '% Equipe':    lambda v: f'{v:.1f}%' if pd.notna(v) else '—',
                '% Município': lambda v: f'{v:.1f}%' if pd.notna(v) else '—',
                'Variação':    _fmt_variacao,
            })
            .applymap(_cor_variacao, subset=['Variação'])
            .set_properties(
                subset=['Grupo', 'Lacuna'],
                **{'text-align': 'left'},
            )
            .set_properties(
                subset=['n / N', '% Equipe', '% Município', 'Variação'],
                **{'text-align': 'center'},
            )
            .set_table_styles([
                {'selector': 'th.col_heading.level0',
                 'props': [('text-align', 'center')]},
                {'selector': 'th.col_heading.level0:nth-child(1), '
                             'th.col_heading.level0:nth-child(2)',
                 'props': [('text-align', 'left')]},
            ])
        )

        st.dataframe(
            styled, hide_index=True, use_container_width=True, height=560,
        )

        st.markdown("---")

        # ── Gráfico vertical filtrado por grupo ─────────────────
        st.markdown("##### Comparação visual por grupo: equipe × município")

        grupos_disponiveis = (df_lac.dropna(subset=['grupo'])
                                    ['grupo'].unique().tolist())
        # Ordenar pela ordem canônica de GRUPOS_LACUNAS
        grupos_disponiveis = [g for g in GRUPOS_LACUNAS.keys()
                              if g in grupos_disponiveis]

        grupo_sel = st.selectbox(
            "Filtrar por grupo",
            options=grupos_disponiveis,
            index=0 if grupos_disponiveis else None,
            key="lac_grupo_filter",
        )

        df_plot = df_lac[(df_lac['grupo'] == grupo_sel)
                         & (df_lac['denominador'] > 0)].copy()
        df_plot = df_plot.sort_values('pct', ascending=False)

        if df_plot.empty:
            st.info(f"Sem lacunas com pacientes elegíveis no grupo "
                   f"**{grupo_sel}** para esta equipe.")
        else:
            # Cor da barra da equipe baseada em comparação com município:
            # acima do município (pior) → vermelho; abaixo (melhor) → verde.
            def _cor_barra_equipe(d):
                if pd.isna(d):
                    return '#9CA3AF'
                if d > 0.5:  return '#E74C3C'
                if d < -0.5: return '#27AE60'
                return '#F59E0B'  # próximo ao município

            cores_equipe = [_cor_barra_equipe(d) for d in df_plot['delta']]

            fig = go.Figure()
            # Barra do município (cinza, atrás)
            fig.add_trace(go.Bar(
                x=df_plot['lacuna'], y=df_plot['pct_mun'],
                name='Município',
                marker=dict(color='#D1D5DB'),
                text=[f'{v:.0f}%' for v in df_plot['pct_mun']],
                textposition='outside',
                textfont=dict(color=T.TEXT_MUTED, size=14),
                hovertemplate='<b>%{x}</b><br>Município: %{y:.1f}%<extra></extra>',
            ))
            # Barra da equipe (cor varia por delta)
            fig.add_trace(go.Bar(
                x=df_plot['lacuna'], y=df_plot['pct'],
                name='Equipe',
                marker=dict(color=cores_equipe),
                text=[f'{v:.0f}%' for v in df_plot['pct']],
                textposition='outside',
                textfont=dict(color=T.TEXT, size=15, family='Arial Black'),
                hovertemplate='<b>%{x}</b><br>Equipe: %{y:.1f}%<extra></extra>',
            ))
            fig.update_layout(
                barmode='group',
                height=520,
                margin=dict(l=10, r=10, t=40, b=160),
                paper_bgcolor=T.PAPER_BG, plot_bgcolor=T.PLOT_BG,
                xaxis=dict(
                    tickangle=-25,
                    tickfont=dict(color=T.TEXT, size=14),
                    automargin=True,
                ),
                yaxis=dict(
                    title=dict(
                        text='% da população elegível',
                        font=dict(color=T.TEXT, size=14),
                    ),
                    tickfont=dict(color=T.TEXT_MUTED, size=13),
                    gridcolor=T.GRID,
                    rangemode='tozero',
                ),
                legend=dict(
                    orientation='h', x=0.5, xanchor='center',
                    y=1.08, yanchor='bottom',
                    font=dict(color=T.TEXT, size=14),
                ),
            )
            st.plotly_chart(fig, use_container_width=True)
            st.caption(
                "🟥 acima do município (≥ +0,5 pp) · "
                "🟧 próximo ao município · "
                "🟩 abaixo do município (≤ −0,5 pp)"
            )

# ─────────────────────────────────────────────────────────────
# ABA 3 — ANÁLISE DO IPC
# ─────────────────────────────────────────────────────────────
with tab_analise:
    st.markdown(
        "Esta aba investiga **colinearidade entre as dimensões do IPC** "
        "e a forma da distribuição de cada uma na equipe selecionada. "
        "É esperada alguma correlação positiva entre Carga de Morbidade e total "
        "de lacunas (mais morbidades → mais oportunidades para lacunas), "
        "mas dimensões muito redundantes empobrecem o índice."
    )

    cols_dim = {
        'charlson_score':           'Carga de Morbidade',
        'acb_score_total':          'ACB',
        'total_criterios_stopp':    'STOPP',
        'dias_desde_ultima_medica': 'Dias s/ médico',
        'total_lacunas':            'N° lacunas',
        'ipc':                      'IPC final',
    }

    df_corr_src = df[list(cols_dim.keys())].copy()
    df_corr_src.columns = list(cols_dim.values())
    # Garante dtype float — colunas Int64 (nullable) não aceitam fillna
    # com mediana fracionária. Pearson precisa de float de qualquer modo.
    df_corr_src = df_corr_src.apply(pd.to_numeric, errors='coerce').astype(float)
    # Tratamento de NaN: paciente sem consulta (NaN) é o caso mais crítico
    # — substituir por valor alto (ex.: 9999) distorceria. Usar mediana.
    df_corr_src = df_corr_src.fillna(df_corr_src.median(numeric_only=True))

    # Matriz de correlação
    st.markdown("#### Matriz de correlação (Pearson)")
    corr = df_corr_src.corr(method='pearson').round(2)
    fig_corr = px.imshow(
        corr,
        text_auto=True,
        color_continuous_scale='RdBu_r',
        zmin=-1, zmax=1,
        aspect='auto',
    )
    fig_corr.update_layout(
        height=420,
        margin=dict(l=10, r=10, t=20, b=10),
        paper_bgcolor=T.PAPER_BG, plot_bgcolor=T.PLOT_BG,
        xaxis=dict(side='bottom', tickfont=dict(color=T.TEXT)),
        yaxis=dict(tickfont=dict(color=T.TEXT)),
        coloraxis_colorbar=dict(title='r'),
    )
    st.plotly_chart(fig_corr, use_container_width=True)

    st.caption(
        "Leitura prática: |r| < 0,3 = baixa correlação (dimensões "
        "razoavelmente independentes); 0,3 ≤ |r| < 0,6 = moderada; "
        "|r| ≥ 0,6 = alta (redundância — pode justificar reformular pesos)."
    )

    # Distribuição de cada dimensão (banda)
    st.markdown("#### Distribuição de cada dimensão (após mapeamento em banda)")
    bandas_cols = {
        'ipc_charlson_band': '🦠 Carga de Morbidade',
        'ipc_lacunas_band':  '⚠️ Lacunas',
        'ipc_acesso_band':   '⏳ Dias s/ médico',
        'ipc_acb_band':      '💊 ACB',
        'ipc_stopp_band':    '🚫 STOPP',
    }
    cb_cols = st.columns(2)
    for i, (col_band, label) in enumerate(bandas_cols.items()):
        target = cb_cols[i % 2]
        with target:
            counts = df[col_band].value_counts().sort_index()
            fig_b = go.Figure(go.Bar(
                x=[f"{v:.2f}" for v in counts.index],
                y=counts.values,
                marker_color='#4f8ef7',
            ))
            fig_b.update_layout(
                title=dict(text=label, font=dict(color=T.TEXT, size=13)),
                height=240, bargap=0.4,
                margin=dict(l=10, r=10, t=40, b=20),
                paper_bgcolor=T.PAPER_BG, plot_bgcolor=T.PLOT_BG,
                xaxis=dict(title='Banda', tickfont=dict(color=T.TEXT_MUTED)),
                yaxis=dict(title='Pacientes', tickfont=dict(color=T.TEXT_MUTED),
                           gridcolor=T.GRID),
            )
            st.plotly_chart(fig_b, use_container_width=True)

    # Tabela de pares com a maior correlação (ranking)
    st.markdown("#### Pares com correlação mais forte")
    pairs = []
    nomes = [v for k, v in cols_dim.items() if k != 'ipc']  # excluir IPC final
    sub = corr.loc[nomes, nomes]
    for i, a in enumerate(nomes):
        for b in nomes[i+1:]:
            pairs.append({'Par': f"{a} × {b}", 'r': sub.loc[a, b]})
    pares_df = pd.DataFrame(pairs).sort_values('r', key=lambda s: s.abs(),
                                               ascending=False)
    pares_df['r'] = pares_df['r'].round(2)
    pares_df['Magnitude'] = pares_df['r'].abs().apply(
        lambda v: 'Alta (≥0.6)' if v >= 0.6
                  else ('Moderada (0.3-0.6)' if v >= 0.3
                        else 'Baixa (<0.3)')
    )
    st.dataframe(pares_df, hide_index=True, use_container_width=True)
