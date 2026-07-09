"""
Page: Risco Cardiovascular
Panorama populacional do risco cardiovascular — Framingham+SBC e WHO 2019/HEARTS.
"""
import re
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from components.cabecalho import renderizar_cabecalho
from utils.bigquery_client import get_bigquery_client
from utils.data_loader import carregar_opcoes_filtros
from utils.anonimizador import (
    anonimizar_nome, anonimizar_ap, anonimizar_clinica,
    anonimizar_esf, mostrar_badge_anonimo, MODO_ANONIMO
)
import config
from utils import theme as T
from utils.risco_cv import (
    cor_categoria_who, cor_categoria_completa, icone_categoria_who,
    COR_CATEGORIA_HEARTS,
)
from pathlib import Path
from hearts import calcular_risco, col_mgdl_para_mmol

st.set_page_config(
    page_title="Risco Cardiovascular · Navegador Clínico",
    page_icon="❤️",
    layout="wide",
    initial_sidebar_state="expanded"
)


# Bloqueia acesso direto desta page para o perfil ESF.
# (ESF tem acesso restrito a Visao_ESF.py via aba 'Meus Pacientes'.)
from utils.auth import bloquear_perfil_esf
bloquear_perfil_esf()
# ═══════════════════════════════════════════════════════════════
# VERIFICAR LOGIN
# ═══════════════════════════════════════════════════════════════
if 'usuario_global' not in st.session_state or not st.session_state.usuario_global:
    st.warning("⚠️ Por favor, faça login na página inicial")
    st.stop()

usuario_logado = st.session_state['usuario_global']

renderizar_cabecalho("Risco CV")

