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
    sql_total_lac = gerar_sql_total_lacunas("total_lacunas")
    sql = f"""
    SELECT
        cpf, nome, idade, genero,
        area_programatica_cadastro,
        nome_clinica_cadastro AS clinica,
        nome_esf_cadastro     AS esf,
        charlson_score,
        charlson_categoria,
        acb_score_total,
        categoria_acb,
        dias_desde_ultima_medica,
        consultas_medicas_365d,
        total_morbidades,
        polifarmacia,
        hiperpolifarmacia,
        -- DCV estabelecida
        CI, stroke, vascular_periferica,
        -- Lacunas individuais usadas no bônus
        lacuna_CI_sem_AAS,
        lacuna_CI_sem_estatina_qualquer,
        -- Total de lacunas (soma dos 41 booleanos)
        {sql_total_lac}
    FROM `{_fqn(config.TABELA_FATO)}`
    WHERE area_programatica_cadastro = '{ap}'
      AND nome_clinica_cadastro     = '{clinica}'
      AND nome_esf_cadastro         = '{esf}'
    """
    return bq(sql)


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

with st.expander("ℹ️ Sobre o IPC — Índice de Prioridade de Cuidado", expanded=False):
    st.markdown(f"""
**O IPC é um índice composto que ordena pacientes por necessidade de
atenção da equipe.** Combina quatro dimensões clínicas em uma única
escala de 0 a 1, com bandas absolutas (independentes da amostra),
permitindo comparar pacientes entre ESFs, clínicas e APs.

#### Dimensões e pesos

| Dimensão | Peso | Bandas |
|---|---|---|
| 🦠 **Charlson** (carga de morbidade) | {PESOS_DEFAULT['charlson']:.0%} | 0–3 → 0 · 4–6 → 0,33 · 7–9 → 0,67 · ≥10 → 1 |
| 💊 **ACB** (carga anticolinérgica) | {PESOS_DEFAULT['acb']:.0%} | 0 → 0 · 1 → 0,33 · 2 → 0,67 · ≥3 → 1 |
| ⏳ **Dias sem consulta médica** | {PESOS_DEFAULT['acesso']:.0%} | 0–180 → 0 · 181–365 → 0,5 · 366–730 → 0,85 · >730 ou nunca → 1 |
| ⚠️ **Total de lacunas de cuidado** | {PESOS_DEFAULT['lacunas']:.0%} | 0 → 0 · 1–3 → 0,33 · 4–7 → 0,67 · ≥8 → 1 |

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

#### Diferença para o ICA

O ICA (Índice Composto de Acesso, na page **Continuidade**) usa
apenas Charlson + intervalo entre consultas, e normaliza pelo
máximo da amostra carregada — útil para ranking interno, mas não
comparável entre territórios. O IPC adiciona ACB e lacunas, e usa
limiares clínicos absolutos. **Os dois coexistem** e podem ser
contrastados conforme o uso.
""")

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
tab_resumo, tab_analise = st.tabs([
    "📊 Resumo da equipe",
    "🔬 Análise do IPC",
])

# ─────────────────────────────────────────────────────────────
# ABA 1 — RESUMO DA EQUIPE
# ─────────────────────────────────────────────────────────────
with tab_resumo:
    n_total = len(df)

    # KPIs primários
    st.markdown("#### 1️⃣ Indicadores da equipe")
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

    # Distribuição de IPC por categoria
    st.markdown("#### 2️⃣ Distribuição do IPC")
    dist = df['ipc_categoria'].value_counts().reindex(
        ['Crítico', 'Alto', 'Moderado', 'Baixo']
    ).fillna(0).astype(int)

    cd1, cd2, cd3, cd4 = st.columns(4)
    for col_w, cat in zip([cd1, cd2, cd3, cd4], ['Crítico', 'Alto', 'Moderado', 'Baixo']):
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

    # Histograma do IPC
    st.markdown("##### Histograma do IPC")
    fig_hist = px.histogram(
        df, x='ipc', nbins=40,
        labels={'ipc': 'IPC', 'count': 'Pacientes'},
    )
    fig_hist.update_traces(marker_color='#4f8ef7', opacity=0.85)
    for limiar, cor_v in [(0.25, '#FFEB3B'), (0.50, '#FF9800'), (0.75, '#7B0000')]:
        fig_hist.add_vline(x=limiar, line_dash='dash', line_color=cor_v)
    fig_hist.update_layout(
        height=320, bargap=0.05,
        margin=dict(l=10, r=10, t=20, b=40),
        paper_bgcolor=T.PAPER_BG, plot_bgcolor=T.PLOT_BG,
        xaxis=dict(range=[0, 1.05], title='IPC',
                   tickfont=dict(color=T.TEXT_MUTED), gridcolor=T.GRID),
        yaxis=dict(tickfont=dict(color=T.TEXT_MUTED), gridcolor=T.GRID),
    )
    st.plotly_chart(fig_hist, use_container_width=True)

    # Top-10 mais críticos
    st.markdown("#### 3️⃣ 10 pacientes mais críticos (maior IPC)")
    st.caption(
        "Ranking pelo IPC. Empates são desempatados por Charlson. "
        "Use como ponto de partida para discussão clínica em equipe."
    )
    top = df.sort_values(['ipc', 'charlson_score'],
                        ascending=[False, False]).head(10).copy()

    if top.empty:
        st.info("Sem pacientes para listar.")
    else:
        # Tabela enxuta
        top_show = pd.DataFrame({
            '#': range(1, len(top) + 1),
            'Paciente': top['nome_exib'].values,
            'Idade': top['idade'].astype('Int64').values,
            'IPC': top['ipc'].round(2).values,
            'Categoria': top['ipc_categoria'].values,
            'Charlson': top['charlson_score'].astype('Int64').values,
            'ACB': top['acb_score_total'].astype('Int64').values,
            'Dias s/ médico': top['dias_desde_ultima_medica'].apply(
                lambda v: f"{int(v)}" if pd.notna(v) else "—"
            ).values,
            'Lacunas': top['total_lacunas'].astype('Int64').values,
            'DCV s/ prev': top['ipc_dcv_sem_prev'].apply(
                lambda v: '⚠️' if v else ''
            ).values,
        })
        st.dataframe(top_show, hide_index=True, use_container_width=True)

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

# ─────────────────────────────────────────────────────────────
# ABA 2 — ANÁLISE DO IPC
# ─────────────────────────────────────────────────────────────
with tab_analise:
    st.markdown(
        "Esta aba investiga **colinearidade entre as dimensões do IPC** "
        "e a forma da distribuição de cada uma na equipe selecionada. "
        "É esperada alguma correlação positiva entre Charlson e total "
        "de lacunas (mais morbidades → mais oportunidades para lacunas), "
        "mas dimensões muito redundantes empobrecem o índice."
    )

    cols_dim = {
        'charlson_score':           'Charlson',
        'acb_score_total':          'ACB',
        'dias_desde_ultima_medica': 'Dias s/ médico',
        'total_lacunas':            'N° lacunas',
        'ipc':                      'IPC final',
    }

    df_corr_src = df[list(cols_dim.keys())].copy()
    df_corr_src.columns = list(cols_dim.values())
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
        'ipc_charlson_band': '🦠 Charlson',
        'ipc_acb_band':      '💊 ACB',
        'ipc_acesso_band':   '⏳ Dias s/ médico',
        'ipc_lacunas_band':  '⚠️ Lacunas',
    }
    cb1, cb2 = st.columns(2)
    for i, (col_band, label) in enumerate(bandas_cols.items()):
        target = cb1 if i % 2 == 0 else cb2
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
