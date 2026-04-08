"""
Página: Minha População
Visão agregada — pirâmides, prevalências e carga de doenças.
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from utils.bigquery_client import get_bigquery_client
from components.cabecalho import renderizar_cabecalho
from utils.auth import get_contexto_territorial, get_perfil
from components.filtros import filtros_territoriais
from utils import theme as T
import config
import math
from utils.anonimizador import (
    anonimizar_ap, anonimizar_clinica, anonimizar_esf,
    anonimizar_nome, mostrar_badge_anonimo, MODO_ANONIMO
)


st.set_page_config(
    page_title="Minha População - Navegador Clínico",
    page_icon="👥",
    layout="wide",
    initial_sidebar_state="expanded"
)

# CABEÇALHO UNIFICADO
renderizar_cabecalho("População")

# CONTEXTO TERRITORIAL
ctx    = get_contexto_territorial()
perfil = get_perfil()


# ============================================
# FUNÇÕES DE CARGA DE DADOS
# ============================================

def _fqn(name: str) -> str:
    return f"{config.PROJECT_ID}.{config.DATASET_ID}.{name}"



# ✅ MUDAR TTL=600 PARA TTL=1 (ou comentar o cache completamente)
@st.cache_data(show_spinner=False, ttl=900)
def carregar_dados_charlson_territorio(ap=None, clinica=None, esf=None):
    """
    Retorna 1 linha por território com indicadores de carga de morbidade (Charlson).
    Nível: sem filtro→clínicas/AP; AP→ESFs/clínica; clínica→ESFs/ESF.
    Denominador = total de pacientes do território.
    """
    if clinica:
        grupo_col = "ESF"
        grupo_x   = "ESF"
    elif ap:
        grupo_col = "ESF"
        grupo_x   = "clinica_familia"
    else:
        grupo_col = "clinica_familia"
        grupo_x   = "area_programatica"

    clauses = []
    if ap:      clauses.append(f"area_programatica = '{ap}'")
    if clinica: clauses.append(f"clinica_familia = '{clinica}'")
    if esf:     clauses.append(f"ESF = '{esf}'")
    where_sql = ("WHERE " + " AND ".join(clauses)) if clauses else ""

    sql = f"""
    SELECT
        {grupo_col}                                                     AS territorio,
        {grupo_x}                                                       AS grupo_x,
        SUM(total_pacientes)                                            AS total_pop,
        SUM(n_multimorbidos)                                            AS n_multimorbidos,
        -- Categorias Charlson (denominador = total de pacientes)
        SAFE_DIVIDE(SUM(n_charlson_muito_alto),
            NULLIF(SUM(total_pacientes), 0)) * 100                     AS pct_muito_alto,
        SAFE_DIVIDE(SUM(n_charlson_alto),
            NULLIF(SUM(total_pacientes), 0)) * 100                     AS pct_alto,
        SAFE_DIVIDE(SUM(n_charlson_moderado),
            NULLIF(SUM(total_pacientes), 0)) * 100                     AS pct_moderado,
        SAFE_DIVIDE(SUM(n_charlson_baixo),
            NULLIF(SUM(total_pacientes), 0)) * 100                     AS pct_baixo,
        -- Multimorbidade
        SAFE_DIVIDE(SUM(n_multimorbidos),
            NULLIF(SUM(total_pacientes), 0)) * 100                     AS pct_multimorbidos,
        -- Absolutos
        SUM(n_charlson_muito_alto)   AS n_muito_alto,
        SUM(n_charlson_alto)         AS n_alto,
        SUM(n_charlson_moderado)     AS n_moderado,
        SUM(n_charlson_baixo)        AS n_baixo
    FROM `rj-sms-sandbox.sub_pav_us.MM_piramides_populacionais`
    {where_sql}
    GROUP BY {grupo_col}, {grupo_x}
    ORDER BY {grupo_x}, {grupo_col}
    """
    try:
        client = get_bigquery_client()
        df = client.query(sql).result().to_dataframe(create_bqstorage_client=False)
        return df if not df.empty else pd.DataFrame()
    except Exception as e:
        st.error(f"❌ Erro ao carregar dados de carga de morbidade: {e}")
        return pd.DataFrame()


@st.cache_data(show_spinner=False, ttl=900)
def carregar_dados_farmaco_territorio(ap=None, clinica=None, esf=None):
    """
    Retorna 1 linha por clínica (sem filtro ou com AP) ou por ESF (com clínica filtrada).
    Inclui área_programatica para agrupamento no eixo X do violino.
    Denominador = multimórbidos do território.
    """
    if clinica:
        # Clínica filtrada — pontos = ESFs, eixo X = ESF (apenas pontos)
        grupo_col  = "ESF"
        grupo_x    = "ESF"
        label_col  = "ESF"
    elif ap:
        # AP filtrada — pontos = ESFs, eixo X = clínica (1 violino por clínica)
        grupo_col  = "ESF"
        grupo_x    = "clinica_familia"
        label_col  = "ESF"
    else:
        # Sem filtro — pontos = clínicas, eixo X = AP (1 violino por AP)
        grupo_col  = "clinica_familia"
        grupo_x    = "area_programatica"
        label_col  = "Clínica"

    clauses = []
    if ap:      clauses.append(f"area_programatica = '{ap}'")
    if clinica: clauses.append(f"clinica_familia = '{clinica}'")
    if esf:     clauses.append(f"ESF = '{esf}'")
    where_sql = ("WHERE " + " AND ".join(clauses)) if clauses else ""

    sql = f"""
    SELECT
        {grupo_col}                                                     AS territorio,
        {grupo_x}                                                       AS grupo_x,
        '{label_col}'                                                   AS label_col,
        SUM(total_pacientes)                                            AS total_pop,
        SUM(n_multimorbidos)                                            AS n_multimorbidos,
        -- Usa colunas _mm: contagem já restrita a multimórbidos na tabela de pirâmides
        -- Garante denominador = multimórbidos e numerador ⊆ multimórbidos → nunca >100%
        SAFE_DIVIDE(SUM(n_polifarmacia_mm),
            NULLIF(SUM(n_multimorbidos), 0)) * 100                     AS pct_poli_mm,
        SAFE_DIVIDE(SUM(n_hiperpolifarmacia_mm),
            NULLIF(SUM(n_multimorbidos), 0)) * 100                     AS pct_hiperpoli_mm,
        SAFE_DIVIDE(SUM(n_acb_alto_mm),
            NULLIF(SUM(n_multimorbidos), 0)) * 100                     AS pct_acb_alto_mm,
        SAFE_DIVIDE(SUM(n_acb_alerta_idoso_mm),
            NULLIF(SUM(n_multimorbidos), 0)) * 100                     AS pct_acb_idoso_mm,
        SAFE_DIVIDE(SUM(n_com_stopp_ativo_mm),
            NULLIF(SUM(n_multimorbidos), 0)) * 100                     AS pct_stopp_mm,
        SAFE_DIVIDE(SUM(n_com_omissao_start_mm),
            NULLIF(SUM(n_multimorbidos), 0)) * 100                     AS pct_start_mm,
        SAFE_DIVIDE(SUM(n_com_beers_ativo_mm),
            NULLIF(SUM(n_multimorbidos), 0)) * 100                     AS pct_beers_mm,
        SAFE_DIVIDE(SUM(n_risco_queda_meds_mm),
            NULLIF(SUM(n_multimorbidos), 0)) * 100                     AS pct_queda_mm,
        SUM(n_polifarmacia)          AS n_poli,
        SUM(n_hiperpolifarmacia)     AS n_hiperpoli,
        SUM(n_acb_alto)              AS n_acb_alto,
        SUM(n_acb_alerta_idoso)      AS n_acb_idoso,
        SUM(n_com_stopp_ativo)       AS n_stopp,
        SUM(n_com_omissao_start)     AS n_start,
        SUM(n_com_beers_ativo)       AS n_beers,
        SUM(n_risco_queda_meds)      AS n_queda
    FROM `rj-sms-sandbox.sub_pav_us.MM_piramides_populacionais`
    {where_sql}
    GROUP BY {grupo_col}, {grupo_x}
    ORDER BY {grupo_x}, {grupo_col}
    """
    try:
        client = get_bigquery_client()
        df = client.query(sql).result().to_dataframe(create_bqstorage_client=False)
        return df if not df.empty else pd.DataFrame()
    except Exception as e:
        st.error(f"❌ Erro ao carregar dados farmacológicos: {e}")
        return pd.DataFrame()


@st.cache_data(show_spinner=False, ttl=1)  # ← MUDAR DE 600 PARA 1
def carregar_dados_piramides(ap=None, clinica=None, esf=None):
    """Carrega dados agregados - COM AGREGAÇÃO NO BIGQUERY"""
    
    where_clauses = []
    if ap:
        where_clauses.append(f"area_programatica = '{ap}'")
    if clinica:
        where_clauses.append(f"clinica_familia = '{clinica}'")
    if esf:
        where_clauses.append(f"ESF = '{esf}'")
    
    where_sql = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""
    
    # SELECT * com SUM de todas as colunas numéricas via EXCEPT nas chaves
    # Assim qualquer nova coluna adicionada à tabela aparece automaticamente
    sql = f"""
    SELECT
        faixa_etaria,
        genero,
        SUM(total_pacientes) AS total_pacientes,
        SUM(n_morb_0) AS n_morb_0, SUM(n_morb_1) AS n_morb_1,
        SUM(n_morb_2) AS n_morb_2, SUM(n_morb_3) AS n_morb_3,
        SUM(n_morb_4) AS n_morb_4, SUM(n_morb_5) AS n_morb_5,
        SUM(n_morb_6) AS n_morb_6, SUM(n_morb_7) AS n_morb_7,
        SUM(n_morb_8) AS n_morb_8, SUM(n_morb_9) AS n_morb_9,
        SUM(n_morb_10mais) AS n_morb_10mais,
        SUM(n_multimorbidos) AS n_multimorbidos,
        SUM(n_charlson_muito_alto) AS n_charlson_muito_alto,
        SUM(n_charlson_alto) AS n_charlson_alto,
        SUM(n_charlson_moderado) AS n_charlson_moderado,
        SUM(n_charlson_baixo) AS n_charlson_baixo,
        SUM(n_nenhum_medicamento) AS n_nenhum_medicamento,
        SUM(n_um_e_dois_medicamentos) AS n_um_e_dois_medicamentos,
        SUM(n_tres_e_quatro_medicamentos) AS n_tres_e_quatro_medicamentos,
        SUM(n_polifarmacia) AS n_polifarmacia,
        SUM(n_hiperpolifarmacia) AS n_hiperpolifarmacia,
        -- ACB
        SUM(n_acb_zero)          AS n_acb_zero,
        SUM(n_acb_baixo)         AS n_acb_baixo,
        SUM(n_acb_moderado)      AS n_acb_moderado,
        SUM(n_acb_alto)          AS n_acb_alto,
        SUM(n_acb_alerta_idoso)  AS n_acb_alerta_idoso,
        -- STOPP/START/Beers
        SUM(n_com_stopp_ativo)         AS n_com_stopp_ativo,
        SUM(n_com_omissao_start)       AS n_com_omissao_start,
        SUM(n_com_beers_ativo)         AS n_com_beers_ativo,
        SUM(n_alerta_prescricao_idoso) AS n_alerta_prescricao_idoso,
        SUM(n_risco_queda_meds)        AS n_risco_queda_meds,
        -- Cardiovascular
        SUM(n_HAS) AS n_HAS, SUM(n_CI) AS n_CI, SUM(n_ICC) AS n_ICC,
        SUM(n_stroke) AS n_stroke, SUM(n_arritmia) AS n_arritmia,
        SUM(n_valvular) AS n_valvular, SUM(n_circ_pulm) AS n_circ_pulm,
        SUM(n_vascular_periferica) AS n_vascular_periferica,
        -- Metabólico
        SUM(n_DM) AS n_DM, SUM(n_pre_DM) AS n_pre_DM,
        SUM(n_obesidade) AS n_obesidade, SUM(n_tireoide) AS n_tireoide,
        SUM(n_dislipidemia) AS n_dislipidemia,
        -- Renal/Hematológico
        SUM(n_IRC) AS n_IRC, SUM(n_coagulo) AS n_coagulo,
        SUM(n_anemias) AS n_anemias,
        -- Neurológico
        SUM(n_epilepsia) AS n_epilepsia, SUM(n_parkinsonismo) AS n_parkinsonismo,
        SUM(n_esclerose_multipla) AS n_esclerose_multipla,
        SUM(n_neuro) AS n_neuro, SUM(n_demencia) AS n_demencia,
        SUM(n_plegia) AS n_plegia,
        -- Saúde Mental
        SUM(n_psicoses) AS n_psicoses, SUM(n_depre_ansiedade) AS n_depre_ansiedade,
        -- Respiratório
        SUM(n_DPOC) AS n_DPOC, SUM(n_asma) AS n_asma,
        -- Oncológico detalhado
        SUM(n_neo_mama) AS n_neo_mama,
        SUM(n_neo_colo_uterino) AS n_neo_colo_uterino,
        SUM(n_neo_ginecologica) AS n_neo_ginecologica,
        SUM(n_neo_prostata) AS n_neo_prostata,
        SUM(n_neo_outros) AS n_neo_outros,
        SUM(n_leucemia) AS n_leucemia,
        SUM(n_linfoma) AS n_linfoma,
        SUM(n_metastase) AS n_metastase,
        SUM(n_neoplasia) AS n_neoplasia,
        -- Gastrointestinal
        SUM(n_peptic) AS n_peptic, SUM(n_liver) AS n_liver,
        SUM(n_diverticular) AS n_diverticular, SUM(n_ibd) AS n_ibd,
        -- Substâncias
        SUM(n_alcool) AS n_alcool, SUM(n_drogas) AS n_drogas,
        SUM(n_tabagismo) AS n_tabagismo,
        -- Infecciosas / Reumatológico
        SUM(n_HIV) AS n_HIV, SUM(n_reumato) AS n_reumato,
        -- Outras
        SUM(n_desnutricao) AS n_desnutricao,
        SUM(n_retardo_mental) AS n_retardo_mental,
        SUM(n_olhos) AS n_olhos, SUM(n_ouvidos) AS n_ouvidos,
        SUM(n_ma_formacoes) AS n_ma_formacoes, SUM(n_pele) AS n_pele,
        SUM(n_dor_cronica) AS n_dor_cronica, SUM(n_prostata) AS n_prostata

    FROM `rj-sms-sandbox.sub_pav_us.MM_piramides_populacionais`
    {where_sql}
    GROUP BY faixa_etaria, genero
    ORDER BY faixa_etaria, genero
    """
    
    try:
        client = get_bigquery_client()
        result = client.query(sql).result().to_dataframe(create_bqstorage_client=False)
    except Exception as e:
        st.error(f"❌ Erro ao carregar dados da pirâmide: {e}")
        return pd.DataFrame()
    return result


@st.cache_data(show_spinner=False, ttl=900)
def carregar_metricas_resumo(ap=None, clinica=None, esf=None):
    """Carrega apenas métricas agregadas - SUPER RÁPIDO"""
    
    where_clauses = []
    
    if ap:
        where_clauses.append(f"area_programatica = '{ap}'")
    if clinica:
        where_clauses.append(f"clinica_familia = '{clinica}'")
    if esf:
        where_clauses.append(f"ESF = '{esf}'")
    
    where_sql = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""
    
    sql = f"""
    SELECT
        SUM(total_pacientes) as total_pop,
        SUM(n_morb_2 + n_morb_3 + n_morb_4 + n_morb_5
            + n_morb_6 + n_morb_7 + n_morb_8 + n_morb_9
            + n_morb_10mais) as multimorbidos,
        SUM(n_polifarmacia) as polifarmacia,
        SUM(n_hiperpolifarmacia) as hiperpolifarmacia
    FROM `rj-sms-sandbox.sub_pav_us.MM_piramides_populacionais`
    {where_sql}
    """

    try:
        client = get_bigquery_client()
        df = client.query(sql).result().to_dataframe(create_bqstorage_client=False)
        if not df.empty:
            return {k: int(v) if v is not None else 0 for k, v in df.iloc[0].to_dict().items()}
    except Exception as e:
        st.warning(f"⚠️ Não foi possível carregar métricas resumo: {e}")
    return {'total_pop': 0, 'multimorbidos': 0, 'polifarmacia': 0, 'hiperpolifarmacia': 0}


# ============================================
# FUNÇÕES DE VISUALIZAÇÃO
# ============================================


def criar_piramide_populacional(df):
    """Cria pirâmide populacional por morbidades"""
    
    if df.empty:
        return None
    
    ordem_faixas = ['0-4', '5-9', '10-14', '15-19', '20-24', '25-29', '30-34', 
                    '35-39', '40-44', '45-49', '50-54', '55-59', '60-64', 
                    '65-69', '70-74', '75-79', '80-84', '85-89', '90+']
    
    df['faixa_etaria'] = pd.Categorical(df['faixa_etaria'], categories=ordem_faixas, ordered=True)
    df = df.sort_values('faixa_etaria')
    
    generos = df['genero'].unique()
    if 'masculino' in generos:
        df_masc = df[df['genero'] == 'masculino'].copy()
        df_fem = df[df['genero'] == 'feminino'].copy()
    else:
        df_masc = df[df['genero'] == 'M'].copy()
        df_fem = df[df['genero'] == 'F'].copy()
    
    cores = px.colors.qualitative.Safe
    while len(cores) < 9:
        cores = cores + cores
    
    fig = go.Figure()
    
    estratos = [
        ('n_morb_10mais', '8+ morbidades', cores[8]),
        ('n_morb_7', '7 morbidades', cores[7]),
        ('n_morb_6', '6 morbidades', cores[6]),
        ('n_morb_5', '5 morbidades', cores[5]),
        ('n_morb_4', '4 morbidades', cores[4]),
        ('n_morb_3', '3 morbidades', cores[3]),
        ('n_morb_2', '2 morbidades', cores[2]),
        ('n_morb_1', '1 morbidade', cores[1]),
        ('n_morb_0', '0 morbidades', cores[0])
    ]
    
    for campo, label, cor in estratos:
        if campo in df_masc.columns:
            fig.add_trace(go.Bar(
                y=df_masc['faixa_etaria'],
                x=-df_masc[campo],
                name=label,
                orientation='h',
                marker=dict(
                    color=cor,
                    line=dict(color='rgba(0,0,0,0.8)', width=0.5)
                ),
                text=df_masc[campo],
                texttemplate='%{text:,}',
                textposition='inside',
                textfont=dict(size=10, color=T.TEXT),
                legendgroup=label,
                showlegend=True,
                hovertemplate='<b>%{y}</b><br>Homens: %{text:,}<extra></extra>'
            ))
    
    for campo, label, cor in estratos:
        if campo in df_fem.columns:
            fig.add_trace(go.Bar(
                y=df_fem['faixa_etaria'],
                x=df_fem[campo],
                name=label,
                orientation='h',
                marker=dict(
                    color=cor,
                    line=dict(color='rgba(0,0,0,0.8)', width=0.5)
                ),
                text=df_fem[campo],
                texttemplate='%{text:,}',
                textposition='inside',
                textfont=dict(size=10, color=T.TEXT),
                legendgroup=label,
                showlegend=False,
                hovertemplate='<b>%{y}</b><br>Mulheres: %{x:,}<extra></extra>'
            ))
    
    # ✅ CALCULAR MÁXIMO - MAIS GRANULAR
    import math
    
    cols_morb = ['n_morb_0', 'n_morb_1', 'n_morb_2', 'n_morb_3', 'n_morb_4', 
                 'n_morb_5', 'n_morb_6', 'n_morb_7', 'n_morb_8', 'n_morb_9', 'n_morb_10mais']
    cols_existentes_masc = [c for c in cols_morb if c in df_masc.columns]
    cols_existentes_fem = [c for c in cols_morb if c in df_fem.columns]
    
    if cols_existentes_masc and cols_existentes_fem:
        max_masc = df_masc[cols_existentes_masc].sum(axis=1).max()
        max_fem = df_fem[cols_existentes_fem].sum(axis=1).max()
        max_val = max(max_masc, max_fem)
    else:
        max_val = 1000
    
    # ✅ STEPS MAIS GRANULARES
    if max_val < 100:
        step = 20
    elif max_val < 300:
        step = 50
    elif max_val < 500:
        step = 100
    elif max_val < 1000:
        step = 200
    elif max_val < 3000:
        step = 500
    elif max_val < 5000:
        step = 1000
    elif max_val < 10000:
        step = 2000
    elif max_val < 30000:
        step = 5000
    elif max_val < 50000:
        step = 10000
    elif max_val < 100000:
        step = 25000
    else:
        step = 50000
    
    max_range = math.ceil(max_val / step) * step
    
    # Criar ticks
    num_ticks = 5
    tick_step = max_range // num_ticks
    tickvals = []
    ticktext = []
    for i in range(-num_ticks, num_ticks + 1):
        val = i * tick_step
        tickvals.append(val)
        ticktext.append(f'{abs(val):,}')
    
    fig.update_layout(
        title='Pirâmide Etária - Distribuição por Sexo e Número de Morbidades',
        barmode='relative',
        bargap=0.0,
        bargroupgap=0,
        height=700,
        xaxis=dict(
            title='População',
            range=[-max_range, max_range],
            tickvals=tickvals,
            ticktext=ticktext,
            zeroline=True,
            zerolinewidth=3,
            zerolinecolor=T.TEXT
        ),
        yaxis=dict(title='Faixa Etária'),
        legend=dict(
            orientation='v',
            yanchor='middle',
            y=0.5,
            xanchor='left',
            x=1.02,
            title=dict(text='<b>Número de Morbidades</b>'),
            traceorder='normal'
        ),
        hovermode='closest',
        margin=dict(l=80, r=200, t=60, b=80)
    )
    
    fig.add_annotation(
        x=-max_range*0.5, y=1.02, xref='x', yref='paper',
        text='<b>Masculino</b>', showarrow=False,
        font=dict(size=16, color='#3498DB')
    )
    fig.add_annotation(
        x=max_range*0.5, y=1.02, xref='x', yref='paper',
        text='<b>Feminino</b>', showarrow=False,
        font=dict(size=16, color='#E91E63')
    )
    
    return fig



# ═══════════════════════════════════════════════════════════════
# DICIONÁRIOS DE MORBIDADES E CATEGORIAS
# ═══════════════════════════════════════════════════════════════

MORBIDADES_COMPLETO = {
    # ── Geral ────────────────────────────────────────────────
    'multimorbidade': {
        'nome': 'Multimorbidade (2+ condições)',
        'descricao': 'Presença de duas ou mais condições crônicas simultâneas.',
        'categoria': 'Geral', 'icone': '🏥'
    },
    # ── Cardiovascular ───────────────────────────────────────
    'n_HAS':                {'nome': 'Hipertensão Arterial',        'descricao': 'PA ≥140/90 mmHg.',                            'categoria': 'Cardiovascular',  'icone': '❤️'},
    'n_CI':                 {'nome': 'Cardiopatia Isquêmica',       'descricao': 'DAC, IAM prévio, angina.',                    'categoria': 'Cardiovascular',  'icone': '💔'},
    'n_ICC':                {'nome': 'Insuficiência Cardíaca',      'descricao': 'IC com FEp e FEr.',                           'categoria': 'Cardiovascular',  'icone': '🫀'},
    'n_stroke':             {'nome': 'AVC Prévio',                  'descricao': 'AVC isquêmico, hemorrágico e AIT.',           'categoria': 'Cardiovascular',  'icone': '🧠'},
    'n_arritmia':           {'nome': 'Arritmias Cardíacas',         'descricao': 'FA, flutter, taquicardias.',                  'categoria': 'Cardiovascular',  'icone': '💓'},
    'n_valvular':           {'nome': 'Valvulopatias',               'descricao': 'Qualquer valvulopatia primária ou secundária.','categoria': 'Cardiovascular',  'icone': '🫀'},
    'n_circ_pulm':          {'nome': 'Doenças Circulação Pulmonar', 'descricao': 'Hipertensão pulmonar, TEP.',                  'categoria': 'Cardiovascular',  'icone': '🫁'},
    'n_vascular_periferica':{'nome': 'Doença Vascular Periférica',  'descricao': 'Obstrução arterial periférica.',              'categoria': 'Cardiovascular',  'icone': '🦵'},
    # ── Metabólico/Endócrino ─────────────────────────────────
    'n_DM':          {'nome': 'Diabetes Mellitus',      'descricao': 'DM tipo 1, 2, MODY e LADA.',              'categoria': 'Metabólico', 'icone': '🍬'},
    'n_pre_DM':      {'nome': 'Pré-Diabetes',           'descricao': 'Glicemia 100-125 mg/dL ou HbA1c 5.7-6.4%.','categoria': 'Metabólico', 'icone': '⚠️'},
    'n_obesidade':   {'nome': 'Obesidade',               'descricao': 'IMC ≥30 kg/m².',                          'categoria': 'Metabólico', 'icone': '⚖️'},
    'n_dislipidemia':{'nome': 'Dislipidemia',            'descricao': 'Colesterol ou triglicérides alterados.',   'categoria': 'Metabólico', 'icone': '🩸'},
    'n_tireoide':    {'nome': 'Doenças da Tireoide',     'descricao': 'Hipo, hipertireoidismo, nódulos.',         'categoria': 'Endócrino',  'icone': '🦋'},
    # ── Renal/Hematológico ───────────────────────────────────
    'n_IRC':    {'nome': 'Doença Renal Crônica',     'descricao': 'TFG <60 ml/min.',                  'categoria': 'Renal',        'icone': '🩺'},
    'n_coagulo':{'nome': 'Distúrbios de Coagulação', 'descricao': 'Trombofilias, anticoagulação.',    'categoria': 'Hematológico', 'icone': '🩸'},
    'n_anemias':{'nome': 'Anemias',                  'descricao': 'Redução de hemoglobina/eritrócitos.','categoria': 'Hematológico','icone': '🩸'},
    # ── Neurológico ──────────────────────────────────────────
    'n_epilepsia':          {'nome': 'Epilepsia',                  'descricao': 'Crises convulsivas recorrentes.',            'categoria': 'Neurológico', 'icone': '⚡'},
    'n_parkinsonismo':      {'nome': 'Parkinsonismo',               'descricao': 'Doença de Parkinson e síndromes.',           'categoria': 'Neurológico', 'icone': '🤝'},
    'n_esclerose_multipla': {'nome': 'Esclerose Múltipla',          'descricao': 'Doença desmielinizante do SNC.',             'categoria': 'Neurológico', 'icone': '🧠'},
    'n_neuro':              {'nome': 'Outras Doenças Neurológicas', 'descricao': 'Neuropatias, mielopatias.',                  'categoria': 'Neurológico', 'icone': '🧠'},
    'n_demencia':           {'nome': 'Demências',                   'descricao': 'Alzheimer, vascular, outras.',               'categoria': 'Neurológico', 'icone': '🧓'},
    'n_plegia':             {'nome': 'Plegias',                     'descricao': 'Hemiplegia, paraplegia, tetraplegia.',       'categoria': 'Neurológico', 'icone': '♿'},
    # ── Saúde Mental ─────────────────────────────────────────
    'n_psicoses':        {'nome': 'Transtornos Psicóticos', 'descricao': 'Esquizofrenia, transtorno bipolar.',    'categoria': 'Saúde Mental', 'icone': '💭'},
    'n_depre_ansiedade': {'nome': 'Depressão e Ansiedade',  'descricao': 'Transtornos depressivos e ansiosos.',  'categoria': 'Saúde Mental', 'icone': '😔'},
    # ── Respiratório ─────────────────────────────────────────
    'n_DPOC': {'nome': 'DPOC', 'descricao': 'Doença Pulmonar Obstrutiva Crônica.', 'categoria': 'Respiratório', 'icone': '🫁'},
    'n_asma': {'nome': 'Asma', 'descricao': 'Casos registrados com CID para Asma.','categoria': 'Respiratório', 'icone': '🌬️'},
    # ── Oncológico ───────────────────────────────────────────
    'n_neo_mama':        {'nome': 'Câncer de Mama',             'descricao': 'Neoplasia maligna da mama.',                'categoria': 'Oncológico', 'icone': '🎗️'},
    'n_neo_colo_uterino':{'nome': 'Câncer de Colo Uterino',     'descricao': 'Neoplasia maligna do colo do útero.',       'categoria': 'Oncológico', 'icone': '🎗️'},
    'n_neo_ginecologica':{'nome': 'Neoplasias Ginecológicas',   'descricao': 'Cânceres do aparelho reprodutor feminino.', 'categoria': 'Oncológico', 'icone': '🎗️'},
    'n_neo_prostata':    {'nome': 'Câncer de Próstata',         'descricao': 'Neoplasia maligna da próstata.',            'categoria': 'Oncológico', 'icone': '🎗️'},
    'n_neo_outros':      {'nome': 'Outros Cânceres (ambos sexos)', 'descricao': 'Neoplasias que acometem ambos os sexos.', 'categoria': 'Oncológico', 'icone': '🎗️'},
    'n_leucemia':        {'nome': 'Leucemias',                  'descricao': 'Neoplasias hematológicas malignas.',        'categoria': 'Oncológico', 'icone': '🩸'},
    'n_linfoma':         {'nome': 'Linfomas',                   'descricao': 'Neoplasias do sistema linfático.',          'categoria': 'Oncológico', 'icone': '🎗️'},
    'n_metastase':       {'nome': 'Câncer Metastático',         'descricao': 'Neoplasias com metástases à distância.',    'categoria': 'Oncológico', 'icone': '⚠️'},
    # ── Gastrointestinal ─────────────────────────────────────
    'n_peptic':      {'nome': 'Doença Péptica',              'descricao': 'Úlceras gástricas e duodenais.',       'categoria': 'Gastrointestinal', 'icone': '🫃'},
    'n_liver':       {'nome': 'Doenças Hepáticas',           'descricao': 'Hepatites, cirrose, esteatose.',       'categoria': 'Gastrointestinal', 'icone': '🫀'},
    'n_diverticular':{'nome': 'Doença Diverticular',         'descricao': 'Diverticulose e diverticulite.',       'categoria': 'Gastrointestinal', 'icone': '🫃'},
    'n_ibd':         {'nome': 'Doença Inflamatória Intestinal','descricao': 'Crohn, retocolite ulcerativa.',      'categoria': 'Gastrointestinal', 'icone': '🫃'},
    # ── Substâncias ──────────────────────────────────────────
    'n_alcool':    {'nome': 'Transtorno por Uso de Álcool',  'descricao': 'Uso problemático de álcool.',          'categoria': 'Substâncias', 'icone': '🍺'},
    'n_drogas':    {'nome': 'Transtorno por Uso de Drogas',  'descricao': 'Uso problemático de substâncias.',     'categoria': 'Substâncias', 'icone': '💉'},
    'n_tabagismo': {'nome': 'Tabagismo',                     'descricao': 'Dependência de nicotina.',             'categoria': 'Substâncias', 'icone': '🚬'},
    # ── Infecciosas ──────────────────────────────────────────
    'n_HIV': {'nome': 'HIV/AIDS', 'descricao': 'Infecção pelo HIV ou AIDS.', 'categoria': 'Infecciosas', 'icone': '🦠'},
    # ── Reumatológico ────────────────────────────────────────
    'n_reumato': {'nome': 'Doenças Reumatológicas', 'descricao': 'AR, lúpus, outras autoimunes.', 'categoria': 'Reumatológico', 'icone': '🦴'},
    # ── Outras condições ─────────────────────────────────────
    'n_desnutricao':   {'nome': 'Desnutrição',                 'descricao': 'Estado nutricional comprometido.',   'categoria': 'Nutricional',         'icone': '🍎'},
    'n_retardo_mental':{'nome': 'Deficiência Intelectual',     'descricao': 'Limitação cognitiva significativa.', 'categoria': 'Neurológico',         'icone': '🧩'},
    'n_olhos':         {'nome': 'Doenças Oftalmológicas',      'descricao': 'Glaucoma, catarata, retinopatias.',  'categoria': 'Oftalmológico',       'icone': '👁️'},
    'n_ouvidos':       {'nome': 'Doenças Otológicas',          'descricao': 'Perda auditiva, vertigem.',          'categoria': 'Otorrinolaringologia', 'icone': '👂'},
    'n_ma_formacoes':  {'nome': 'Má-formações Congênitas',     'descricao': 'Anomalias congênitas.',              'categoria': 'Congênito',           'icone': '👶'},
    'n_pele':          {'nome': 'Doenças Dermatológicas',      'descricao': 'Psoríase, eczema, dermatoses.',      'categoria': 'Dermatológico',       'icone': '🧴'},
    'n_dor_cronica':   {'nome': 'Condições Dolorosas Crônicas','descricao': 'Dor crônica, fibromialgia.',         'categoria': 'Dor',                 'icone': '⚡'},
    'n_prostata':      {'nome': 'Doenças Prostáticas Benignas','descricao': 'Hiperplasia prostática benigna.',    'categoria': 'Urológico',           'icone': '💧'},
    # ── Farmacológico ────────────────────────────────────────
    'n_polifarmacia':     {'nome': 'Polifarmácia (5-9)',     'descricao': 'Uso de 5-9 medicamentos.',  'categoria': 'Farmacológico', 'icone': '💊'},
    'n_hiperpolifarmacia':{'nome': 'Hiperpolifarmácia (10+)','descricao': 'Uso de 10+ medicamentos.', 'categoria': 'Farmacológico', 'icone': '💊'},
}

CATEGORIA_CONSOLIDADA = {
    'Geral': 'Multimorbidade',
    'Cardiovascular': 'Problemas Cardiovasculares',
    'Metabólico': 'Problemas Metabólicos e Endócrinos',
    'Endócrino': 'Problemas Metabólicos e Endócrinos',
    'Renal': 'Problemas Renais e Hematológicos',
    'Hematológico': 'Problemas Renais e Hematológicos',
    'Neurológico': 'Problemas Neurológicos',
    'Saúde Mental': 'Saúde Mental e uso de substâncias',
    'Substâncias': 'Saúde Mental e uso de substâncias',
    'Respiratório': 'Problemas Respiratórios',
    'Oncológico': 'Problemas Oncológicos',
    'Reumatológico': 'Problemas Reumatológicos',
    'Gastrointestinal': 'Problemas Gastrointestinais',
    'Infecciosas': 'Doenças Infecciosas',
    'Farmacológico': 'Polifarmácia',
    'Nutricional': 'Outras Condições de Saúde',
    'Oftalmológico': 'Outras Condições de Saúde',
    'Otorrinolaringologia': 'Outras Condições de Saúde',
    'Congênito': 'Outras Condições de Saúde',
    'Dermatológico': 'Outras Condições de Saúde',
    'Dor': 'Outras Condições de Saúde',
    'Urológico': 'Outras Condições de Saúde',
}

ORDEM_CATEGORIAS = [
    'Multimorbidade',
    'Problemas Cardiovasculares',
    'Problemas Metabólicos e Endócrinos',
    'Problemas Renais e Hematológicos',
    'Problemas Neurológicos',
    'Problemas Oncológicos',
    'Saúde Mental e uso de substâncias',
    'Problemas Respiratórios',
    'Problemas Reumatológicos',
    'Problemas Gastrointestinais',
    'Doenças Infecciosas',
    'Polifarmácia',
    'Outras Condições de Saúde',
]

ICONES_CATEGORIAS_CONSOLIDADAS = {
    'Multimorbidade':                    '📊',
    'Problemas Cardiovasculares':        '❤️',
    'Problemas Metabólicos e Endócrinos':'⚖️',
    'Problemas Renais e Hematológicos':  '🩺',
    'Problemas Neurológicos':            '🧠',
    'Problemas Oncológicos':             '🎗️',
    'Saúde Mental e uso de substâncias': '💭',
    'Problemas Respiratórios':           '🫁',
    'Problemas Reumatológicos':          '🦴',
    'Problemas Gastrointestinais':       '🫃',
    'Doenças Infecciosas':               '🦠',
    'Polifarmácia':                      '💊',
    'Outras Condições de Saúde':         '📋',
}


def calcular_multimorbidade(df):
    """Calcula número de pacientes com 2+ morbidades a partir das colunas do schema atual."""
    if df.empty:
        return 0
    # Tabela de pirâmides tem n_multimorbidos diretamente — usar se disponível
    if 'n_multimorbidos' in df.columns:
        return int(df['n_multimorbidos'].sum())
    # Fallback: somar colunas individuais
    cols_multi = ['n_morb_2', 'n_morb_3', 'n_morb_4', 'n_morb_5',
                  'n_morb_6', 'n_morb_7', 'n_morb_8', 'n_morb_9', 'n_morb_10mais']
    total = sum(int(df[c].sum()) for c in cols_multi if c in df.columns)
    return total


def criar_piramide_charlson(df):
    """Pirâmide por Carga de Morbidade — 4 categorias do schema atual."""

    if df.empty:
        return None

    ordem_faixas = ['0-4', '5-9', '10-14', '15-19', '20-24', '25-29', '30-34',
                    '35-39', '40-44', '45-49', '50-54', '55-59', '60-64',
                    '65-69', '70-74', '75-79', '80-84', '85-89', '90+']

    df = df.copy()
    df['faixa_etaria'] = pd.Categorical(df['faixa_etaria'], categories=ordem_faixas, ordered=True)
    df = df.sort_values('faixa_etaria')

    generos = df['genero'].unique()
    sufixo_masc = 'masculino' if 'masculino' in generos else 'M'
    sufixo_fem  = 'feminino'  if 'feminino'  in generos else 'F'
    df_masc = df[df['genero'] == sufixo_masc].copy()
    df_fem  = df[df['genero'] == sufixo_fem].copy()

    # Estratos: do mais grave para o menos grave (para empilhamento correto)
    estratos = [
        ('n_charlson_muito_alto', 'Muito Alto',  '#C0392B'),
        ('n_charlson_alto',       'Alto',         '#E67E22'),
        ('n_charlson_moderado',   'Moderado',     '#F4D03F'),
        ('n_charlson_baixo',      'Baixo',        '#2ECC71'),
    ]

    fig = go.Figure()

    for campo, label, cor in estratos:
        if campo not in df_masc.columns:
            continue
        fig.add_trace(go.Bar(
            y=df_masc['faixa_etaria'],
            x=-df_masc[campo],
            name=label,
            orientation='h',
            marker=dict(color=cor, line=dict(color='rgba(0,0,0,0.4)', width=0.3)),
            text=df_masc[campo],
            texttemplate='%{text:,}',
            textposition='inside',
            textfont=dict(size=9, color=T.TEXT),
            legendgroup=label,
            showlegend=True,
            hovertemplate=f'<b>%{{y}}</b><br>Homens ({label}): %{{text:,}}<extra></extra>'
        ))

    for campo, label, cor in estratos:
        if campo not in df_fem.columns:
            continue
        fig.add_trace(go.Bar(
            y=df_fem['faixa_etaria'],
            x=df_fem[campo],
            name=label,
            orientation='h',
            marker=dict(color=cor, line=dict(color='rgba(0,0,0,0.4)', width=0.3)),
            text=df_fem[campo],
            texttemplate='%{text:,}',
            textposition='inside',
            textfont=dict(size=9, color=T.TEXT),
            legendgroup=label,
            showlegend=False,
            hovertemplate=f'<b>%{{y}}</b><br>Mulheres ({label}): %{{x:,}}<extra></extra>'
        ))

    cols_val = [c for c, _, _ in estratos if c in df_masc.columns]
    max_val = max(
        df_masc[cols_val].sum(axis=1).max() if cols_val else 0,
        df_fem[cols_val].sum(axis=1).max()  if cols_val else 0,
        1
    )
    steps = [20,50,100,200,500,1000,2000,5000,10000,25000,50000]
    step = next((s for s in steps if max_val < s * 5), 50000)
    max_range = math.ceil(max_val / step) * step
    num_ticks = 5
    tick_step = max(max_range // num_ticks, 1)
    tickvals = [i * tick_step for i in range(-num_ticks, num_ticks + 1)]
    ticktext = [f'{abs(v):,}' for v in tickvals]

    fig.update_layout(
        title='Pirâmide Etária — Distribuição por Sexo e Carga de Morbidade (Charlson)',
        barmode='relative',
        bargap=0.0,
        height=700,
        xaxis=dict(title='População', range=[-max_range, max_range],
                   tickvals=tickvals, ticktext=ticktext,
                   zeroline=True, zerolinewidth=3, zerolinecolor=T.TEXT),
        yaxis=dict(title='Faixa Etária'),
        legend=dict(orientation='v', yanchor='middle', y=0.5,
                    xanchor='left', x=1.02,
                    title=dict(text='<b>Carga de Morbidade</b>')),
        hovermode='closest',
        margin=dict(l=80, r=200, t=60, b=80)
    )
    fig.add_annotation(x=-max_range*0.5, y=1.02, xref='x', yref='paper',
                       text='<b>Masculino</b>', showarrow=False,
                       font=dict(size=16, color='#3498DB'))
    fig.add_annotation(x=max_range*0.5, y=1.02, xref='x', yref='paper',
                       text='<b>Feminino</b>', showarrow=False,
                       font=dict(size=16, color='#E91E63'))
    return fig


def criar_piramide_medicamentos(df):
    """Cria pirâmide por medicamentos"""
    
    if df.empty:
        return None
    
    ordem_faixas = ['0-4', '5-9', '10-14', '15-19', '20-24', '25-29', '30-34', 
                    '35-39', '40-44', '45-49', '50-54', '55-59', '60-64', 
                    '65-69', '70-74', '75-79', '80-84', '85-89', '90+']
    
    df['faixa_etaria'] = pd.Categorical(df['faixa_etaria'], categories=ordem_faixas, ordered=True)
    df = df.sort_values('faixa_etaria')
    
    generos = df['genero'].unique()
    if 'masculino' in generos:
        df_masc = df[df['genero'] == 'masculino'].copy()
        df_fem = df[df['genero'] == 'feminino'].copy()
    else:
        df_masc = df[df['genero'] == 'M'].copy()
        df_fem = df[df['genero'] == 'F'].copy()
    
    cores = px.colors.qualitative.Safe
    while len(cores) < 5:
        cores = cores + cores
    
    fig = go.Figure()
    
    estratos = [
        ('n_hiperpolifarmacia', 'Hiperpolifarmácia (10+)', cores[4]),
        ('n_polifarmacia', 'Polifarmácia (5-9)', cores[3]),
        ('n_tres_e_quatro_medicamentos', '3-4 medicamentos', cores[2]),
        ('n_um_e_dois_medicamentos', '1-2 medicamentos', cores[1]),
        ('n_nenhum_medicamento', '0 medicamentos', cores[0])
    ]
    
    for campo, label, cor in estratos:
        if campo in df_masc.columns:
            fig.add_trace(go.Bar(
                y=df_masc['faixa_etaria'], 
                x=-df_masc[campo],
                name=label, 
                orientation='h', 
                marker=dict(color=cor, line=dict(color='rgba(0,0,0,0.8)', width=0.5)),
                text=df_masc[campo],
                texttemplate='%{text:,}',
                textposition='inside',
                textfont=dict(size=10, color=T.TEXT),
                legendgroup=label, 
                showlegend=True,
                hovertemplate='<b>%{y}</b><br>Homens: %{text:,}<extra></extra>'
            ))
    
    for campo, label, cor in estratos:
        if campo in df_fem.columns:
            fig.add_trace(go.Bar(
                y=df_fem['faixa_etaria'], 
                x=df_fem[campo],
                name=label, 
                orientation='h', 
                marker=dict(color=cor, line=dict(color='rgba(0,0,0,0.8)', width=0.5)),
                text=df_fem[campo],
                texttemplate='%{text:,}',
                textposition='inside',
                textfont=dict(size=10, color=T.TEXT),
                legendgroup=label, 
                showlegend=False,
                hovertemplate='<b>%{y}</b><br>Mulheres: %{x:,}<extra></extra>'
            ))
    
    # CALCULAR MÁXIMO
    import math
    cols_meds = ['n_nenhum_medicamento', 'n_um_e_dois_medicamentos', 
                 'n_tres_e_quatro_medicamentos', 'n_polifarmacia', 'n_hiperpolifarmacia']
    cols_existentes = [c for c in cols_meds if c in df_masc.columns]
    
    if cols_existentes:
        max_masc = df_masc[cols_existentes].sum(axis=1).max()
        max_fem = df_fem[cols_existentes].sum(axis=1).max()
        max_val = max(max_masc, max_fem)
    else:
        max_val = 1000
    
    if max_val < 100:
        step = 20
    elif max_val < 300:
        step = 50
    elif max_val < 500:
        step = 100
    elif max_val < 1000:
        step = 200
    elif max_val < 3000:
        step = 500
    elif max_val < 5000:
        step = 1000
    elif max_val < 10000:
        step = 2000
    elif max_val < 30000:
        step = 5000
    elif max_val < 50000:
        step = 10000
    else:
        step = 25000
    
    max_range = math.ceil(max_val / step) * step
    num_ticks = 5
    tick_step = max_range // num_ticks
    tickvals = [i * tick_step for i in range(-num_ticks, num_ticks + 1)]
    ticktext = [f'{abs(val):,}' for val in tickvals]
    
    fig.update_layout(
        title='Pirâmide Etária - Distribuição por Sexo e Complexidade Farmacológica',
        barmode='relative', 
        bargap=0.0,
        bargroupgap=0,
        height=700,
        xaxis=dict(
            title='População', 
            range=[-max_range, max_range],
            tickvals=tickvals,
            ticktext=ticktext,
            zeroline=True,
            zerolinewidth=3,
            zerolinecolor=T.TEXT
        ),
        yaxis=dict(title='Faixa Etária'),
        legend=dict(
            orientation='v',
            yanchor='middle',
            y=0.5,
            xanchor='left',
            x=1.02,
            title=dict(text='<b>Medicamentos Crônicos</b>')
        ),
        hovermode='closest',
        margin=dict(l=80, r=250, t=60, b=80)
    )
    
    fig.add_annotation(
        x=-max_range*0.5, y=1.02, xref='x', yref='paper',
        text='<b>Masculino</b>', showarrow=False,
        font=dict(size=16, color='#3498DB')
    )
    fig.add_annotation(
        x=max_range*0.5, y=1.02, xref='x', yref='paper',
        text='<b>Feminino</b>', showarrow=False,
        font=dict(size=16, color='#E91E63')
    )
    
    return fig


def criar_grafico_charlson(df):
    """Cria gráfico de distribuição de Charlson"""
    
    # Agregar por categoria Charlson
    charlson_cols = [f'n_charlson_{i}' for i in range(17)]
    
    dados_charlson = []
    for i, col in enumerate(charlson_cols):
        if col in df.columns:
            n = df[col].sum()
            if i < 16:
                categoria = str(i)
            else:
                categoria = '16+'
            dados_charlson.append({'categoria': categoria, 'n_pacientes': n})
    
    df_charlson = pd.DataFrame(dados_charlson)
    
    fig = go.Figure()
    
    fig.add_trace(go.Bar(
        x=df_charlson['categoria'],
        y=df_charlson['n_pacientes'],
        marker=dict(color=px.colors.qualitative.Prism[4]),
        text=df_charlson['n_pacientes'],
        textposition='outside',
        hovertemplate='Charlson %{x}<br>Pacientes: %{y:,}<extra></extra>'
    ))
    
    fig.update_layout(
        title='Distribuição de Carga de Morbidade (Índice de Charlson)',
        xaxis_title='Pontuação de Charlson',
        yaxis_title='Número de Pacientes',
        height=400,
        showlegend=False
    )
    
    return fig

def criar_grafico_medicamentos(df):
    """Cria gráfico de distribuição de medicamentos"""
    
    categorias = [
        ('n_nenhum_medicamento', '0 medicamentos'),
        ('n_um_e_dois_medicamentos', '1-2 medicamentos'),
        ('n_tres_e_quatro_medicamentos', '3-4 medicamentos'),
        ('n_polifarmacia', 'Polifarmácia (5-9)'),
        ('n_hiperpolifarmacia', 'Hiperpolifarmácia (10+)')
    ]
    
    dados = []
    for campo, label in categorias:
        if campo in df.columns:
            n = df[campo].sum()
            dados.append({'categoria': label, 'n_pacientes': n})
    
    df_meds = pd.DataFrame(dados)
    
    fig = go.Figure()
    
    cores = px.colors.qualitative.Prism[:5]
    
    fig.add_trace(go.Bar(
        x=df_meds['categoria'],
        y=df_meds['n_pacientes'],
        marker=dict(color=cores),
        text=df_meds['n_pacientes'],
        textposition='outside',
        hovertemplate='%{x}<br>Pacientes: %{y:,}<extra></extra>'
    ))
    
    fig.update_layout(
        title='Distribuição de Complexidade Farmacológica',
        xaxis_title='',
        yaxis_title='Número de Pacientes',
        height=400,
        showlegend=False
    )
    
    return fig

def criar_visualizacao_morbidades_prevalentes(df):
    """Cria visualização de TODAS as morbidades - VERSÃO ELEGANTE"""
    
    if df.empty:
        return None, None
    
    total_pacientes = df['total_pacientes'].sum()
    
    # ✅ ADICIONAR MULTIMORBIDADE
    n_multi = calcular_multimorbidade(df)
    prev_multi = (n_multi / total_pacientes * 100) if total_pacientes > 0 else 0
    
    resultados = [{
        'Condição': 'Multimorbidade (2+ condições)',
        'N': n_multi,
        'Prevalência (%)': round(prev_multi, 1),
        'Descrição': 'Presença de duas ou mais condições crônicas. Aumenta complexidade do cuidado.',
        'Categoria': 'Geral',
        'Coluna': 'multimorbidade'
    }]
    
    # Calcular prevalências das outras condições
    for coluna, info in MORBIDADES_COMPLETO.items():
        if coluna == 'multimorbidade':
            continue
            
        if coluna in df.columns:
            n = int(df[coluna].sum())
            prev = (n / total_pacientes * 100) if total_pacientes > 0 else 0
            
            if n > 0:
                # ✅ MAPEAR PARA CATEGORIA CONSOLIDADA
                cat_original = info['categoria']
                cat_consolidada = CATEGORIA_CONSOLIDADA.get(cat_original, cat_original)
                
                resultados.append({
                    'Condição': info['nome'],
                    'N': n,
                    'Prevalência (%)': round(prev, 1),
                    'Descrição': info['descricao'],
                    'Categoria': cat_consolidada,
                    'Coluna': coluna
                })
    
    if not resultados:
        return None, None
    
    df_prev = pd.DataFrame(resultados).sort_values('Prevalência (%)', ascending=False)
    
    # GRÁFICO TOP 20
    df_top20 = df_prev.head(20).sort_values('Prevalência (%)', ascending=True)
    
    fig = go.Figure()
    
    fig.add_trace(go.Bar(
        y=df_top20['Condição'],
        x=df_top20['Prevalência (%)'],
        orientation='h',
        text=df_top20['Prevalência (%)'].apply(lambda x: f'{x:.1f}%'),
        textposition='outside',
        marker=dict(
            color=df_top20['Prevalência (%)'],
            colorscale='YlOrRd',
            showscale=False
        ),
        hovertemplate='<b>%{y}</b><br>Prevalência: %{x:.1f}%<br>Pacientes: %{customdata:,}<extra></extra>',
        customdata=df_top20['N']
    ))
    
    max_prev = df_top20['Prevalência (%)'].max()
    range_max = max(50, math.ceil(max_prev / 10) * 10)
    
    fig.update_layout(
        title='Top 20 Condições Mais Prevalentes',
        xaxis=dict(
            title='Prevalência (%)',
            range=[0, range_max],
            tickmode='linear',
            tick0=0,
            dtick=5
        ),
        yaxis=dict(title=''),
        height=700,
        margin=dict(l=300, r=100, t=60, b=80)
    )
    
    return fig, df_prev

# ============================================
# INTERFACE PRINCIPAL
# ============================================

st.title("👥 Minha População")
st.markdown("Visão agregada das características demográficas e clínicas da população")
st.markdown("---")



# ============================================
# SIDEBAR - FILTROS
# ============================================

st.sidebar.title("Filtros")

# Filtros pré-carregados do contexto da Home
from utils.data_loader import carregar_opcoes_filtros
_opcoes = carregar_opcoes_filtros()
_areas = _opcoes.get('areas', [])

# ── Callbacks para reset hierárquico ─────────────────────────
def _reset_clinica_esf():
    st.session_state['pop_cli'] = None
    st.session_state['pop_esf'] = None

def _reset_esf():
    st.session_state['pop_esf'] = None

# Inicializar session_state com contexto do usuário (apenas na primeira vez)
if 'pop_ap' not in st.session_state:
    st.session_state['pop_ap'] = ctx.get('ap')
if 'pop_cli' not in st.session_state:
    st.session_state['pop_cli'] = ctx.get('clinica')
if 'pop_esf' not in st.session_state:
    st.session_state['pop_esf'] = ctx.get('esf')

ap_sel = st.sidebar.selectbox(
    "Área Programática",
    options=[None] + _areas,
    format_func=lambda x: "Todas" if x is None else anonimizar_ap(str(x)),
    key="pop_ap",
    on_change=_reset_clinica_esf,
)
_clinicas = sorted(_opcoes['clinicas'].get(ap_sel, [])) if ap_sel else []

cli_sel = st.sidebar.selectbox(
    "Clínica da Família",
    options=[None] + _clinicas,
    format_func=lambda x: "Todas" if x is None else anonimizar_clinica(x),
    key="pop_cli",
    disabled=not ap_sel,
    on_change=_reset_esf,
)
# Garantir que cli_sel seja válido para a AP atual
if cli_sel not in _clinicas:
    cli_sel = None

_esfs = sorted(_opcoes['esf'].get(cli_sel, [])) if cli_sel else []

esf_sel = st.sidebar.selectbox(
    "Equipe ESF",
    options=[None] + _esfs,
    format_func=lambda x: "Todas" if x is None else anonimizar_esf(x),
    key="pop_esf",
    disabled=not cli_sel,
)
# Garantir que esf_sel seja válido para a clínica atual
if esf_sel not in _esfs:
    esf_sel = None

territorio = {'ap': ap_sel, 'clinica': cli_sel, 'esf': esf_sel}

# ── Navegação por aba (persiste entre reruns) ─────────────────
NOMES_ABAS = [
    "📊 Perfil da População",
    "📈 Carga de Morbidade",
    "💊 Complexidade Farmacológica",
    "❤️ Hipertensão",
    "🍬 Diabetes",
    "🔄 Acesso e Continuidade",
]
st.sidebar.markdown("---")
st.sidebar.markdown("### 📑 Navegar para")
if 'pop_aba_ativa' not in st.session_state:
    st.session_state['pop_aba_ativa'] = 0
aba_escolhida = st.sidebar.radio(
    "",
    options=range(len(NOMES_ABAS)),
    format_func=lambda i: NOMES_ABAS[i],
    index=st.session_state['pop_aba_ativa'],
    key="pop_nav_aba",
    label_visibility="collapsed",
)
st.session_state['pop_aba_ativa'] = aba_escolhida




# ============================================
# QUERY CLÍNICA AGREGADA — tabela fato
# ============================================

@st.cache_data(show_spinner=False, ttl=900)
def carregar_sumario_clinico(ap=None, clinica=None, esf=None) -> dict:
    """Agrega indicadores clínicos de HAS, DM e Acesso da tabela fato."""
    clauses = []
    if ap:      clauses.append(f"area_programatica_cadastro = '{ap}'")
    if clinica: clauses.append(f"nome_clinica_cadastro = '{clinica}'")
    if esf:     clauses.append(f"nome_esf_cadastro = '{esf}'")
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    sql = f"""
    SELECT
        COUNT(*) AS total_pop,

        -- ── HAS: DIAGNÓSTICO ─────────────────────────────────
        COUNTIF(HAS IS NOT NULL)                                        AS n_HAS,
        COUNTIF(has_por_cid IS NOT NULL)                                AS n_HAS_por_cid,
        COUNTIF(has_por_medida_critica IS NOT NULL)                     AS n_HAS_medida_critica,
        COUNTIF(has_por_medidas_repetidas IS NOT NULL)                  AS n_HAS_medidas_repetidas,
        COUNTIF(has_por_medicamento IS NOT NULL)                        AS n_HAS_medicamento,
        COUNTIF(HAS_sem_CID = TRUE)                                     AS n_HAS_sem_cid,

        -- ── HAS: CONTROLE PRESSÓRICO ─────────────────────────
        COUNTIF(HAS IS NOT NULL AND status_controle_pressorio = 'controlado')    AS n_HAS_controlado,
        COUNTIF(HAS IS NOT NULL AND status_controle_pressorio = 'descontrolado') AS n_HAS_descontrolado,
        COUNTIF(HAS IS NOT NULL AND status_controle_pressorio IS NULL)           AS n_HAS_sem_info,
        ROUND(AVG(CASE WHEN HAS IS NOT NULL THEN pct_dias_has_controlado_365d END), 1) AS media_pct_has_ctrl,

        -- ── HAS: TENDÊNCIA DA PA ─────────────────────────────
        COUNTIF(HAS IS NOT NULL AND tendencia_pa = 'melhorando')        AS n_HAS_melhorando,
        COUNTIF(HAS IS NOT NULL AND tendencia_pa = 'estavel')           AS n_HAS_estavel,
        COUNTIF(HAS IS NOT NULL AND tendencia_pa = 'piorando')          AS n_HAS_piorando,

        -- ── HAS: LACUNAS ─────────────────────────────────────
        COUNTIF(lacuna_rastreio_PA_adulto = TRUE)                       AS n_lac_rastreio_pa,
        COUNTIF(lacuna_PA_hipertenso_180d = TRUE)                       AS n_lac_has_sem_pa_180d,
        COUNTIF(lacuna_HAS_descontrolado_menor80 = TRUE)                AS n_lac_has_desctrl_menor80,
        COUNTIF(lacuna_HAS_descontrolado_80mais = TRUE)                 AS n_lac_has_desctrl_80mais,
        COUNTIF(lacuna_DM_HAS_PA_descontrolada = TRUE)                  AS n_lac_dm_has_pa_desctrl,
        -- HAS exames laboratoriais
        COUNTIF(HAS IS NOT NULL AND lacuna_creatinina_HAS_DM = TRUE)   AS n_lac_has_creatinina,
        COUNTIF(HAS IS NOT NULL AND lacuna_colesterol_HAS_DM = TRUE)   AS n_lac_has_colesterol,
        COUNTIF(HAS IS NOT NULL AND lacuna_eas_HAS_DM = TRUE)          AS n_lac_has_eas,
        COUNTIF(HAS IS NOT NULL AND lacuna_ecg_HAS_DM = TRUE)          AS n_lac_has_ecg,
        COUNTIF(HAS IS NOT NULL AND lacuna_IMC_HAS_DM = TRUE)          AS n_lac_has_imc,
        -- HAS estratificação de risco total
        COUNTIF(HAS IS NOT NULL AND idade >= 80)                        AS n_HAS_80mais,
        COUNTIF(HAS IS NOT NULL AND idade >= 80
                AND status_controle_pressorio = 'controlado')           AS n_HAS_controlado_80mais,
        COUNTIF(HAS IS NOT NULL AND idade < 80)                         AS n_HAS_menor80,
        COUNTIF(HAS IS NOT NULL AND idade < 80
                AND status_controle_pressorio = 'controlado')           AS n_HAS_controlado_menor80,

        -- ── DM: DIAGNÓSTICO ──────────────────────────────────
        COUNTIF(DM IS NOT NULL)                                         AS n_DM,
        COUNTIF(dm_por_cid IS NOT NULL)                                 AS n_DM_por_cid,
        COUNTIF(dm_por_exames IS NOT NULL)                              AS n_DM_por_exames,
        COUNTIF(dm_por_progressao_pre_dm IS NOT NULL)                   AS n_DM_por_progressao,
        COUNTIF(dm_por_medicamento_forte IS NOT NULL)                   AS n_DM_por_medicamento,
        COUNTIF(DM_sem_CID = TRUE)                                      AS n_DM_sem_cid,
        COUNTIF(provavel_dm1 = TRUE)                                    AS n_DM1_provavel,
        COUNTIF(pre_DM IS NOT NULL)                                     AS n_pre_DM,

        -- ── DM: CONTROLE GLICÊMICO ───────────────────────────
        COUNTIF(DM IS NOT NULL AND DM_controlado = TRUE)                AS n_DM_controlado,
        COUNTIF(DM IS NOT NULL AND lacuna_DM_descontrolado = TRUE)      AS n_DM_descontrolado,
        COUNTIF(DM IS NOT NULL AND DM_melhorando = TRUE)                AS n_DM_melhorando,
        COUNTIF(DM IS NOT NULL AND DM_piorando = TRUE)                  AS n_DM_piorando,
        ROUND(AVG(CASE WHEN DM IS NOT NULL THEN pct_dias_dm_controlado_365d END), 1) AS media_pct_dm_ctrl,

        -- ── DM: HbA1c ────────────────────────────────────────
        COUNTIF(DM IS NOT NULL AND hba1c_atual IS NOT NULL)             AS n_DM_com_hba1c,
        COUNTIF(DM IS NOT NULL AND lacuna_DM_sem_HbA1c_recente = TRUE)  AS n_DM_sem_hba1c,
        COUNTIF(DM IS NOT NULL AND lacuna_DM_hba1c_nao_solicitado = TRUE) AS n_DM_hba1c_nao_sol,
        -- DM exames laboratoriais
        COUNTIF(DM IS NOT NULL AND lacuna_creatinina_HAS_DM = TRUE)       AS n_lac_dm_creatinina,
        COUNTIF(DM IS NOT NULL AND lacuna_colesterol_HAS_DM = TRUE)       AS n_lac_dm_colesterol,
        COUNTIF(DM IS NOT NULL AND lacuna_eas_HAS_DM = TRUE)              AS n_lac_dm_eas,
        COUNTIF(DM IS NOT NULL AND lacuna_ecg_HAS_DM = TRUE)              AS n_lac_dm_ecg,
        COUNTIF(DM IS NOT NULL AND lacuna_IMC_HAS_DM = TRUE)              AS n_lac_dm_imc,
        -- DM complicado / IRC
        COUNTIF(DM IS NOT NULL AND lacuna_IRC_sem_SGLT2 = TRUE)           AS n_lac_dm_irc_sglt2,
        COUNTIF(DM IS NOT NULL AND lacuna_DM_complicado_sem_SGLT2 = TRUE) AS n_lac_dm_comp_sglt2,
        -- Elegíveis SGLT2: total com IRC ou DM complicado (com e sem SGLT2)
        COUNTIF(DM IS NOT NULL AND IRC IS NOT NULL)                        AS n_dm_com_irc,
        COUNTIF(DM IS NOT NULL AND (ICC IS NOT NULL OR IRC IS NOT NULL OR CI IS NOT NULL)) AS n_dm_complicado_total,
        -- Com SGLT2 prescritos
        COUNTIF(DM IS NOT NULL AND IRC IS NOT NULL
                AND COALESCE(lacuna_IRC_sem_SGLT2, FALSE) = FALSE)         AS n_dm_irc_com_sglt2,
        COUNTIF(DM IS NOT NULL AND (ICC IS NOT NULL OR IRC IS NOT NULL OR CI IS NOT NULL)
                AND COALESCE(lacuna_DM_complicado_sem_SGLT2, FALSE) = FALSE) AS n_dm_comp_com_sglt2,
        ROUND(AVG(CASE WHEN DM IS NOT NULL THEN hba1c_atual END), 2)   AS media_hba1c,

        -- ── DM: LACUNAS ──────────────────────────────────────
        COUNTIF(lacuna_DM_microalbuminuria_nao_solicitado = TRUE)       AS n_lac_microalb,
        COUNTIF(lacuna_rastreio_DM_hipertenso = TRUE)                   AS n_lac_rastreio_dm_has,
        COUNTIF(lacuna_rastreio_DM_45mais = TRUE)                       AS n_lac_rastreio_dm_45,
        COUNTIF(lacuna_DM_sem_exame_pe_365d = TRUE)                     AS n_lac_pe_365d,
        COUNTIF(lacuna_DM_sem_exame_pe_180d = TRUE)                     AS n_lac_pe_180d,
        COUNTIF(lacuna_DM_nunca_teve_exame_pe = TRUE)                   AS n_lac_pe_nunca,

        -- ── ACESSO E CONTINUIDADE ─────────────────────────────
        COUNTIF(consultas_medicas_365d = 0)                             AS n_sem_consulta_medica_ano,
        COUNTIF(dias_desde_ultima_medica > 180)                         AS n_sem_medico_180d,
        COUNTIF(dias_desde_ultima_medica > 365)                         AS n_sem_medico_365d,
        -- Regularidade clínica: médico + enfermeiro + técnico (exclui ACS)
        COUNTIF((COALESCE(consultas_medicas_365d,0)
                 + COALESCE(consultas_enfermagem_365d,0)
                 + COALESCE(consultas_tecnico_enfermagem_365d,0)) >= 6)  AS n_regular,
        COUNTIF((COALESCE(consultas_medicas_365d,0)
                 + COALESCE(consultas_enfermagem_365d,0)
                 + COALESCE(consultas_tecnico_enfermagem_365d,0)) BETWEEN 3 AND 5) AS n_irregular,
        COUNTIF((COALESCE(consultas_medicas_365d,0)
                 + COALESCE(consultas_enfermagem_365d,0)
                 + COALESCE(consultas_tecnico_enfermagem_365d,0)) BETWEEN 1 AND 2) AS n_esporadico,
        COUNTIF((COALESCE(consultas_medicas_365d,0)
                 + COALESCE(consultas_enfermagem_365d,0)
                 + COALESCE(consultas_tecnico_enfermagem_365d,0)) = 0)   AS n_sem_acompanhamento,
        COUNTIF(baixa_longitudinalidade = TRUE)                         AS n_baixa_longitudinalidade,
        COUNTIF(alto_risco_baixo_acesso = TRUE)                         AS n_alto_risco_baixo_acesso,
        COUNTIF(usuario_frequente_urgencia = TRUE)                      AS n_freq_urgencia,
        COUNTIF(teve_internacao_365d = TRUE)                            AS n_internacao_365d,
        ROUND(AVG(intervalo_mediano_dias), 1)                           AS intervalo_mediano_medio,
        ROUND(AVG(consultas_medicas_365d), 1)                           AS media_consultas_ano

    FROM `rj-sms-sandbox.sub_pav_us.MM_2026_novos_cadastros_stopp_start`
    {where}
    """
    try:
        client = get_bigquery_client()
        df = client.query(sql).result().to_dataframe(create_bqstorage_client=False)
        if not df.empty:
            return {k: (int(v) if isinstance(v, float) and v == int(v) else
                        round(float(v), 2) if isinstance(v, float) else
                        int(v) if v is not None else 0)
                    for k, v in df.iloc[0].to_dict().items()}
    except Exception as e:
        st.error(f"❌ Erro ao carregar sumário clínico: {e}")
    return {}



@st.cache_data(show_spinner=False, ttl=900)
def carregar_resumo_pa(ap=None, clinica=None, esf=None) -> dict:
    """Agrega MM_pressao_arterial_historico por território — 1 aferição por paciente (mais recente)."""
    # Filtro territorial: busca CPFs do território na tabela fato
    clauses_fato = ["HAS IS NOT NULL"]
    if ap:      clauses_fato.append(f"area_programatica_cadastro = '{ap}'")
    if clinica: clauses_fato.append(f"nome_clinica_cadastro = '{clinica}'")
    if esf:     clauses_fato.append(f"nome_esf_cadastro = '{esf}'")
    where_fato = "WHERE " + " AND ".join(clauses_fato)
    sql = f"""
    WITH
    -- Passo 1: CPFs do território (tabela fato — rápido, já tem índices)
    cpfs_territorio AS (
        SELECT cpf, categoria_risco_final, idade
        FROM `rj-sms-sandbox.sub_pav_us.MM_2026_novos_cadastros_stopp_start`
        {where_fato}
    ),
    -- Passo 2: aferição mais recente por paciente (filtra por CPF)
    mais_recente AS (
        SELECT p.cpf, ct.idade, ct.categoria_risco_final,
               p.tem_has, p.tem_dm, p.tem_ci, p.tem_icc,
               p.tem_stroke, p.tem_irc, p.tem_has_alto_risco,
               p.meta_pas, p.meta_pad, p.pas, p.pad,
               p.data_afericao, p.dias_desde_afericao,
               p.recencia, p.controle_pa, p.tendencia_pas,
               p.classificacao_pa, p.pa_elevada_sem_has
        FROM `rj-sms-sandbox.sub_pav_us.MM_pressao_arterial_historico` p
        INNER JOIN cpfs_territorio ct ON p.cpf = ct.cpf
        QUALIFY ROW_NUMBER() OVER (PARTITION BY p.cpf ORDER BY p.data_afericao DESC) = 1
    )
    SELECT
        COUNT(*)                                                    AS n_has,
        -- Recência da última aferição
        COUNTIF(dias_desde_afericao <= 90)                          AS n_afericao_90d,
        COUNTIF(dias_desde_afericao BETWEEN 91 AND 180)             AS n_afericao_91_180d,
        COUNTIF(dias_desde_afericao BETWEEN 181 AND 365)            AS n_afericao_181_365d,
        COUNTIF(dias_desde_afericao > 365)                          AS n_afericao_mais_365d,
        -- Controle geral
        COUNTIF(controle_pa = 'controlado')                         AS n_ctrl,
        COUNTIF(controle_pa = 'nao_controlado')                     AS n_nao_ctrl,
        -- Controle por faixa etária (meta individualizada — consistente com bloco 2)
        COUNTIF(idade < 80)                                         AS n_menor80,
        COUNTIF(idade < 80 AND controle_pa = 'controlado')          AS n_ctrl_menor80,
        COUNTIF(idade < 80 AND controle_pa = 'nao_controlado')      AS n_nctrl_menor80,
        COUNTIF(idade >= 80)                                        AS n_80mais,
        COUNTIF(idade >= 80 AND controle_pa = 'controlado')         AS n_ctrl_80mais,
        COUNTIF(idade >= 80 AND controle_pa = 'nao_controlado')     AS n_nctrl_80mais,
        -- Tendência
        COUNTIF(tendencia_pas = 'melhorando')                       AS n_mel,
        COUNTIF(tendencia_pas = 'piorando')                         AS n_pio,
        COUNTIF(tendencia_pas = 'controlado_estavel')               AS n_ctrl_estavel,
        COUNTIF(tendencia_pas = 'estavel')                          AS n_est,
        COUNTIF(tendencia_pas = 'sem_referencia')                   AS n_sem_ref,
        -- Classificação da PA
        COUNTIF(classificacao_pa = 'Normal')                        AS n_pa_normal,
        COUNTIF(classificacao_pa = 'Elevada')                       AS n_pa_elevada,
        COUNTIF(classificacao_pa = 'HAS Grau 1')                    AS n_has_grau1,
        COUNTIF(classificacao_pa = 'HAS Grau 2')                    AS n_has_grau2,
        COUNTIF(classificacao_pa = 'HAS Grau 3 / Crise')            AS n_has_grau3,
        -- Comorbidades — grupos individuais
        COUNTIF(tem_dm OR tem_irc OR tem_ci OR tem_icc OR tem_stroke) AS n_has_com_comorbidades,
        COUNTIF(tem_dm = TRUE)                                      AS n_tem_dm,
        COUNTIF(tem_irc = TRUE)                                     AS n_tem_irc,
        COUNTIF(tem_ci = TRUE)                                      AS n_tem_ci,
        COUNTIF(tem_icc = TRUE)                                     AS n_tem_icc,
        COUNTIF(tem_stroke = TRUE)                                  AS n_tem_avc,
        -- Intersecções par a par (para Venn)
        COUNTIF(tem_dm AND tem_irc)                                 AS n_dm_irc,
        COUNTIF(tem_dm AND tem_ci)                                  AS n_dm_ci,
        COUNTIF(tem_dm AND tem_icc)                                 AS n_dm_icc,
        COUNTIF(tem_dm AND tem_stroke)                              AS n_dm_avc,
        COUNTIF(tem_irc AND tem_ci)                                 AS n_irc_ci,
        COUNTIF(tem_irc AND tem_icc)                                AS n_irc_icc,
        COUNTIF(tem_irc AND tem_stroke)                             AS n_irc_avc,
        COUNTIF(tem_ci AND tem_icc)                                 AS n_ci_icc,
        COUNTIF(tem_ci AND tem_stroke)                              AS n_ci_avc,
        COUNTIF(tem_icc AND tem_stroke)                             AS n_icc_avc,
        -- Triplas mais relevantes
        COUNTIF(tem_dm AND tem_ci AND tem_icc)                      AS n_dm_ci_icc,
        COUNTIF(tem_dm AND tem_irc AND tem_ci)                      AS n_dm_irc_ci,
        COUNTIF(tem_dm AND tem_irc AND tem_icc)                     AS n_dm_irc_icc,
        -- Apenas 1 comorbidade (exclusivos)
        COUNTIF(tem_dm AND NOT tem_irc AND NOT tem_ci
                AND NOT tem_icc AND NOT tem_stroke)                 AS n_so_dm,
        COUNTIF(tem_irc AND NOT tem_dm AND NOT tem_ci
                AND NOT tem_icc AND NOT tem_stroke)                 AS n_so_irc,
        COUNTIF(tem_ci AND NOT tem_dm AND NOT tem_irc
                AND NOT tem_icc AND NOT tem_stroke)                 AS n_so_ci,
        COUNTIF(tem_icc AND NOT tem_dm AND NOT tem_irc
                AND NOT tem_ci AND NOT tem_stroke)                  AS n_so_icc,
        COUNTIF(tem_stroke AND NOT tem_dm AND NOT tem_irc
                AND NOT tem_ci AND NOT tem_icc)                     AS n_so_avc,
        -- Risco cardiovascular — escore de Framingham com reclassificação SBC
        COUNTIF(categoria_risco_final = 'MUITO ALTO')               AS n_risco_muito_alto,
        COUNTIF(categoria_risco_final = 'ALTO')                     AS n_risco_alto,
        COUNTIF(categoria_risco_final = 'INTERMEDIÁRIO')            AS n_risco_intermediario,
        COUNTIF(categoria_risco_final = 'BAIXO')                    AS n_risco_baixo,
        -- Médias
        ROUND(AVG(pas), 1)                                          AS media_pas,
        ROUND(AVG(pad), 1)                                          AS media_pad
    FROM mais_recente
    """
    try:
        client = get_bigquery_client()
        df = client.query(sql).result().to_dataframe(create_bqstorage_client=False)
        return df.iloc[0].to_dict() if not df.empty else {}
    except Exception as e:
        st.error(f"❌ Erro ao carregar resumo PA: {e}")
        return {}


@st.cache_data(show_spinner=False, ttl=900)
def carregar_resumo_hba1c(ap=None, clinica=None, esf=None) -> dict:
    """Agrega MM_glicemia_hba1c_historico — HbA1c mais recente por paciente."""
    # Filtro territorial: busca CPFs do território na tabela fato
    clauses_fato_h = []
    if ap:      clauses_fato_h.append(f"area_programatica_cadastro = '{ap}'")
    if clinica: clauses_fato_h.append(f"nome_clinica_cadastro = '{clinica}'")
    if esf:     clauses_fato_h.append(f"nome_esf_cadastro = '{esf}'")
    where_fato_h = ("WHERE " + " AND ".join(clauses_fato_h)) if clauses_fato_h else ""
    sql = f"""
    WITH
    -- Passo 1: CPFs do território com DM (tabela fato — rápido)
    cpfs_dm AS (
        SELECT cpf
        FROM `rj-sms-sandbox.sub_pav_us.MM_2026_novos_cadastros_stopp_start`
        {where_fato_h}
    ),
    -- Passo 2: todos os CPFs do território (para rastreio incorreto)
    cpfs_todos AS (
        SELECT cpf
        FROM `rj-sms-sandbox.sub_pav_us.MM_2026_novos_cadastros_stopp_start`
        {where_fato_h}
    ),
    -- Passo 3: HbA1c mais recente por paciente do território
    mais_recente AS (
        SELECT g.cpf, g.tem_dm, g.tem_pre_dm, g.tem_has, g.tem_dm_complicado,
               g.tem_ci, g.tem_icc, g.tem_stroke, g.tem_irc,
               g.valor, g.data_exame, g.dias_desde_exame, g.recencia,
               g.interpretacao_hba1c, g.hba1c_em_nao_diabetico, g.meta_hba1c
        FROM `rj-sms-sandbox.sub_pav_us.MM_glicemia_hba1c_historico` g
        INNER JOIN cpfs_todos ct ON g.cpf = ct.cpf
        WHERE g.tipo_exame = 'hba1c'
        QUALIFY ROW_NUMBER() OVER (PARTITION BY g.cpf ORDER BY g.data_exame DESC) = 1
    ),
    -- Passo 4: diabéticos do território sem nenhuma HbA1c
    diabeticos_sem_hba1c AS (
        SELECT c.cpf
        FROM cpfs_dm c
        INNER JOIN `rj-sms-sandbox.sub_pav_us.MM_2026_novos_cadastros_stopp_start` f
            ON c.cpf = f.cpf
        WHERE f.DM IS NOT NULL
          AND c.cpf NOT IN (SELECT cpf FROM mais_recente)
    )
    SELECT
        -- Diabéticos por recência do exame
        COUNTIF(tem_dm AND recencia = 'ate_180d')                   AS n_dm_hba1c_180d,
        COUNTIF(tem_dm AND recencia = 'ate_365d')                   AS n_dm_hba1c_365d,
        COUNTIF(tem_dm AND recencia = 'mais_de_365d')               AS n_dm_hba1c_antiga,
        (SELECT COUNT(*) FROM diabeticos_sem_hba1c)                 AS n_dm_nunca_hba1c,
        -- Controle glicêmico (apenas exames ≤ 180 dias)
        COUNTIF(tem_dm AND recencia = 'ate_180d'
                AND interpretacao_hba1c = 'dm_controlado')          AS n_ctrl,
        COUNTIF(tem_dm AND recencia = 'ate_180d'
                AND interpretacao_hba1c = 'dm_nao_controlado')      AS n_nao_ctrl,
        COUNTIF(tem_dm AND dias_desde_exame <= 365
                AND interpretacao_hba1c = 'dm_controlado')          AS n_trend_ctrl,
        -- Valores médios
        ROUND(AVG(CASE WHEN tem_dm AND recencia = 'ate_180d'
                       THEN valor END), 2)                          AS media_hba1c_dm_recente,
        ROUND(AVG(CASE WHEN tem_dm THEN valor END), 2)              AS media_hba1c_dm_total,
        -- Rastreio incorreto
        COUNTIF(hba1c_em_nao_diabetico = TRUE)                      AS n_rastreio_incorreto,
        COUNTIF(hba1c_em_nao_diabetico AND interpretacao_hba1c = 'rastreio_normal')       AS n_rastreio_normal,
        COUNTIF(hba1c_em_nao_diabetico AND interpretacao_hba1c = 'rastreio_pre_diabetes') AS n_rastreio_pre_dm,
        COUNTIF(hba1c_em_nao_diabetico AND interpretacao_hba1c = 'rastreio_provavel_dm')  AS n_rastreio_provavel_dm,
        -- DM complicado
        COUNTIF(tem_dm_complicado = TRUE)                           AS n_dm_complicado,
        -- ── Comorbidades em diabéticos (para heatmap) ─────────────
        -- Totais isolados (dentro dos diabéticos)
        COUNTIF(tem_dm AND tem_has)                                 AS n_dm_has,
        COUNTIF(tem_dm AND tem_irc)                                 AS n_dm_irc,
        COUNTIF(tem_dm AND tem_ci)                                  AS n_dm_ci,
        COUNTIF(tem_dm AND tem_icc)                                 AS n_dm_icc,
        COUNTIF(tem_dm AND tem_stroke)                              AS n_dm_avc,
        -- Pares (dentro dos diabéticos)
        COUNTIF(tem_dm AND tem_has AND tem_irc)                     AS n_dm_has_irc,
        COUNTIF(tem_dm AND tem_has AND tem_ci)                      AS n_dm_has_ci,
        COUNTIF(tem_dm AND tem_has AND tem_icc)                     AS n_dm_has_icc,
        COUNTIF(tem_dm AND tem_has AND tem_stroke)                  AS n_dm_has_avc,
        COUNTIF(tem_dm AND tem_irc AND tem_ci)                      AS n_dm_irc_ci,
        COUNTIF(tem_dm AND tem_irc AND tem_icc)                     AS n_dm_irc_icc,
        COUNTIF(tem_dm AND tem_irc AND tem_stroke)                  AS n_dm_irc_avc,
        COUNTIF(tem_dm AND tem_ci  AND tem_icc)                     AS n_dm_ci_icc,
        COUNTIF(tem_dm AND tem_ci  AND tem_stroke)                  AS n_dm_ci_avc,
        COUNTIF(tem_dm AND tem_icc AND tem_stroke)                  AS n_dm_icc_avc,
        -- Todas as 5
        COUNTIF(tem_dm AND tem_has AND tem_irc AND tem_ci
                AND tem_icc AND tem_stroke)                         AS n_dm_todas5
    FROM mais_recente
    """
    try:
        client = get_bigquery_client()
        df = client.query(sql).result().to_dataframe(create_bqstorage_client=False)
        return df.iloc[0].to_dict() if not df.empty else {}
    except Exception as e:
        st.error(f"❌ Erro ao carregar resumo HbA1c: {e}")
        return {}

@st.cache_data(show_spinner=False, ttl=900)
def carregar_sumario_por_territorio(ap=None, clinica=None, esf=None) -> pd.DataFrame:
    """
    Retorna 1 linha por unidade geográfica com indicadores de HAS, DM e Acesso em %.
    Nível automático: sem filtro→AP; AP selecionada→Clínica; Clínica selecionada→ESF.
    """
    if clinica:
        grupo_col = "nome_esf_cadastro"
        label_col = "ESF"
    elif ap:
        grupo_col = "nome_clinica_cadastro"
        label_col = "Clínica"
    else:
        grupo_col = "area_programatica_cadastro"
        label_col = "AP"

    clauses = []
    if ap:      clauses.append(f"area_programatica_cadastro = '{ap}'")
    if clinica: clauses.append(f"nome_clinica_cadastro = '{clinica}'")
    if esf:     clauses.append(f"nome_esf_cadastro = '{esf}'")
    clauses.append(f"{grupo_col} IS NOT NULL")
    where = "WHERE " + " AND ".join(clauses)

    sql = f"""
    SELECT
        {grupo_col}                                                              AS territorio,
        COUNT(*)                                                                 AS total_pop,
        -- HAS controle
        ROUND(COUNTIF(HAS IS NOT NULL AND status_controle_pressorio = 'controlado')
              * 100.0 / NULLIF(COUNTIF(HAS IS NOT NULL), 0), 1)                  AS pct_has_ctrl,
        ROUND(COUNTIF(HAS IS NOT NULL AND status_controle_pressorio = 'descontrolado')
              * 100.0 / NULLIF(COUNTIF(HAS IS NOT NULL), 0), 1)                  AS pct_has_desctrl,
        ROUND(COUNTIF(HAS IS NOT NULL AND status_controle_pressorio IS NULL)
              * 100.0 / NULLIF(COUNTIF(HAS IS NOT NULL), 0), 1)                  AS pct_has_seminfo,
        -- HAS tendência
        ROUND(COUNTIF(HAS IS NOT NULL AND tendencia_pa = 'melhorando')
              * 100.0 / NULLIF(COUNTIF(HAS IS NOT NULL), 0), 1)                  AS pct_has_mel,
        ROUND(COUNTIF(HAS IS NOT NULL AND tendencia_pa = 'estavel')
              * 100.0 / NULLIF(COUNTIF(HAS IS NOT NULL), 0), 1)                  AS pct_has_est,
        ROUND(COUNTIF(HAS IS NOT NULL AND tendencia_pa = 'piorando')
              * 100.0 / NULLIF(COUNTIF(HAS IS NOT NULL), 0), 1)                  AS pct_has_pio,
        -- DM controle
        ROUND(COUNTIF(DM IS NOT NULL AND DM_controlado = TRUE)
              * 100.0 / NULLIF(COUNTIF(DM IS NOT NULL), 0), 1)                   AS pct_dm_ctrl,
        ROUND(COUNTIF(DM IS NOT NULL AND lacuna_DM_descontrolado = TRUE)
              * 100.0 / NULLIF(COUNTIF(DM IS NOT NULL), 0), 1)                   AS pct_dm_desctrl,
        ROUND(COUNTIF(DM IS NOT NULL AND DM_controlado IS NULL AND lacuna_DM_descontrolado IS NULL)
              * 100.0 / NULLIF(COUNTIF(DM IS NOT NULL), 0), 1)                   AS pct_dm_seminfo,
        -- DM tendência
        ROUND(COUNTIF(DM IS NOT NULL AND DM_melhorando = TRUE)
              * 100.0 / NULLIF(COUNTIF(DM IS NOT NULL), 0), 1)                   AS pct_dm_mel,
        ROUND(COUNTIF(DM IS NOT NULL AND DM_piorando = TRUE)
              * 100.0 / NULLIF(COUNTIF(DM IS NOT NULL), 0), 1)                   AS pct_dm_pio,
        -- Acesso: regularidade clínica (médico + enfermeiro + técnico de enfermagem — exclui ACS)
        -- Usamos a soma de consultas clínicas nos últimos 365 dias como proxy de regularidade.
        -- Cortes equivalentes aos da tabela fato, mas restritos a profissionais clínicos:
        --   Regular    → ≥ 6 consultas clínicas no ano  (≈ bimestral ou mais frequente)
        --   Irregular  → 3 a 5 consultas clínicas no ano
        --   Esporádico → 1 a 2 consultas clínicas no ano
        --   Sem acomp. → 0 consultas clínicas no ano
        ROUND(COUNTIF(
            (COALESCE(consultas_medicas_365d,0)
             + COALESCE(consultas_enfermagem_365d,0)
             + COALESCE(consultas_tecnico_enfermagem_365d,0)) >= 6)
              * 100.0 / COUNT(*), 1)                                              AS pct_regular,
        ROUND(COUNTIF(
            (COALESCE(consultas_medicas_365d,0)
             + COALESCE(consultas_enfermagem_365d,0)
             + COALESCE(consultas_tecnico_enfermagem_365d,0)) BETWEEN 3 AND 5)
              * 100.0 / COUNT(*), 1)                                              AS pct_irregular,
        ROUND(COUNTIF(
            (COALESCE(consultas_medicas_365d,0)
             + COALESCE(consultas_enfermagem_365d,0)
             + COALESCE(consultas_tecnico_enfermagem_365d,0)) BETWEEN 1 AND 2)
              * 100.0 / COUNT(*), 1)                                              AS pct_esporadico,
        ROUND(COUNTIF(
            (COALESCE(consultas_medicas_365d,0)
             + COALESCE(consultas_enfermagem_365d,0)
             + COALESCE(consultas_tecnico_enfermagem_365d,0)) = 0)
              * 100.0 / COUNT(*), 1)                                              AS pct_sem_acomp,
        -- HAS prevalência + stacked absoluto (para barra total = % HAS na AP)
        ROUND(COUNTIF(HAS IS NOT NULL) * 100.0 / COUNT(*), 1)                     AS pct_has_pop,
        ROUND(COUNTIF(HAS IS NOT NULL AND status_controle_pressorio = 'controlado')
              * 100.0 / COUNT(*), 1)                                               AS pct_has_ctrl_pop,
        ROUND(COUNTIF(HAS IS NOT NULL AND status_controle_pressorio = 'descontrolado')
              * 100.0 / COUNT(*), 1)                                               AS pct_has_desctrl_pop,
        ROUND(COUNTIF(HAS IS NOT NULL
                      AND (status_controle_pressorio IS NULL
                           OR status_controle_pressorio NOT IN ('controlado','descontrolado')))
              * 100.0 / COUNT(*), 1)                                               AS pct_has_seminfo_pop,
        ROUND(COUNTIF(HAS IS NOT NULL AND tendencia_pa = 'melhorando')
              * 100.0 / COUNT(*), 1)                                               AS pct_has_mel_pop,
        ROUND(COUNTIF(HAS IS NOT NULL AND tendencia_pa = 'estavel')
              * 100.0 / COUNT(*), 1)                                               AS pct_has_est_pop,
        ROUND(COUNTIF(HAS IS NOT NULL AND tendencia_pa = 'piorando')
              * 100.0 / COUNT(*), 1)                                               AS pct_has_pio_pop,
        -- DM prevalência + stacked absoluto
        ROUND(COUNTIF(DM IS NOT NULL) * 100.0 / COUNT(*), 1)                      AS pct_dm_pop,
        ROUND(COUNTIF(DM IS NOT NULL AND DM_controlado = TRUE)
              * 100.0 / COUNT(*), 1)                                               AS pct_dm_ctrl_pop,
        ROUND(COUNTIF(DM IS NOT NULL AND COALESCE(lacuna_DM_descontrolado, FALSE) = TRUE)
              * 100.0 / COUNT(*), 1)                                               AS pct_dm_desctrl_pop,
        ROUND(COUNTIF(DM IS NOT NULL
                      AND COALESCE(DM_controlado, FALSE) = FALSE
                      AND COALESCE(lacuna_DM_descontrolado, FALSE) = FALSE)
              * 100.0 / COUNT(*), 1)                                               AS pct_dm_seminfo_pop,
        -- DM recência HbA1c (janelas temporais — para gráfico de barras)
        ROUND(COUNTIF(DM IS NOT NULL
                      AND dias_desde_ultima_hba1c IS NOT NULL
                      AND dias_desde_ultima_hba1c <= 180)
              * 100.0 / COUNT(*), 1)                                               AS pct_dm_hba1c_180d_pop,
        ROUND(COUNTIF(DM IS NOT NULL
                      AND dias_desde_ultima_hba1c IS NOT NULL
                      AND dias_desde_ultima_hba1c BETWEEN 181 AND 365)
              * 100.0 / COUNT(*), 1)                                               AS pct_dm_hba1c_365d_pop,
        ROUND(COUNTIF(DM IS NOT NULL
                      AND dias_desde_ultima_hba1c IS NOT NULL
                      AND dias_desde_ultima_hba1c > 365)
              * 100.0 / COUNT(*), 1)                                               AS pct_dm_hba1c_ant_pop,
        ROUND(COUNTIF(DM IS NOT NULL
                      AND dias_desde_ultima_hba1c IS NULL)
              * 100.0 / COUNT(*), 1)                                               AS pct_dm_hba1c_nunca_pop,
        ROUND(COUNTIF(DM IS NOT NULL AND DM_melhorando = TRUE)
              * 100.0 / COUNT(*), 1)                                               AS pct_dm_mel_pop,
        ROUND(COUNTIF(DM IS NOT NULL
                      AND COALESCE(DM_melhorando, FALSE) = FALSE
                      AND COALESCE(DM_piorando, FALSE) = FALSE)
              * 100.0 / COUNT(*), 1)                                               AS pct_dm_est_pop,
        ROUND(COUNTIF(DM IS NOT NULL AND DM_piorando = TRUE)
              * 100.0 / COUNT(*), 1)                                               AS pct_dm_pio_pop,
        -- Indicadores de acesso
        ROUND(COUNTIF(consultas_medicas_365d = 0)
              * 100.0 / COUNT(*), 1)                                              AS pct_sem_consulta,
        ROUND(COUNTIF(dias_desde_ultima_medica > 180)
              * 100.0 / COUNT(*), 1)                                              AS pct_sem_medico_180d,
        ROUND(COUNTIF(dias_desde_ultima_medica > 365)
              * 100.0 / COUNT(*), 1)                                              AS pct_sem_medico_365d,
        ROUND(COUNTIF(usuario_frequente_urgencia = TRUE)
              * 100.0 / COUNT(*), 1)                                              AS pct_freq_urgencia,
        ROUND(COUNTIF(baixa_longitudinalidade = TRUE)
              * 100.0 / COUNT(*), 1)                                              AS pct_baixa_longitudinalidade
    FROM `rj-sms-sandbox.sub_pav_us.MM_2026_novos_cadastros_stopp_start`
    {where}
    GROUP BY {grupo_col}
    ORDER BY {grupo_col}
    """
    try:
        client = get_bigquery_client()
        df = client.query(sql).result().to_dataframe(create_bqstorage_client=False)
        df['label_col'] = '{label_col}'
        return df
    except Exception as e:
        st.error(f"❌ Erro ao carregar sumário por território: {{e}}")
        return pd.DataFrame()

# ============================================
# CARREGAR DADOS COM MEDIÇÃO DETALHADA
# ============================================

import time

## st.write("### ⏱️ Medindo Performance...")

# 1. Teste: Carregar métricas agregadas (deveria ser instantâneo)
inicio_metricas = time.time()
metricas = carregar_metricas_resumo(
    ap=territorio['ap'],
    clinica=territorio['clinica'],
    esf=territorio['esf']
)
fim_metricas = time.time()
tempo_metricas = fim_metricas - inicio_metricas

st.sidebar.info(f"⚡ Métricas: **{tempo_metricas:.2f}s**")

# 2. Teste: Carregar dados completos
inicio_dados = time.time()

with st.spinner("🔄 Carregando dados da população..."):
    df_dados = carregar_dados_piramides(
        ap=territorio['ap'],
        clinica=territorio['clinica'],
        esf=territorio['esf']
    )

fim_dados = time.time()
tempo_dados = fim_dados - inicio_dados

st.sidebar.warning(f"\U0001f40c Dados completos: **{tempo_dados:.2f}s**")

# Carregar sumário clínico (tabela fato)
with st.spinner("🔬 Carregando indicadores clínicos..."):
    sumario = carregar_sumario_clinico(
        ap=territorio['ap'],
        clinica=territorio['clinica'],
        esf=territorio['esf']
    )
    resumo_pa   = carregar_resumo_pa(
        ap=territorio['ap'],
        clinica=territorio['clinica'],
        esf=territorio['esf']
    )
    resumo_hba1c = carregar_resumo_hba1c(
        ap=territorio['ap'],
        clinica=territorio['clinica'],
        esf=territorio['esf']
    )

with st.spinner("📊 Carregando dados por território..."):
    df_terr = carregar_sumario_por_territorio(
        ap=territorio['ap'],
        clinica=territorio['clinica'],
        esf=territorio['esf']
    )
    # Anonimizar nomes no eixo X dos gráficos de território
    if MODO_ANONIMO and not df_terr.empty and 'territorio' in df_terr.columns:
        if territorio['clinica']:
            df_terr['territorio'] = df_terr['territorio'].apply(anonimizar_esf)
        elif territorio['ap']:
            df_terr['territorio'] = df_terr['territorio'].apply(anonimizar_clinica)
        else:
            df_terr['territorio'] = df_terr['territorio'].apply(lambda x: anonimizar_ap(str(x)))

# Diagnóstico
if tempo_dados > 10:
    st.sidebar.error("⚠️ Carregamento MUITO lento! Veja possíveis causas:")
    st.sidebar.write("1. Conexão lenta com BigQuery")
    st.sidebar.write("2. Tabela sem índices/particionamento")
    st.sidebar.write("3. Região do BigQuery distante")

# ============================================
# MÉTRICAS GERAIS (TOPO)
# ============================================

metricas = carregar_metricas_resumo(
    ap=territorio['ap'],
    clinica=territorio['clinica'],
    esf=territorio['esf']
)

total_pop = int(metricas['total_pop'])
multimorbidos = int(metricas['multimorbidos'])
polifarmacia = int(metricas['polifarmacia'])
hiperpolifarmacia = int(metricas['hiperpolifarmacia'])

pct_multi = (multimorbidos / total_pop * 100) if total_pop > 0 else 0
pct_poli = (polifarmacia / total_pop * 100) if total_pop > 0 else 0
pct_hiper = (hiperpolifarmacia / total_pop * 100) if total_pop > 0 else 0

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric("👥 População Total", f"{total_pop:,}")

with col2:
    st.metric("🏥 Multimorbidade", f"{pct_multi:.1f}%", help=f"{multimorbidos:,} pacientes com 2+ morbidades")

with col3:
    st.metric("💊 Polifarmácia", f"{pct_poli:.1f}%", help=f"{polifarmacia:,} pacientes com 5-9 medicamentos")

with col4:
    st.metric("⚠️ Hiperpolifarmácia", f"{pct_hiper:.1f}%", help=f"{hiperpolifarmacia:,} pacientes com 10+ medicamentos")

st.markdown("---")






def _stacked_bar_ap(df, cols_pop, labels, cores, titulo,
                    eixo_y='% da população total'):
    """
    Stacked bar por AP onde altura total = % da condição na população.
    cols_pop: colunas em % da população total (não % dos doentes).
    """
    if df is None or df.empty:
        st.info("Sem dados por território.")
        return
    import re
    def _ord(v):
        m = re.search(r"(\d+\.?\d*)", str(v))
        return float(m.group(1)) if m else 999
    df_s = df.copy()
    df_s['_ord'] = df_s['territorio'].apply(_ord)
    df_s = df_s.sort_values('_ord')
    terrs = [str(t) for t in df_s['territorio'].tolist()]

    fig = go.Figure()
    for col, label, cor in zip(cols_pop, labels, cores):
        vals = df_s[col].tolist() if col in df_s.columns else [0]*len(terrs)
        fig.add_trace(go.Bar(
            name=label, x=terrs, y=vals,
            marker_color=cor,
            text=[f"{v:.1f}%" for v in vals],
            textposition='inside',
            textfont=dict(size=9, color=T.TEXT),
        ))
    fig.update_layout(
        barmode='stack',
        height=340,
        bargap=0.35,
        margin=dict(l=10, r=160, t=50, b=60 if len(terrs) <= 12 else 130),
        paper_bgcolor=T.PAPER_BG,
        plot_bgcolor=T.PLOT_BG,
        title=dict(text=titulo, font=dict(color=T.TEXT, size=13)),
        xaxis=dict(
            type='category', categoryorder='array', categoryarray=terrs,
            tickfont=dict(color=T.TEXT, size=10),
            tickangle=-35,
        ),
        yaxis=dict(
            title=eixo_y,
            tickfont=dict(color=T.TEXT_MUTED, size=10),
            gridcolor=T.GRID,
            range=[0, 40],
        ),
        legend=dict(
            orientation='v', xanchor='left', x=1.01,
            yanchor='middle', y=0.5,
            font=dict(color=T.TEXT, size=11),
            bgcolor=T.LEGEND_BG,
            bordercolor=T.LEGEND_BORDER, borderwidth=1,
        ),
    )
    st.plotly_chart(fig, use_container_width=True)

# ── Helper: grouped bar por território ───────────────────────
def _grouped_bar_territorio(df, cols, labels, cores, titulo, eixo_y='% dos pacientes',
                            legenda_baixo=False):
    """
    Grouped bar: eixo X = território (sempre categórico).
    APs são ordenadas numericamente mas tratadas como strings no eixo.
    legenda_baixo=True move a legenda para abaixo do gráfico (útil com labels longas).
    """
    if df is None or df.empty:
        st.info("Sem dados por território para o filtro selecionado.")
        return
    import re

    def _ord(v):
        m = re.search(r"(\d+\.?\d*)", str(v))
        return float(m.group(1)) if m else 999

    df_s = df.copy()
    df_s['_ord'] = df_s['territorio'].apply(_ord)
    df_s = df_s.sort_values('_ord')

    # Eixo X sempre como string categórica — nunca contínuo
    terrs = [str(t) for t in df_s['territorio'].tolist()]

    fig = go.Figure()
    for col, label, cor in zip(cols, labels, cores):
        vals = df_s[col].tolist() if col in df_s.columns else [0] * len(terrs)
        fig.add_trace(go.Bar(
            name=label,
            x=terrs,
            y=vals,
            marker_color=cor,
            text=[f"{v:.1f}%" for v in vals],
            textposition='outside',
            textfont=dict(size=9),
        ))

    if legenda_baixo:
        legend_cfg = dict(
            orientation='h',
            xanchor='center', x=0.5,
            yanchor='top',    y=-0.22,
            font=dict(color=T.TEXT, size=11),
            bgcolor=T.LEGEND_BG,
            bordercolor=T.LEGEND_BORDER, borderwidth=1,
            traceorder='normal',
        )
        altura     = 520
        margin_b   = 180 if len(terrs) <= 12 else 220
        margin_r   = 10
    else:
        legend_cfg = dict(
            orientation='v',
            xanchor='left', x=1.01,
            yanchor='middle', y=0.5,
            font=dict(color=T.TEXT, size=11),
            bgcolor=T.LEGEND_BG,
            bordercolor=T.LEGEND_BORDER, borderwidth=1,
        )
        altura   = 420
        margin_b = 60 if len(terrs) <= 12 else 130
        margin_r = 160

    fig.update_layout(
        barmode='group',
        height=altura,
        bargap=0.25,
        bargroupgap=0.06,
        margin=dict(l=10, r=margin_r, t=50, b=margin_b),
        paper_bgcolor=T.PAPER_BG,
        plot_bgcolor=T.PLOT_BG,
        title=dict(text=titulo, font=dict(color=T.TEXT, size=13)),
        xaxis=dict(
            type='category',
            categoryorder='array',
            categoryarray=terrs,
            tickfont=dict(color=T.TEXT, size=11 if len(terrs) <= 12 else 9),
            tickangle=0 if len(terrs) <= 12 else -40,
        ),
        yaxis=dict(
            title=eixo_y,
            tickfont=dict(color=T.TEXT_MUTED, size=11),
            gridcolor=T.GRID,
            range=[0, 62],
        ),
        legend=legend_cfg,
    )
    st.plotly_chart(fig, use_container_width=True)

# ============================================
# TABS COM VISUALIZAÇÕES
# ============================================

# st.tabs para navegação visual — sincronizado com o radio da sidebar
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(NOMES_ABAS)

# TAB 1 — Perfil da População (pirâmide + morbidades prevalentes)
with tab1:
    # ── Pirâmide populacional ─────────────────────────────────────
    fig_piramide = criar_piramide_populacional(df_dados)
    if fig_piramide:
        st.plotly_chart(fig_piramide, use_container_width=True, key='piramide_morb')
    else:
        st.error("Erro ao criar pirâmide")

    st.markdown("---")

    # ── Morbidades prevalentes ────────────────────────────────────
    st.markdown("### 🏥 Condições de Saúde Mais Prevalentes")

    fig_prev, df_prevalencias = criar_visualizacao_morbidades_prevalentes(df_dados)

    if fig_prev is not None and df_prevalencias is not None:
        st.plotly_chart(fig_prev, use_container_width=True, key='grafico_prevalencias')

        st.markdown("---")
        st.markdown(f"### 📋 Detalhamento por Categoria")

        for categoria in ORDEM_CATEGORIAS:
            df_cat = df_prevalencias[df_prevalencias['Categoria'] == categoria]

            if df_cat.empty:
                continue

            df_cat = df_cat.sort_values('Prevalência (%)', ascending=False)
            icone = ICONES_CATEGORIAS_CONSOLIDADAS.get(categoria, '📌')
            st.markdown(f"## {icone} {categoria}")

            cols = st.columns(3)
            for idx, row in df_cat.iterrows():
                col_idx = df_cat.index.get_loc(idx) % 3

                with cols[col_idx]:
                    if row['Prevalência (%)'] >= 20:
                        cor = '🔴'
                        delta_color = 'inverse'
                    elif row['Prevalência (%)'] >= 10:
                        cor = '🟠'
                        delta_color = 'inverse'
                    elif row['Prevalência (%)'] >= 5:
                        cor = '🟡'
                        delta_color = 'off'
                    else:
                        cor = '🔵'
                        delta_color = 'normal'

                    with st.container(border=True):
                        st.markdown(f"**{cor} {row['Condição']}**")
                        st.metric(
                            label="Pacientes",
                            value=f"{row['N']:,}",
                            delta=f"{row['Prevalência (%)']}%",
                            delta_color=delta_color
                        )
                        st.caption(row['Descrição'])

            st.markdown("<br>", unsafe_allow_html=True)
    else:
        st.error("⚠️ Nenhuma condição encontrada")


# TAB 2 — CARGA DE MORBIDADE
with tab2:
    st.markdown("### 📈 Carga de Morbidade")

    # ── BLOCO 1: Explicação e pontuação ─────────────────────────
    st.markdown("""