from utils.auth import get_contexto_territorial
ctx = get_contexto_territorial()

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

        -- WHO calculado (categoria simplificada PAHO/HEARTS)
        COUNTIF(who_categoria_risco_simplificada IS NOT NULL) AS n_who_calculado,
        COUNTIF(who_categoria_risco_simplificada = 'Crítico')    AS n_who_gte30,
        COUNTIF(who_categoria_risco_simplificada = 'Muito alto') AS n_who_20_30,
        COUNTIF(who_categoria_risco_simplificada = 'Alto')       AS n_who_10_20,
        COUNTIF(who_categoria_risco_simplificada = 'Moderado')   AS n_who_5_10,
        COUNTIF(who_categoria_risco_simplificada = 'Baixo')      AS n_who_lt5,
        -- Crítico: por DCV estabelecida vs por fatores
        COUNTIF(who_categoria_risco_simplificada = 'Crítico'
                AND (CI IS NOT NULL OR stroke IS NOT NULL OR vascular_periferica IS NOT NULL)) AS n_who_gte30_dcv,
        COUNTIF(who_categoria_risco_simplificada = 'Crítico'
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
        COUNTIF(who_modelo_utilizado = 'nonlab') AS n_who_nonlab,

        -- Calculabilidade detalhada
        COUNTIF(idade BETWEEN 30 AND 74 AND framingham_calculavel = TRUE) AS n_fram_calculavel,
        COUNTIF(idade BETWEEN 30 AND 74 AND framingham_calculavel = FALSE) AS n_fram_nao_calculavel,
        COUNTIF(idade BETWEEN 40 AND 80 AND who_lab_calculavel = TRUE) AS n_who_lab_calculavel,
        COUNTIF(idade BETWEEN 40 AND 80 AND who_lab_calculavel = FALSE) AS n_who_lab_nao_calculavel,
        COUNTIF(idade BETWEEN 40 AND 80 AND who_nonlab_calculavel = TRUE) AS n_who_nonlab_calculavel,
        COUNTIF(idade BETWEEN 40 AND 80 AND who_nonlab_calculavel = FALSE) AS n_who_nonlab_nao_calculavel,

        -- Variáveis ausentes em elegíveis WHO (40-80)
        COUNTIF(idade BETWEEN 40 AND 80 AND colesterol_total IS NULL) AS n_who_sem_colesterol,
        COUNTIF(idade BETWEEN 40 AND 80 AND (pressao_sistolica IS NULL OR dias_desde_ultima_pa > 365)) AS n_who_sem_pa,
        COUNTIF(idade BETWEEN 40 AND 80 AND IMC IS NULL) AS n_who_sem_imc,

        -- Concordância entre modelos (quando ambos calculáveis)
        COUNTIF(categoria_risco_final = 'MUITO ALTO' AND who_categoria_risco_simplificada = 'Crítico') AS n_concordancia_muito_alto,
        COUNTIF(categoria_risco_final = 'BAIXO' AND who_categoria_risco_simplificada = 'Baixo')       AS n_concordancia_baixo

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
        -- WHO como % dos elegíveis (40-80a) do território (categoria simplificada)
        ROUND(COUNTIF(who_categoria_risco_simplificada = 'Crítico') * 100.0
              / NULLIF(COUNTIF(idade BETWEEN 40 AND 80), 0), 1) AS pct_who_gte30,
        ROUND(COUNTIF(who_categoria_risco_simplificada = 'Muito alto') * 100.0
              / NULLIF(COUNTIF(idade BETWEEN 40 AND 80), 0), 1) AS pct_who_20_30,
        ROUND(COUNTIF(who_categoria_risco_simplificada = 'Alto') * 100.0
              / NULLIF(COUNTIF(idade BETWEEN 40 AND 80), 0), 1) AS pct_who_10_20,
        ROUND(COUNTIF(who_categoria_risco_simplificada = 'Moderado') * 100.0
              / NULLIF(COUNTIF(idade BETWEEN 40 AND 80), 0), 1) AS pct_who_5_10,
        ROUND(COUNTIF(who_categoria_risco_simplificada = 'Baixo') * 100.0
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
# CARREGAR DADOS E ABAS
# ═══════════════════════════════════════════════════════════════
st.title("❤️ Risco Cardiovascular")
st.markdown("Panorama do risco cardiovascular na população e calculadora WHO HEARTS.")
st.markdown("---")

# Render preguiçoso: st.tabs renderizava as 2 abas em todo rerun
# (a do Panorama dispara queries pesadas). Trocado por
# segmented_control — só a aba selecionada executa.
_ABAS_RCV = ["📊 Panorama Populacional", "🧮 Calculadora HEARTS"]
_aba_rcv = st.segmented_control(
    "Seção", _ABAS_RCV, default=_ABAS_RCV[0],
    key="rcv_aba_ativa", label_visibility="collapsed",
)
if not _aba_rcv:
    _aba_rcv = _ABAS_RCV[0]

if _aba_rcv == "📊 Panorama Populacional":
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

  n_who_lab      = int(sumario.get('n_who_lab', 0) or 0)
  n_who_nonlab   = int(sumario.get('n_who_nonlab', 0) or 0)

  # Cards com alturas fixas: coluna 1 (tall) = 2× coluna 2/3 (small) + gap
  _H_SMALL = 130
  _H_TALL  = _H_SMALL * 2 + 16  # dois cards empilhados + gap do Streamlit

  def _card_html(titulo, valor, delta=None, caption=None, h=_H_SMALL):
      delta_html = (f"<div style='color:#09ab3b; font-size:0.85em; "
                    f"margin-top:4px;'>↑ {delta}</div>" if delta else "")
      cap_html = (f"<div style='color:{T.TEXT_MUTED}; font-size:0.8em; "
                  f"margin-top:6px;'>{caption}</div>" if caption else "")
      font_size = "2.5rem" if h > _H_SMALL else "2rem"
      return (
          f"<div style='border:1px solid {T.BORDER}; border-radius:8px; "
          f"padding:14px 16px; height:{h}px; box-sizing:border-box; "
          f"display:flex; flex-direction:column; justify-content:center; "
          f"background:{T.CARD_BG};'>"
          f"<div style='color:{T.TEXT_SECONDARY}; font-size:0.88em;'>{titulo}</div>"
          f"<div style='font-size:{font_size}; font-weight:500; "
          f"line-height:1.1; margin-top:4px; color:{T.TEXT};'>{valor}</div>"
          f"{delta_html}{cap_html}"
          f"</div>"
      )

  c1, c2, c3 = st.columns(3)
  with c1:
      st.markdown(_card_html("👥 População total", f"{tot:,}", h=_H_TALL),
                  unsafe_allow_html=True)
  with c2:
      st.markdown(_card_html(
          "📊 Elegíveis Framingham (30-74a)", f"{n_eleg_fram:,}",
          delta=f"{_p(n_eleg_fram, tot):.0f}% da população"
      ), unsafe_allow_html=True)
      st.markdown(_card_html(
          "🌍 Elegíveis WHO/HEARTS (40-80a)", f"{n_eleg_who:,}",
          delta=f"{_p(n_eleg_who, tot):.0f}% da população"
      ), unsafe_allow_html=True)
  with c3:
      st.markdown(_card_html(
          "📊 Framingham+SBC calculado", f"{n_fram_calc:,}",
          delta=f"{_p(n_fram_calc, n_eleg_fram):.0f}% dos elegíveis (30-74a)"
      ), unsafe_allow_html=True)
      st.markdown(_card_html(
          "🌍 WHO/HEARTS calculado", f"{n_who_calc:,}",
          delta=f"{_p(n_who_calc, n_eleg_who):.0f}% dos elegíveis (40-80a)",
          caption=f"Versão laboratorial: {n_who_lab:,} · Versão não-laboratorial: {n_who_nonlab:,}"
      ), unsafe_allow_html=True)

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

  # Calculabilidade detalhada
  st.markdown("##### Calculabilidade dos modelos")

  n_fram_calculavel     = int(sumario.get('n_fram_calculavel', 0) or 0)
  n_fram_nao_calculavel = int(sumario.get('n_fram_nao_calculavel', 0) or 0)
  n_who_lab_calc        = int(sumario.get('n_who_lab_calculavel', 0) or 0)
  n_who_lab_nao         = int(sumario.get('n_who_lab_nao_calculavel', 0) or 0)
  n_who_nonlab_calc     = int(sumario.get('n_who_nonlab_calculavel', 0) or 0)
  n_who_nonlab_nao      = int(sumario.get('n_who_nonlab_nao_calculavel', 0) or 0)

  cc1, cc2, cc3 = st.columns(3)
  with cc1:
      with st.container(border=True):
          st.markdown("**Framingham (30-74a)**")
          st.metric("Calculável", f"{n_fram_calculavel:,}",
                    f"{_p(n_fram_calculavel, n_eleg_fram):.0f}% dos elegíveis")
          st.caption(f"Não calculável: {n_fram_nao_calculavel:,}")
  with cc2:
      with st.container(border=True):
          st.markdown("**WHO (versão laboratorial) — 40-80a**")
          st.metric("Calculável", f"{n_who_lab_calc:,}",
                    f"{_p(n_who_lab_calc, n_eleg_who):.0f}% dos elegíveis")
          st.caption(f"Não calculável: {n_who_lab_nao:,}")
  with cc3:
      with st.container(border=True):
          st.markdown("**WHO (versão não-laboratorial) — 40-80a**")
          st.metric("Calculável", f"{n_who_nonlab_calc:,}",
                    f"{_p(n_who_nonlab_calc, n_eleg_who):.0f}% dos elegíveis")
          st.caption(f"Não calculável: {n_who_nonlab_nao:,}")

  # Variáveis ausentes — ranking
  st.markdown("##### Variáveis ausentes nos elegíveis")

  n_fram_sem_col = int(sumario.get('n_fram_sem_colesterol', 0) or 0)
  n_fram_sem_hdl = int(sumario.get('n_fram_sem_hdl', 0) or 0)
  n_fram_sem_pa  = int(sumario.get('n_fram_sem_pa', 0) or 0)
  n_who_sem_col  = int(sumario.get('n_who_sem_colesterol', 0) or 0)
  n_who_sem_pa   = int(sumario.get('n_who_sem_pa', 0) or 0)
  n_who_sem_imc  = int(sumario.get('n_who_sem_imc', 0) or 0)

  va1, va2 = st.columns(2)
  with va1:
      with st.container(border=True):
          st.markdown("**Framingham (30-74a) — o que falta**")
          ausentes_fram = [
              (f"Colesterol total", n_fram_sem_col, _p(n_fram_sem_col, n_eleg_fram)),
              (f"HDL", n_fram_sem_hdl, _p(n_fram_sem_hdl, n_eleg_fram)),
              (f"PA recente (≤365d)", n_fram_sem_pa, _p(n_fram_sem_pa, n_eleg_fram)),
          ]
          for label, n, pct in sorted(ausentes_fram, key=lambda x: -x[1]):
              st.markdown(f"🔴 **{label}**: {n:,} ({pct:.0f}% dos elegíveis)")
  with va2:
      with st.container(border=True):
          st.markdown("**WHO (40-80a) — o que falta para versão laboratorial**")
          ausentes_who = [
              (f"Colesterol total", n_who_sem_col, _p(n_who_sem_col, n_eleg_who)),
              (f"PA recente (≤365d)", n_who_sem_pa, _p(n_who_sem_pa, n_eleg_who)),
              (f"IMC (usado na versão não-laboratorial)", n_who_sem_imc, _p(n_who_sem_imc, n_eleg_who)),
          ]
          for label, n, pct in sorted(ausentes_who, key=lambda x: -x[1]):
              st.markdown(f"🔴 **{label}**: {n:,} ({pct:.0f}% dos elegíveis)")

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

  # Cabeçalhos
  h_f, h_w = st.columns(2)
  with h_f:
      st.markdown(f"**Framingham + SBC** (n={n_fram_calc:,})")
  with h_w:
      st.markdown(f"**WHO 2019 / HEARTS** (n={n_who_calc:,})")

  def _card(label, n, cor, detalhe, total):
      if label is None:
          # Spacer invisível com altura equivalente a card com detalhe
          st.markdown(
              "<div style='padding:8px 12px; margin:4px 0; "
              "visibility:hidden;'>—<br><span style='font-size:0.85em;'>—</span></div>",
              unsafe_allow_html=True
          )
          return
      pct = _p(n, total) if total else 0
      # Reserva sempre a altura da linha de detalhe para manter os pares
      # (ex.: MUITO ALTO ↔ Muito alto) alinhados horizontalmente entre as colunas.
      if detalhe:
          det_html = f"<br><span style='font-size:0.85em; color:#666;'>{detalhe}</span>"
      else:
          det_html = "<br><span style='font-size:0.85em; visibility:hidden;'>—</span>"
      st.markdown(
          f"<div style='background:{cor}20; border-left:4px solid {cor}; "
          f"padding:8px 12px; margin:4px 0; border-radius:4px;'>"
          f"<strong>{label}</strong>: {n:,} ({pct:.0f}%){det_html}</div>",
          unsafe_allow_html=True
      )

  # Pares emparelhados por faixa de risco
  linhas = [
      # (Framingham side, WHO side)
      (None,
       ("🔴 Crítico (≥30%)", n_who_gte30, "#7B0000",
        f"DCV estabelecida: {n_who_gte30_dcv:,} · Por fatores: {n_who_gte30_fat:,}")),
      (("MUITO ALTO (>20%)", n_fram_ma, "#C0392B",
        f"DCV estabelecida: {n_fram_ma_dcv:,} · Por fatores: {n_fram_ma_fat:,}"),
       ("🔴 Muito alto (20-30%)", int(sumario.get('n_who_20_30', 0) or 0), "#F44336", None)),
      (("ALTO (10-20%)", int(sumario.get('n_fram_alto', 0) or 0), "#E74C3C", None),
       ("🟠 Alto (10-20%)", int(sumario.get('n_who_10_20', 0) or 0), "#FF9800", None)),
      (("INTERMEDIÁRIO (5-10%)", int(sumario.get('n_fram_intermediario', 0) or 0), "#F39C12", None),
       ("🟡 Moderado (5-10%)", int(sumario.get('n_who_5_10', 0) or 0), "#FFEB3B", None)),
      (("BAIXO (<5%)", int(sumario.get('n_fram_baixo', 0) or 0), "#2ECC71", None),
       ("🟢 Baixo (<5%)", int(sumario.get('n_who_lt5', 0) or 0), "#4CAF50", None)),
  ]
  for linha_f, linha_w in linhas:
      r_f, r_w = st.columns(2)
      with r_f:
          if linha_f is None:
              _card(None, None, None, None, None)
          else:
              _card(*linha_f, total=n_fram_calc)
      with r_w:
          _card(*linha_w, total=n_who_calc)


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
              yaxis=dict(title='% dos elegíveis', tickfont=dict(color=T.TEXT_MUTED, size=10),
                         gridcolor=T.GRID, range=[0, 75]),
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
              ['Crítico', 'Muito alto', 'Alto', 'Moderado', 'Baixo'],
              ['#7B0000', '#F44336', '#FF9800', '#FFEB3B', '#4CAF50'],
              f'WHO 2019 / HEARTS por {lbl}',
          )

  # ═══════════════════════════════════════════════════════════════
# ═══════════════════════════════════════════════════════════════
# ABA 2 — CALCULADORA HEARTS
# ═══════════════════════════════════════════════════════════════

if _aba_rcv == "🧮 Calculadora HEARTS":

    # ── Helpers da calculadora. Toda a lógica clínica vem de hearts.calcular_risco. ──
    _MODELO_LBL = {'lab': 'Versão laboratorial', 'nonlab': 'Versão não-laboratorial'}

    def _dot_hearts(r, dcv, modelo, sexo_lbl, idade):
        """Fluxograma da cascata real, destacando o caminho do caso atual.
        DCV = ramo duro (curto-circuita para Muito alto). DRC/DM = piso que eleva
        o nó de resultado (não desviam o cálculo)."""
        motivo = r['motivo_override']
        piso_ativo = (not dcv) and motivo is not None            # DM/DRC elevaram a categoria
        cat_final = r['categoria']
        risco_txt = f"{r['risco_cvd'] * 100:.1f}%"

        if dcv:
            caminho = ['paciente', 'q_dcv', 'r_muito_alto']
        else:
            caminho = ['paciente', 'q_dcv', 'q_col',
                       'm_lab' if modelo == 'lab' else 'm_nonlab',
                       'escore', 'q_drcdm', 'resultado']
        ativos = set(caminho)
        pares = set(zip(caminho, caminho[1:]))

        nodes = {
            'paciente':     ('box',     f"Paciente\\n{sexo_lbl}, {idade} anos", None),
            'q_dcv':        ('diamond', "DCV estabelecida?", None),
            'r_muito_alto': ('box',     "Muito alto\\n(override por DCV)", 'Muito alto'),
            'q_col':        ('diamond', "Conhece o\\ncolesterol?", None),
            'm_lab':        ('box',     "Modelo laboratorial\\n(com colesterol)", None),
            'm_nonlab':     ('box',     "Modelo não-laboratorial\\n(com IMC)", None),
            'escore':       ('box',     "Escore CVD calibrado\\n(Tropical LA)", None),
            'q_drcdm':      ('diamond', "DRC ou DM?", None),
            'resultado':    ('box',     f"{risco_txt} → {cat_final}", cat_final),
        }

        def _node(nid):
            shape, label, cat = nodes[nid]
            box_style = "rounded,filled" if shape == 'box' else "filled"
            if nid in ativos and cat is not None:              # terminal ativo → cor da categoria
                c = COR_CATEGORIA_HEARTS.get(cat, '#9E9E9E')
                return (f'  {nid} [shape={shape} style="{box_style}" fillcolor="{c}" '
                        f'color="{c}" fontcolor="white" penwidth=2 label="{label}"];')
            if nid in ativos:                                  # etapa/decisão ativa → destaque azul
                return (f'  {nid} [shape={shape} style="{box_style}" fillcolor="#E8F0FE" '
                        f'color="#4f8ef7" fontcolor="#1a1a2e" penwidth=2 label="{label}"];')
            return (f'  {nid} [shape={shape} style="{box_style}" fillcolor="#F5F5F5" '   # inativo → esmaecido
                    f'color="#D0D0D0" fontcolor="#B0B0B0" penwidth=1 label="{label}"];')

        piso_lbl = "piso ≥ Alto" if piso_ativo else "sem piso"
        edges = [
            ('paciente', 'q_dcv', None),
            ('q_dcv', 'r_muito_alto', 'Sim'), ('q_dcv', 'q_col', 'Não'),
            ('q_col', 'm_lab', 'Sim'),        ('q_col', 'm_nonlab', 'Não'),
            ('m_lab', 'escore', None), ('m_nonlab', 'escore', None),
            ('escore', 'q_drcdm', None),
            ('q_drcdm', 'resultado', piso_lbl),
        ]

        def _edge(a, b, lbl):
            on = (a, b) in pares
            cor = "#333333" if on else "#D5D5D5"
            fc = "#333333" if on else "#C0C0C0"
            pw = 2.5 if on else 1.0
            l = f' label="{lbl}" fontcolor="{fc}" fontsize=9' if lbl else ''
            return f'  {a} -> {b} [color="{cor}" penwidth={pw}{l}];'

        corpo = "\n".join(_node(n) for n in nodes)
        corpo += "\n" + "\n".join(_edge(*e) for e in edges)
        return ('digraph hearts {\n  rankdir=TB;\n  bgcolor="transparent";\n'
                '  ranksep=0.30;\n  nodesep=0.24;\n  size="4.2,6";\n  ratio="compress";\n'
                '  node [fontname="Helvetica" fontsize=10 margin="0.16,0.05"];\n'
                '  edge [fontname="Helvetica" fontsize=9];\n' + corpo + '\n}')

    def _legenda_categorias():
        faixas = [('Baixo', '<5%'), ('Moderado', '5–10%'), ('Alto', '10–20%'),
                  ('Muito alto', '20–30%'), ('Crítico', '≥30%')]
        chips = "".join(
            f"<span style='display:inline-flex; align-items:center; gap:5px; "
            f"margin:2px 12px 2px 0; font-size:0.78rem; color:{T.TEXT_SECONDARY};'>"
            f"<span style='width:12px; height:12px; border-radius:3px; "
            f"background:{COR_CATEGORIA_HEARTS[c]}; display:inline-block;'></span>"
            f"{c} ({fx})</span>"
            for c, fx in faixas
        )
        st.markdown(
            f"<div style='margin:2px 0 6px 0; line-height:1.9;'>{chips}</div>",
            unsafe_allow_html=True,
        )

    def _whatif_row(titulo, kw, base_pct):
        """Recalcula um cenário 'e se…' pelo motor e mostra novo escore + variação."""
        rr = calcular_risco(**kw)
        novo = rr['risco_cvd'] * 100
        delta = base_pct - novo                         # positivo = redução (bom)
        corcat = COR_CATEGORIA_HEARTS.get(rr['categoria'], '#9E9E9E')
        if delta >= 0.05:
            dcor, dtxt = '#2E7D32', f"↓ {delta:.1f} pp"
        elif delta <= -0.05:
            dcor, dtxt = '#C62828', f"↑ {abs(delta):.1f} pp"
        else:
            dcor, dtxt = T.TEXT_MUTED, "≈ igual"
        st.markdown(
            f"<div style='border:1px solid {T.BORDER}; border-radius:8px; padding:9px 12px; margin-bottom:8px;'>"
            f"<div style='font-size:0.88rem; color:{T.TEXT}; margin-bottom:3px;'>{titulo}</div>"
            f"<div style='display:flex; align-items:baseline; gap:8px;'>"
            f"<span style='font-size:1.45rem; font-weight:700; color:{corcat};'>{novo:.1f}%</span>"
            f"<span style='font-weight:600; color:{dcor}; font-size:0.85rem;'>{dtxt}</span></div>"
            f"<div style='font-size:0.72rem; color:{T.TEXT_MUTED};'>→ {rr['categoria']}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )

    def _card_resultado(r):
        cat = r['categoria']
        cor = COR_CATEGORIA_HEARTS.get(cat, '#9E9E9E')
        risco_txt = f"{r['risco_cvd'] * 100:.1f}%"
        motivo = r['motivo_override']
        badge_txt = cat if not motivo else f"{cat} — por {motivo}"
        override_html = ""
        if motivo and r['categoria'] != r['categoria_escore']:
            override_html = (
                f"<div style='color:{T.TEXT_SECONDARY}; margin-top:8px; font-size:0.85rem;'>"
                f"O escore indica <strong>{r['categoria_escore']}</strong>; a classificação sobe "
                f"para <strong>{cat}</strong> por regra clínica ({motivo}).</div>")
        modelo_lbl = _MODELO_LBL.get(r['modelo'], r['modelo'])
        st.markdown(
            f"<div style='border:1px solid {cor}; border-left:8px solid {cor}; "
            f"border-radius:10px; padding:16px 20px; margin-top:4px; background:{cor}12;'>"
            f"<div style='color:{T.TEXT_MUTED}; font-size:0.74rem; text-transform:uppercase; "
            f"letter-spacing:0.04em;'>Escore HEARTS · Tropical LA</div>"
            f"<div style='font-size:2.4rem; font-weight:700; color:{cor}; line-height:1.1;'>{risco_txt}</div>"
            f"<div style='color:{T.TEXT_SECONDARY}; font-size:0.82rem;'>risco de evento cardiovascular "
            f"(infarto ou AVC) em 10 anos</div>"
            f"<div style='display:inline-block; margin-top:12px; background:{cor}; color:white; "
            f"padding:3px 14px; border-radius:20px; font-weight:600; font-size:0.95rem;'>{badge_txt}</div>"
            f"{override_html}"
            f"<div style='color:{T.TEXT}; margin-top:12px; font-size:0.95rem;'>{r['conduta']}</div>"
            f"<div style='color:{T.TEXT_MUTED}; margin-top:8px; font-size:0.8rem;'>Modelo: {modelo_lbl}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )

    st.markdown("### 🧮 Calculadora de Risco Cardiovascular — WHO HEARTS 2019")
    st.caption(
        "Modelo WHO 2019 (Kaptoge) recalibrado para a América Latina tropical contra o app da OPAS. "
        "Preencha os dados à esquerda — o caminho de decisão é destacado ao vivo à direita."
    )
    st.markdown("")

    col_in, col_mid, col_wi = st.columns([1.05, 1.05, 0.9], gap="large")

    # ── Coluna de entrada — fluxo igual à OPAS ──
    with col_in:
        with st.container(border=True):
            st.markdown("**1 · Condições de base**")
            st.caption("Gatilhos que reclassificam por regra clínica, por cima do escore.")
            calc_dcv = st.checkbox(
                "DCV estabelecida (IAM, AVC ou DAP prévios)", value=False, key="calc_dcv",
                help="Curto-circuita para Muito alto; o escore é mostrado só como referência.")
            calc_drc = st.checkbox(
                "Doença renal crônica (DRC)", value=False, key="calc_irc",
                help="Eleva a categoria para ao menos Alto (PCDT HAS).")
            calc_dm = st.checkbox(
                "Diabetes (ou pré-diabetes)", value=False, key="calc_dm",
                help="Na via laboratorial entra no escore e eleva para ao menos Alto. "
                     "Pré-diabetes é tratada de forma conservadora como diabetes.")

        with st.container(border=True):
            st.markdown("**2 · Dados do paciente**")
            d1, d2 = st.columns(2)
            with d1:
                calc_sexo = st.selectbox("Sexo", options=["Masculino", "Feminino"], key="calc_sexo")
                calc_pas = st.number_input(
                    "PA sistólica (mmHg)", min_value=90, max_value=200, value=130, key="calc_pas",
                    help="Média das medidas mais recentes de PA sistólica.")
            with d2:
                calc_idade = st.number_input(
                    "Idade (anos)", min_value=40, max_value=75, value=55, key="calc_idade",
                    help="Válido de 40 a 74 anos; 75 é tratado como 74 (como a OPAS).")
                _tabaco_sel = st.segmented_control(
                    "Tabagismo", options=["Não fuma", "Fumante"], default="Não fuma",
                    key="calc_tabaco_seg")
                calc_tabaco = (_tabaco_sel == "Fumante")

        with st.container(border=True):
            st.markdown("**3 · Colesterol**")
            conhece_col = st.radio(
                "Conhece o colesterol total?", options=["Sim", "Não"],
                horizontal=True, key="calc_conhece_col")
            if conhece_col == "Sim":
                calc_col = st.number_input(
                    "Colesterol total (mg/dL)", min_value=140, max_value=300, value=200, key="calc_col")
                calc_peso = calc_altura = None
            else:
                p1, p2 = st.columns(2)
                with p1:
                    calc_peso = st.number_input(
                        "Peso (kg)", min_value=50.0, max_value=230.0, value=70.0, step=0.5, key="calc_peso")
                with p2:
                    calc_altura = st.number_input(
                        "Altura (cm)", min_value=140.0, max_value=230.0, value=165.0, step=1.0, key="calc_altura")
                calc_col = None
                if calc_dm:
                    st.caption(
                        "ℹ️ Sem colesterol, a diabetes **não altera o escore** (o modelo WHO não-laboratorial "
                        "não tem termo de diabetes); ela reclassifica pelo PCDT (→ ao menos Alto).")

    # ── Cálculo: fonte única de verdade é hearts.calcular_risco ──
    sexo_api = "male" if calc_sexo == "Masculino" else "female"
    if conhece_col == "Sim":
        modelo = "lab"
        imc_val = None
        r = calcular_risco(sexo_api, calc_idade, calc_pas, calc_tabaco,
                           colesterol_mmol=col_mgdl_para_mmol(calc_col),
                           diabetes=calc_dm, dcv_estabelecida=calc_dcv, drc=calc_drc)
    else:
        modelo = "nonlab"
        imc_val = calc_peso / (calc_altura / 100.0) ** 2
        r = calcular_risco(sexo_api, calc_idade, calc_pas, calc_tabaco,
                           imc=imc_val, diabetes=calc_dm, dcv_estabelecida=calc_dcv, drc=calc_drc)

    # ── Coluna do meio — fluxograma + legenda ──
    with col_mid:
        if modelo == "nonlab":
            st.info(f"Via **não-laboratorial** (IMC {imc_val:.1f} kg/m²) — sem colesterol informado.")
        else:
            st.caption("Via **laboratorial** (com colesterol).")
        if int(r['idade_usada']) != int(calc_idade):
            st.caption(f"Idade {int(calc_idade)} tratada como {int(r['idade_usada'])} (topo da faixa, como a OPAS).")

        st.graphviz_chart(
            _dot_hearts(r, calc_dcv, modelo,
                        "Masculino" if sexo_api == "male" else "Feminino", int(r['idade_usada'])),
            use_container_width=False)
        _legenda_categorias()

    # ── Coluna 3 — "O que aconteceria se…" ──
    with col_wi:
        st.markdown("**O que aconteceria se…**")
        st.caption("Efeito no escore de mudanças nos fatores modificáveis.")
        base_pct = r['risco_cvd'] * 100
        base_kwargs = dict(
            sexo=sexo_api, idade=calc_idade, pas=calc_pas, fumante=calc_tabaco,
            diabetes=calc_dm, dcv_estabelecida=calc_dcv, drc=calc_drc,
        )
        if modelo == 'lab':
            base_kwargs['colesterol_mmol'] = col_mgdl_para_mmol(calc_col)
        else:
            base_kwargs['imc'] = imc_val

        cenarios = []
        if calc_tabaco:
            cenarios.append(("🚭 Parar de fumar", {**base_kwargs, 'fumante': False}))
        if modelo == 'lab' and calc_col > 190:
            cenarios.append(("🧪 Colesterol a 190 mg/dL",
                             {**base_kwargs, 'colesterol_mmol': col_mgdl_para_mmol(190)}))
        if calc_pas > 130:
            cenarios.append(("🩺 PA sistólica a 130 mmHg", {**base_kwargs, 'pas': 130}))
        if modelo == 'nonlab' and imc_val > 25:
            cenarios.append(("⚖️ IMC a 25 kg/m²", {**base_kwargs, 'imc': 25.0}))
        if len(cenarios) >= 2:
            combo = dict(base_kwargs)
            if calc_tabaco:
                combo['fumante'] = False
            if modelo == 'lab' and calc_col > 190:
                combo['colesterol_mmol'] = col_mgdl_para_mmol(190)
            if calc_pas > 130:
                combo['pas'] = 130
            if modelo == 'nonlab' and imc_val > 25:
                combo['imc'] = 25.0
            cenarios.append(("✨ Tudo combinado", combo))

        if not cenarios:
            st.success("Fatores de risco modificáveis já otimizados.")
        else:
            for titulo, kw in cenarios:
                _whatif_row(titulo, kw, base_pct)
            if calc_dcv:
                st.caption("Com DCV estabelecida, a categoria final permanece **Muito alto**; "
                           "os valores acima são o risco basal (escore).")
            elif calc_dm or calc_drc:
                st.caption("A categoria tem piso **Alto** por regra clínica: o escore pode cair "
                           "abaixo disso, mas a categoria final não.")

    # ── Resultado em largura total, abaixo das três colunas ──
    _card_resultado(r)
    st.markdown("")

    with st.expander("Dados usados no cálculo"):
        st.markdown(f"""
| Variável | Valor |
|---|---|
| Sexo | {calc_sexo} |
| Idade usada | {int(r['idade_usada'])} anos |
| PAS | {int(calc_pas)} mmHg |
| Tabagismo | {'Sim' if calc_tabaco else 'Não'} |
| Via | {_MODELO_LBL[modelo]} |
| Colesterol total | {'—' if calc_col is None else f'{calc_col} mg/dL ({col_mgdl_para_mmol(calc_col):.2f} mmol/L)'} |
| IMC | {'—' if imc_val is None else f'{imc_val:.1f} kg/m²'} |
| Diabetes | {'Sim' if calc_dm else 'Não'} |
| DRC | {'Sim' if calc_drc else 'Não'} |
| DCV estabelecida | {'Sim' if calc_dcv else 'Não'} |
| Escore CVD | {r['risco_cvd'] * 100:.1f}% |
| Categoria pelo escore | {r['categoria_escore']} |
| Categoria final | {r['categoria']} |
| Motivo do override | {r['motivo_override'] or '—'} |
""")

    # ── Sobre o HEARTS (conteúdo versionado em sobre_hearts.md) ──
    with st.expander("Sobre o HEARTS"):
        _p_sobre = Path(__file__).resolve().parent.parent / "sobre_hearts.md"
        if _p_sobre.exists():
            st.markdown(_p_sobre.read_text(encoding="utf-8"))
        else:
            st.caption("Conteúdo em preparação (`sobre_hearts.md` não encontrado).")

    with st.expander("Referências e metodologia"):
        st.markdown("""
    **WHO CVD Risk Charts 2019** — Kaptoge S et al. *Lancet Global Health* 2019;7(10):e1332-e1345.
    - Coeficientes: Tabela 1.6 do suplemento WHO 2019 (versões laboratorial e não-laboratorial).
    - **Recalibração** afim do risco CVD combinado contra o app da OPAS, região **Tropical Latin America**
      (erro < 0,65pp), estratificada por sexo, via e tabagismo.
    - **Overlay clínico** (PCDT HAS): DCV estabelecida → Muito alto; DRC ou diabetes → ao menos Alto.
        """)

    # ═══════════════════════════════════════════════════════════════
    # RODAPÉ
    # ═══════════════════════════════════════════════════════════════
    st.markdown("---")
    st.caption(
        "Motor: hearts.py — WHO 2019 (Kaptoge) recalibrado para Tropical Latin America. "
        "Overlay clínico: PCDT HAS / Diretriz SBC."
    )
