"""
Página: Polifarmácia e Carga Anticolinérgica
Análise de polifarmácia, carga de morbidade e escore ACB por território
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from collections import Counter
from components.filtros import filtros_territoriais
from utils.bigquery_client import get_bigquery_client
import config
import math

# ═══════════════════════════════════════════════════════════════
# ANONIMIZAÇÃO
# ═══════════════════════════════════════════════════════════════
def anonimizar_ap(x): return str(x) if x else x
def anonimizar_clinica(x): return str(x) if x else x
def anonimizar_esf(x): return str(x) if x else x
def anonimizar_nome(nome, genero=''):
    import random
    nomes_m = ['A.S.', 'J.R.', 'M.F.', 'C.O.', 'P.L.']
    nomes_f = ['M.S.', 'A.R.', 'F.O.', 'C.L.', 'P.M.']
    return random.choice(nomes_f if str(genero).lower() in ['f','feminino'] else nomes_m)
MODO_ANONIMO = False

from utils.auth import exibir_usuario_logado

# ═══════════════════════════════════════════════════════════════
# VERIFICAR LOGIN
# ═══════════════════════════════════════════════════════════════
if 'usuario_global' not in st.session_state or not st.session_state.usuario_global:
    st.warning("⚠️ Por favor, faça login na página inicial")
    st.stop()

usuario_logado = st.session_state['usuario_global']
if isinstance(usuario_logado, dict):
    nome     = usuario_logado.get('nome_completo', 'Usuário')
    esf_usr  = usuario_logado.get('esf') or 'N/A'
    clinica_usr = usuario_logado.get('clinica') or 'N/A'
    ap_usr   = usuario_logado.get('area_programatica') or 'N/A'
else:
    nome = str(usuario_logado)
    esf_usr = clinica_usr = ap_usr = 'N/A'

# ═══════════════════════════════════════════════════════════════
# CABEÇALHO
# ═══════════════════════════════════════════════════════════════
from streamlit_option_menu import option_menu

st.markdown("""
<style>
    [data-testid="stSidebarNav"] {display: none;}