A Carga de Morbidade aqui apresentada é um escore composto que combina informações sobre
idade dos pacientes, morbidades e fármacos em uso. Foi criada a partir de três escalas
internacionalmente consagradas e que capturam dimensões complementares da complexidade
clínica: a **Charlson Comorbidity Index (CCI)**, a
**Cumulative Illness Rating Scale-Geriatric (CIRS-G)** e a
**Elixhauser Comorbidity Index**. Estas escalas foram largamente utilizadas para estimar
riscos de ocorrência de eventos adversos em internações hospitalares.

---

**⚙️ Como o escore é calculado neste Navegador**

O escore integrado combina três componentes:

| Componente | Critério | Pontuação |
|---|---|---|
| **Morbidades** | Cada condição crônica pesa de 1 a 6 pontos conforme gravidade (baseado no CCI) | 1–6 por condição |
| **Idade** | <40a: 0 · 40–49a: 1 · 50–59a: 2 · 60–69a: 3 · 70–79a: 4 · ≥80a: 5 | 0–5 |
| **Polifarmácia** | 0–4 medicamentos: 0 · 5–9 medicamentos: 1 · ≥10 medicamentos: 2 | 0–2 |

**Pesos das morbidades:**
- **Peso 1:** HAS, arritmia, doença valvular, circulação pulmonar, doença vascular periférica,
  epilepsia, doenças neurológicas, psicoses, DPOC, DM, coagulopatias, doenças reumatológicas,
  álcool, drogas, tabagismo, DII
- **Peso 2:** Cardiopatia isquêmica, ICC, AVC/stroke, parkinsonismo, esclerose múltipla,
  demência, plegia/paralisia, HIV, desnutrição, neoplasias sólidas, leucemia, linfoma
- **Peso 3:** IRC, hepatopatia grave
- **Peso 6:** Metástases

**Categorias de risco:**
    """)

    col_cat1, col_cat2, col_cat3, col_cat4 = st.columns(4)
    with col_cat1:
        with st.container(border=True):
            st.markdown("🟢 **Baixo**")
            st.markdown("#### Escore ≤ 2")
            st.caption("Paciente com poucas condições leves, jovem e sem polifarmácia.")
    with col_cat2:
        with st.container(border=True):
            st.markdown("🟡 **Moderado**")
            st.markdown("#### Escore 3–6")
            st.caption("Condições moderadas, idade avançada ou início de polifarmácia.")
    with col_cat3:
        with st.container(border=True):
            st.markdown("🟠 **Alto**")
            st.markdown("#### Escore 7–9")
            st.caption("Multimorbidade grave, idoso com várias condições ou hiperpolifarmácia.")
    with col_cat4:
        with st.container(border=True):
            st.markdown("🔴 **Muito Alto**")
            st.markdown("#### Escore ≥ 10")
            st.caption("Paciente com alto risco de hospitalização, eventos adversos e mortalidade.")

    st.markdown("---")

    # ── BLOCO 2: Pirâmide etária ─────────────────────────────────
    st.markdown("#### 1️⃣ Pirâmide etária — distribuição por carga de morbidade")
    fig_charlson = criar_piramide_charlson(df_dados)
    if fig_charlson:
        st.plotly_chart(fig_charlson, use_container_width=True, key='piramide_charlson')
    else:
        st.warning("Dados de Charlson não disponíveis")

    st.markdown("---")

    # ── BLOCO 3: Violinos por território ─────────────────────────
    st.markdown("#### 2️⃣ Distribuição por território — em pacientes com carga de morbidade")
    st.caption(
        "Cada ponto = um território. "
        "Denominador: total de pacientes do território. "
        "Sem filtro: pontos = clínicas, agrupados por AP. "
        "Com AP filtrada: pontos = ESFs, agrupados por clínica."
    )

    df_charl = carregar_dados_charlson_territorio(
        ap=territorio['ap'],
        clinica=territorio['clinica'],
        esf=territorio['esf']
    )

    if df_charl.empty:
        st.info("Sem dados por território para o filtro selecionado.")
    else:
        import plotly.express as px
        import re

        indicadores_charl = [
            ('pct_muito_alto',   '🔴 Carga Muito Alta (escore ≥10)', '#C0392B',
             '% de pacientes com escore de Charlson ≥10 por território'),
            ('pct_alto',         '🟠 Carga Alta (escore 7–9)',        '#E67E22',
             '% de pacientes com escore de Charlson 7–9 por território'),
            ('pct_moderado',     '🟡 Carga Moderada (escore 3–6)',    '#F4D03F',
             '% de pacientes com escore de Charlson 3–6 por território'),
            ('pct_baixo',        '🟢 Carga Baixa (escore ≤2)',        '#2ECC71',
             '% de pacientes com escore de Charlson ≤2 por território'),
            ('pct_multimorbidos','👥 Multimórbidos (≥2 condições)',   '#3498DB',
             '% de pacientes com 2 ou mais condições crônicas por território'),
        ]

        opcoes_charl = [v[1] for v in indicadores_charl]
        sel_charl = st.selectbox(
            "Selecione o indicador:",
            opcoes_charl,
            index=0,
            key='charlson_violin_selector'
        )
        col_c, label_c, cor_c, cap_c = next(
            (v for v in indicadores_charl if v[1] == sel_charl), indicadores_charl[0]
        )

        if col_c not in df_charl.columns or 'grupo_x' not in df_charl.columns:
            st.info("Dados não disponíveis para este indicador.")
        else:
            df_plot_c = df_charl[['territorio', 'grupo_x', col_c]].dropna(subset=[col_c]).copy()

            # Anonimizar territórios antes de plotar
            if MODO_ANONIMO:
                if territorio['clinica']:
                    # grupo_x = clínica, territorio = ESF
                    df_plot_c['grupo_x']   = df_plot_c['grupo_x'].apply(anonimizar_clinica)
                    df_plot_c['territorio'] = df_plot_c['territorio'].apply(anonimizar_esf)
                elif territorio['ap']:
                    # grupo_x = clínica, territorio = ESF
                    df_plot_c['grupo_x']   = df_plot_c['grupo_x'].apply(anonimizar_clinica)
                    df_plot_c['territorio'] = df_plot_c['territorio'].apply(anonimizar_esf)
                else:
                    # grupo_x = AP, territorio = clínica
                    df_plot_c['grupo_x']   = df_plot_c['grupo_x'].apply(lambda x: anonimizar_ap(str(x)))
                    df_plot_c['territorio'] = df_plot_c['territorio'].apply(anonimizar_clinica)
        
            df_plot_c.columns = ['territorio', 'grupo_x', 'valor']
            df_plot_c['valor'] = df_plot_c['valor'].round(1)

            def _ord_c(v):
                m = re.search(r'(\d+\.?\d*)', str(v))
                return float(m.group(1)) if m else str(v)
            grupos_ord_c = sorted(df_plot_c['grupo_x'].unique().tolist(), key=_ord_c)

            if territorio['clinica']:
                label_eixo_c  = "Equipe ESF"
                label_ponto_c = "ESF"
                modo_c        = "pontos"
            elif territorio['ap']:
                label_eixo_c  = "Clínica da Família"
                label_ponto_c = "ESF"
                modo_c        = "violin"
            else:
                label_eixo_c  = "Área Programática"
                label_ponto_c = "Clínica"
                modo_c        = "violin"

            n_c    = len(df_plot_c)
            media_c  = df_plot_c['valor'].mean()
            median_c = df_plot_c['valor'].median()

            titulo_c = (
                f"Distribuição de {label_c} por {label_eixo_c} | "
                f"Cada ponto = uma {label_ponto_c.lower()} · "
                f"Média: {media_c:.1f}% · Mediana: {median_c:.1f}% · "
                f"{n_c} territórios"
            )

            if modo_c == "pontos":
                fig_c = px.strip(
                    df_plot_c, x='grupo_x', y='valor', color='grupo_x',
                    hover_data=['territorio'],
                    labels={'valor': f'% — {label_c}', 'grupo_x': label_eixo_c,
                            'territorio': label_ponto_c},
                    title=titulo_c,
                    category_orders={'grupo_x': grupos_ord_c},
                    height=400,
                    color_discrete_sequence=px.colors.qualitative.Bold,
                )
                fig_c.update_traces(marker=dict(size=12, opacity=0.8))
            else:
                fig_c = px.violin(
                    df_plot_c, x='grupo_x', y='valor', color='grupo_x',
                    box=True, points='all',
                    hover_data=['territorio'],
                    labels={'valor': f'% — {label_c}', 'grupo_x': label_eixo_c,
                            'territorio': label_ponto_c},
                    title=titulo_c,
                    category_orders={'grupo_x': grupos_ord_c},
                    height=520,
                    color_discrete_sequence=px.colors.qualitative.Bold,
                )
                fig_c.update_traces(
                    meanline_visible=True,
                    marker=dict(size=8, opacity=0.65, line=dict(width=0)),
                    spanmode='hard',
                )

            fig_c.update_xaxes(
                type='category', categoryorder='array', categoryarray=grupos_ord_c,
                tickangle=-40 if len(grupos_ord_c) > 5 else 0,
                tickfont=dict(size=11, color=T.TEXT),
                title_font=dict(color=T.TEXT),
            )
            fig_c.update_yaxes(
                tickfont=dict(size=11, color=T.TEXT_MUTED),
                ticksuffix='%', gridcolor=T.GRID, rangemode='tozero',
            )
            fig_c.update_layout(
                showlegend=False,
                paper_bgcolor=T.PAPER_BG,
                plot_bgcolor=T.PLOT_BG,
                font=dict(color=T.TEXT),
                title_font=dict(size=12, color=T.TEXT),
                margin=dict(l=60, r=20, t=70, b=80),
            )
            st.plotly_chart(fig_c, use_container_width=True, key='charlson_violin')
            st.caption(cap_c)

# TAB 3 — COMPLEXIDADE FARMACOLÓGICA
with tab3:
    st.caption(
        "Polifarmácia: ≥5 medicamentos crônicos · Hiperpolifarmácia: ≥10 · "
        "ACB: Anticholinergic Cognitive Burden (≥3 = risco clínico) · "
        "STOPP/START/Beers: critérios de prescrição potencialmente inapropriada · "
        "**Denominador dos indicadores por território: multimórbidos (≥2 condições crônicas)**"
    )

    df_farm = carregar_dados_farmaco_territorio(
        ap=territorio['ap'], clinica=territorio['clinica'], esf=territorio['esf']
    )

    tot_pop       = int(df_dados['total_pacientes'].sum())     if not df_dados.empty else 0
    tot_mm        = int(df_dados['n_multimorbidos'].sum())     if 'n_multimorbidos'     in df_dados.columns else 0
    tot_poli      = int(df_dados['n_polifarmacia'].sum())      if 'n_polifarmacia'      in df_dados.columns else 0
    tot_hiperpoli = int(df_dados['n_hiperpolifarmacia'].sum()) if 'n_hiperpolifarmacia' in df_dados.columns else 0
    tot_acb_alto  = int(df_dados['n_acb_alto'].sum())          if 'n_acb_alto'          in df_dados.columns else 0
    tot_acb_idoso = int(df_dados['n_acb_alerta_idoso'].sum())  if 'n_acb_alerta_idoso'  in df_dados.columns else 0
    tot_stopp     = int(df_dados['n_com_stopp_ativo'].sum())   if 'n_com_stopp_ativo'   in df_dados.columns else 0
    tot_start     = int(df_dados['n_com_omissao_start'].sum()) if 'n_com_omissao_start' in df_dados.columns else 0
    tot_beers     = int(df_dados['n_com_beers_ativo'].sum())   if 'n_com_beers_ativo'   in df_dados.columns else 0
    tot_queda     = int(df_dados['n_risco_queda_meds'].sum())  if 'n_risco_queda_meds'  in df_dados.columns else 0

    def _pp(n, d): return round(n/d*100, 1) if d else 0.0

    st.markdown("#### 1️⃣ Panorama geral")
    c1, c2, c3 = st.columns(3)
    with c1:
        with st.container(border=True):
            st.metric("👥 Multimórbidos", f"{tot_mm:,}",
                      f"{_pp(tot_mm, tot_pop):.1f}% da população cadastrada",
                      help="Pacientes com 2 ou mais condições crônicas simultâneas.")
    with c2:
        with st.container(border=True):
            st.metric("💊 Polifarmácia (5–9 medicamentos)", f"{tot_poli:,}",
                      f"{_pp(tot_poli, tot_mm):.1f}% dos multimórbidos",
                      help="Uso concomitante de 5 a 9 medicamentos crônicos.")
    with c3:
        with st.container(border=True):
            st.metric("⚠️ Hiperpolifarmácia (≥10 medicamentos)", f"{tot_hiperpoli:,}",
                      f"{_pp(tot_hiperpoli, tot_mm):.1f}% dos multimórbidos",
                      delta_color="inverse",
                      help="Uso de 10 ou mais medicamentos crônicos.")

    c4, c5, c6 = st.columns(3)
    with c4:
        with st.container(border=True):
            st.metric("🧠 ACB alto (≥3)", f"{tot_acb_alto:,}",
                      f"{_pp(tot_acb_alto, tot_mm):.1f}% dos multimórbidos",
                      delta_color="inverse",
                      help="ACB ≥3 — risco de declínio cognitivo, quedas e delirium.")
    with c5:
        with st.container(border=True):
            st.metric("👴 ACB alto em idosos (≥65a)", f"{tot_acb_idoso:,}",
                      f"{_pp(tot_acb_idoso, tot_mm):.1f}% dos multimórbidos",
                      delta_color="inverse")
    with c6:
        with st.container(border=True):
            st.metric("🚨 Risco de queda por medicamentos", f"{tot_queda:,}",
                      f"{_pp(tot_queda, tot_mm):.1f}% dos multimórbidos",
                      delta_color="inverse",
                      help="BZD, hipnóticos, antipsicóticos ou opioides prescritos.")

    c7, c8, c9 = st.columns(3)
    with c7:
        with st.container(border=True):
            st.metric("🔴 STOPP ativo", f"{tot_stopp:,}",
                      f"{_pp(tot_stopp, tot_mm):.1f}% dos multimórbidos",
                      delta_color="inverse",
                      help="≥1 critério STOPP v3 — prescrição potencialmente inapropriada.")
    with c8:
        with st.container(border=True):
            st.metric("🟡 Omissão START", f"{tot_start:,}",
                      f"{_pp(tot_start, tot_mm):.1f}% dos multimórbidos",
                      delta_color="inverse",
                      help="≥1 critério START v3 — medicamento indicado não prescrito.")
    with c9:
        with st.container(border=True):
            st.metric("🟠 Beers ativo", f"{tot_beers:,}",
                      f"{_pp(tot_beers, tot_mm):.1f}% dos multimórbidos",
                      delta_color="inverse",
                      help="≥1 critério Beers 2023 em paciente ≥65a.")

    st.markdown("---")
    st.markdown("#### 2️⃣ Pirâmide etária — complexidade farmacológica")
    fig_meds = criar_piramide_medicamentos(df_dados)
    if fig_meds:
        st.plotly_chart(fig_meds, use_container_width=True, key='piramide_meds')
    else:
        st.warning("Dados de medicamentos não disponíveis para o filtro selecionado.")

    st.markdown("---")
    st.markdown("#### 3️⃣ Distribuição por território — em pacientes multimórbidos (2 ou mais condições crônicas)")
    st.caption(
        "Cada ponto = um território. "
        "Denominador: multimórbidos do território. "
        "O violino mostra a distribuição da prevalência entre os territórios."
    )

    if df_farm.empty:
        st.info("Sem dados por território para o filtro selecionado.")
    else:
        import plotly.express as px
        import re

        violinos = [
            ('pct_poli_mm',      '💊 Polifarmácia (5–9 medicamentos)',         '#3498DB',
             '% de multimórbidos com 5–9 medicamentos crônicos · cada ponto = um território'),
            ('pct_hiperpoli_mm', '⚠️ Hiperpolifarmácia (≥10 medicamentos)',     '#E74C3C',
             '% de multimórbidos com ≥10 medicamentos crônicos · cada ponto = um território'),
            ('pct_acb_alto_mm',  '🧠 ACB alto (≥3)',                            '#9B59B6',
             '% de multimórbidos com ACB ≥3 · cada ponto = um território'),
            ('pct_stopp_mm',     '🔴 STOPP ativo',                              '#E67E22',
             '% de multimórbidos com ≥1 critério STOPP · cada ponto = um território'),
            ('pct_start_mm',     '🟡 Omissão START',                            '#F1C40F',
             '% de multimórbidos com ≥1 omissão START · cada ponto = um território'),
            ('pct_beers_mm',     '🟠 Beers ativo',                              '#D35400',
             '% de multimórbidos com ≥1 critério Beers · cada ponto = um território'),
        ]

        # Seletor de indicador
        opcoes_label = [v[1] for v in violinos]
        sel_label = st.selectbox(
            "Selecione o indicador:",
            opcoes_label,
            index=0,
            key='violin_selector'
        )
        col_v, label_v, cor_v, cap_v = next(
            (v for v in violinos if v[1] == sel_label), violinos[0]
        )

        if col_v not in df_farm.columns or 'grupo_x' not in df_farm.columns:
            st.info("Dados não disponíveis para este indicador.")
        else:
            df_plot = df_farm[['territorio', 'grupo_x', col_v]].dropna(subset=[col_v]).copy()
            df_plot.columns = ['territorio', 'grupo_x', 'valor']
            df_plot['valor'] = df_plot['valor'].round(1)

            # Ordenar grupo_x numericamente
            def _ord(v):
                m = re.search(r'(\d+\.?\d*)', str(v))
                return float(m.group(1)) if m else str(v)
            grupos_ord = sorted(df_plot['grupo_x'].unique().tolist(), key=_ord)

            # Labels dinâmicos
            if territorio['clinica']:
                label_eixo  = "Equipe ESF"
                label_ponto = "ESF"
                modo        = "pontos"   # apenas scatter
            elif territorio['ap']:
                label_eixo  = "Clínica da Família"
                label_ponto = "ESF"
                modo        = "violin"
            else:
                label_eixo  = "Área Programática"
                label_ponto = "Clínica"
                modo        = "violin"

            n_terr  = len(df_plot)
            media   = df_plot['valor'].mean()
            mediana = df_plot['valor'].median()

            titulo = (
                f"Distribuição de {label_v} por {label_eixo} | "
                f"Cada ponto = uma {label_ponto.lower()} · "
                f"Média: {media:.1f}% · Mediana: {mediana:.1f}% · "
                f"{n_terr} territórios"
            )

            if modo == "pontos":
                # Clínica filtrada — apenas strip plot (ESFs como pontos)
                fig_v = px.strip(
                    df_plot,
                    x='grupo_x',
                    y='valor',
                    color='grupo_x',
                    hover_data=['territorio'],
                    labels={
                        'valor':    f'% multimórbidos — {label_v}',
                        'grupo_x':  label_eixo,
                        'territorio': label_ponto,
                    },
                    title=titulo,
                    category_orders={'grupo_x': grupos_ord},
                    height=400,
                    color_discrete_sequence=px.colors.qualitative.Bold,
                )
                fig_v.update_traces(marker=dict(size=12, opacity=0.8))
            else:
                # AP filtrada ou sem filtro — violino com pontos
                fig_v = px.violin(
                    df_plot,
                    x='grupo_x',
                    y='valor',
                    color='grupo_x',
                    box=True,
                    points='all',
                    hover_data=['territorio'],
                    labels={
                        'valor':    f'% multimórbidos — {label_v}',
                        'grupo_x':  label_eixo,
                        'territorio': label_ponto,
                    },
                    title=titulo,
                    category_orders={'grupo_x': grupos_ord},
                    height=520,
                    color_discrete_sequence=px.colors.qualitative.Bold,
                )
                fig_v.update_traces(
                    meanline_visible=True,
                    marker=dict(size=8, opacity=0.65, line=dict(width=0)),
                    spanmode='hard',
                )

            fig_v.update_xaxes(
                type='category',
                categoryorder='array',
                categoryarray=grupos_ord,
                tickangle=-40 if len(grupos_ord) > 5 else 0,
                tickfont=dict(size=11, color=T.TEXT),
                title_font=dict(color=T.TEXT),
            )
            fig_v.update_yaxes(
                tickfont=dict(size=11, color=T.TEXT_MUTED),
                ticksuffix='%',
                gridcolor=T.GRID,
                rangemode='tozero',
            )
            fig_v.update_layout(
                showlegend=False,
                paper_bgcolor=T.PAPER_BG,
                plot_bgcolor=T.PLOT_BG,
                font=dict(color=T.TEXT),
                title_font=dict(size=12, color=T.TEXT),
                margin=dict(l=60, r=20, t=70, b=80),
            )
            st.plotly_chart(fig_v, use_container_width=True, key='violin_unico')
            st.caption(cap_v)

    with st.expander("📖 Sobre os critérios utilizados"):
        st.markdown("""