</style>
""", unsafe_allow_html=True)

col1, col2 = st.columns([3, 1])
with col1:
    st.markdown("""
    <h1 style='margin: 0; padding: 0; color: #FAFAFA;'>
        🏥 Navegador Clínico <small style='color: #999; font-size: 0.5em;'>SMS-RJ</small>
    </h1>
    """, unsafe_allow_html=True)
with col2:
    info_lines = [f"<strong>{nome}</strong>"]
    if esf_usr != 'N/A':  info_lines.append(f"ESF: {esf_usr}")
    if clinica_usr != 'N/A': info_lines.append(f"Clínica: {clinica_usr}")
    if ap_usr != 'N/A':   info_lines.append(f"AP: {ap_usr}")
    st.markdown(f"""
    <div style='text-align: right; padding-top: 10px; color: #FAFAFA; font-size: 0.9em;'>
        <span style='font-size: 1.3em;'>👤</span> {"<br>".join(info_lines)}
    </div>
    """, unsafe_allow_html=True)

st.markdown("---")

# ── Menu de navegação ─────────────────────────────────────────
selected = option_menu(
    menu_title=None,
    options=["Home", "Minha População", "Meus Pacientes", "Lacunas de Cuidado", "Polifarmácia"],
    icons=['house-fill', 'people-fill', 'person-lines-fill',
           'exclamation-triangle-fill', 'capsule'],
    menu_icon="cast",
    default_index=4,
    orientation="horizontal",
    styles={
        "container": {"padding": "0!important", "background-color": "#0E1117"},
        "icon":      {"color": "#FAFAFA", "font-size": "18px"},
        "nav-link":  {
            "font-size": "15px", "text-align": "center",
            "margin": "0px", "padding": "10px 15px",
            "color": "#FAFAFA", "background-color": "#262730",
            "--hover-color": "#404040"
        },
        "nav-link-selected": {"background-color": "#404040", "color": "#FAFAFA", "font-weight": "bold"},
    }
)

if selected == "Home":             st.switch_page("Home.py")
elif selected == "Minha População": st.switch_page("pages/Minha_Populacao.py")
elif selected == "Meus Pacientes":  st.switch_page("pages/Meus_Pacientes.py")
elif selected == "Lacunas de Cuidado": st.switch_page("pages/Lacunas_de_Cuidado.py")

st.markdown("---")

# ═══════════════════════════════════════════════════════════════
# BIGQUERY
# ═══════════════════════════════════════════════════════════════
@st.cache_data(ttl=900, show_spinner=False)
def run_query(query: str) -> pd.DataFrame:
    try:
        client = get_bigquery_client()
        return client.query(query).result().to_dataframe(create_bqstorage_client=False)
    except Exception as e:
        st.error(f"❌ Erro ao executar query: {e}")
        return pd.DataFrame()

def _fqn(tabela: str) -> str:
    return f"`{config.PROJECT_ID}.{config.DATASET_ID}.{tabela}`"

def _where(ap=None, clinica=None, esf=None, extra=None) -> str:
    clauses = []
    if ap:      clauses.append(f"area_programatica_cadastro = '{ap}'")
    if clinica: clauses.append(f"nome_clinica_cadastro = '{clinica}'")
    if esf:     clauses.append(f"nome_esf_cadastro = '{esf}'")
    if extra:   clauses.extend(extra)
    return ("WHERE " + " AND ".join(clauses)) if clauses else ""

# ═══════════════════════════════════════════════════════════════
# QUERIES
# ═══════════════════════════════════════════════════════════════

@st.cache_data(ttl=900, show_spinner=False)
def carregar_piramide_meds(ap=None, clinica=None, esf=None) -> pd.DataFrame:
    """Dados para pirâmide etária de medicamentos (reutiliza MM_piramides_populacionais)."""
    clauses = []
    if ap:      clauses.append(f"area_programatica_cadastro = '{ap}'")
    if clinica: clauses.append(f"nome_clinica_cadastro = '{clinica}'")
    if esf:     clauses.append(f"nome_esf_cadastro = '{esf}'")
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    sql = f"""
    SELECT
        faixa_etaria, genero,
        SUM(total_pacientes)              AS total_pacientes,
        SUM(n_nenhum_medicamento)         AS n_nenhum_medicamento,
        SUM(n_um_e_dois_medicamentos)     AS n_um_e_dois_medicamentos,
        SUM(n_tres_e_quatro_medicamentos) AS n_tres_e_quatro_medicamentos,
        SUM(n_polifarmacia)               AS n_polifarmacia,
        SUM(n_hiperpolifarmacia)          AS n_hiperpolifarmacia
    FROM `rj-sms-sandbox.sub_pav_us.MM_piramides_populacionais`
    {where}
    GROUP BY faixa_etaria, genero
    """
    return run_query(sql)


@st.cache_data(ttl=900, show_spinner=False)
def carregar_cards(ap=None, clinica=None, esf=None) -> dict:
    """Cards de resumo: totais de polifarmácia, hiperpolifarmácia, ACB."""
    where = _where(ap, clinica, esf)
    sql = f"""
    SELECT
        COUNT(*)                                              AS total_pacientes,
        COUNTIF(idade >= 65)                                  AS n_idosos,
        COUNTIF(polifarmacia = TRUE)                          AS n_polifarmacia,
        COUNTIF(hiperpolifarmacia = TRUE)                     AS n_hiperpolifarmacia,
        COUNTIF(COALESCE(acb_score_total, 0) >= 3)            AS n_acb_relevante,
        COUNTIF(alerta_acb_idoso = TRUE)                      AS n_acb_idoso,
        COUNTIF(COALESCE(acb_score_total, 0) >= 3
                AND polifarmacia = TRUE)                      AS n_acb_e_poli,
        ROUND(AVG(COALESCE(acb_score_total, 0)), 2)           AS media_acb,
        ROUND(AVG(total_medicamentos_cronicos), 1)            AS media_meds,
        MAX(COALESCE(acb_score_total, 0))                     AS max_acb
    FROM {_fqn(config.TABELA_FATO)}
    {where}
    """
    df = run_query(sql)
    return df.iloc[0].to_dict() if not df.empty else {}


@st.cache_data(ttl=900, show_spinner=False)
def carregar_polifarmacia_por_charlson(ap=None, clinica=None, esf=None) -> pd.DataFrame:
    """Distribuição de faixas de medicamentos por categoria Charlson."""
    where = _where(ap, clinica, esf, extra=[
        "charlson_categoria IS NOT NULL",
        "charlson_categoria != 'Não Classificado'"
    ])
    sql = f"""
    SELECT
        charlson_categoria,
        COUNTIF(total_medicamentos_cronicos = 0)                AS n_zero,
        COUNTIF(total_medicamentos_cronicos BETWEEN 1 AND 4)    AS n_1a4,
        COUNTIF(total_medicamentos_cronicos BETWEEN 5 AND 9)    AS n_poli,
        COUNTIF(total_medicamentos_cronicos >= 10)              AS n_hiperpoli,
        COUNT(*)                                                AS total
    FROM {_fqn(config.TABELA_FATO)}
    {where}
    GROUP BY charlson_categoria
    ORDER BY
        CASE charlson_categoria
            WHEN 'Muito Alto' THEN 1
            WHEN 'Alto'       THEN 2
            WHEN 'Moderado'   THEN 3
            WHEN 'Baixo'      THEN 4
        END
    """
    return run_query(sql)


@st.cache_data(ttl=900, show_spinner=False)
def carregar_acb_por_charlson(ap=None, clinica=None, esf=None) -> pd.DataFrame:
    """ACB score total por categoria Charlson (para violin)."""
    where = _where(ap, clinica, esf, extra=[
        "charlson_categoria IS NOT NULL",
        "charlson_categoria != 'Não Classificado'",
        "acb_score_total IS NOT NULL"
    ])
    sql = f"""
    SELECT
        charlson_categoria,
        COALESCE(acb_score_total, 0) AS acb_score_total
    FROM {_fqn(config.TABELA_FATO)}
    {where}
    """
    return run_query(sql)


@st.cache_data(ttl=900, show_spinner=False)
def carregar_top_medicamentos_acb(ap=None, clinica=None, esf=None) -> pd.DataFrame:
    """Top medicamentos anticolinérgicos prescritos, com seus scores."""
    where = _where(ap, clinica, esf, extra=[
        "medicamentos_acb_positivos IS NOT NULL",
        "medicamentos_acb_positivos != ''"
    ])
    sql = f"""
    SELECT medicamentos_acb_positivos
    FROM {_fqn(config.TABELA_FATO)}
    {where}
    LIMIT 50000
    """
    return run_query(sql)


@st.cache_data(ttl=900, show_spinner=False)
def carregar_lista_pacientes(ap=None, clinica=None, esf=None,
                              apenas_alerta_idoso=False) -> pd.DataFrame:
    """Lista nominal ordenada por ACB decrescente."""
    extra = ["acb_score_total IS NOT NULL"]
    if apenas_alerta_idoso:
        extra.append("alerta_acb_idoso = TRUE")
    where = _where(ap, clinica, esf, extra=extra)
    sql = f"""
    SELECT
        nome, idade, genero,
        nome_esf_cadastro,
        nome_clinica_cadastro,
        charlson_categoria,
        charlson_score,
        total_medicamentos_cronicos,
        polifarmacia,
        hiperpolifarmacia,
        acb_score_total,
        acb_score_cronicos,
        n_meds_acb_alto,
        medicamentos_acb_positivos,
        categoria_acb,
        alerta_acb_idoso,
        nucleo_cronico_atual
    FROM {_fqn(config.TABELA_FATO)}
    {where}
    ORDER BY acb_score_total DESC, charlson_score DESC
    LIMIT 5000
    """
    return run_query(sql)


# ═══════════════════════════════════════════════════════════════
# SIDEBAR — FILTROS
# ═══════════════════════════════════════════════════════════════
mostrar_badge_anonimo = lambda: None
territorio = filtros_territoriais(
    key_prefix="poli",
    obrigatorio_esf=False,
    mostrar_todas_opcoes=True
)

# Persistência de aba
if 'aba_poli' not in st.session_state:
    st.session_state['aba_poli'] = 0

st.sidebar.markdown("---")
st.sidebar.markdown("### 📑 Navegar para")
NOMES_ABAS_POLI = [
    "👥 Panorama",
    "📊 Polifarmácia × Morbidade",
    "🔴 Carga Anticolinérgica",
    "📋 Lista de Pacientes",
]
aba_sel = st.sidebar.radio(
    "", options=range(len(NOMES_ABAS_POLI)),
    format_func=lambda i: NOMES_ABAS_POLI[i],
    index=st.session_state['aba_poli'],
    key="nav_aba_poli",
    label_visibility="collapsed"
)
st.session_state['aba_poli'] = aba_sel

# ═══════════════════════════════════════════════════════════════
# TÍTULO
# ═══════════════════════════════════════════════════════════════
st.title("💊 Polifarmácia e Carga Anticolinérgica")
st.markdown(
    "Análise da carga medicamentosa, polifarmácia e escore ACB "
    "(*Anticholinergic Cognitive Burden*) por território e complexidade clínica."
)
st.markdown("---")

# ═══════════════════════════════════════════════════════════════
# ABAS
# ═══════════════════════════════════════════════════════════════
tab1, tab2, tab3, tab4 = st.tabs(NOMES_ABAS_POLI)

ap      = territorio.get('ap')
clinica = territorio.get('clinica')
esf     = territorio.get('esf')

# ──────────────────────────────────────────────────────────────
# ABA 1 — PANORAMA
# ──────────────────────────────────────────────────────────────
with tab1:
    st.markdown("### 👥 Panorama da Carga Medicamentosa")

    with st.spinner("Carregando dados..."):
        cards   = carregar_cards(ap, clinica, esf)
        df_pir  = carregar_piramide_meds(ap, clinica, esf)

    if not cards:
        st.warning("Nenhum dado encontrado para os filtros selecionados.")
    else:
        total   = int(cards.get('total_pacientes', 0)) or 1
        n_poli  = int(cards.get('n_polifarmacia', 0))
        n_hiper = int(cards.get('n_hiperpolifarmacia', 0))
        n_acb   = int(cards.get('n_acb_relevante', 0))
        n_acbi  = int(cards.get('n_acb_idoso', 0))
        media_acb  = round(float(cards.get('media_acb', 0)), 2)
        media_meds = round(float(cards.get('media_meds', 0)), 1)

        # ── Cards de alerta ────────────────────────────────────
        c1, c2, c3, c4, c5, c6 = st.columns(6)
        c1.metric("👥 Pacientes",       f"{total:,}")
        c2.metric("💊 Média de meds",   f"{media_meds}",
                  help="Média de medicamentos crônicos por paciente")
        c3.metric("⚠️ Polifarmácia",
                  f"{n_poli:,}",
                  delta=f"{n_poli/total*100:.1f}%",
                  delta_color="inverse",
                  help="5–9 medicamentos crônicos simultâneos")
        c4.metric("🚨 Hiperpolifarmácia",
                  f"{n_hiper:,}",
                  delta=f"{n_hiper/total*100:.1f}%",
                  delta_color="inverse",
                  help="≥ 10 medicamentos crônicos simultâneos")
        c5.metric("🔴 ACB ≥ 3",
                  f"{n_acb:,}",
                  delta=f"{n_acb/total*100:.1f}%",
                  delta_color="inverse",
                  help="Carga anticolinérgica clinicamente relevante (Boustani 2008)")
        c6.metric("🧠 ACB ≥ 3 em ≥65a",
                  f"{n_acbi:,}",
                  delta=f"{n_acbi/total*100:.1f}%",
                  delta_color="inverse",
                  help="Risco aumentado de demência e quedas em idosos")

        st.markdown("---")

        # ── Pirâmide ───────────────────────────────────────────
        st.subheader("🔺 Pirâmide Etária por Carga Medicamentosa")
        st.caption(
            "Cada barra representa uma faixa etária estratificada pela quantidade "
            "de medicamentos crônicos em uso. "
            "Masculino à esquerda, Feminino à direita."
        )

        if df_pir.empty:
            st.warning("Dados de pirâmide não disponíveis.")
        else:
            ordem_faixas = [
                '0-4','5-9','10-14','15-19','20-24','25-29','30-34',
                '35-39','40-44','45-49','50-54','55-59','60-64',
                '65-69','70-74','75-79','80-84','85-89','90+'
            ]
            df_pir['faixa_etaria'] = pd.Categorical(
                df_pir['faixa_etaria'], categories=ordem_faixas, ordered=True
            )
            df_pir = df_pir.sort_values('faixa_etaria')

            generos = df_pir['genero'].unique()
            col_m = 'masculino' if 'masculino' in generos else 'M'
            col_f = 'feminino'  if 'feminino'  in generos else 'F'
            df_m = df_pir[df_pir['genero'] == col_m].copy()
            df_f = df_pir[df_pir['genero'] == col_f].copy()

            cores_meds = ['#4A90D9', '#5BA85A', '#E8A838', '#D95F5F', '#9B59B6']
            estratos = [
                ('n_hiperpolifarmacia',          'Hiperpolifarmácia (≥10)',  cores_meds[4]),
                ('n_polifarmacia',               'Polifarmácia (5–9)',       cores_meds[3]),
                ('n_tres_e_quatro_medicamentos', '3–4 medicamentos',         cores_meds[2]),
                ('n_um_e_dois_medicamentos',     '1–2 medicamentos',         cores_meds[1]),
                ('n_nenhum_medicamento',         '0 medicamentos',           cores_meds[0]),
            ]

            fig_pir = go.Figure()
            for campo, label, cor in estratos:
                if campo in df_m.columns:
                    fig_pir.add_trace(go.Bar(
                        y=df_m['faixa_etaria'], x=-df_m[campo],
                        name=label, orientation='h',
                        marker=dict(color=cor, line=dict(color='rgba(0,0,0,0.5)', width=0.3)),
                        legendgroup=label, showlegend=True,
                        hovertemplate='<b>%{y} — Homens</b><br>' + label + ': %{text:,}<extra></extra>',
                        text=df_m[campo]
                    ))
            for campo, label, cor in estratos:
                if campo in df_f.columns:
                    fig_pir.add_trace(go.Bar(
                        y=df_f['faixa_etaria'], x=df_f[campo],
                        name=label, orientation='h',
                        marker=dict(color=cor, line=dict(color='rgba(0,0,0,0.5)', width=0.3)),
                        legendgroup=label, showlegend=False,
                        hovertemplate='<b>%{y} — Mulheres</b><br>' + label + ': %{x:,}<extra></extra>',
                    ))

            cols_sum = [c for c, *_ in estratos if c in df_m.columns]
            max_val = max(
                df_m[cols_sum].sum(axis=1).max() if cols_sum else 0,
                df_f[cols_sum].sum(axis=1).max() if cols_sum else 0
            )
            step = max(100, int(max_val / 5 / 100) * 100)
            ticks = list(range(0, int(max_val * 1.15), step))
            tick_vals  = [-t for t in ticks] + ticks
            tick_texts = [str(t) for t in ticks] + [str(t) for t in ticks]

            fig_pir.update_layout(
                barmode='relative',
                height=650,
                xaxis=dict(tickvals=tick_vals, ticktext=tick_texts,
                           title="Número de Pacientes",
                           gridcolor='rgba(255,255,255,0.08)'),
                yaxis=dict(title="Faixa Etária"),
                legend=dict(orientation='h', yanchor='bottom', y=1.02,
                            xanchor='right', x=1),
                plot_bgcolor='rgba(0,0,0,0)',
                paper_bgcolor='rgba(0,0,0,0)',
                margin=dict(l=60, r=40, t=60, b=60),
                annotations=[
                    dict(x=-max_val*0.5, y=1.02, xref='x', yref='paper',
                         text='◀ Masculino', showarrow=False,
                         font=dict(size=13, color='#AAAAAA')),
                    dict(x=max_val*0.5, y=1.02, xref='x', yref='paper',
                         text='Feminino ▶', showarrow=False,
                         font=dict(size=13, color='#AAAAAA')),
                ]
            )
            st.plotly_chart(fig_pir, use_container_width=True)
            st.caption(
                "⚠️ A concentração de polifarmácia e hiperpolifarmácia nas faixas etárias mais "
                "avançadas é esperada clinicamente, mas exige atenção especial ao risco de "
                "interações medicamentosas e carga anticolinérgica acumulada."
            )


# ──────────────────────────────────────────────────────────────
# ABA 2 — POLIFARMÁCIA × MORBIDADE
# ──────────────────────────────────────────────────────────────
with tab2:
    st.markdown("""
    ### 📊 Polifarmácia por Categoria de Carga de Morbidade (Charlson)

    Pacientes com maior carga de morbidade naturalmente tendem a usar mais medicamentos.
    O gráfico abaixo verifica se esse padrão se sustenta na população — e identifica
    grupos onde a prescrição pode estar aquém ou além do esperado.
    """)

    with st.spinner("Carregando dados..."):
        df_ch = carregar_polifarmacia_por_charlson(ap, clinica, esf)

    if df_ch.empty:
        st.warning("Nenhum dado encontrado.")
    else:
        # ── Barras 100% empilhadas ─────────────────────────────
        df_pct = df_ch.copy()
        for col in ['n_zero', 'n_1a4', 'n_poli', 'n_hiperpoli']:
            df_pct[col + '_pct'] = (df_pct[col] / df_pct['total'] * 100).round(1)

        cores_faixas = {
            '0 meds':             '#4A90D9',
            '1–4 meds':           '#5BA85A',
            'Polifarmácia (5–9)': '#E8A838',
            'Hiperpolifarmácia (≥10)': '#D95F5F',
        }

        fig_bar = go.Figure()
        dados_barras = [
            ('n_zero_pct',     'n_zero',     '0 meds',                  '#4A90D9'),
            ('n_1a4_pct',      'n_1a4',      '1–4 meds',                '#5BA85A'),
            ('n_poli_pct',     'n_poli',      'Polifarmácia (5–9)',      '#E8A838'),
            ('n_hiperpoli_pct','n_hiperpoli', 'Hiperpolifarmácia (≥10)', '#D95F5F'),
        ]
        for col_pct, col_n, label, cor in dados_barras:
            fig_bar.add_trace(go.Bar(
                name=label,
                x=df_pct['charlson_categoria'],
                y=df_pct[col_pct],
                marker_color=cor,
                text=df_pct.apply(
                    lambda r: f"{r[col_pct]:.1f}%<br>({int(r[col_n]):,})", axis=1
                ),
                textposition='inside',
                insidetextanchor='middle',
                textfont=dict(size=11),
                hovertemplate=(
                    "<b>%{x}</b><br>"
                    f"{label}: %{{y:.1f}}%<br>"
                    "N: %{customdata:,}<extra></extra>"
                ),
                customdata=df_pct[col_n]
            ))

        fig_bar.update_layout(
            barmode='stack',
            xaxis=dict(title="Categoria Charlson",
                       categoryorder='array',
                       categoryarray=['Muito Alto', 'Alto', 'Moderado', 'Baixo']),
            yaxis=dict(title="% de Pacientes", range=[0, 100]),
            legend=dict(orientation='h', yanchor='bottom', y=1.02,
                        xanchor='right', x=1),
            height=460,
            margin=dict(t=80, b=60),
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)',
        )
        st.plotly_chart(fig_bar, use_container_width=True)

        st.caption(
            "Cada barra soma 100%. Quanto maior a fatia laranja + vermelha em categorias "
            "de alto risco, maior a sobreposição entre complexidade clínica e polifarmácia — "
            "um sinal de alerta para revisão de prescrições."
        )

        st.markdown("---")

        # ── Tabela resumo ──────────────────────────────────────
        st.subheader("📋 Resumo por Categoria Charlson")
        df_exib = df_ch[['charlson_categoria','total','n_zero','n_1a4','n_poli','n_hiperpoli']].copy()
        df_exib['% Polifarmácia']      = (df_exib['n_poli']      / df_exib['total'] * 100).round(1)
        df_exib['% Hiperpolifarmácia'] = (df_exib['n_hiperpoli'] / df_exib['total'] * 100).round(1)
        df_exib.columns = [
            'Charlson', 'Total', '0 meds', '1–4 meds',
            'Polifarmácia (5–9)', 'Hiperpolifarmácia (≥10)',
            '% Polifarmácia', '% Hiperpolifarmácia'
        ]
        st.dataframe(df_exib, hide_index=True, use_container_width=True)


# ──────────────────────────────────────────────────────────────
# ABA 3 — CARGA ANTICOLINÉRGICA (ACB)
# ──────────────────────────────────────────────────────────────
with tab3:
    st.markdown("""
    ### 🔴 Carga Anticolinérgica (ACB — *Anticholinergic Cognitive Burden*)

    A escala ACB pontua medicamentos de acordo com seu potencial anticolinérgico:
    **score 1** = efeito possível; **score 2** = efeito estabelecido;
    **score 3** = efeito clinicamente relevante.
    O **score total ≥ 3** indica carga clinicamente significativa associada a
    comprometimento cognitivo e aumento de mortalidade
    *(Boustani et al., Aging Health 2008)*.
    """)

    with st.spinner("Carregando dados de ACB..."):
        df_acb_ch  = carregar_acb_por_charlson(ap, clinica, esf)
        df_meds_acb = carregar_top_medicamentos_acb(ap, clinica, esf)

    col_v, col_t = st.columns([1, 1])

    # ── Esquerda: violin ACB × Charlson ───────────────────────
    with col_v:
        st.subheader("Distribuição ACB por Complexidade Clínica")
        if df_acb_ch.empty:
            st.warning("Sem dados.")
        else:
            ordem_cat = ['Muito Alto', 'Alto', 'Moderado', 'Baixo']
            fig_viol = px.violin(
                df_acb_ch,
                x='charlson_categoria',
                y='acb_score_total',
                color='charlson_categoria',
                category_orders={'charlson_categoria': ordem_cat},
                labels={
                    'acb_score_total': 'ACB Score Total',
                    'charlson_categoria': 'Categoria Charlson'
                },
                box=True,
                points=False,
                height=480,
            )
            fig_viol.update_traces(
                meanline_visible=True,
                spanmode='hard',
            )
            # Linha de referência ACB = 3
            fig_viol.add_hline(
                y=3, line_dash='dash', line_color='#FF4444', line_width=2,
                annotation_text='Limiar clínico (ACB = 3)',
                annotation_position='top right',
                annotation_font_color='#FF4444'
            )
            fig_viol.update_layout(
                showlegend=False,
                xaxis=dict(title="Categoria Charlson"),
                yaxis=dict(title="ACB Score Total", zeroline=False),
                plot_bgcolor='rgba(0,0,0,0)',
                paper_bgcolor='rgba(0,0,0,0)',
                margin=dict(t=60, b=60),
            )
            st.plotly_chart(fig_viol, use_container_width=True)
            st.caption(
                "A linha vermelha tracejada marca o limiar clínico (ACB ≥ 3). "
                "Pacientes acima dela têm risco aumentado de efeitos cognitivos adversos."
            )

    # ── Direita: top medicamentos ACB ─────────────────────────
    with col_t:
        st.subheader("Top Medicamentos Anticolinérgicos Prescritos")
        if df_meds_acb.empty:
            st.warning("Sem dados.")
        else:
            # Parsear string "Medicamento(score); Medicamento(score)"
            contagens = Counter()
            scores_map = {}
            for row in df_meds_acb['medicamentos_acb_positivos'].dropna():
                for item in str(row).split(';'):
                    item = item.strip()
                    if not item:
                        continue
                    import re
                    m = re.match(r'^(.+)\((\d)\)$', item)
                    if m:
                        nome_med = m.group(1).strip()
                        score    = int(m.group(2))
                        contagens[nome_med] += 1
                        scores_map[nome_med] = score

            if not contagens:
                st.warning("Nenhum medicamento anticolinérgico identificado.")
            else:
                top_n = 15
                top_meds = contagens.most_common(top_n)
                nomes  = [m for m, _ in top_meds]
                counts = [c for _, c in top_meds]
                scores = [scores_map.get(m, 1) for m in nomes]

                cor_score = {1: '#F4D03F', 2: '#E67E22', 3: '#E74C3C'}
                cores_barras = [cor_score.get(s, '#888') for s in scores]

                fig_top = go.Figure(go.Bar(
                    y=nomes[::-1],
                    x=counts[::-1],
                    orientation='h',
                    marker=dict(
                        color=cores_barras[::-1],
                        line=dict(color='rgba(0,0,0,0.3)', width=0.5)
                    ),
                    text=[f"Score {s}" for s in scores[::-1]],
                    textposition='inside',
                    insidetextanchor='middle',
                    textfont=dict(size=10, color='white'),
                    hovertemplate=(
                        "<b>%{y}</b><br>"
                        "Pacientes: %{x:,}<extra></extra>"
                    )
                ))
                fig_top.update_layout(
                    xaxis=dict(title="Número de Pacientes"),
                    yaxis=dict(title=""),
                    height=480,
                    plot_bgcolor='rgba(0,0,0,0)',
                    paper_bgcolor='rgba(0,0,0,0)',
                    margin=dict(l=160, r=40, t=20, b=60),
                )
                st.plotly_chart(fig_top, use_container_width=True)
                st.caption(
                    "🟡 Score 1 = possível efeito &nbsp;|&nbsp; "
                    "🟠 Score 2 = efeito estabelecido &nbsp;|&nbsp; "
                    "🔴 Score 3 = clinicamente relevante"
                )

    st.markdown("---")

    # ── Distribuição de categorias ACB ────────────────────────
    st.subheader("📊 Distribuição por Categoria ACB na População")
    cards2 = carregar_cards(ap, clinica, esf)
    if cards2:
        total2 = int(cards2.get('total_pacientes', 1))
        n_acb2 = int(cards2.get('n_acb_relevante', 0))
        n_acbi2 = int(cards2.get('n_acb_idoso', 0))
        st.info(
            f"**{n_acb2:,} pacientes ({n_acb2/total2*100:.1f}%)** têm ACB ≥ 3 "
            f"(carga clinicamente relevante). "
            f"Desses, **{n_acbi2:,} têm 65 anos ou mais**, com risco aumentado "
            f"de comprometimento cognitivo e quedas."
        )


# ──────────────────────────────────────────────────────────────
# ABA 4 — LISTA DE PACIENTES
# ──────────────────────────────────────────────────────────────
with tab4:
    st.markdown("### 📋 Lista Nominal — Ordenada por Carga Anticolinérgica")

    # ── Cards de resumo (respondem aos filtros de território) ──
    with st.spinner("Carregando resumo..."):
        cards4 = carregar_cards(ap, clinica, esf)

    if cards4:
        total4  = int(cards4.get('total_pacientes', 0)) or 1
        n_id4   = int(cards4.get('n_idosos', 0))
        n_po4   = int(cards4.get('n_polifarmacia', 0))
        n_hi4   = int(cards4.get('n_hiperpolifarmacia', 0))
        n_acb4  = int(cards4.get('n_acb_relevante', 0))
        n_acbi4 = int(cards4.get('n_acb_idoso', 0))
        n_both4 = int(cards4.get('n_acb_e_poli', 0))
        m_acb4  = float(cards4.get('media_acb', 0))
        m_med4  = float(cards4.get('media_meds', 0))
        max_acb4= int(cards4.get('max_acb', 0))

        r1c1, r1c2, r1c3, r1c4 = st.columns(4)
        r1c1.metric("👥 Total de pacientes",    f"{total4:,}")
        r1c2.metric("🧓 Idosos (≥65 anos)",     f"{n_id4:,}",
                    delta=f"{n_id4/total4*100:.1f}%")
        r1c3.metric("💊 Média de meds crônicos", f"{m_med4}")
        r1c4.metric("📈 ACB médio / máximo",    f"{m_acb4} / {max_acb4}")

        st.markdown("")
        r2c1, r2c2, r2c3, r2c4 = st.columns(4)
        r2c1.metric("⚠️ Polifarmácia (5–9)",
                    f"{n_po4:,}",
                    delta=f"{n_po4/total4*100:.1f}%",
                    delta_color="inverse")
        r2c2.metric("🚨 Hiperpolifarmácia (≥10)",
                    f"{n_hi4:,}",
                    delta=f"{n_hi4/total4*100:.1f}%",
                    delta_color="inverse")
        r2c3.metric("🔴 ACB ≥ 3 (carga relevante)",
                    f"{n_acb4:,}",
                    delta=f"{n_acb4/total4*100:.1f}%",
                    delta_color="inverse",
                    help="Ponto de corte clínico — Boustani et al., 2008")
        r2c4.metric("🧠 ACB ≥ 3 em idosos ≥65a",
                    f"{n_acbi4:,}",
                    delta=f"{n_acbi4/total4*100:.1f}%",
                    delta_color="inverse",
                    help="Risco aumentado de demência e quedas")

        if n_both4 > 0:
            st.caption(
                f"ℹ️ **{n_both4:,} pacientes ({n_both4/total4*100:.1f}%)** "
                f"têm simultaneamente polifarmácia E carga anticolinérgica ≥ 3 — "
                f"o grupo de maior risco para revisão de prescrições."
            )

    st.markdown("---")

    # ── Filtros da lista ───────────────────────────────────────
    col_f1, col_f2 = st.columns([2, 2])
    with col_f1:
        apenas_idosos = st.toggle(
            "🧠 Mostrar apenas idosos com alerta ACB (≥65 anos, ACB ≥ 3)",
            value=False, key="poli_apenas_idosos"
        )
    with col_f2:
        cat_filtro = st.multiselect(
            "Filtrar por Categoria ACB",
            options=['MUITO_ALTO', 'ALTO', 'MODERADO', 'BAIXO'],
            default=['MUITO_ALTO', 'ALTO'],
            key="poli_cat_acb"
        )

    with st.spinner("Carregando lista de pacientes..."):
        df_lista = carregar_lista_pacientes(
            ap, clinica, esf, apenas_alerta_idoso=apenas_idosos
        )

    if df_lista.empty:
        st.warning("Nenhum paciente encontrado.")
    else:
        if cat_filtro:
            df_lista = df_lista[df_lista['categoria_acb'].isin(cat_filtro)]

        if df_lista.empty:
            st.warning("Nenhum paciente nas categorias selecionadas.")
        else:
            st.caption(f"**{len(df_lista):,} pacientes** exibidos na lista.")

            df_exib = df_lista.copy()

            if MODO_ANONIMO:
                df_exib['nome'] = df_exib.apply(
                    lambda r: anonimizar_nome(r['nome'], r.get('genero','')), axis=1
                )
                df_exib['nome_esf_cadastro']     = df_exib['nome_esf_cadastro'].apply(anonimizar_esf)
                df_exib['nome_clinica_cadastro']  = df_exib['nome_clinica_cadastro'].apply(anonimizar_clinica)

            df_exib['polifarmacia']      = df_exib['polifarmacia'].map({True: '💊 Sim', False: '—'})
            df_exib['hiperpolifarmacia'] = df_exib['hiperpolifarmacia'].map({True: '💊💊 Sim', False: '—'})
            df_exib['alerta_acb_idoso']  = df_exib['alerta_acb_idoso'].map({True: '🧠 Alerta', False: '—'})

            colunas = {
                'nome':                        'Paciente',
                'idade':                       'Idade',
                'nome_esf_cadastro':           'ESF',
                'charlson_categoria':          'Charlson',
                'total_medicamentos_cronicos': 'Total Meds',
                'polifarmacia':                'Polifarmácia',
                'hiperpolifarmacia':           'Hiperpolifarmácia',
                'acb_score_total':             'ACB Total',
                'n_meds_acb_alto':             'Meds anticolinérgicos fortes (score 3)',
                'categoria_acb':               'Categoria ACB',
                'alerta_acb_idoso':            'Alerta Idoso',
                'medicamentos_acb_positivos':  'Medicamentos ACB',
            }
            cols_ok = {k: v for k, v in colunas.items() if k in df_exib.columns}
            st.dataframe(
                df_exib[list(cols_ok.keys())].rename(columns=cols_ok),
                hide_index=True,
                use_container_width=True,
                height=500,
                column_config={
                    'Medicamentos ACB':                       st.column_config.TextColumn(width='large'),
                    'Meds anticolinérgicos fortes (score 3)': st.column_config.NumberColumn(
                        help="Número de medicamentos com score ACB = 3 (efeito anticolinérgico clinicamente relevante: ex. Quetiapina, Amitriptilina, Oxibutinina)"
                    ),
                }
            )

            csv = df_exib[list(cols_ok.keys())].rename(columns=cols_ok).to_csv(
                index=False, sep=';', encoding='utf-8-sig'
            )
            st.download_button(
                "⬇️ Baixar lista (.csv)", csv,
                "lista_polifarmacia_acb.csv", "text/csv"
            )

# ═══════════════════════════════════════════════════════════════
# RODAPÉ
# ═══════════════════════════════════════════════════════════════
st.markdown("---")
st.caption(
    "SMS-RJ | Navegador Clínico | Polifarmácia e Carga Anticolinérgica  |  "
    "Referência ACB: Boustani et al., *Aging Health* 2008;4(3):311–320"
)