**Polifarmácia e Hiperpolifarmácia** — 5+ e 10+ medicamentos crônicos respectivamente.
Associam-se a interações, efeitos adversos, quedas e internações.

**ACB — Anticholinergic Cognitive Burden** — ACB ≥3 associado a declínio cognitivo,
quedas e delirium, especialmente em idosos. Ref: Boustani et al., *Aging Health* 2008.

**STOPP/START v3** — STOPP: prescrições potencialmente inapropriadas.
START: omissões terapêuticas. Ref: O'Mahony et al., *Age Ageing* 2023.

**Critérios de Beers 2023** — Medicamentos potencialmente inapropriados em ≥65 anos.
American Geriatrics Society, 2023.
        """)

# ─────────────────────────────────────────────────────────────
# TAB 2 — HIPERTENSÃO
# ─────────────────────────────────────────────────────────────
with tab4:
    if not sumario:
        st.warning("Dados clínicos indisponíveis.")
    else:
        def _p(n, d): return round(n / d * 100, 1) if d else 0.0
        n_has = sumario.get('n_HAS', 0) or 1
        tot   = sumario.get('total_pop', 0) or 1

        st.markdown("### ❤️ Hipertensão Arterial Sistêmica")
        st.caption("Fonte: tabela fato — dados individuais agregados por território. Do diagnóstico ao controle.")

        # ══ BLOCO 1: DIAGNÓSTICO ══════════════════════════════
        st.markdown("#### 1️⃣ Prevalência e como foram identificados")

        # Linha 1: número total e alerta de CID
        col_tot, col_cid, col_sem_cid = st.columns(3)
        n_sem_cid = sumario.get('n_HAS_sem_cid', 0)
        pct_sem_cid = _p(n_sem_cid, n_has)
        with col_tot:
            with st.container(border=True):
                st.metric("❤️ Hipertensos identificados", f"{n_has:,}",
                          f"{_p(n_has, tot):.1f}% da população cadastrada",
                          help="Total de pacientes identificados como hipertensos por qualquer critério.")
        with col_cid:
            with st.container(border=True):
                st.metric("📋 Com CID registrado", f"{sumario.get('n_HAS_por_cid',0):,}",
                          f"{_p(sumario.get('n_HAS_por_cid',0), n_has):.1f}% dos hipertensos",
                          help="CID I10–I15 registrado. Diagnóstico documentado formalmente no prontuário.")
        with col_sem_cid:
            with st.container(border=True):
                st.metric("⚠️ Sem CID registrado", f"{n_sem_cid:,}",
                          f"{pct_sem_cid:.1f}% dos hipertensos",
                          delta_color="inverse",
                          help="Hipertensos identificados apenas por medida ou medicamento, sem CID. Requerem revisão e codificação.")
        if pct_sem_cid > 15:
            st.warning(f"⚠️ **Alerta:** {pct_sem_cid:.1f}% dos hipertensos ({n_sem_cid:,}) não têm CID registrado. "
                       "Subnotificação compromete a qualidade do cuidado prestado.")

        st.markdown("##### Como estes pacientes foram identificados")
        st.caption("Um mesmo paciente pode ser identificado por mais de um critério. "
                   "A identificação por CID é a forma mais robusta e recomendada.")

        # Cards dos critérios — layout 2+2
        c1, c2 = st.columns(2)
        with c1:
            with st.container(border=True):
                st.markdown("**📋 Por CID registrado**")
                st.metric("Pacientes", f"{sumario.get('n_HAS_por_cid', 0):,}",
                          f"{_p(sumario.get('n_HAS_por_cid', 0), n_has):.1f}% dos hipertensos")
                st.caption("CID I10–I15 registrado no prontuário. Forma mais confiável de documentação diagnóstica. "
                           "Pacientes sem CID podem não aparecer corretamente nos relatórios de acompanhamento.")
        with c2:
            with st.container(border=True):
                st.markdown("**📏 Por medida crítica (PA ≥180/110)**")
                st.metric("Pacientes", f"{sumario.get('n_HAS_medida_critica', 0):,}",
                          f"{_p(sumario.get('n_HAS_medida_critica', 0), n_has):.1f}% dos hipertensos")
                st.caption("Ao menos uma aferição com PA ≥180 mmHg sistólica ou ≥110 mmHg diastólica. "
                           "Nível de crise hipertensiva — estes pacientes devem ter CID registrado imediatamente.")

        c3, c4 = st.columns(2)
        with c3:
            with st.container(border=True):
                st.markdown("**📊 Por medidas repetidas**")
                st.metric("Pacientes", f"{sumario.get('n_HAS_medidas_repetidas', 0):,}",
                          f"{_p(sumario.get('n_HAS_medidas_repetidas', 0), n_has):.1f}% dos hipertensos")
                st.caption("Duas ou mais aferições com PA elevada em ocasiões distintas. "
                           "Critério diagnóstico válido — pacientes identificados assim devem ter CID registrado.")
        with c4:
            with st.container(border=True):
                st.markdown("**💊 Por prescrição de anti-hipertensivo**")
                st.metric("Pacientes", f"{sumario.get('n_HAS_medicamento', 0):,}",
                          f"{_p(sumario.get('n_HAS_medicamento', 0), n_has):.1f}% dos hipertensos")
                st.caption("Uso de anti-hipertensivo sem CID registrado — indica diagnóstico já estabelecido "
                           "mas não codificado. Oportunidade de melhoria na documentação clínica.")
        st.markdown("---")

        # ══ BLOCO 2: CONTROLE PRESSÓRICO ══════════════════════
        st.markdown("#### 2️⃣ Controle pressórico — situação atual")
        st.caption("Fonte: MM_pressao_arterial_historico · aferição mais recente por paciente")

        rpa = resumo_pa  # alias curto
        n_has_rpa     = int(rpa.get('n_has', 0) or 0)
        n_afe_90      = int(rpa.get('n_afericao_90d', 0) or 0)
        n_afe_180     = int(rpa.get('n_afericao_91_180d', 0) or 0)
        n_afe_365     = int(rpa.get('n_afericao_181_365d', 0) or 0)
        n_afe_ant     = int(rpa.get('n_afericao_mais_365d', 0) or 0)
        n_ctrl_pa     = int(rpa.get('n_ctrl', 0) or 0)
        n_nctrl_pa    = int(rpa.get('n_nao_ctrl', 0) or 0)
        media_pas     = rpa.get('media_pas', 0) or 0
        media_pad     = rpa.get('media_pad', 0) or 0

        # Métricas topo
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("✅ Controlados (aferição ≤180d)", f"{n_ctrl_pa:,}",
                  f"{_p(n_ctrl_pa, n_has_rpa):.1f}% dos hipertensos",
                  help="PA dentro da meta na aferição mais recente (≤180 dias).")
        m2.metric("⚠️ Não controlados (aferição ≤180d)", f"{n_nctrl_pa:,}",
                  f"{_p(n_nctrl_pa, n_has_rpa):.1f}% dos hipertensos",
                  delta_color="inverse")
        m3.metric("📊 PA média (última aferição)",
                  f"{media_pas:.0f}/{media_pad:.0f} mmHg",
                  help="Média das últimas aferições de PAS e PAD dos hipertensos.")
        m4.metric("📊 % médio do tempo controlado",
                  f"{sumario.get('media_pct_has_ctrl', 0):.1f}%",
                  help="Média histórica de pct_dias_has_controlado_365d.")

        # Cards de recência
        st.markdown("**🗓️ Recência da última aferição de PA**")
        rc1, rc2, rc3, rc4 = st.columns(4)
        with rc1:
            with st.container(border=True):
                st.markdown("🟢 **Aferição ≤ 90 dias**")
                st.markdown(f"## {_p(n_afe_90, n_has_rpa):.1f}%")
                st.metric("Hipertensos", f"{n_afe_90:,}", "dos hipertensos")
                st.caption("Acompanhamento em dia — PA aferida no último trimestre.")
        with rc2:
            with st.container(border=True):
                st.markdown("🟡 **Aferição entre 91 e 180 dias**")
                st.markdown(f"## {_p(n_afe_180, n_has_rpa):.1f}%")
                st.metric("Hipertensos", f"{n_afe_180:,}", "dos hipertensos")
                st.caption("Dentro do prazo mínimo semestral.")
        with rc3:
            with st.container(border=True):
                st.markdown("🟠 **Aferição entre 181 e 365 dias**")
                st.markdown(f"## {_p(n_afe_365, n_has_rpa):.1f}%")
                st.metric("Hipertensos", f"{n_afe_365:,}", "dos hipertensos",
                          delta_color="inverse" if _p(n_afe_365, n_has_rpa) > 20 else "off")
                st.caption("Aferição atrasada — fora do acompanhamento semestral recomendado.")
        with rc4:
            with st.container(border=True):
                st.markdown("🔴 **Última aferição há mais de 365 dias**")
                st.markdown(f"## {_p(n_afe_ant, n_has_rpa):.1f}%")
                st.metric("Hipertensos", f"{n_afe_ant:,}", "dos hipertensos",
                          delta_color="inverse")
                st.caption("Pacientes sem acompanhamento há mais de 1 ano. Prioridade de busca ativa.")

        # Classificação da PA
        st.markdown("**📊 Classificação da PA (última aferição)**")
        cl1, cl2, cl3, cl4, cl5 = st.columns(5)
        for col, key, label, detalhe in [
            (cl1, 'n_pa_normal',  '🟢 Normal',      'PAS < 120 E PAD < 80 mmHg'),
            (cl2, 'n_pa_elevada', '🟡 Elevada',      'PAS 120–129 E PAD < 80 mmHg'),
            (cl3, 'n_has_grau1',  '🟠 HAS Grau 1',  'PAS 130–139 OU PAD 80–89 mmHg'),
            (cl4, 'n_has_grau2',  '🔴 HAS Grau 2',  'PAS 140–179 OU PAD 90–109 mmHg'),
            (cl5, 'n_has_grau3',  '🚨 HAS Grau 3',  'PAS ≥ 180 OU PAD ≥ 110 mmHg'),
        ]:
            val = int(rpa.get(key, 0) or 0)
            with col:
                with st.container(border=True):
                    st.markdown(f"**{label}**")
                    st.caption(detalhe)
                    st.markdown(f"## {_p(val, n_has_rpa):.1f}%")
                    st.metric("Pacientes", f"{val:,}")

        lbl = df_terr['label_col'].iloc[0] if not df_terr.empty else 'Território'
        _stacked_bar_ap(
            df_terr,
            cols_pop=['pct_has_ctrl_pop','pct_has_desctrl_pop','pct_has_seminfo_pop'],
            labels=['Controlados','Não controlados','Sem aferição recente'],
            cores=['#2ECC71','#E74C3C','#777777'],
            titulo='Prevalência de hipertensão e controle pressórico por ' + lbl,
        )
        st.markdown("---")

        # ══ BLOCO 3: TENDÊNCIA DA PA ══════════════════════════
        st.markdown("#### 3️⃣ Tendência da pressão arterial")
        st.caption("Baseada na comparação entre a última e a penúltima aferição registrada.")

        n_mel_pa   = int(rpa.get('n_mel', 0) or 0)
        n_pio_pa   = int(rpa.get('n_pio', 0) or 0)
        n_est_pa   = int(rpa.get('n_est', 0) or 0)
        n_cest_pa  = int(rpa.get('n_ctrl_estavel', 0) or 0)
        n_sref_pa  = int(rpa.get('n_sem_ref', 0) or 0)

        t1, t2, t3, t4, t5 = st.columns(5)
        t1.metric("✅ Controlado/Estável", f"{n_cest_pa:,}",
                  f"{_p(n_cest_pa, n_has_rpa):.1f}%",
                  help="PA dentro da meta e estável entre as duas últimas aferições.")
        t2.metric("📈 Melhorando", f"{n_mel_pa:,}",
                  f"{_p(n_mel_pa, n_has_rpa):.1f}%")
        t3.metric("➡️ Estável (fora da meta)", f"{n_est_pa:,}",
                  f"{_p(n_est_pa, n_has_rpa):.1f}%", delta_color="off")
        t4.metric("📉 Piorando", f"{n_pio_pa:,}",
                  f"{_p(n_pio_pa, n_has_rpa):.1f}%", delta_color="inverse")
        t5.metric("❓ Sem aferição anterior", f"{n_sref_pa:,}",
                  f"{_p(n_sref_pa, n_has_rpa):.1f}%", delta_color="off",
                  help="Apenas 1 aferição registrada — não é possível calcular tendência.")

        # ── Comorbidades associadas: cards + Venn ─────────────────
        n_comorbidades = int(rpa.get('n_has_com_comorbidades', 0) or 0)
        n_dm  = int(rpa.get('n_tem_dm',  0) or 0)
        n_irc = int(rpa.get('n_tem_irc', 0) or 0)
        n_ci  = int(rpa.get('n_tem_ci',  0) or 0)
        n_icc = int(rpa.get('n_tem_icc', 0) or 0)
        n_avc = int(rpa.get('n_tem_avc', 0) or 0)

        st.markdown("**🫀 Hipertensos com comorbidades associadas — alto risco CV (SBC 2025)**")
        st.caption(
            f"Total com ao menos 1 comorbidade: **{n_comorbidades:,}** "
            f"({_p(n_comorbidades, n_has_rpa):.1f}% dos hipertensos). "
            f"Meta pressórica: <130/80 mmHg para todos (SBC/AHA 2025)."
        )

        # Cards individuais
        cv1, cv2, cv3, cv4, cv5 = st.columns(5)
        for col, val, label, emoji, ajuda in [
            (cv1, n_dm,  "Diabetes (DM)",          "🩸",
             "HAS+DM: meta <130/80 mmHg. Alto risco por definição — indicação de IECA/BRA como 1ª linha."),
            (cv2, n_irc, "Ins. Renal Crônica",      "🫘",
             "HAS+IRC: meta <130/80 mmHg. Indicação de IECA/BRA para nefroproteção. Monitorar K+."),
            (cv3, n_ci,  "Cardiopatia Isquêmica",   "💔",
             "HAS+CI: meta <130/80 mmHg. Indicação de betabloqueador + estatina de alta intensidade."),
            (cv4, n_icc, "Ins. Cardíaca (ICC)",     "🫀",
             "HAS+ICC: meta <130/80 mmHg. Indicação de IECA/BRA/INRA + BB + ARM + SGLT-2."),
            (cv5, n_avc, "AVC",                     "🧠",
             "HAS+AVC: meta <130/80 mmHg. Indicação de antiagregação + estatina. Risco muito alto."),
        ]:
            with col:
                with st.container(border=True):
                    st.markdown(f"{emoji} **{label}**")
                    st.markdown(f"## {val:,}")
                    st.caption(f"{_p(val, n_has_rpa):.1f}% dos hipertensos")
                    st.caption(ajuda)

        # ── Heatmap de sobreposição 5×5 ────────────────────────────
        # Matriz simétrica: diagonal = total isolado, off-diagonal = interseção par
        import plotly.graph_objects as go
        import numpy as np

        grupos_ord  = ['DM', 'IRC', 'CI', 'ICC', 'AVC']
        totais_ord  = [n_dm, n_irc, n_ci, n_icc, n_avc]
        cores_ord   = ['#2980B9', '#C0392B', '#27AE60', '#D68910', '#8E44AD']

        pares = {
            ('DM',  'IRC'): int(rpa.get('n_dm_irc',  0) or 0),
            ('DM',  'CI'):  int(rpa.get('n_dm_ci',   0) or 0),
            ('DM',  'ICC'): int(rpa.get('n_dm_icc',  0) or 0),
            ('DM',  'AVC'): int(rpa.get('n_dm_avc',  0) or 0),
            ('IRC', 'CI'):  int(rpa.get('n_irc_ci',  0) or 0),
            ('IRC', 'ICC'): int(rpa.get('n_irc_icc', 0) or 0),
            ('IRC', 'AVC'): int(rpa.get('n_irc_avc', 0) or 0),
            ('CI',  'ICC'): int(rpa.get('n_ci_icc',  0) or 0),
            ('CI',  'AVC'): int(rpa.get('n_ci_avc',  0) or 0),
            ('ICC', 'AVC'): int(rpa.get('n_icc_avc', 0) or 0),
        }

        n = len(grupos_ord)
        # Matriz de valores absolutos (para cor)
        mat_z = np.zeros((n, n))
        # Matriz de texto (para anotação)
        mat_txt = [[''] * n for _ in range(n)]

        for i in range(n):
            for j in range(n):
                if i == j:
                    val = totais_ord[i]
                else:
                    key = (grupos_ord[min(i,j)], grupos_ord[max(i,j)])
                    val = pares.get(key, 0)
                mat_z[i][j] = val
                pct = _p(val, n_has_rpa)
                mat_txt[i][j] = (
                    f"<b>{val:,}</b><br>{pct:.1f}%"
                    if i == j
                    else f"{val:,}<br>{pct:.1f}%"
                )

        col_hm, col_leg2 = st.columns([3, 2])

        with col_hm:
            # Escala de cor: azul escuro → teal → verde → amarelo → laranja → vermelho
            colorscale_hm = T.HEATMAP_COLORSCALE

            fig_hm = go.Figure(data=go.Heatmap(
                z=mat_z.tolist(),
                x=grupos_ord,
                y=grupos_ord,
                text=mat_txt,
                texttemplate="%{text}",
                textfont=dict(size=12, color=T.TEXT),
                colorscale=colorscale_hm,
                showscale=True,
                colorbar=dict(
                    title=dict(
                        text='Pacientes',
                        font=dict(color=T.TEXT_SECONDARY, size=11),
                    ),
                    tickfont=dict(color=T.TEXT_SECONDARY, size=9),
                    thickness=14, len=0.85,
                    bgcolor=T.PAPER_BG,
                    bordercolor=T.PAPER_BG,
                ),
                hovertemplate=(
                    "<b>%{y} + %{x}</b><br>"
                    "Pacientes com ambas: <b>%{z:,}</b><extra></extra>"
                ),
            ))

            # Borda colorida + fundo suave na diagonal
            # Converte hex #RRGGBB → rgba(r,g,b,0.13) para Plotly
            def _hex_to_rgba(h, a=0.13):
                h = h.lstrip('#')
                r, g, b = int(h[0:2],16), int(h[2:4],16), int(h[4:6],16)
                return f"rgba({r},{g},{b},{a})"

            for i, (nome, cor) in enumerate(zip(grupos_ord, cores_ord)):
                fig_hm.add_shape(
                    type='rect', xref='x', yref='y',
                    x0=i-0.5, y0=i-0.5, x1=i+0.5, y1=i+0.5,
                    fillcolor=_hex_to_rgba(cor),
                    line=dict(color=cor, width=3),
                )
                # Tick colorido no eixo X
                fig_hm.add_annotation(
                    x=i, y=5.05, xref='x', yref='y',
                    text=f"<span style='color:{cor}'>▲</span>",
                    showarrow=False, font=dict(size=14),
                )

            fig_hm.update_layout(
                title=dict(
                    text=(
                        f"Sobreposição de comorbidades — hipertensos"
                        f"<br><sup style='color:{T.TEXT_MUTED}'>"
                        f"Total de hipertensos: {n_has_rpa:,} · "
                        f"Diagonal = total isolado · Off-diagonal = interseção"
                        f"</sup>"
                    ),
                    font=dict(size=13, color=T.TEXT), x=0.5,
                ),
                height=430,
                paper_bgcolor=T.PAPER_BG,
                plot_bgcolor=T.PLOT_BG,
                xaxis=dict(
                    tickfont=dict(color=T.TEXT, size=13, family='monospace'),
                    side='bottom', showgrid=False,
                    tickvals=list(range(5)),
                    ticktext=[
                        f"<b style='color:{c}'>{g}</b>"
                        for g, c in zip(grupos_ord, cores_ord)
                    ],
                ),
                yaxis=dict(
                    tickfont=dict(color=T.TEXT, size=13, family='monospace'),
                    autorange='reversed', showgrid=False,
                    tickvals=list(range(5)),
                    ticktext=[
                        f"<b style='color:{c}'>{g}</b>"
                        for g, c in zip(grupos_ord, cores_ord)
                    ],
                ),
                margin=dict(l=10, r=10, t=70, b=30),
            )
            st.plotly_chart(fig_hm, use_container_width=True)

        with col_leg2:
            # ── Dois painéis lado a lado ──────────────────────────
            sub_g, sub_p = st.columns(2)

            with sub_g:
                st.markdown(
                    f"<p style='font-size:13px;font-weight:700;"
                    f"color:{T.TEXT_SECONDARY};margin-bottom:8px'>"
                    f"🩺 Grupos</p>",
                    unsafe_allow_html=True
                )
                for nome, val, cor in zip(grupos_ord, totais_ord, cores_ord):
                    pct_g = _p(val, n_has_rpa)
                    # Barra de progresso colorida
                    bar_w = max(4, int(pct_g * 2.2))
                    st.markdown(
                        f"<div style='margin-bottom:10px'>"
                        f"<span style='color:{cor};font-size:15px'>⬤</span> "
                        f"<span style='font-weight:700;color:{T.TEXT}'>{nome}</span><br>"
                        f"<span style='font-size:13px;color:{T.TEXT_SECONDARY}'>"
                        f"{val:,}</span> "
                        f"<span style='font-size:11px;color:{T.TEXT_MUTED}'>{pct_g:.1f}%</span><br>"
                        f"<div style='background:{cor};height:4px;"
                        f"width:{bar_w}%;border-radius:2px;opacity:0.7'></div>"
                        f"</div>",
                        unsafe_allow_html=True
                    )

            with sub_p:
                st.markdown(
                    f"<p style='font-size:13px;font-weight:700;"
                    f"color:{T.TEXT_SECONDARY};margin-bottom:8px'>"
                    f"🔗 Sobreposições</p>",
                    unsafe_allow_html=True
                )
                pares_sorted = sorted(pares.items(), key=lambda x: -x[1])
                for (g1, g2), val in pares_sorted:
                    if val > 0:
                        pct_p = _p(val, n_has_rpa)
                        cor1 = cores_ord[grupos_ord.index(g1)]
                        cor2 = cores_ord[grupos_ord.index(g2)]
                        st.markdown(
                            f"<div style='margin-bottom:8px'>"
                            f"<span style='color:{cor1}'>⬤</span>"
                            f"<span style='color:{cor2}'>⬤</span> "
                            f"<span style='font-size:12px;color:{T.TEXT}'>"
                            f"<b>{g1}+{g2}</b></span><br>"
                            f"<span style='font-size:12px;color:{T.TEXT_SECONDARY}'>{val:,}</span> "
                            f"<span style='font-size:11px;color:{T.TEXT_MUTED}'>{pct_p:.1f}%</span>"
                            f"</div>",
                            unsafe_allow_html=True
                        )

            # Carga máxima
            n_todas5 = int(rpa.get('n_todas_5', 0) or 0)
            if n_todas5 > 0:
                st.markdown(
                    f"<div style='margin-top:12px;padding:8px 12px;"
                    f"border-left:3px solid #E63946;"
                    f"background:rgba(230,57,70,0.1);border-radius:4px'>"
                    f"<span style='font-size:11px;color:{T.TEXT_MUTED}'>Com todas as 5</span><br>"
                    f"<span style='font-size:18px;font-weight:700;color:{T.TEXT}'>"
                    f"{n_todas5:,}</span> "
                    f"<span style='font-size:11px;color:{T.TEXT_MUTED}'>"
                    f"({_p(n_todas5, n_has_rpa):.1f}%)</span>"
                    f"</div>",
                    unsafe_allow_html=True
                )

        # ── Alerta 2: Risco cardiovascular por Framingham/SBC ─────
        n_muito_alto = int(rpa.get('n_risco_muito_alto', 0) or 0)
        n_alto_f     = int(rpa.get('n_risco_alto', 0) or 0)
        n_interm     = int(rpa.get('n_risco_intermediario', 0) or 0)
        n_baixo_f    = int(rpa.get('n_risco_baixo', 0) or 0)
        if n_muito_alto + n_alto_f > 0:
            st.warning(
                f"📊 **Estratificação de risco cardiovascular — Escore de Framingham "
                f"com reclassificação SBC:** "
                f"Risco Muito Alto: **{n_muito_alto:,}** ({_p(n_muito_alto, n_has_rpa):.1f}%) · "
                f"Risco Alto: **{n_alto_f:,}** ({_p(n_alto_f, n_has_rpa):.1f}%) · "
                f"Intermediário: **{n_interm:,}** ({_p(n_interm, n_has_rpa):.1f}%) · "
                f"Baixo: **{n_baixo_f:,}** ({_p(n_baixo_f, n_has_rpa):.1f}%). "
                f"Reclassificação automática para Muito Alto em casos de aterosclerose "
                f"prévia (CI, AVC, DAP); para Alto em DRC ou LDL ≥190 mg/dL."
            )

        _stacked_bar_ap(
            df_terr,
            cols_pop=['pct_has_mel_pop','pct_has_est_pop','pct_has_pio_pop'],
            labels=['Melhorando','Estável','Piorando'],
            cores=['#2ECC71','#F4D03F','#E74C3C'],
            titulo='Tendência de pressão arterial na população hipertensa por ' + lbl,
        )
        st.markdown("---")

        # ══ BLOCO 4: LACUNAS ══════════════════════════════════
        st.markdown("#### 4️⃣ Lacunas de cuidado na HAS")

        # Faixa etária — fonte: resumo_pa (consistente com bloco 2)
        # Meta individualizada: <80 anos → PA <140/90; ≥80 anos → PA <150/90
        n_has_80mais      = int(rpa.get('n_80mais', 0) or 0)
        n_has_ctrl_80     = int(rpa.get('n_ctrl_80mais', 0) or 0)
        n_has_nctrl_80    = int(rpa.get('n_nctrl_80mais', 0) or 0)
        n_has_menor80     = int(rpa.get('n_menor80', 0) or 0)
        n_has_ctrl_men80  = int(rpa.get('n_ctrl_menor80', 0) or 0)
        n_has_nctrl_men80 = int(rpa.get('n_nctrl_menor80', 0) or 0)

        def _card_lac(col, emoji, titulo, pct_val, pct_denom, abs_val, denom_label, caption_txt, pct_extra=None):
            with col:
                with st.container(border=True):
                    st.markdown(f"{emoji} **{titulo}**")
                    st.markdown(f"## {_p(pct_val, pct_denom):.1f}%")
                    st.metric("Pacientes", f"{abs_val:,}", denom_label, delta_color="inverse")
                    if pct_extra:
                        st.markdown(pct_extra)
                    st.caption(caption_txt)

        # ── Grupo 1: Controle de PA ─────────────────────────────
        st.markdown("**🩺 Controle da Pressão Arterial**")
        g1 = st.columns(5)

        _card_lac(g1[0], "🔵", "Adultos sem rastreamento de PA",
                  sumario.get('n_lac_rastreio_pa', 0), tot,
                  sumario.get('n_lac_rastreio_pa', 0), "da população total",
                  "Adultos ≥18 anos sem nenhuma aferição de PA registrada no último ano. "
                  "Meta: rastrear todos os adultos cadastrados.")

        _card_lac(g1[1], "🔴", "Hipertensos sem aferição nos últimos 180 dias",
                  sumario.get('n_lac_has_sem_pa_180d', 0), n_has,
                  sumario.get('n_lac_has_sem_pa_180d', 0), "dos hipertensos",
                  "Fora do acompanhamento mínimo. A PA deve ser aferida ao menos a cada 6 meses.")

        # Card <80 anos
        with g1[2]:
            with st.container(border=True):
                st.markdown("🟠 **Hipertensos com menos de 80 anos**")
                st.markdown(
                    f"De **{n_has_menor80:,}** hipertensos com menos de 80 anos "
                    f"(**{_p(n_has_menor80, n_has):.1f}%** de todos os hipertensos), "
                    f"**{n_has_nctrl_men80:,}** indivíduos "
                    f"(**{_p(n_has_nctrl_men80, n_has_menor80):.1f}%**) "
                    f"não estão com a PA controlada."
                )
                st.markdown(f"## {_p(n_has_nctrl_men80, n_has_menor80):.1f}%")
                st.metric("Não controlados", f"{n_has_nctrl_men80:,}",
                          delta_color="inverse")
                st.markdown(f"✅ Controlados: **{n_has_ctrl_men80:,}** "
                            f"({_p(n_has_ctrl_men80, n_has_menor80):.1f}%)")
                st.caption("Meta: PA <140/90 mmHg. Hipertensão não controlada é o "
                           "principal fator de risco para AVC e infarto.")

        # Card ≥80 anos
        with g1[3]:
            with st.container(border=True):
                st.markdown("🟡 **Hipertensos com 80 anos ou mais**")
                st.markdown(
                    f"De **{n_has_80mais:,}** hipertensos com ≥80 anos "
                    f"(**{_p(n_has_80mais, n_has):.1f}%** de todos os hipertensos), "
                    f"**{n_has_nctrl_80:,}** indivíduos "
                    f"(**{_p(n_has_nctrl_80, n_has_80mais):.1f}%**) "
                    f"não estão com a PA controlada."
                )
                st.markdown(f"## {_p(n_has_nctrl_80, n_has_80mais):.1f}%")
                st.metric("Não controlados", f"{n_has_nctrl_80:,}",
                          delta_color="inverse")
                st.markdown(f"✅ Controlados: **{n_has_ctrl_80:,}** "
                            f"({_p(n_has_ctrl_80, n_has_80mais):.1f}%)")
                st.caption("Meta: PA <150/90 mmHg — mais permissiva para evitar "
                           "hipotensão postural e quedas em idosos.")

        _card_lac(g1[4], "🟣", "Diabéticos hipertensos com PA não controlada",
                  sumario.get('n_lac_dm_has_pa_desctrl', 0), n_has,
                  sumario.get('n_lac_dm_has_pa_desctrl', 0), "dos hipertensos",
                  "PA >135/80 mmHg em pacientes com DM e HAS. Meta mais rigorosa "
                  "pelo risco cardiovascular e renal elevado.")

        # ── Grupo 2: Rastreio de DM em hipertensos ──────────────
        st.markdown("**🩸 Rastreio de Diabetes em Hipertensos**")
        g2 = st.columns(5)

        _card_lac(g2[0], "🔶", "Hipertensos sem rastreio de DM",
                  sumario.get('n_lac_rastreio_dm_has', 0), n_has,
                  sumario.get('n_lac_rastreio_dm_has', 0), "dos hipertensos",
                  "Hipertensos sem glicemia de jejum ou HbA1c nos últimos 12 meses. "
                  "Diabetes é 2× mais frequente em hipertensos. Rastreio anual recomendado.")

        # ── Grupo 3: Exames laboratoriais ───────────────────────
        st.markdown("**🔬 Exames Laboratoriais Mínimos para Hipertensos**")
        st.caption("Todo hipertenso deve realizar estes exames ao menos uma vez ao ano "
                   "para estratificação de risco cardiovascular e renal.")
        g3 = st.columns(5)

        _card_lac(g3[0], "🧪", "Sem creatinina no último ano",
                  sumario.get('n_lac_has_creatinina', 0), n_has,
                  sumario.get('n_lac_has_creatinina', 0), "dos hipertensos",
                  "Creatinina sérica avalia função renal e estágio de DRC. "
                  "Essencial para escolha e dose dos anti-hipertensivos.")

        _card_lac(g3[1], "🧪", "Sem colesterol/lipidograma no último ano",
                  sumario.get('n_lac_has_colesterol', 0), n_has,
                  sumario.get('n_lac_has_colesterol', 0), "dos hipertensos",
                  "Perfil lipídico para estratificação de risco cardiovascular. "
                  "Dislipidemia é fator de risco independente em hipertensos.")

        _card_lac(g3[2], "🧪", "Sem exame de urina (EAS) no último ano",
                  sumario.get('n_lac_has_eas', 0), n_has,
                  sumario.get('n_lac_has_eas', 0), "dos hipertensos",
                  "Exame de urina identifica proteinúria e hematúria — marcadores "
                  "de lesão de órgão-alvo renal na hipertensão.")

        _card_lac(g3[3], "📟", "Sem eletrocardiograma (ECG) no último ano",
                  sumario.get('n_lac_has_ecg', 0), n_has,
                  sumario.get('n_lac_has_ecg', 0), "dos hipertensos",
                  "ECG detecta hipertrofia ventricular esquerda e arritmias — "
                  "lesões de órgão-alvo cardíaco da hipertensão não controlada.")

        _card_lac(g3[4], "⚖️", "Sem IMC calculável registrado",
                  sumario.get('n_lac_has_imc', 0), n_has,
                  sumario.get('n_lac_has_imc', 0), "dos hipertensos",
                  "Peso e altura para cálculo do IMC não registrados. "
                  "Obesidade está presente em >50% dos hipertensos e é fator de risco independente.")

        st.caption("Lacunas calculadas sobre o denominador indicado em cada card.")


# ─────────────────────────────────────────────────────────────
# TAB 5 — DIABETES
# ─────────────────────────────────────────────────────────────
with tab5:
    if not sumario:
        st.warning("Dados clínicos indisponíveis.")
    else:
        def _p(n, d): return round(n / d * 100, 1) if d else 0.0
        n_dm = sumario.get('n_DM', 0) or 1
        tot  = sumario.get('total_pop', 0) or 1

        st.markdown("### 🍬 Diabetes Mellitus")
        st.caption("Fonte: tabela fato — dados individuais agregados por território. Do diagnóstico ao controle.")

        # ══ BLOCO 1: DIAGNÓSTICO ══════════════════════════════
        st.markdown("#### 1️⃣ Prevalência e como foram identificados")
        n_sem_cid_dm = sumario.get('n_DM_sem_cid', 0)
        n_pre_dm     = sumario.get('n_pre_DM', 0)
        n_dm1        = sumario.get('n_DM1_provavel', 0)
        pct_sem_cid_dm = _p(n_sem_cid_dm, n_dm)

        # Linha 1: totais principais
        col_dm1, col_dm2, col_dm3, col_dm4 = st.columns(4)
        with col_dm1:
            with st.container(border=True):
                st.metric("🍬 Diabéticos identificados", f"{n_dm:,}",
                          f"{_p(n_dm, tot):.1f}% da população",
                          help="Total de pacientes identificados como diabéticos por qualquer critério.")
        with col_dm2:
            with st.container(border=True):
                st.metric("🟡 Pré-Diabetes", f"{n_pre_dm:,}",
                          f"{_p(n_pre_dm, tot):.1f}% da população",
                          help="Glicemia de jejum 100–125 mg/dL ou HbA1c 5,7–6,4%. Risco elevado de progredir para DM.")
        with col_dm3:
            with st.container(border=True):
                st.metric("💉 Provável DM tipo 1", f"{n_dm1:,}",
                          f"{_p(n_dm1, n_dm):.1f}% dos diabéticos",
                          help="Pacientes jovens, e/ou que nunca receberam hipoglicemiantes orais, e/ou com prescrição de insulina de ação rápida.")
        with col_dm4:
            with st.container(border=True):
                st.metric("⚠️ Sem CID registrado", f"{n_sem_cid_dm:,}",
                          f"{pct_sem_cid_dm:.1f}% dos diabéticos",
                          delta_color="inverse",
                          help="Diabéticos identificados sem CID E10–E14. Subnotificação compromete acompanhamento e metas.")

        if pct_sem_cid_dm > 20:
            st.warning(f"⚠️ **Alerta de subnotificação:** {pct_sem_cid_dm:.1f}% dos diabéticos ({n_sem_cid_dm:,}) "
                       "não têm CID registrado. Subnotificação compromete a qualidade do cuidado prestado.")

        st.markdown("##### Como estes pacientes foram identificados")
        st.caption("Um mesmo paciente pode ser identificado por mais de um critério. "
                   "Critérios clínicos e laboratoriais devem sempre resultar em CID registrado.")

        # Cards dos 4 critérios — 2 colunas
        c1, c2 = st.columns(2)
        with c1:
            with st.container(border=True):
                st.markdown("**📋 Por CID registrado (E10–E14)**")
                st.metric("Pacientes", f"{sumario.get('n_DM_por_cid', 0):,}",
                          f"{_p(sumario.get('n_DM_por_cid', 0), n_dm):.1f}% dos diabéticos")
                st.caption("Forma mais robusta. CID E10 (DM1), E11 (DM2), E13/E14 (outras formas). "
                           "Essencial para geração correta de listas de acompanhamento e indicadores de qualidade.")
        with c2:
            with st.container(border=True):
                st.markdown("**🩸 Por exames laboratoriais**")
                st.metric("Pacientes", f"{sumario.get('n_DM_por_exames', 0):,}",
                          f"{_p(sumario.get('n_DM_por_exames', 0), n_dm):.1f}% dos diabéticos")
                st.caption("Glicemia de jejum ≥126 mg/dL em duas ocasiões, ou HbA1c ≥6,5%. "
                           "Diagnóstico laboratorial confirmado — estes pacientes devem ter CID registrado.")

        c3, c4 = st.columns(2)
        with c3:
            with st.container(border=True):
                st.markdown("**📈 Por progressão do pré-DM**")
                st.metric("Pacientes", f"{sumario.get('n_DM_por_progressao', 0):,}",
                          f"{_p(sumario.get('n_DM_por_progressao', 0), n_dm):.1f}% dos diabéticos")
                st.caption("Paciente com pré-DM que atingiu critérios diagnósticos em exame subsequente. "
                           "Progressão esperada em ~10% dos pré-diabéticos/ano sem intervenção.")
        with c4:
            with st.container(border=True):
                st.markdown("**💊 Por prescrição de insulina ou similares**")
                st.metric("Pacientes", f"{sumario.get('n_DM_por_medicamento', 0):,}",
                          f"{_p(sumario.get('n_DM_por_medicamento', 0), n_dm):.1f}% dos diabéticos")
                st.caption("Uso de insulina, análogos ou antidiabéticos de uso exclusivo em DM sem CID registrado. "
                           "Diagnóstico implícito pelo tratamento — oportunidade de codificação formal.")
        st.markdown("---")

        # ══ BLOCO 2: CONTROLE GLICÊMICO ══════════════════════
        st.markdown("#### 2️⃣ Controle glicêmico — situação atual")
        st.caption("Fonte: MM_glicemia_hba1c_historico · HbA1c mais recente por paciente diabético")

        rh = resumo_hba1c  # alias curto
        n_hba1c_180  = int(rh.get('n_dm_hba1c_180d', 0) or 0)
        n_hba1c_365  = int(rh.get('n_dm_hba1c_365d', 0) or 0)
        n_hba1c_ant  = int(rh.get('n_dm_hba1c_antiga', 0) or 0)
        n_nunca      = int(rh.get('n_dm_nunca_hba1c', 0) or 0)
        n_ctrl_dm    = int(rh.get('n_ctrl', 0) or 0)
        n_nctrl_dm   = int(rh.get('n_nao_ctrl', 0) or 0)
        media_hba1c  = rh.get('media_hba1c_dm_recente') or 0
        n_rastreio   = int(rh.get('n_rastreio_incorreto', 0) or 0)
        n_rast_norm  = int(rh.get('n_rastreio_normal', 0) or 0)
        n_rast_pre   = int(rh.get('n_rastreio_pre_dm', 0) or 0)
        n_rast_dm    = int(rh.get('n_rastreio_provavel_dm', 0) or 0)
        n_dm_comp    = int(rh.get('n_dm_complicado', 0) or 0)

        # Métricas topo
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("✅ Controlados (HbA1c ≤180d)", f"{n_ctrl_dm:,}",
                  f"{_p(n_ctrl_dm, n_dm):.1f}% dos diabéticos",
                  help="HbA1c dentro da meta nos últimos 6 meses.")
        m2.metric("⚠️ Não controlados (HbA1c ≤180d)", f"{n_nctrl_dm:,}",
                  f"{_p(n_nctrl_dm, n_dm):.1f}% dos diabéticos",
                  delta_color="inverse")
        m3.metric("🩸 HbA1c média (exames ≤180d)",
                  f"{media_hba1c:.1f}%" if media_hba1c else "—",
                  help="Média da HbA1c mais recente entre diabéticos com exame nos últimos 6 meses.")
        m4.metric("📊 % médio do tempo controlado",
                  f"{sumario.get('media_pct_dm_ctrl', 0):.1f}%",
                  help="Média histórica de pct_dias_dm_controlado_365d.")

        # Cards de recência da HbA1c
        st.markdown("**🗓️ Recência da última HbA1c — todos os diabéticos**")
        rc1, rc2, rc3, rc4 = st.columns(4)
        with rc1:
            with st.container(border=True):
                st.markdown("🟢 **HbA1c ≤ 180 dias**")
                st.markdown(f"## {_p(n_hba1c_180, n_dm):.1f}%")
                st.metric("Diabéticos", f"{n_hba1c_180:,}", "dos diabéticos")
                st.caption("Monitoramento em dia — exame no último semestre.")
        with rc2:
            with st.container(border=True):
                st.markdown("🟡 **HbA1c entre 181 e 365 dias**")
                st.markdown(f"## {_p(n_hba1c_365, n_dm):.1f}%")
                st.metric("Diabéticos", f"{n_hba1c_365:,}", "dos diabéticos")
                st.caption("Exame dentro do ano — monitoramento anual mínimo atendido.")
        with rc3:
            with st.container(border=True):
                st.markdown("🟠 **HbA1c há mais de 365 dias**")
                st.markdown(f"## {_p(n_hba1c_ant, n_dm):.1f}%")
                st.metric("Diabéticos", f"{n_hba1c_ant:,}", "dos diabéticos",
                          delta_color="inverse")
                st.caption("Exame desatualizado — não é possível classificar controle atual.")
        with rc4:
            with st.container(border=True):
                st.markdown("🔴 **Nunca realizou HbA1c**")
                st.markdown(f"## {_p(n_nunca, n_dm):.1f}%")
                st.metric("Diabéticos", f"{n_nunca:,}", "dos diabéticos",
                          delta_color="inverse")
                st.caption("Sem nenhum exame de HbA1c registrado. Prioridade máxima de solicitação.")

        # Alerta rastreio incorreto
        if n_rastreio > 0:
            st.warning(
                f"⚠️ **{n_rastreio:,} pacientes sem diabetes fizeram HbA1c** "
                f"— exame de acompanhamento usado como rastreio (uso inadequado). "
                f"Resultado: {n_rast_norm:,} normais, {n_rast_pre:,} pré-DM, "
                f"{n_rast_dm:,} com provável DM não diagnosticado. "
                f"Para rastreio, o correto é glicemia de jejum."
            )
            if n_rast_dm > 0:
                st.error(
                    f"🚨 **{n_rast_dm:,} pacientes com HbA1c ≥6,5% sem diagnóstico de DM** "
                    f"— possível DM não diagnosticado. Revisar e diagnosticar formalmente."
                )

        lbl = df_terr['label_col'].iloc[0] if not df_terr.empty else 'Território'
        _stacked_bar_ap(
            df_terr,
            cols_pop=[
                'pct_dm_hba1c_180d_pop',
                'pct_dm_hba1c_365d_pop',
                'pct_dm_hba1c_ant_pop',
                'pct_dm_hba1c_nunca_pop',
            ],
            labels=['HbA1c ≤180 dias', 'HbA1c 181–365 dias', 'HbA1c >365 dias', 'Nunca realizou'],
            cores=['#2ECC71', '#F4D03F', '#E67E22', '#777777'],
            titulo='Janelas temporais para o resultado de HbA1c pela prevalência de diabetes na população por ' + lbl,
        )
        st.markdown("---")

        # ══ BLOCO 3: TENDÊNCIA GLICÊMICA ══════════════════════
        st.markdown("#### 3️⃣ Tendência glicêmica")
        st.caption("Baseada na comparação entre a última e a penúltima HbA1c registrada (intervalo ≥90 dias).")

        n_mel_dm = sumario.get('n_DM_melhorando', 0)
        n_pio_dm = sumario.get('n_DM_piorando', 0)
        n_est_dm = sumario.get('n_DM_estavel', max(0, n_dm - n_mel_dm - n_pio_dm))
        n_dm_comp = int(rh.get('n_dm_complicado', 0) or 0)

        td1, td2, td3, td4 = st.columns(4)
        td1.metric("📈 Melhorando", f"{n_mel_dm:,}",
                   f"{_p(n_mel_dm, n_dm):.1f}%",
                   help="HbA1c mais recente caiu >0,5% em relação à anterior.")
        td2.metric("➡️ Estável", f"{n_est_dm:,}",
                   f"{_p(n_est_dm, n_dm):.1f}%", delta_color="off",
                   help="Variação entre exames < 0,5% ou exame antigo/único.")
        td3.metric("📉 Piorando", f"{n_pio_dm:,}",
                   f"{_p(n_pio_dm, n_dm):.1f}%", delta_color="inverse",
                   help="HbA1c mais recente subiu >0,5% em relação à anterior.")
        td4.metric("🔗 DM complicado (DM+CI/ICC/IRC)", f"{n_dm_comp:,}",
                   f"{_p(n_dm_comp, n_dm):.1f}%", delta_color="inverse",
                   help="Diabéticos com cardiopatia isquêmica, insuficiência cardíaca ou IRC — indicação de SGLT-2.")

        _stacked_bar_ap(
            df_terr,
            cols_pop=['pct_dm_mel_pop','pct_dm_est_pop','pct_dm_pio_pop'],
            labels=['Melhorando','Estável/sem info','Piorando'],
            cores=['#2ECC71','#F4D03F','#E74C3C'],
            titulo='Tendência de controle glicêmico na população por ' + lbl,
        )
        st.markdown("---")

        # ══ BLOCO 3B: HEATMAP DE COMORBIDADES EM DIABÉTICOS ══════
        st.markdown("#### 🔗 Comorbidades associadas ao DM")
        st.caption("Sobreposição entre diabetes e comorbidades cardiovasculares e renais.")

        # Totais das comorbidades em diabéticos
        n_dm_has = int(rh.get('n_dm_has', 0) or 0)
        n_dm_irc = int(rh.get('n_dm_irc', 0) or 0)
        n_dm_ci  = int(rh.get('n_dm_ci',  0) or 0)
        n_dm_icc = int(rh.get('n_dm_icc', 0) or 0)
        n_dm_avc = int(rh.get('n_dm_avc', 0) or 0)

        # Cards individuais
        dmc1, dmc2, dmc3, dmc4, dmc5 = st.columns(5)
        for col, val, label, emoji, cor_c, ajuda in [
            (dmc1, n_dm_has, 'HAS',  '🩸', '#3498DB',
             'DM+HAS: meta PA <130/80 mmHg (SBC 2025). IECA/BRA como 1ª linha.'),
            (dmc2, n_dm_irc, 'IRC',  '🫘', '#9B59B6',
             'DM+IRC: indicação de IECA/BRA + SGLT-2 para nefroproteção.'),
            (dmc3, n_dm_ci,  'CI',   '💔', '#E74C3C',
             'DM+CI: indicação de SGLT-2 + estatina alta intensidade + AAS.'),
            (dmc4, n_dm_icc, 'ICC',  '🫀', '#E67E22',
             'DM+ICC: indicação de SGLT-2 + IECA/BRA/INRA + BB + ARM.'),
            (dmc5, n_dm_avc, 'AVC',  '🧠', '#1ABC9C',
             'DM+AVC: risco muito alto. Controle rigoroso da HbA1c e PA.'),
        ]:
            with col:
                with st.container(border=True):
                    st.markdown(f"{emoji} **{label}**")
                    st.markdown(f"## {val:,}")
                    st.caption(f"{_p(val, n_dm):.1f}% dos diabéticos")
                    st.caption(ajuda)

        # Heatmap
        import plotly.graph_objects as go
        import numpy as np

        grupos_dm   = ['HAS', 'IRC', 'CI', 'ICC', 'AVC']
        totais_dm   = [n_dm_has, n_dm_irc, n_dm_ci, n_dm_icc, n_dm_avc]
        cores_dm    = ['#3498DB', '#9B59B6', '#E74C3C', '#E67E22', '#1ABC9C']

        pares_dm = {
            ('HAS', 'IRC'): int(rh.get('n_dm_has_irc', 0) or 0),
            ('HAS', 'CI'):  int(rh.get('n_dm_has_ci',  0) or 0),
            ('HAS', 'ICC'): int(rh.get('n_dm_has_icc', 0) or 0),
            ('HAS', 'AVC'): int(rh.get('n_dm_has_avc', 0) or 0),
            ('IRC', 'CI'):  int(rh.get('n_dm_irc_ci',  0) or 0),
            ('IRC', 'ICC'): int(rh.get('n_dm_irc_icc', 0) or 0),
            ('IRC', 'AVC'): int(rh.get('n_dm_irc_avc', 0) or 0),
            ('CI',  'ICC'): int(rh.get('n_dm_ci_icc',  0) or 0),
            ('CI',  'AVC'): int(rh.get('n_dm_ci_avc',  0) or 0),
            ('ICC', 'AVC'): int(rh.get('n_dm_icc_avc', 0) or 0),
        }

        nd = len(grupos_dm)
        mat_z_dm  = np.zeros((nd, nd))
        mat_txt_dm = [[''] * nd for _ in range(nd)]

        for i in range(nd):
            for j in range(nd):
                if i == j:
                    val = totais_dm[i]
                else:
                    key = (grupos_dm[min(i,j)], grupos_dm[max(i,j)])
                    val = pares_dm.get(key, 0)
                mat_z_dm[i][j] = val
                pct = _p(val, n_dm)
                mat_txt_dm[i][j] = (
                    f"<b>{val:,}</b><br>{pct:.1f}%"
                    if i == j else f"{val:,}<br>{pct:.1f}%"
                )

        col_hm_dm, col_leg_dm = st.columns([3, 2])

        def _hex_to_rgba_dm(h, a=0.13):
            h = h.lstrip('#')
            r, g, b = int(h[0:2],16), int(h[2:4],16), int(h[4:6],16)
            return f"rgba({r},{g},{b},{a})"

        with col_hm_dm:
            colorscale_dm = T.HEATMAP_COLORSCALE
            fig_hm_dm = go.Figure(data=go.Heatmap(
                z=mat_z_dm.tolist(),
                x=grupos_dm, y=grupos_dm,
                text=mat_txt_dm,
                texttemplate="%{text}",
                textfont=dict(size=12, color=T.TEXT),
                colorscale=colorscale_dm,
                showscale=True,
                colorbar=dict(
                    title=dict(text='Pacientes',
                               font=dict(color=T.TEXT_SECONDARY, size=11)),
                    tickfont=dict(color=T.TEXT_SECONDARY, size=9),
                    thickness=14, len=0.85,
                    bgcolor=T.PAPER_BG,
                    bordercolor=T.PAPER_BG,
                ),
                hovertemplate=(
                    "<b>DM + %{y} + %{x}</b><br>"
                    "Pacientes: <b>%{z:,}</b><extra></extra>"
                ),
            ))
            for i, (nome, cor) in enumerate(zip(grupos_dm, cores_dm)):
                fig_hm_dm.add_shape(
                    type='rect', xref='x', yref='y',
                    x0=i-0.5, y0=i-0.5, x1=i+0.5, y1=i+0.5,
                    fillcolor=_hex_to_rgba_dm(cor),
                    line=dict(color=cor, width=3),
                )
            fig_hm_dm.update_layout(
                title=dict(
                    text=(
                        f"Comorbidades em diabéticos"
                        f"<br><sup style='color:{T.TEXT_MUTED}'>"
                        f"Total de diabéticos: {n_dm:,} · "
                        f"Diagonal = total com DM+comorbidade · "
                        f"Off-diagonal = interseção</sup>"
                    ),
                    font=dict(size=13, color=T.TEXT), x=0.5,
                ),
                height=430,
                paper_bgcolor=T.PAPER_BG,
                plot_bgcolor=T.PLOT_BG,
                xaxis=dict(
                    tickfont=dict(color=T.TEXT, size=13, family='monospace'),
                    side='bottom', showgrid=False,
                ),
                yaxis=dict(
                    tickfont=dict(color=T.TEXT, size=13, family='monospace'),
                    autorange='reversed', showgrid=False,
                ),
                margin=dict(l=10, r=10, t=70, b=30),
            )
            st.plotly_chart(fig_hm_dm, use_container_width=True)

        with col_leg_dm:
            sub_g_dm, sub_p_dm = st.columns(2)
            with sub_g_dm:
                st.markdown(
                    f"<p style='font-size:13px;font-weight:700;"
                    f"color:{T.TEXT_SECONDARY};margin-bottom:8px'>🩺 Grupos</p>",
                    unsafe_allow_html=True
                )
                for nome, val, cor in zip(grupos_dm, totais_dm, cores_dm):
                    pct_g = _p(val, n_dm)
                    bar_w = max(4, int(pct_g * 1.5))
                    st.markdown(
                        f"<div style='margin-bottom:10px'>"
                        f"<span style='color:{cor};font-size:15px'>⬤</span> "
                        f"<span style='font-weight:700;color:{T.TEXT}'>{nome}</span><br>"
                        f"<span style='font-size:13px;color:{T.TEXT_SECONDARY}'>{val:,}</span> "
                        f"<span style='font-size:11px;color:{T.TEXT_MUTED}'>{pct_g:.1f}%</span><br>"
                        f"<div style='background:{cor};height:4px;"
                        f"width:{bar_w}%;border-radius:2px;opacity:0.7'></div>"
                        f"</div>",
                        unsafe_allow_html=True
                    )
            with sub_p_dm:
                st.markdown(
                    f"<p style='font-size:13px;font-weight:700;"
                    f"color:{T.TEXT_SECONDARY};margin-bottom:8px'>🔗 Sobreposições</p>",
                    unsafe_allow_html=True
                )
                pares_dm_sorted = sorted(pares_dm.items(), key=lambda x: -x[1])
                for (g1, g2), val in pares_dm_sorted:
                    if val > 0:
                        pct_p = _p(val, n_dm)
                        cor1 = cores_dm[grupos_dm.index(g1)]
                        cor2 = cores_dm[grupos_dm.index(g2)]
                        st.markdown(
                            f"<div style='margin-bottom:8px'>"
                            f"<span style='color:{cor1}'>⬤</span>"
                            f"<span style='color:{cor2}'>⬤</span> "
                            f"<span style='font-size:12px;color:{T.TEXT}'>"
                            f"<b>{g1}+{g2}</b></span><br>"
                            f"<span style='font-size:12px;color:{T.TEXT_SECONDARY}'>{val:,}</span> "
                            f"<span style='font-size:11px;color:{T.TEXT_MUTED}'>{pct_p:.1f}%</span>"
                            f"</div>",
                            unsafe_allow_html=True
                        )
            n_dm_todas5 = int(rh.get('n_dm_todas5', 0) or 0)
            if n_dm_todas5 > 0:
                st.markdown(
                    f"<div style='margin-top:12px;padding:8px 12px;"
                    f"border-left:3px solid #E63946;"
                    f"background:rgba(230,57,70,0.1);border-radius:4px'>"
                    f"<span style='font-size:11px;color:{T.TEXT_MUTED}'>"
                    f"DM + todas as 5 comorbidades</span><br>"
                    f"<span style='font-size:18px;font-weight:700;color:{T.TEXT}'>"
                    f"{n_dm_todas5:,}</span> "
                    f"<span style='font-size:11px;color:{T.TEXT_MUTED}'>"
                    f"({_p(n_dm_todas5, n_dm):.1f}%)</span>"
                    f"</div>",
                    unsafe_allow_html=True
                )
        st.markdown("---")
        # ══ BLOCO 4: LACUNAS ══════════════════════════════════
        st.markdown("#### 4️⃣ Lacunas de cuidado no DM")

        def _card_dm(col, emoji, titulo, val, denom, denom_label, caption_txt):
            with col:
                with st.container(border=True):
                    st.markdown(f"{emoji} **{titulo}**")
                    st.markdown(f"## {_p(val, denom):.1f}%")
                    st.metric("Pacientes", f"{val:,}", denom_label, delta_color="inverse")
                    st.caption(caption_txt)

        # ── Grupo 1: Controle glicêmico ──────────────────────────
        st.markdown("**🩸 Controle Glicêmico**")
        g_ctrl = st.columns(4)
        _card_dm(g_ctrl[0], "🔴", "DM não controlado (HbA1c acima da meta)",
                 sumario.get('n_DM_descontrolado', 0), n_dm, "dos diabéticos",
                 "HbA1c acima da meta individualizada. Meta geral: <7% (HbA1c). "
                 "Meta mais permissiva (≤8%) em idosos frágeis ou com múltiplas comorbidades.")

        _card_dm(g_ctrl[1], "🟠", "Sem HbA1c recente (>180 dias)",
                 sumario.get('n_DM_sem_hba1c', 0), n_dm, "dos diabéticos",
                 "Diabéticos com último exame de HbA1c há mais de 6 meses. "
                 "A maioria dos diabéticos necessita de HbA1c a cada 3–6 meses para ajuste terapêutico.")

        _card_dm(g_ctrl[2], "⛔", "HbA1c nunca solicitada",
                 sumario.get('n_DM_hba1c_nao_sol', 0), n_dm, "dos diabéticos",
                 "Sem nenhum registro de solicitação de HbA1c. Estes pacientes nunca tiveram "
                 "o controle glicêmico monitorado pelo exame padrão-ouro.")

        _card_dm(g_ctrl[3], "🔵", "DM+HAS com PA não controlada",
                 sumario.get('n_lac_dm_has_pa_desctrl', 0), n_dm, "dos diabéticos",
                 "PA >135/80 mmHg em diabéticos hipertensos. Meta mais rigorosa que na HAS isolada "
                 "pelo risco cumulativo cardiovascular e renal.")

        # ── Grupo 2: Rastreio ────────────────────────────────────
        st.markdown("**🔍 Rastreio de Diabetes na População**")
        g_rastr = st.columns(4)
        _card_dm(g_rastr[0], "🟣", "Hipertensos sem rastreio de DM",
                 sumario.get('n_lac_rastreio_dm_has', 0), tot, "da população total",
                 "Hipertensos sem glicemia de jejum ou HbA1c nos últimos 12 meses. "
                 "Diabéticos são diagnosticados 2× mais entre hipertensos. "
                 "Rastreio anual é recomendado para todos os hipertensos.")

        _card_dm(g_rastr[1], "🟣", "Adultos ≥45 anos sem rastreio de DM",
                 sumario.get('n_lac_rastreio_dm_45', 0), tot, "da população total",
                 "A partir dos 45 anos o rastreio de DM deve ocorrer ao menos a cada 3 anos "
                 "em assintomáticos sem outros fatores de risco. Com fatores de risco: anual.")

        # ── Grupo 3: Exames laboratoriais ────────────────────────
        st.markdown("**🔬 Exames Laboratoriais Mínimos para Diabéticos**")
        st.caption("Todo diabético deve realizar estes exames ao menos uma vez ao ano "
                   "para monitoramento de complicações e estratificação de risco.")
        g_lab = st.columns(5)
        _card_dm(g_lab[0], "🧪", "Sem creatinina no último ano",
                 sumario.get('n_lac_dm_creatinina', 0), n_dm, "dos diabéticos",
                 "Creatinina e TFG estimada são essenciais no DM para estadiamento de DRC "
                 "e ajuste de dose de metformina e outros hipoglicemiantes.")

        _card_dm(g_lab[1], "🧪", "Sem colesterol/lipidograma no último ano",
                 sumario.get('n_lac_dm_colesterol', 0), n_dm, "dos diabéticos",
                 "Diabéticos têm risco cardiovascular elevado. Perfil lipídico anual "
                 "orienta a terapia com estatinas, que é recomendada para a maioria dos diabéticos.")

        _card_dm(g_lab[2], "🧪", "Sem exame de urina (EAS) no último ano",
                 sumario.get('n_lac_dm_eas', 0), n_dm, "dos diabéticos",
                 "O EAS (urina tipo 1) identifica proteinúria e hematúria. "
                 "Importante na triagem de nefropatia diabética juntamente com microalbuminúria.")

        _card_dm(g_lab[3], "🧫", "Sem microalbuminúria no último ano",
                 sumario.get('n_lac_microalb', 0), n_dm, "dos diabéticos",
                 "Marcador mais precoce de nefropatia diabética, antes do surgimento de "
                 "proteinúria maciça. Detecta lesão renal quando ainda é reversível com tratamento.")

        _card_dm(g_lab[4], "⚖️", "Sem IMC calculável registrado",
                 sumario.get('n_lac_dm_imc', 0), n_dm, "dos diabéticos",
                 "Peso e altura não registrados. O IMC guia metas de perda de peso, "
                 "elegibilidade para cirurgia bariátrica e ajuste de metas glicêmicas.")

        # ── Grupo 4: Prevenção de pé diabético ───────────────────
        st.markdown("**🦶 Prevenção de Pé Diabético**")
        st.caption("O exame dos pés identifica neuropatia, doença arterial periférica e lesões "
                   "precoces — principais causas de amputação não traumática no Brasil.")
        g_pe = st.columns(3)
        _card_dm(g_pe[0], "🟠", "Sem exame do pé nos últimos 365 dias",
                 sumario.get('n_lac_pe_365d', 0), n_dm, "dos diabéticos",
                 "Meta mínima: ao menos 1 exame dos pés por ano para todos os diabéticos. "
                 "Inclui inspeção visual, monofilamento e pulsos periféricos.")

        _card_dm(g_pe[1], "🟡", "Sem exame do pé nos últimos 180 dias",
                 sumario.get('n_lac_pe_180d', 0), n_dm, "dos diabéticos",
                 "Para diabéticos de maior risco (neuropatia, DRC, DCP), o exame semestral "
                 "é recomendado. Atenção: grande parte desses pacientes tem exame antigo, "
                 "não necessariamente nunca fizeram o exame.")

        _card_dm(g_pe[2], "⛔", "Nunca teve exame do pé registrado",
                 sumario.get('n_lac_pe_nunca', 0), n_dm, "dos diabéticos",
                 "Sem nenhum registro de exame dos pés em toda a história clínica. "
                 "Estes pacientes são a prioridade máxima para intervenção — "
                 "risco elevado de úlcera e amputação não detectado.")

        # ── Grupo 5: Medicamentos SGLT2 ──────────────────────────
        n_irc_sglt2  = sumario.get('n_lac_dm_irc_sglt2', 0)
        n_comp_sglt2 = sumario.get('n_lac_dm_comp_sglt2', 0)
        n_dm_irc_total    = sumario.get('n_dm_com_irc', 0)
        n_dm_comp_total   = sumario.get('n_dm_complicado_total', 0)
        n_dm_irc_com      = sumario.get('n_dm_irc_com_sglt2', 0)
        n_dm_comp_com     = sumario.get('n_dm_comp_com_sglt2', 0)

        if n_irc_sglt2 > 0 or n_comp_sglt2 > 0:
            st.markdown("**💊 Oportunidades de Proteção Orgânica — Inibidores SGLT-2**")
            st.caption("Inibidores de SGLT-2 (empagliflozina, dapagliflozina) têm benefício "
                       "cardiovascular e renal comprovado além do controle glicêmico.")
            g_sglt = st.columns(2)

            with g_sglt[0]:
                with st.container(border=True):
                    st.markdown("💊 **DM+IRC sem SGLT-2**")
                    st.markdown(
                        f"**{n_dm_irc_total:,}** pacientes com DM e Doença Renal Crônica "
                        f"poderiam utilizar inibidor de SGLT-2 para reduzir a progressão da DRC. "
                        f"Destes, **{n_dm_irc_com:,}** pacientes "
                        f"(**{_p(n_dm_irc_com, n_dm_irc_total):.1f}%**) "
                        f"já receberam prescrição deste medicamento."
                    )
                    st.markdown(f"## {_p(n_irc_sglt2, n_dm_irc_total):.1f}%")
                    st.metric("Sem SGLT-2", f"{n_irc_sglt2:,}",
                              f"dos {n_dm_irc_total:,} pacientes elegíveis com DM+IRC",
                              delta_color="inverse")
                    st.caption(
                        "Inibidores de SGLT-2, além de ajudarem no controle da diabetes e na perda de peso, "
                        "reduzem a progressão de Doença Renal Crônica, diminuem a ocorrência de "
                        "hospitalizações por insuficiência cardíaca e eventos cardiovasculares."
                    )

            with g_sglt[1]:
                with st.container(border=True):
                    st.markdown("💊 **DM complicado sem SGLT-2**")
                    st.caption(
                        "DM complicado: pacientes com diabetes associada a "
                        "Doença Renal Crônica, Insuficiência Cardíaca e/ou Cardiopatia Isquêmica."
                    )
                    st.markdown(
                        f"**{n_dm_comp_total:,}** pacientes com DM complicado "
                        f"poderiam utilizar inibidor de SGLT-2 para reduzir eventos cardiovasculares "
                        f"e renais. Destes, **{n_dm_comp_com:,}** pacientes "
                        f"(**{_p(n_dm_comp_com, n_dm_comp_total):.1f}%**) "
                        f"já receberam prescrição deste medicamento."
                    )
                    st.markdown(f"## {_p(n_comp_sglt2, n_dm_comp_total):.1f}%")
                    st.metric("Sem SGLT-2", f"{n_comp_sglt2:,}",
                              f"dos {n_dm_comp_total:,} pacientes elegíveis com DM complicado",
                              delta_color="inverse")
                    st.caption(
                        "Inibidores de SGLT-2, além de ajudarem no controle da diabetes e na perda de peso, "
                        "reduzem a progressão de Doença Renal Crônica, diminuem a ocorrência de "
                        "hospitalizações por insuficiência cardíaca e eventos cardiovasculares. "
                        "Indicação com grau de evidência A nas diretrizes internacionais."
                    )

        st.caption("Lacunas calculadas sobre o denominador indicado em cada card. "
                   "Valores de 'sem exame' referem-se ao período indicado, "
                   "não necessariamente ausência histórica do exame.")



# TAB 6 — ACESSO E CONTINUIDADE
# ─────────────────────────────────────────────────────────────
with tab6:
    if not sumario:
        st.warning("Dados clínicos indisponíveis.")
    else:
        import plotly.express as px_exp

        def _p(n, d): return round(n / d * 100, 1) if d else 0.0
        tot = sumario.get('total_pop', 0) or 1
        lbl = df_terr['label_col'].iloc[0] if not df_terr.empty else 'Território'

        st.markdown("### 🔄 Acesso e Continuidade do Cuidado")
        st.caption(
            "Fonte: tabela fato (sumário por território). "
            "Denominador: total de pacientes cadastrados na área. "
            "Regularidade baseada no número de meses distintos com pelo menos uma consulta nos últimos 12 meses."
        )

        # ══ MÉTRICAS TOPO ══════════════════════════════════════
        c1, c2, c3, c4, c5, c6 = st.columns(6)
        c1.metric(
            "✅ Acompanhamento Regular",
            f"{sumario.get('n_regular',0):,}",
            f"{_p(sumario.get('n_regular',0), tot):.1f}%",
            help=(
                "Pacientes que tiveram consulta em 6 ou mais meses distintos "
                "nos últimos 12 meses — independentemente do tipo de profissional. "
                "Critério: meses_com_consulta_12m ≥ 6."
            )
        )
        c2.metric(
            "⚠️ Sem consulta médica há mais de 180 dias",
            f"{sumario.get('n_sem_medico_180d',0):,}",
            f"{_p(sumario.get('n_sem_medico_180d',0), tot):.1f}%",
            delta_color="inverse",
            help=(
                "Pacientes cuja última consulta com médico ocorreu há mais de 180 dias, "
                "ou que nunca consultaram com médico no sistema."
            )
        )
        c3.metric(
            "🚨 Alto risco com baixo acesso",
            f"{sumario.get('n_alto_risco_baixo_acesso',0):,}",
            f"{_p(sumario.get('n_alto_risco_baixo_acesso',0), tot):.1f}%",
            delta_color="inverse",
            help=(
                "Pacientes com escore de Charlson ≥7 (carga de morbidade muito alta) "
                "que consultam abaixo do percentil 25 do seu grupo de pares "
                "(mesma faixa etária, sexo e nível de risco). "
                "São os que mais precisam de cuidado e menos o acessam."
            )
        )
        c4.metric(
            "🏥 Internação nos últimos 12 meses",
            f"{sumario.get('n_internacao_365d',0):,}",
            f"{_p(sumario.get('n_internacao_365d',0), tot):.1f}%",
            delta_color="inverse",
            help="Pacientes com pelo menos uma internação hospitalar nos últimos 365 dias."
        )
        c5.metric(
            "📅 Intervalo mediano entre consultas",
            f"{sumario.get('intervalo_mediano_medio',0):.0f} dias",
            help=(
                "Mediana do intervalo em dias entre consultas médicas consecutivas, "
                "calculado individualmente por paciente nos últimos 365 dias. "
                "Valores maiores indicam menor frequência de acompanhamento."
            )
        )
        c6.metric(
            "📋 Média de consultas médicas por ano",
            f"{sumario.get('media_consultas_ano',0):.1f}",
            help="Média do número de consultas com médico realizadas nos últimos 365 dias."
        )

        st.markdown("---")

        # ══ BLOCO A: REGULARIDADE ══════════════════════════════
        st.markdown("#### A · Regularidade de Acompanhamento")
        st.caption(
            "Classificação baseada no número de meses distintos com pelo menos uma consulta "
            "(de qualquer profissional) nos últimos 12 meses. "
            "Cada barra representa a proporção de pacientes naquela categoria em relação "
            "ao total de cadastrados no território."
        )

        reg_cats = {
            "Acompanhamento regular — consulta em 6 ou mais meses do ano":
                sumario.get('n_regular', 0),
            "Acompanhamento irregular — consulta em 3 a 5 meses do ano":
                sumario.get('n_irregular', 0),
            "Acompanhamento esporádico — consulta em apenas 1 ou 2 meses do ano":
                sumario.get('n_esporadico', 0),
            "Sem nenhum registro de consulta nos últimos 12 meses":
                sumario.get('n_sem_acompanhamento', 0),
        }
        cores_reg = ['#2ECC71','#F4D03F','#E67E22','#E74C3C']

        # A1 — Grouped bar por território
        st.markdown("**A1 · Frequência de acompanhamento por território (% da população cadastrada)**")
        st.caption(
            "Conta o total de consultas com médico, enfermeiro ou técnico de enfermagem "
            "nos últimos 12 meses — excluindo visitas de Agente Comunitário de Saúde (ACS). "
            "Consideramos como «acompanhamento regular» ter 6 ou mais consultas no ano; "
            "«irregular» entre 3 e 5 consultas no ano; "
            "«esporádico» com 1 ou 2 consultas no ano; "
            "e «sem acompanhamento clínico» sem nenhuma consulta nos últimos 12 meses."
        )
        _grouped_bar_territorio(
            df_terr,
            cols=['pct_regular','pct_irregular','pct_esporadico','pct_sem_acomp'],
            labels=[
                'Regular — 6 ou mais consultas clínicas nos últimos 12 meses (médico, enfermeiro ou técnico de enfermagem)',
                'Irregular — 3 a 5 consultas clínicas nos últimos 12 meses',
                'Esporádico — 1 a 2 consultas clínicas nos últimos 12 meses',
                'Sem acompanhamento clínico — nenhuma consulta clínica registrada nos últimos 12 meses',
            ],
            cores=cores_reg,
            titulo='Frequência de acompanhamento por ' + lbl + ' — altura = % da população cadastrada',
            legenda_baixo=True,
        )

        # A2 — Grouped bar por AP para indicadores de acesso
        st.markdown("**A2 · Indicadores de Acesso e Continuidade por Território**")
        st.caption(
            "⚠️ **Atenção:** estes indicadores medem especificamente consultas **médicas** — "
            "diferente do gráfico A1, que conta consultas de médico, enfermeiro e técnico de enfermagem. "
            "Por isso os percentuais são maiores: um paciente pode ter consultado com enfermeiro ou técnico "
            "e ainda assim não ter visto um médico no período. "
            "As barras de ausência de médico NÃO são cumulativas: "
            "quem está sem médico há mais de 365 dias também está contado nos 180 dias."
        )
        _grouped_bar_territorio(
            df_terr,
            cols=['pct_sem_consulta','pct_sem_medico_180d','pct_sem_medico_365d',
                  'pct_freq_urgencia','pct_baixa_longitudinalidade'],
            labels=[
                'Sem nenhuma consulta médica nos últimos 12 meses',
                'Sem consulta médica há mais de 180 dias (6 meses)',
                'Sem consulta médica há mais de 365 dias (1 ano)',
                'Usuário frequente de urgência — 3 ou mais visitas a UPA ou hospital nos últimos 12 meses',
                'Baixa longitudinalidade — mais de 50% das consultas médicas realizadas fora da unidade de referência nos últimos 12 meses',
            ],
            cores=['#8E44AD','#E74C3C','#C0392B','#E67E22','#F4D03F'],
            titulo='Indicadores de Acesso e Continuidade por ' + lbl + ' (% da população cadastrada)',
            eixo_y='% da população',
            legenda_baixo=True,
        )

        # ── Card Alto Risco + Baixo Acesso ──
        n_arba = sumario.get('n_alto_risco_baixo_acesso', 0)
        st.markdown(f"""
        <div style='background:{T.CARD_BG}; border-left:4px solid #E74C3C;
                    border-radius:10px; padding:16px; margin:8px 0;'>
            <span style='color:#E74C3C; font-weight:700;'>🚨 Alto Risco + Baixo Acesso</span>
            &nbsp;&nbsp;
            <span style='color:{T.TEXT}; font-size:1.6em; font-weight:800;'>{n_arba:,}</span>
            &nbsp;&nbsp;
            <span style='color:{T.TEXT_MUTED}; font-size:0.85em;'>
            pacientes com Charlson muito alto que consultam abaixo do P25 do seu grupo —
            os que <strong>mais precisam</strong> e <strong>menos acessam</strong>.
            </span>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("---")

        # ══ BLOCO B: PIRÂMIDES DE COBERTURA (MM_consultas_agregado) ═══════
        st.markdown("#### B · Cobertura por Faixa Etária — Pirâmides")
        st.caption("Fonte: MM_consultas_agregado · população (cinza) vs pacientes com ao menos 1 consulta por período")

        @st.cache_data(show_spinner=False, ttl=1)
        def carregar_consultas_agregado(ap=None, clinica=None, esf=None):
            # Filtros diretos na tabela fato (sem grupo_etario que é calculado)
            clauses = ["genero IS NOT NULL", "idade IS NOT NULL",
                       "area_programatica_cadastro IS NOT NULL",
                       "nome_clinica_cadastro IS NOT NULL",
                       "nome_esf_cadastro IS NOT NULL"]
            if ap:      clauses.append(f"area_programatica_cadastro = '{ap}'")
            if clinica: clauses.append(f"nome_clinica_cadastro = '{clinica}'")
            if esf:     clauses.append(f"nome_esf_cadastro = '{esf}'")
            where_fato = "WHERE " + " AND ".join(clauses)
            sql = f"""
            WITH fato AS (
                SELECT
                    genero,
                    CASE
                        WHEN idade <  5 THEN '00-04' WHEN idade < 10 THEN '05-09'
                        WHEN idade < 15 THEN '10-14' WHEN idade < 20 THEN '15-19'
                        WHEN idade < 25 THEN '20-24' WHEN idade < 30 THEN '25-29'
                        WHEN idade < 35 THEN '30-34' WHEN idade < 40 THEN '35-39'
                        WHEN idade < 45 THEN '40-44' WHEN idade < 50 THEN '45-49'
                        WHEN idade < 55 THEN '50-54' WHEN idade < 60 THEN '55-59'
                        WHEN idade < 65 THEN '60-64' WHEN idade < 70 THEN '65-69'
                        WHEN idade < 75 THEN '70-74' WHEN idade < 80 THEN '75-79'
                        WHEN idade < 85 THEN '80-84' WHEN idade < 90 THEN '85-89'
                        WHEN idade < 95 THEN '90-94' ELSE '95+'
                    END AS grupo_etario,
                    CASE
                        WHEN idade <  5 THEN  1 WHEN idade < 10 THEN  2
                        WHEN idade < 15 THEN  3 WHEN idade < 20 THEN  4
                        WHEN idade < 25 THEN  5 WHEN idade < 30 THEN  6
                        WHEN idade < 35 THEN  7 WHEN idade < 40 THEN  8
                        WHEN idade < 45 THEN  9 WHEN idade < 50 THEN 10
                        WHEN idade < 55 THEN 11 WHEN idade < 60 THEN 12
                        WHEN idade < 65 THEN 13 WHEN idade < 70 THEN 14
                        WHEN idade < 75 THEN 15 WHEN idade < 80 THEN 16
                        WHEN idade < 85 THEN 17 WHEN idade < 90 THEN 18
                        WHEN idade < 95 THEN 19 ELSE 20
                    END AS grupo_etario_ordem,
                    -- OR verdadeiro por paciente individual
                    CASE WHEN COALESCE(consultas_medicas_365d,0) > 0
                              OR COALESCE(consultas_enfermagem_365d,0) > 0
                              OR COALESCE(consultas_tecnico_enfermagem_365d,0) > 0
                         THEN 1 ELSE 0 END AS clinico_365d,
                    CASE WHEN COALESCE(consultas_medicas_180d,0) > 0
                              OR COALESCE(consultas_enfermagem_180d,0) > 0
                         THEN 1 ELSE 0 END AS clinico_180d,
                    CASE WHEN COALESCE(consultas_medicas_90d,0) > 0
                              OR COALESCE(consultas_enfermagem_90d,0) > 0
                         THEN 1 ELSE 0 END AS clinico_90d,
                    CASE WHEN COALESCE(consultas_medicas_365d,0) > 0 THEN 1 ELSE 0 END AS med_365d,
                    CASE WHEN COALESCE(consultas_medicas_180d,0) > 0 THEN 1 ELSE 0 END AS med_180d,
                    CASE WHEN COALESCE(consultas_medicas_90d,0)  > 0 THEN 1 ELSE 0 END AS med_90d,
                    CASE WHEN COALESCE(consultas_enfermagem_365d,0) > 0 THEN 1 ELSE 0 END AS enf_365d,
                    CASE WHEN COALESCE(consultas_enfermagem_180d,0) > 0 THEN 1 ELSE 0 END AS enf_180d,
                    CASE WHEN COALESCE(consultas_enfermagem_90d,0)  > 0 THEN 1 ELSE 0 END AS enf_90d,
                    -- Regularidade clínica (médico+enfermeiro+técnico, sem ACS)
                    CASE
                        WHEN (COALESCE(consultas_medicas_365d,0)+COALESCE(consultas_enfermagem_365d,0)+COALESCE(consultas_tecnico_enfermagem_365d,0)) >= 6 THEN 'regular'
                        WHEN (COALESCE(consultas_medicas_365d,0)+COALESCE(consultas_enfermagem_365d,0)+COALESCE(consultas_tecnico_enfermagem_365d,0)) BETWEEN 3 AND 5 THEN 'irregular'
                        WHEN (COALESCE(consultas_medicas_365d,0)+COALESCE(consultas_enfermagem_365d,0)+COALESCE(consultas_tecnico_enfermagem_365d,0)) BETWEEN 1 AND 2 THEN 'esporadico'
                        ELSE 'sem_acompanhamento'
                    END AS regularidade_clinica,
                    -- Perfil
                    COALESCE(perfil_cuidado_365d, 'sem_consultas') AS perfil_cuidado_365d
                FROM `rj-sms-sandbox.sub_pav_us.MM_2026_novos_cadastros_stopp_start`
                WHERE genero IS NOT NULL AND idade IS NOT NULL
                  AND area_programatica_cadastro IS NOT NULL
                  AND nome_clinica_cadastro IS NOT NULL
                  AND nome_esf_cadastro IS NOT NULL
                  {'AND area_programatica_cadastro = ' + chr(39) + ap + chr(39) if ap else ''}
                  {'AND nome_clinica_cadastro = ' + chr(39) + clinica + chr(39) if clinica else ''}
                  {'AND nome_esf_cadastro = ' + chr(39) + esf + chr(39) if esf else ''}
            )
            SELECT
                genero, grupo_etario, grupo_etario_ordem,
                COUNT(*)          AS n_pacientes,
                SUM(med_365d)     AS n_com_medico_365d,
                SUM(med_180d)     AS n_com_medico_180d,
                SUM(med_90d)      AS n_com_medico_90d,
                SUM(enf_365d)     AS n_com_enfermagem_365d,
                SUM(enf_180d)     AS n_com_enfermagem_180d,
                SUM(enf_90d)      AS n_com_enfermagem_90d,
                SUM(clinico_365d) AS n_com_consulta_365d,
                SUM(clinico_180d) AS n_com_consulta_180d,
                SUM(clinico_90d)  AS n_com_consulta_90d,
                COUNTIF(regularidade_clinica = 'regular')           AS n_regular,
                COUNTIF(regularidade_clinica = 'irregular')         AS n_irregular,
                COUNTIF(regularidade_clinica = 'esporadico')        AS n_esporadico,
                COUNTIF(regularidade_clinica = 'sem_acompanhamento') AS n_sem_acompanhamento,
                COUNTIF(perfil_cuidado_365d = 'medico_centrado')    AS n_medico_centrado,
                COUNTIF(perfil_cuidado_365d = 'enfermagem_centrado') AS n_enfermagem_centrado,
                COUNTIF(perfil_cuidado_365d = 'compartilhado')      AS n_compartilhado,
                COUNTIF(perfil_cuidado_365d IN ('sem_consultas','indefinido') OR perfil_cuidado_365d IS NULL) AS n_sem_consultas
            FROM fato
            GROUP BY genero, grupo_etario, grupo_etario_ordem
            ORDER BY grupo_etario_ordem, genero
            """
            try:
                client = get_bigquery_client()
                return client.query(sql).result().to_dataframe(create_bqstorage_client=False)
            except Exception as e:
                st.error(f"❌ Erro ao carregar MM_consultas_agregado: {e}")
                return pd.DataFrame()

        with st.spinner("Carregando pirâmides de cobertura..."):
            df_cons = carregar_consultas_agregado(
                ap=territorio['ap'],
                clinica=territorio['clinica'],
                esf=territorio['esf']
            )

        ORDEM_FAIXA = ['00-04','05-09','10-14','15-19','20-24','25-29','30-34',
                       '35-39','40-44','45-49','50-54','55-59','60-64','65-69',
                       '70-74','75-79','80-84','85-89','90-94','95+']

        def _piramide_cobertura(df, col_365, col_180, col_90, titulo):
            """Pirâmide de cobertura: pop (cinza) + 3 períodos sobrepostos."""
            if df.empty: return None
            masc = df[df['genero'].str.lower().str.contains('masc|^m$', regex=True)].copy()
            fem  = df[~df['genero'].str.lower().str.contains('masc|^m$', regex=True)].copy()
            for d in [masc, fem]:
                d.sort_values('grupo_etario_ordem', inplace=True)

            max_val = max(
                masc['n_pacientes'].max() if len(masc) else 0,
                fem['n_pacientes'].max()  if len(fem)  else 0
            ) * 1.15 or 1

            fig = go.Figure()
            # Pop base masculino
            fig.add_trace(go.Bar(
                y=masc['grupo_etario'], x=-masc['n_pacientes'],
                orientation='h', name='Sem atendimento nos últimos 12 meses',
                marker_color='#AAAAAA', opacity=0.35,
                hovertemplate='%{customdata:,} pacientes<extra>Masculino · Sem atendimento</extra>',
                customdata=masc['n_pacientes'], showlegend=True, legendgroup='pop'
            ))
            # Cobertura masculino — 3 períodos
            for col, nome, cor, op in [
                (col_365,'Com atendimento nos últimos 12 meses','#2980b9',0.50),
                (col_180,'Com atendimento nos últimos 6 meses', '#1abc9c',0.68),
                (col_90, 'Com atendimento nos últimos 3 meses', '#f39c12',0.86),
            ]:
                fig.add_trace(go.Bar(
                    y=masc['grupo_etario'], x=-masc[col],
                    orientation='h', name=nome,
                    marker_color=cor, opacity=op,
                    hovertemplate=f'%{{customdata:,}} pacientes ({nome})<extra>Masculino</extra>',
                    customdata=masc[col],
                    showlegend=True, legendgroup=nome
                ))
            # Pop base feminino
            fig.add_trace(go.Bar(
                y=fem['grupo_etario'], x=fem['n_pacientes'],
                orientation='h', name='Sem atendimento nos últimos 12 meses',
                marker_color='#AAAAAA', opacity=0.35,
                hovertemplate='%{x:,} pacientes<extra>Feminino · Sem atendimento</extra>',
                showlegend=False, legendgroup='pop'
            ))
            for col, nome, cor, op in [
                (col_365,'Com atendimento nos últimos 12 meses','#2980b9',0.50),
                (col_180,'Com atendimento nos últimos 6 meses', '#1abc9c',0.68),
                (col_90, 'Com atendimento nos últimos 3 meses', '#f39c12',0.86),
            ]:
                fig.add_trace(go.Bar(
                    y=fem['grupo_etario'], x=fem[col],
                    orientation='h', name=nome,
                    marker_color=cor, opacity=op,
                    hovertemplate=f'%{{x:,}} pacientes ({nome})<extra>Feminino</extra>',
                    showlegend=False, legendgroup=nome
                ))

            fig.update_layout(
                barmode='overlay', height=520,
                title=dict(text=titulo, font=dict(color=T.TEXT, size=14), x=0.5),
                margin=dict(l=60, r=20, t=60, b=40),
                paper_bgcolor=T.PAPER_BG, plot_bgcolor=T.PLOT_BG,
                xaxis=dict(
                    range=[-max_val, max_val], zeroline=True,
                    zerolinecolor=T.TEXT_MUTED, zerolinewidth=2,
                    title='← Masculino | Feminino →',
                    tickformat=',',
                    tickvals=[-max_val,-max_val*0.5,0,max_val*0.5,max_val],
                    ticktext=[f'{abs(v):,.0f}' for v in [-max_val,-max_val*0.5,0,max_val*0.5,max_val]],
                    tickfont=dict(color=T.TEXT_MUTED, size=10)
                ),
                yaxis=dict(
                    type='category', categoryorder='array',
                    categoryarray=ORDEM_FAIXA, title='',
                    tickfont=dict(color=T.TEXT, size=10)
                ),
                legend=dict(
                    orientation='v', xanchor='left', x=1.01,
                    yanchor='middle', y=0.5,
                    font=dict(color=T.TEXT, size=10),
                    bgcolor=T.LEGEND_BG,
                    bordercolor=T.LEGEND_BORDER, borderwidth=1,
                ),
                bargap=0.1
            )
            return fig

        def _linha_cobertura(df, col_365, col_180, col_90, titulo):
            """Linha de cobertura por período e faixa etária."""
            if df.empty: return None
            agg = df.groupby(['grupo_etario','grupo_etario_ordem']).agg(
                n_pacientes=(col_365[:-5]+'0d'[:-2]+'acientes' if False else 'n_pacientes','sum'),
                c365=(col_365,'sum'), c180=(col_180,'sum'), c90=(col_90,'sum')
            ).reset_index().sort_values('grupo_etario_ordem')
            # Reagrupar corretamente
            agg = df.groupby(['grupo_etario','grupo_etario_ordem']).sum(numeric_only=True).reset_index()
            agg = agg.sort_values('grupo_etario_ordem')
            agg['pct_12m'] = agg[col_365] / agg['n_pacientes'] * 100
            agg['pct_6m']  = agg[col_180] / agg['n_pacientes'] * 100
            agg['pct_3m']  = agg[col_90]  / agg['n_pacientes'] * 100

            fig = go.Figure()
            for col_pct, nome, cor, lw, ms in [
                ('pct_12m','Últimos 12 meses','#2980b9',2,6),
                ('pct_6m', 'Últimos 6 meses', '#1abc9c',3,8),
                ('pct_3m', 'Últimos 3 meses', '#f39c12',4,10),
            ]:
                fig.add_trace(go.Scatter(
                    x=agg['grupo_etario'], y=agg[col_pct],
                    mode='lines+markers', name=nome,
                    line=dict(color=cor, width=lw),
                    marker=dict(size=ms),
                    hovertemplate='%{y:.1f}%<extra>'+nome+'</extra>'
                ))
            fig.update_layout(
                title=dict(text=titulo, font=dict(color=T.TEXT, size=14)),
                height=360, margin=dict(l=50, r=20, t=50, b=80),
                paper_bgcolor=T.PAPER_BG, plot_bgcolor=T.PLOT_BG,
                xaxis=dict(type='category', categoryorder='array',
                           categoryarray=ORDEM_FAIXA,
                           tickangle=45, tickfont=dict(color=T.TEXT, size=10),
                           title='Faixa etária', gridcolor=T.GRID),
                yaxis=dict(title='% com atendimento', range=[0,105],
                           tickfont=dict(color=T.TEXT_MUTED, size=10), gridcolor=T.GRID),
                legend=dict(
                    orientation='v', xanchor='left', x=1.01,
                    yanchor='middle', y=0.5,
                    font=dict(color=T.TEXT, size=11),
                    bgcolor=T.LEGEND_BG,
                    bordercolor=T.LEGEND_BORDER, borderwidth=1,
                )
            )
            return fig

        def _piramide_bilateral_empilhada(df, cats_cols, cats_labels, cats_cores, titulo):
            """
            Pirâmide bilateral com barras empilhadas em valores ABSOLUTOS.
            Masculino à esquerda (negativo), Feminino à direita (positivo).
            A escala é simétrica baseada na faixa com mais pacientes.
            Hover mostra % da população da faixa.
            """
            if df.empty: return None
            masc = df[df['genero'].str.lower().str.contains('masc|^m$', regex=True)].copy()
            fem  = df[~df['genero'].str.lower().str.contains('masc|^m$', regex=True)].copy()
            masc = masc.groupby(['grupo_etario','grupo_etario_ordem']).sum(numeric_only=True).reset_index().sort_values('grupo_etario_ordem')
            fem  = fem.groupby(['grupo_etario','grupo_etario_ordem']).sum(numeric_only=True).reset_index().sort_values('grupo_etario_ordem')

            faixas_validas = set(masc['grupo_etario'].tolist() + fem['grupo_etario'].tolist())
            ordem_filtrada = [f for f in ORDEM_FAIXA if f in faixas_validas]

            # Escala simétrica pelo lado com mais pacientes
            max_val = max(
                masc['n_pacientes'].max() if len(masc) else 0,
                fem['n_pacientes'].max()  if len(fem)  else 0
            ) * 1.05 or 1

            # Pré-calcular % por faixa para o hover
            for d in [masc, fem]:
                for col in cats_cols:
                    if col in d.columns:
                        d[f'{col}_pct'] = (d[col] / d['n_pacientes'].replace(0, 1) * 100).round(1)

            fig = go.Figure()
            shown = set()
            for col, nome, cor in zip(cats_cols, cats_labels, cats_cores):
                show = nome not in shown
                shown.add(nome)
                col_pct = f'{col}_pct'
                # Masculino (negativo)
                fig.add_trace(go.Bar(
                    y=masc['grupo_etario'],
                    x=-masc[col] if col in masc.columns else [0]*len(masc),
                    orientation='h', name=nome,
                    marker_color=cor, showlegend=show, legendgroup=nome,
                    hovertemplate=(
                        '<b>%{y}</b> · Masculino<br>'
                        f'{nome}<br>'
                        'Pacientes: <b>%{customdata[0]:,}</b><br>'
                        '% da faixa: <b>%{customdata[1]:.1f}%</b>'
                        '<extra></extra>'
                    ),
                    customdata=list(zip(
                        masc[col].tolist() if col in masc.columns else [0]*len(masc),
                        masc[col_pct].tolist() if col_pct in masc.columns else [0]*len(masc),
                    ))
                ))
                # Feminino (positivo)
                fig.add_trace(go.Bar(
                    y=fem['grupo_etario'],
                    x=fem[col] if col in fem.columns else [0]*len(fem),
                    orientation='h', name=nome,
                    marker_color=cor, showlegend=False, legendgroup=nome,
                    hovertemplate=(
                        '<b>%{y}</b> · Feminino<br>'
                        f'{nome}<br>'
                        'Pacientes: <b>%{customdata[0]:,}</b><br>'
                        '% da faixa: <b>%{customdata[1]:.1f}%</b>'
                        '<extra></extra>'
                    ),
                    customdata=list(zip(
                        fem[col].tolist() if col in fem.columns else [0]*len(fem),
                        fem[col_pct].tolist() if col_pct in fem.columns else [0]*len(fem),
                    ))
                ))

            tick_vals = [-max_val, -max_val*0.5, 0, max_val*0.5, max_val]
            tick_text = [f'{abs(v):,.0f}' for v in tick_vals]

            fig.update_layout(
                barmode='relative',
                height=580,
                title=dict(text=titulo, font=dict(color=T.TEXT, size=14), x=0.5),
                margin=dict(l=60, r=20, t=70, b=130),
                paper_bgcolor=T.PAPER_BG, plot_bgcolor=T.PLOT_BG,
                xaxis=dict(
                    range=[-max_val*1.02, max_val*1.02],
                    zeroline=True, zerolinecolor=T.TEXT_MUTED, zerolinewidth=2,
                    title='← Masculino  |  Feminino →',
                    tickvals=tick_vals, ticktext=tick_text,
                    tickfont=dict(color=T.TEXT_MUTED, size=10),
                    gridcolor=T.GRID
                ),
                yaxis=dict(
                    type='category', categoryorder='array',
                    categoryarray=ordem_filtrada, title='',
                    tickfont=dict(color=T.TEXT, size=10)
                ),
                legend=dict(
                    orientation='h',
                    xanchor='center', x=0.5,
                    yanchor='top',    y=-0.18,
                    font=dict(color=T.TEXT, size=10),
                    bgcolor=T.LEGEND_BG,
                    bordercolor=T.LEGEND_BORDER, borderwidth=1,
                ),
                bargap=0.35
            )
            return fig

        def _piramide_regularidade(df, titulo):
            return _piramide_bilateral_empilhada(
                df,
                cats_cols=['n_regular','n_irregular','n_esporadico','n_sem_acompanhamento'],
                cats_labels=[
                    'Regular — 6 ou mais consultas clínicas no ano (médico, enfermeiro ou técnico de enfermagem)',
                    'Irregular — entre 3 e 5 consultas clínicas no ano',
                    'Esporádico — apenas 1 ou 2 consultas clínicas no ano',
                    'Sem acompanhamento clínico — nenhuma consulta nos últimos 12 meses',
                ],
                cats_cores=['#2ECC71','#F4D03F','#E67E22','#E74C3C'],
                titulo=titulo
            )

        def _piramide_perfis(df, titulo):
            return _piramide_bilateral_empilhada(
                df,
                cats_cols=['n_medico_centrado','n_enfermagem_centrado',
                           'n_compartilhado','n_sem_consultas'],
                cats_labels=[
                    'Cuidado médico-centrado — mais de 75% das consultas realizadas com médico',
                    'Cuidado enfermagem-centrado — mais de 75% das consultas realizadas com enfermeiro',
                    'Cuidado compartilhado — consultas distribuídas entre médico e enfermeiro',
                    'Sem nenhuma consulta registrada nos últimos 12 meses',
                ],
                cats_cores=['#1A6FBF','#E91E8C','#27AE60','#C0392B'],
                titulo=titulo
            )

        if not df_cons.empty:
            # ── BLOCO B: Cobertura com seletor ──────────────────
            st.markdown("#### B · Cobertura de Atendimento por Faixa Etária")
            st.caption(
                "Proporção da população cadastrada que teve pelo menos uma consulta "
                "nos períodos de 3, 6 e 12 meses. "
                "Selecione o tipo de profissional para comparar diferentes dimensões do cuidado."
            )

            opcao_cob = st.selectbox(
                "Tipo de profissional:",
                [
                    "Qualquer profissional clínico (médico, enfermeiro ou técnico de enfermagem)",
                    "Apenas consultas médicas",
                    "Apenas consultas de enfermagem",
                ],
                key='sel_cobertura'
            )

            if "Apenas consultas médicas" in opcao_cob:
                col_365, col_180, col_90 = 'n_com_medico_365d','n_com_medico_180d','n_com_medico_90d'
                titulo_pir = "Cobertura por Consulta Médica"
                titulo_lin = "Cobertura Médica por faixa etária e período"
                n_cob = int(df_cons['n_com_medico_365d'].sum())
            elif "Apenas consultas de enfermagem" in opcao_cob:
                col_365, col_180, col_90 = 'n_com_enfermagem_365d','n_com_enfermagem_180d','n_com_enfermagem_90d'
                titulo_pir = "Cobertura por Consulta de Enfermagem"
                titulo_lin = "Cobertura de Enfermagem por faixa etária e período"
                n_cob = int(df_cons['n_com_enfermagem_365d'].sum())
            else:
                col_365, col_180, col_90 = 'n_com_consulta_365d','n_com_consulta_180d','n_com_consulta_90d'
                titulo_pir = "Cobertura — Qualquer Profissional Clínico"
                titulo_lin = "Cobertura por faixa etária e período — qualquer profissional clínico"
                n_cob = int(df_cons['n_com_consulta_365d'].sum())

            n_pop  = int(df_cons['n_pacientes'].sum())
            n_sem  = n_pop - n_cob
            pct    = round(n_cob / n_pop * 100, 1) if n_pop else 0

            mc1, mc2, mc3 = st.columns(3)
            mc1.metric("👥 Com atendimento (12 meses)", f"{n_cob:,}", f"{pct:.1f}% da população")
            mc2.metric("❌ Sem atendimento (12 meses)", f"{n_sem:,}",
                       f"{100-pct:.1f}% da população", delta_color="inverse")
            mc3.metric("📊 Total cadastrado", f"{n_pop:,}")

            col_pir, col_lin = st.columns([3, 2])
            with col_pir:
                fig_pir = _piramide_cobertura(df_cons, col_365, col_180, col_90, titulo_pir)
                if fig_pir:
                    st.plotly_chart(fig_pir, use_container_width=True, key='pir_cobertura')
            with col_lin:
                fig_lin = _linha_cobertura(df_cons, col_365, col_180, col_90, titulo_lin)
                if fig_lin:
                    st.plotly_chart(fig_lin, use_container_width=True, key='lin_cobertura')

            st.markdown("---")

            # ── B3 e B4 lado a lado ─────────────────────────────
            col_b3, col_b4 = st.columns(2)

            with col_b3:
                st.markdown("**B3 · Regularidade de Acompanhamento por Faixa Etária e Sexo**")
                st.caption(
                    "Masculino à esquerda, feminino à direita. "
                    "Conta consultas com médico, enfermeiro ou técnico de enfermagem — exclui ACS. "
                    "**Regular:** ≥6 consultas/ano · **Irregular:** 3–5 · "
                    "**Esporádico:** 1–2 · **Sem acompanhamento:** nenhuma."
                )
                fig_reg_faixa = _piramide_regularidade(df_cons,
                    'Regularidade de Acompanhamento Clínico')
                if fig_reg_faixa:
                    st.plotly_chart(fig_reg_faixa, use_container_width=True, key='reg_faixa')

            with col_b4:
                st.markdown("**B4 · Perfil de Atendimento por Faixa Etária e Sexo**")
                st.caption(
                    "Masculino à esquerda, feminino à direita. "
                    "**Médico-centrado:** >75% das consultas com médico. "
                    "**Enfermagem-centrado:** >75% com enfermeiro. "
                    "**Compartilhado:** distribuição equilibrada — perfil ideal na ESF."
                )
                fig_perfis = _piramide_perfis(df_cons,
                    'Perfil de Atendimento')
                if fig_perfis:
                    st.plotly_chart(fig_perfis, use_container_width=True, key='perfis_faixa')

            st.markdown("---")

            # ── C · Violino — Barreira de acesso por carga de morbidade ──
            st.markdown("#### C · Barreira de Acesso por Carga de Morbidade")
            st.caption(
                "Percentual de pacientes sem consulta médica há mais de 180 dias, "
                "por território. Cada ponto representa uma clínica da família. "
                "Selecione a carga de morbidade para identificar em quais territórios "
                "os pacientes mais doentes enfrentam maior barreira de acesso ao médico."
            )

            charlson_opcoes = ['Muito Alto', 'Alto', 'Moderado', 'Baixo', 'Todos os pacientes']
            sel_charlson = st.selectbox(
                "Carga de morbidade:",
                charlson_opcoes,
                key='sel_charlson_barreira'
            )

            @st.cache_data(show_spinner=False, ttl=900)
            def carregar_barreira_acesso(ap=None, clinica=None, esf=None):
                # Hierarquia: sem filtro → AP no eixo, clínica como ponto
                #             AP filtrada → clínica no eixo, ESF como ponto
                #             Clínica filtrada → ESF no eixo (strip plot)
                if clinica:
                    grupo_x = "nome_esf_cadastro"
                    ponto   = "nome_esf_cadastro"
                elif ap:
                    grupo_x = "nome_clinica_cadastro"
                    ponto   = "nome_esf_cadastro"
                else:
                    grupo_x = "area_programatica_cadastro"
                    ponto   = "nome_clinica_cadastro"

                clauses = []
                if ap:      clauses.append(f"area_programatica_cadastro = '{ap}'")
                if clinica: clauses.append(f"nome_clinica_cadastro = '{clinica}'")
                if esf:     clauses.append(f"nome_esf_cadastro = '{esf}'")
                where = ("WHERE " + " AND ".join(clauses)) if clauses else ""

                sql = f"""
                SELECT
                    {grupo_x}   AS grupo_x,
                    {ponto}     AS ponto,
                    charlson_categoria,
                    COUNT(*)    AS n_total,
                    ROUND(COUNTIF(dias_desde_ultima_medica > 180
                                  OR dias_desde_ultima_medica IS NULL)
                          * 100.0 / COUNT(*), 1)  AS pct_sem_medico_180d
                FROM `rj-sms-sandbox.sub_pav_us.MM_2026_novos_cadastros_stopp_start`
                {where}
                GROUP BY {grupo_x}, {ponto}, charlson_categoria
                HAVING COUNT(*) >= 10
                ORDER BY {grupo_x}, {ponto}, charlson_categoria
                """
                try:
                    client = get_bigquery_client()
                    return client.query(sql).result().to_dataframe(create_bqstorage_client=False)
                except Exception as e:
                    st.error(f"❌ Erro ao carregar barreira de acesso: {e}")
                    return pd.DataFrame()

            df_barreira = carregar_barreira_acesso(
                ap=territorio['ap'],
                clinica=territorio['clinica'],
                esf=territorio['esf']
            )

            if not df_barreira.empty:
                import re

                # Filtrar por carga de morbidade selecionada
                if sel_charlson == 'Todos os pacientes':
                    df_v = df_barreira.groupby(['grupo_x','ponto'], as_index=False).apply(
                        lambda g: pd.Series({
                            'pct_sem_medico_180d': round(
                                (g['n_total'] * g['pct_sem_medico_180d']).sum()
                                / g['n_total'].sum(), 1
                            ) if g['n_total'].sum() > 0 else 0.0,
                            'n_total': int(g['n_total'].sum()),
                        })
                    ).reset_index(drop=True)
                else:
                    df_v = df_barreira[
                        df_barreira['charlson_categoria'] == sel_charlson
                    ][['grupo_x','ponto','n_total','pct_sem_medico_180d']].copy()

                # Ordenar grupo_x numericamente
                def _ord_gx(v):
                    m = re.search(r'(\d+\.?\d*)', str(v))
                    return float(m.group(1)) if m else 999
                grupos_ord = sorted(df_v['grupo_x'].unique().tolist(), key=_ord_gx)

                # Labels conforme nível hierárquico
                if territorio['clinica']:
                    label_x     = "ESF"
                    label_ponto = "ESF"
                    modo_strip  = True   # clínica filtrada → 1 ponto por ESF
                elif territorio['ap']:
                    label_x     = "Clínica da Família"
                    label_ponto = "ESF"
                    modo_strip  = False  # AP filtrada → violino por clínica
                else:
                    label_x     = "Área Programática"
                    label_ponto = "Clínica da Família"
                    modo_strip  = False  # sem filtro → violino por AP

                titulo_fig = (
                    f"Barreira de acesso — {sel_charlson} · "
                    f"% sem consulta médica há >180 dias · "
                    f"cada ponto = uma {label_ponto.lower()}"
                )
                labels_fig = {
                    'pct_sem_medico_180d': '% sem consulta médica há >180 dias',
                    'grupo_x':  label_x,
                    'ponto':    label_ponto,
                    'n_total':  'Pacientes no grupo',
                }

                if modo_strip:
                    # Strip plot simples — 1 ponto por unidade (sem violino)
                    fig_bar = px.strip(
                        df_v,
                        x='grupo_x',
                        y='pct_sem_medico_180d',
                        color='grupo_x',
                        hover_data=['ponto','n_total'],
                        labels=labels_fig,
                        title=titulo_fig,
                        category_orders={'grupo_x': grupos_ord},
                        color_discrete_sequence=px.colors.qualitative.Bold,
                        height=420,
                    )
                    fig_bar.update_traces(
                        marker=dict(size=14, opacity=0.85, line=dict(width=1, color=T.BORDER)),
                        jitter=0,
                    )
                else:
                    # Violino com pontos — distribuição por território
                    fig_bar = px.violin(
                        df_v,
                        x='grupo_x',
                        y='pct_sem_medico_180d',
                        color='grupo_x',
                        box=True,
                        points='all',
                        hover_data=['ponto','n_total'],
                        labels=labels_fig,
                        title=titulo_fig,
                        category_orders={'grupo_x': grupos_ord},
                        color_discrete_sequence=px.colors.qualitative.Bold,
                        height=500,
                    )
                    fig_bar.update_traces(
                        meanline_visible=True,
                        marker=dict(size=8, opacity=0.65, line=dict(width=0)),
                        spanmode='hard',
                    )

                fig_bar.update_xaxes(
                    type='category',
                    categoryorder='array',
                    categoryarray=grupos_ord,
                    tickangle=-40 if len(grupos_ord) > 5 else 0,
                    tickfont=dict(color=T.TEXT, size=11),
                    title_font=dict(color=T.TEXT),
                )
                fig_bar.update_yaxes(
                    tickfont=dict(color=T.TEXT_MUTED, size=11),
                    ticksuffix='%',
                    gridcolor=T.GRID,
                    rangemode='tozero',
                    title_font=dict(color=T.TEXT),
                )
                fig_bar.update_layout(
                    showlegend=False,
                    paper_bgcolor=T.PAPER_BG,
                    plot_bgcolor=T.PLOT_BG,
                    font=dict(color=T.TEXT),
                    title_font=dict(size=12, color=T.TEXT),
                    margin=dict(l=60, r=20, t=55, b=80),
                )
                st.plotly_chart(fig_bar, use_container_width=True, key='violin_barreira')
                st.caption(
                    "Territórios com valores mais altos indicam maior proporção de pacientes "
                    "sem acesso ao médico. Filtre por 'Muito Alto' para identificar "
                    "onde os pacientes mais doentes enfrentam as maiores barreiras de acesso."
                )
            else:
                st.info("Sem dados suficientes para o violino de barreira de acesso.")

        else:
            st.info("Dados de cobertura indisponíveis.")


# Rodapé
st.markdown("---")
st.caption("SMS-RJ | Navegador Clínico | Dados agregados da população")