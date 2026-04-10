import streamlit as st
from utils.bigquery_client import test_connection
from utils.data_loader import limpar_cache
from utils.auth import requer_login
from streamlit_option_menu import option_menu
from utils import theme as T

# ═══════════════════════════════════════════════════════════════
# CONFIGURAÇÃO DA PÁGINA
# ═══════════════════════════════════════════════════════════════
st.set_page_config(
    page_title="Navegador Clínico",
    page_icon="🏥",
    layout="wide"
)

# ═══════════════════════════════════════════════════════════════
# ✅ LOGIN GLOBAL - EXIGIR EM TODA A APLICAÇÃO
# ═══════════════════════════════════════════════════════════════
usuario_logado = requer_login()

# ═══════════════════════════════════════════════════════════════
# SALVAR USUÁRIO NO SESSION STATE PARA OUTRAS PÁGINAS
# ═══════════════════════════════════════════════════════════════
st.session_state['usuario_global'] = usuario_logado

# ═══════════════════════════════════════════════════════════════
# EXTRAIR DADOS DO USUÁRIO (é um dicionário)
# ═══════════════════════════════════════════════════════════════
if isinstance(usuario_logado, dict):
    nome = usuario_logado.get('nome_completo', 'Usuário')
    esf = usuario_logado.get('esf') or 'N/A'
    clinica = usuario_logado.get('clinica') or 'N/A'
    ap = usuario_logado.get('area_programatica') or 'N/A'
else:
    nome = str(usuario_logado)
    esf = clinica = ap = 'N/A'

# ═══════════════════════════════════════════════════════════════
# 🎨 CABEÇALHO COM INFO DO USUÁRIO E NAVEGAÇÃO
# ═══════════════════════════════════════════════════════════════

# Esconder o menu lateral nativo do Streamlit
st.markdown("""
<style>
    [data-testid="stSidebarNav"] {display: none;}
</style>
""", unsafe_allow_html=True)

# Header com título e usuário
col1, col2 = st.columns([3, 1])

with col1:
    st.markdown(f"""
    <h1 style='margin: 0; padding: 0; color: {T.TEXT};'>
        🏥 Navegador Clínico de Multimorbidade e Polifarmácia
    </h1>
    """, unsafe_allow_html=True)

with col2:
    info_lines = [f"<strong>{nome}</strong>"]
    if esf != 'N/A':
        info_lines.append(f"ESF: {esf}")
    if clinica != 'N/A':
        info_lines.append(f"Clínica: {clinica}")
    if ap != 'N/A':
        info_lines.append(f"AP: {ap}")

    st.markdown(f"""
    <div style='text-align: right; padding-top: 10px; color: {T.TEXT}; font-size: 0.9em;'>
        <span style='font-size: 1.3em;'>👤</span> {"<br>".join(info_lines)}
    </div>
    """, unsafe_allow_html=True)

st.markdown("---")

PAGINA_ATUAL = "Home"   # ← ÚNICA linha que muda em cada página
ROTAS = {
    "Home":           "Home.py",
    "População":      "pages/Minha_Populacao.py",
    "Pacientes":      "pages/Meus_Pacientes.py",
    "Lacunas":        "pages/Lacunas_de_Cuidado.py",
    "Continuidade":   "pages/Acesso_Continuidade.py",
    "Polifarmácia":   "pages/Polifarmacia_ACB.py",
    "Diabetes":       "pages/Diabetes.py",
    "Hipertensão":    "pages/Hipertensao.py",
}
ICONES = [
    "house-fill", "people-fill", "person-lines-fill",
    "exclamation-triangle-fill", "arrow-repeat", "capsule",
    "droplet-fill", "heart-pulse-fill",
]
selected = option_menu(
    menu_title=None,
    options=list(ROTAS.keys()),
    icons=ICONES,
    default_index=list(ROTAS.keys()).index(PAGINA_ATUAL),
    orientation="horizontal",
    styles={
        "container": {
            "padding": "0!important",
            "background-color": T.NAV_BG,
        },
        "icon": {
            "font-size": "22px",
            "color": T.TEXT,
            "display": "block",
            "margin-bottom": "4px",
        },
        "nav-link": {
            "font-size": "11px",
            "text-align": "center",
            "margin": "0px",
            "padding": "10px 18px",
            "color": T.NAV_LINK,
            "background-color": T.SECONDARY_BG,
            "--hover-color": T.NAV_HOVER,
            "display": "flex",
            "flex-direction": "column",
            "align-items": "center",
            "line-height": "1.2",
            "white-space": "nowrap",
        },
        "nav-link-selected": {
            "background-color": T.NAV_SELECTED_BG,
            "color": T.NAV_SELECTED_TEXT,
            "font-weight": "600",
        },
    }
)
if selected != PAGINA_ATUAL:
    st.switch_page(ROTAS[selected])

st.markdown("---")


# ═══════════════════════════════════════════════════════════════
# CONTEÚDO DA HOME
# ═══════════════════════════════════════════════════════════════

# Testar conexão com BigQuery
with st.spinner("🔍 Testando conexão com BigQuery..."):
    conexao_ok = test_connection()

if conexao_ok:
    st.success("✅ Conexão com BigQuery estabelecida com sucesso!")
else:
    st.error("❌ Não foi possível conectar ao BigQuery. Verifique suas credenciais.")
    st.stop()

st.markdown("---")

# Título e boas-vindas
st.title("🏥 Navegador Clínico de Multimorbidade e Polifarmácia")
st.markdown("##### Superintendência de Atenção Primária")
st.markdown("---")

# ═══════════════════════════════════════════════════════════════
# BLOCO B3 — CARROSSEL DE CASOS DE USO (HTML/JS auto-avançante)
# ═══════════════════════════════════════════════════════════════

CASOS_USO_HTML = [
    {
        "perfil": "Gestor Municipal / Distrital",
        "cor":    "#E74C3C",
        "titulo": "Identificar onde as lacunas de cuidado são mais críticas",
        "passos": [
            "① Acesse <b>Lacunas de Cuidado</b>",
            "② No gráfico violino, selecione uma lacuna (ex: HAS descontrolada)",
            "③ Compare a distribuição entre Áreas Programáticas",
            "④ Identifique as APs com maior % de pacientes afetados",
        ],
        "pagina": "Lacunas",
    },
    {
        "perfil": "Gerente de Clínica da Família",
        "cor":    "#E67E22",
        "titulo": "Ver hipertensos não controlados na minha clínica",
        "passos": [
            "① Acesse <b>Hipertensão</b> e filtre pela sua clínica",
            "② Na aba <b>Controle Pressórico</b>, veja o % controlado por faixa etária",
            "③ Analise tendência — quantos estão piorando vs melhorando",
            "④ Na aba <b>Lista de Pacientes</b>, ordene por PA mais alta",
        ],
        "pagina": "Hipertensão",
    },
    {
        "perfil": "Médico de Família / Equipe ESF",
        "cor":    "#F39C12",
        "titulo": "Priorizar diabéticos sem HbA1c recente para busca ativa",
        "passos": [
            "① Acesse <b>Diabetes</b> e filtre pela sua ESF",
            "② Na aba <b>Lista de Pacientes</b>, ative <i>Nunca fez HbA1c</i>",
            "③ Ou ative <i>Sem HbA1c recente (&gt;180 dias)</i>",
            "④ Exporte a lista em CSV para organizar as buscas",
        ],
        "pagina": "Diabetes",
    },
    {
        "perfil": "Farmacêutico / Médico de Família",
        "cor":    "#9B59B6",
        "titulo": "Revisar prescrições em idosos com polifarmácia",
        "passos": [
            "① Acesse <b>Polifarmácia e ACB</b>",
            "② Na aba <b>STOPP / START</b>, veja critérios ativos no território",
            "③ Na aba <b>Lista de Pacientes</b>, filtre por Alerta ACB ≥ 3",
            "④ Identifique combinações de risco (opioide + benzodiazepínico)",
        ],
        "pagina": "Polifarmácia",
    },
    {
        "perfil": "Enfermeiro / Agente de Saúde",
        "cor":    "#2ECC71",
        "titulo": "Identificar pacientes sem consulta há mais de 180 dias",
        "passos": [
            "① Acesse <b>Acesso e Continuidade</b>",
            "② Filtre pela sua ESF na sidebar",
            "③ Veja o painel de pacientes sem consulta recente",
            "④ Ordene por <i>Mais tempo sem consulta médica</i> para priorizar",
        ],
        "pagina": "Continuidade",
    },
    {
        "perfil": "Qualquer nível de uso",
        "cor":    "#4f8ef7",
        "titulo": "Entender o perfil clínico da minha população",
        "passos": [
            "① Acesse <b>Minha População</b> e selecione AP, clínica ou ESF",
            "② Aba <b>HAS</b>: prevalência e controle da hipertensão",
            "③ Aba <b>DM</b>: prevalência e controle do diabetes",
            "④ Aba <b>Acesso e Continuidade</b>: quem está sendo acompanhado",
        ],
        "pagina": "População",
    },
]

# ── Montar HTML dos slides ─────────────────────────────────────
def _build_carrossel_uso(casos):
    n = len(casos)

    slides = ""
    for i, c in enumerate(casos):
        passos_li = "".join(f"<li>{p}</li>" for p in c["passos"])
        display = "block" if i == 0 else "none"
        slides += (
            f'<div class="uso-slide" id="uslide-{i}" style="display:{display}">'
            f'<div class="uso-grid">'
            f'<div class="uso-esq" style="border-left:4px solid {c["cor"]}">'
            f'<div class="uso-perfil" style="color:{c["cor"]}">🧭 {c["perfil"]}</div>'
            f'<div class="uso-titulo">{c["titulo"]}</div>'
            f'<div class="uso-tag">📍 {c["pagina"]}</div>'
            f'</div>'
            f'<div class="uso-dir">'
            f'<div class="uso-passos-titulo">Como fazer:</div>'
            f'<ul class="uso-passos">{passos_li}</ul>'
            f'</div>'
            f'</div>'
            f'</div>'
        )

    dots = "".join(
        f'<span class="udot" id="udot-{i}" onclick="uGoTo({i})"></span>'
        for i in range(n)
    )

    html = f"""
<div id="uso-car">
<style>
#uso-car {{ background:transparent; padding:4px 0 12px 0; font-family: sans-serif; }}
.uso-slide {{ animation: uFade .45s ease; }}
@keyframes uFade {{ from{{opacity:0;transform:translateY(5px)}} to{{opacity:1;transform:translateY(0)}} }}
.uso-grid {{ display:grid; grid-template-columns:1fr 1fr; gap:18px; }}
.uso-esq {{ background:{T.CARD_BG}; border-radius:12px; padding:20px 22px; min-height:190px; }}
.uso-dir {{ background:{T.SECONDARY_BG}; border-radius:12px; padding:20px 22px; min-height:190px; }}
.uso-perfil {{ font-size:.74em; font-weight:700; letter-spacing:.07em; text-transform:uppercase; margin-bottom:8px; }}
.uso-titulo {{ font-size:1.0em; font-weight:700; color:{T.TEXT}; line-height:1.35; margin-bottom:10px; }}
.uso-tag {{ font-size:.76em; color:{T.TEXT_MUTED}; margin-top:6px; }}
.uso-passos-titulo {{ font-size:.72em; font-weight:700; color:{T.TEXT_MUTED}; text-transform:uppercase; letter-spacing:.06em; margin-bottom:8px; }}
.uso-passos {{ list-style:none; padding:0; margin:0; }}
.uso-passos li {{ font-size:.85em; color:{T.TEXT_SECONDARY}; padding:4px 0; border-bottom:1px solid {T.BORDER}; line-height:1.5; }}
.uso-passos li:last-child {{ border-bottom:none; }}
.uso-passos b {{ color:{T.TEXT}; }}
.uso-passos i {{ color:{T.TEXT_MUTED}; }}
.uso-nav {{ display:flex; justify-content:center; align-items:center; gap:7px; margin-top:12px; }}
.udot {{ width:9px; height:9px; border-radius:50%; background:{T.BORDER}; cursor:pointer; transition:background .3s,transform .3s; display:inline-block; }}
.udot.active {{ background:{T.ACCENT}; transform:scale(1.35); }}
.uarrow {{ cursor:pointer; color:{T.TEXT_SECONDARY}; font-size:1em; padding:0 8px; user-select:none; }}
.uarrow:hover {{ color:{T.TEXT}; }}
.ucounter {{ font-size:.72em; color:{T.TEXT_SECONDARY}; margin-left:8px; }}
.uprog {{ height:3px; background:{T.GRID}; border-radius:2px; margin-bottom:10px; overflow:hidden; }}
.uprog-bar {{ height:100%; background:{T.ACCENT}; width:0%; transition:width 6s linear; }}
</style>
<div class="uprog"><div class="uprog-bar" id="uprog-bar"></div></div>
{slides}
<div class="uso-nav">
  <span class="uarrow" onclick="uPrev()">&#9664;</span>
  {dots}
  <span class="uarrow" onclick="uNext()">&#9654;</span>
  <span class="ucounter" id="ucounter">1 / {n}</span>
</div>
</div>
<script>
(function(){{
  var cur=0, n={n}, timer=null;
  function show(k){{
    for(var i=0;i<n;i++){{
      var s=document.getElementById('uslide-'+i);
      var d=document.getElementById('udot-'+i);
      if(s) s.style.display=(i===k)?'block':'none';
      if(d) d.className=(i===k)?'udot active':'udot';
    }}
    document.getElementById('ucounter').innerText=(k+1)+' / '+n;
    cur=k; resetProg();
  }}
  function resetProg(){{
    var b=document.getElementById('uprog-bar');
    if(!b) return;
    b.style.transition='none'; b.style.width='0%';
    setTimeout(function(){{b.style.transition='width 6s linear';b.style.width='100%';}},50);
  }}
  function resetTimer(){{
    if(timer) clearInterval(timer);
    timer=setInterval(function(){{show((cur+1)%n);}},6000);
  }}
  window.uNext=function(){{show((cur+1)%n);resetTimer();}};
  window.uPrev=function(){{show((cur-1+n)%n);resetTimer();}};
  window.uGoTo=function(k){{show(k);resetTimer();}};
  show(0); resetTimer();
}})();
</script>
"""
    return html

_uso_html = _build_carrossel_uso(CASOS_USO_HTML)

st.markdown("#### 🧭 O que você pode fazer aqui")
st.caption("Casos de uso por perfil · auto-avança a cada 6 segundos · clique nas bolinhas para navegar")
st.components.v1.html(_uso_html, height=310, scrolling=False)
st.markdown("---")


# ═══════════════════════════════════════════════════════════════
# BLOCO B2 — PAINEL DE SITUAÇÃO (HTML/JS + Chart.js auto-avançante)
# ═══════════════════════════════════════════════════════════════
if conexao_ok:
    import plotly.graph_objects as go
    import plotly.express as px
    from utils.bigquery_client import get_bigquery_client

    @st.cache_data(ttl=900, show_spinner=False)
    def carregar_dados_carrossel(ap=None, clinica=None, esf=None):
        """Carrega todos os dados do carrossel em 2 queries — cacheado."""
        client = get_bigquery_client()
        clauses_pir = []
        if ap:      clauses_pir.append(f"area_programatica = \'{ap}\'")
        if clinica: clauses_pir.append(f"clinica_familia = \'{clinica}\'")
        if esf:     clauses_pir.append(f"ESF = \'{esf}\'")
        where_pir = ("WHERE " + " AND ".join(clauses_pir)) if clauses_pir else ""

        clauses_lac = []
        if ap:      clauses_lac.append(f"area_programatica_cadastro = \'{ap}\'")
        if clinica: clauses_lac.append(f"nome_clinica_cadastro = \'{clinica}\'")
        if esf:     clauses_lac.append(f"nome_esf_cadastro = \'{esf}\'")
        where_lac = ("WHERE " + " AND ".join(clauses_lac)) if clauses_lac else ""

        try:
            sql_pir = f"""
            SELECT
                SUM(total_pacientes)           AS total_pop,
                SUM(n_multimorbidos)           AS n_multi,
                SUM(n_morb_0)                  AS n_morb_0,
                SUM(n_morb_1)                  AS n_morb_1,
                SUM(n_morb_2)                  AS n_morb_2,
                SUM(n_morb_3)                  AS n_morb_3,
                SUM(n_morb_4)                  AS n_morb_4,
                SUM(n_morb_5)                  AS n_morb_5,
                SUM(n_morb_6)                  AS n_morb_6,
                SUM(n_morb_7)                  AS n_morb_7,
                SUM(n_morb_8 + n_morb_9 + n_morb_10mais) AS n_morb_8mais,
                SUM(n_polifarmacia)            AS n_poli,
                SUM(n_hiperpolifarmacia)       AS n_hiperpoli,
                SUM(n_nenhum_medicamento)      AS n_zero_meds,
                SUM(n_um_e_dois_medicamentos)  AS n_1a2_meds,
                SUM(n_tres_e_quatro_medicamentos) AS n_3a4_meds,
                SUM(n_acb_alto)                AS n_acb_alto,
                SUM(n_acb_alto_idoso)          AS n_acb_idoso,
                SUM(n_sem_consulta_365d)       AS n_sem_consulta,
                SUM(n_alto_risco_baixo_acesso) AS n_alto_risco_ba,
                SUM(n_seguimento_regular)      AS n_regular,
                SUM(n_charlson_muito_alto)     AS n_ch_muito_alto,
                SUM(n_charlson_alto)           AS n_ch_alto,
                SUM(n_charlson_moderado)       AS n_ch_moderado,
                SUM(n_charlson_baixo)          AS n_ch_baixo,
                SUM(n_HAS)                     AS n_HAS,
                SUM(n_DM)                      AS n_DM,
                SUM(n_IRC)                     AS n_IRC,
                SUM(n_ICC)                     AS n_ICC,
                SUM(n_CI)                      AS n_CI,
                SUM(n_stroke)                  AS n_stroke,
                SUM(n_arritmia)                AS n_arritmia,
                SUM(n_depre_ansiedade)         AS n_depre,
                SUM(n_DPOC)                    AS n_DPOC,
                SUM(n_obesidade)               AS n_obesidade,
                SUM(n_neoplasia)               AS n_neoplasia,
                SUM(n_dislipidemia)            AS n_dislip
            FROM `rj-sms-sandbox.sub_pav_us.MM_piramides_populacionais`
            {where_pir}
            """
            df_pir = client.query(sql_pir).result().to_dataframe(create_bqstorage_client=False)
            dados_pir = df_pir.iloc[0].to_dict() if not df_pir.empty else {}

            sql_lac = f"""
            SELECT
                lacuna,
                ROUND(AVG(percentual_lacuna), 1) AS pct_media,
                SUM(n_com_lacuna)                AS n_total
            FROM `rj-sms-sandbox.sub_pav_us.MM_sumario_lacunas`
            {where_lac}
            GROUP BY lacuna
            ORDER BY pct_media DESC
            LIMIT 5
            """
            df_lac = client.query(sql_lac).result().to_dataframe(create_bqstorage_client=False)
            return dados_pir, df_lac

        except Exception as e:
            return {}, None

    # ── Carregar dados ──────────────────────────────────────────
    _u = st.session_state.get('usuario_global') or {}
    ctx_car = {
        'ap':      _u.get('area_programatica') if isinstance(_u, dict) else None,
        'clinica': _u.get('clinica')           if isinstance(_u, dict) else None,
        'esf':     _u.get('esf')               if isinstance(_u, dict) else None,
    }
    dados_pir, df_lac = carregar_dados_carrossel(
        ap=ctx_car.get('ap'),
        clinica=ctx_car.get('clinica'),
        esf=ctx_car.get('esf')
    )

    def _int(v): return int(v) if v and str(v) != 'nan' else 0
    def _pct(n, d): return round(n / d * 100, 1) if d else 0.0

    total_pop = _int(dados_pir.get('total_pop', 0)) or 1

    # ── Preparar dados para os 6 slides ────────────────────────

    # Slide 1 — Multimorbidade
    n_multi   = _int(dados_pir.get('n_multi', 0))
    pct_multi = _pct(n_multi, total_pop)
    morb_labels = ['0','1','2','3','4','5','6','7','8+']
    morb_vals   = [
        _int(dados_pir.get('n_morb_0',0)), _int(dados_pir.get('n_morb_1',0)),
        _int(dados_pir.get('n_morb_2',0)), _int(dados_pir.get('n_morb_3',0)),
        _int(dados_pir.get('n_morb_4',0)), _int(dados_pir.get('n_morb_5',0)),
        _int(dados_pir.get('n_morb_6',0)), _int(dados_pir.get('n_morb_7',0)),
        _int(dados_pir.get('n_morb_8mais',0)),
    ]
    morb_cores  = ['#4A90D9','#4A90D9','#F4D03F','#F4D03F','#E67E22','#E67E22','#C0392B','#C0392B','#C0392B']

    # Slide 2 — Top Morbidades
    morb_map = {
        'Hipertensão':   _int(dados_pir.get('n_HAS',0)),
        'Diabetes':      _int(dados_pir.get('n_DM',0)),
        'Dislipidemia':  _int(dados_pir.get('n_dislip',0)),
        'Depressão/Ans': _int(dados_pir.get('n_depre',0)),
        'Obesidade':     _int(dados_pir.get('n_obesidade',0)),
        'Neoplasias':    _int(dados_pir.get('n_neoplasia',0)),
        'DPOC':          _int(dados_pir.get('n_DPOC',0)),
        'Doença Renal':  _int(dados_pir.get('n_IRC',0)),
        'Cardiopatia':   _int(dados_pir.get('n_CI',0)),
        'Ins. Cardíaca': _int(dados_pir.get('n_ICC',0)),
    }
    top8 = sorted(morb_map.items(), key=lambda x: x[1], reverse=True)[:8]
    top8_labels = [x[0] for x in top8]
    top8_pcts   = [round(x[1]/total_pop*100, 1) for x in top8]

    # Slide 3 — Lacunas
    if df_lac is not None and not df_lac.empty:
        lac_labels  = [str(l)[:32] for l in df_lac['lacuna'].tolist()]
        lac_vals    = [round(float(v), 1) for v in df_lac['pct_media'].tolist()]
        pct_lac_med = round(sum(lac_vals)/len(lac_vals), 1) if lac_vals else 0
    else:
        lac_labels  = ['Sem dados']
        lac_vals    = [0]
        pct_lac_med = 0

    # Slide 4 — Acesso
    n_sem    = _int(dados_pir.get('n_sem_consulta',0))
    n_arba   = _int(dados_pir.get('n_alto_risco_ba',0))
    n_reg    = _int(dados_pir.get('n_regular',0))
    pct_sem  = _pct(n_sem,  total_pop)
    pct_arba = _pct(n_arba, total_pop)
    pct_reg  = _pct(n_reg,  total_pop)

    # Slide 5 — Polifarmácia
    n_zero  = _int(dados_pir.get('n_zero_meds',0))
    n_1a2   = _int(dados_pir.get('n_1a2_meds',0))
    n_3a4   = _int(dados_pir.get('n_3a4_meds',0))
    n_poli  = _int(dados_pir.get('n_poli',0))
    n_hiper = _int(dados_pir.get('n_hiperpoli',0))
    pct_poli  = _pct(n_poli,  total_pop)
    pct_hiper = _pct(n_hiper, total_pop)

    # Slide 6 — ACB / Charlson
    n_acb_alto  = _int(dados_pir.get('n_acb_alto',0))
    n_acb_idoso = _int(dados_pir.get('n_acb_idoso',0))
    pct_acb     = _pct(n_acb_alto, total_pop)
    pct_acbi    = _pct(n_acb_idoso, total_pop)
    ch_labels   = ['Muito Alto','Alto','Moderado','Baixo']
    ch_vals     = [
        _int(dados_pir.get('n_ch_muito_alto',0)),
        _int(dados_pir.get('n_ch_alto',0)),
        _int(dados_pir.get('n_ch_moderado',0)),
        _int(dados_pir.get('n_ch_baixo',0)),
    ]
    ch_cores = ['#C0392B','#E67E22','#F4D03F','#2ECC71']

    # ── Gerar HTML do carrossel ─────────────────────────────────
    import json as _json

    _painel_html = f"""
<div id="painel-car">
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.0/chart.umd.min.js"></script>
<style>
#painel-car {{ font-family:sans-serif; background:transparent; padding:4px 0 12px 0; }}
.pslide {{ display:none; animation:pFade .45s ease; }}
.pslide.active {{ display:grid; grid-template-columns:1fr 1fr; gap:18px; }}
@keyframes pFade {{ from{{opacity:0;transform:translateY(5px)}} to{{opacity:1;transform:translateY(0)}} }}
.pcard {{
    background:{T.CARD_BG}; border-radius:12px; padding:18px 20px;
    border-left:4px solid {T.ACCENT}; min-height:260px;
}}
.pcard-title {{ font-size:.78em; font-weight:700; color:{T.TEXT_MUTED};
    text-transform:uppercase; letter-spacing:.07em; margin-bottom:6px; }}
.pcard-num {{ font-size:2.2em; font-weight:800; color:{T.ACCENT}; line-height:1.1; }}
.pcard-sub {{ font-size:.82em; color:{T.TEXT_MUTED}; margin-top:3px; line-height:1.4; }}
.pcard-divider {{ border:none; border-top:1px solid {T.BORDER}; margin:10px 0 8px 0; }}
.pchart-wrap {{ position:relative; height:160px; margin-top:6px; }}
.pnav {{ display:flex; justify-content:center; align-items:center;
    gap:7px; margin-top:12px; }}
.pdot {{ width:9px; height:9px; border-radius:50%; background:{T.BORDER};
    cursor:pointer; transition:background .3s,transform .3s; display:inline-block; }}
.pdot.active {{ background:{T.ACCENT}; transform:scale(1.35); }}
.parrow {{ cursor:pointer; color:{T.TEXT_SECONDARY}; font-size:1em;
    padding:0 8px; user-select:none; }}
.parrow:hover {{ color:{T.TEXT}; }}
.pcounter {{ font-size:.72em; color:{T.TEXT_SECONDARY}; margin-left:8px; }}
.pprog {{ height:3px; background:{T.GRID}; border-radius:2px; margin-bottom:10px; overflow:hidden; }}
.pprog-bar {{ height:100%; background:{T.ACCENT}; width:0%; transition:width 6s linear; }}
</style>

<div class="pprog"><div class="pprog-bar" id="pprog-bar"></div></div>

<!-- Slide 1 — Multimorbidade -->
<div class="pslide" id="pslide-0">
  <div class="pcard" style="border-left-color:{T.ACCENT}">
    <div class="pcard-title">🏥 Multimorbidade</div>
    <div class="pcard-num">{pct_multi:.1f}%</div>
    <div class="pcard-sub">{n_multi:,} pacientes com 2 ou mais condições crônicas<br>de {total_pop:,} cadastrados</div>
    <hr class="pcard-divider">
    <div class="pcard-sub">Distribuição por número de morbidades</div>
    <div class="pchart-wrap"><canvas id="c-morb"></canvas></div>
  </div>
  <div class="pcard" style="border-left-color:{T.ACCENT}">
    <div class="pcard-title">📊 Morbidades Mais Prevalentes</div>
    <div class="pcard-sub" style="margin-bottom:8px">Proporção da população com cada condição registrada</div>
    <hr class="pcard-divider">
    <div class="pchart-wrap" style="height:190px"><canvas id="c-top"></canvas></div>
  </div>
</div>

<!-- Slide 2 — Lacunas + Acesso -->
<div class="pslide" id="pslide-1">
  <div class="pcard" style="border-left-color:#E74C3C">
    <div class="pcard-title">⚠️ Lacunas de Cuidado</div>
    <div class="pcard-num" style="color:#E74C3C">{pct_lac_med:.1f}%</div>
    <div class="pcard-sub">Lacuna média nas 5 condições mais críticas</div>
    <hr class="pcard-divider">
    <div class="pcard-sub">Top 5 lacunas por % de pacientes afetados</div>
    <div class="pchart-wrap" style="height:170px"><canvas id="c-lac"></canvas></div>
  </div>
  <div class="pcard" style="border-left-color:#2ECC71">
    <div class="pcard-title">🔄 Acesso e Continuidade</div>
    <div class="pcard-num" style="color:#2ECC71">{pct_reg:.1f}%</div>
    <div class="pcard-sub">{n_reg:,} com acompanhamento regular</div>
    <hr class="pcard-divider">
    <div class="pcard-sub">Indicadores de acesso ao cuidado</div>
    <div class="pchart-wrap"><canvas id="c-ac"></canvas></div>
  </div>
</div>

<!-- Slide 3 — Polifarmácia + ACB -->
<div class="pslide" id="pslide-2">
  <div class="pcard" style="border-left-color:#E67E22">
    <div class="pcard-title">💊 Polifarmácia</div>
    <div class="pcard-num" style="color:#E67E22">{pct_poli:.1f}%</div>
    <div class="pcard-sub">{n_poli:,} com 5–9 meds &nbsp;·&nbsp; {n_hiper:,} com ≥10 ({pct_hiper:.1f}%)</div>
    <hr class="pcard-divider">
    <div class="pcard-sub">Distribuição de carga medicamentosa</div>
    <div class="pchart-wrap"><canvas id="c-poli"></canvas></div>
  </div>
  <div class="pcard" style="border-left-color:#9B59B6">
    <div class="pcard-title">🔴 Carga Anticolinérgica</div>
    <div class="pcard-num" style="color:#9B59B6">{pct_acb:.1f}%</div>
    <div class="pcard-sub">ACB ≥ 3 — risco cognitivo relevante<br>🧓 Alerta em idosos: {pct_acbi:.1f}% ({n_acb_idoso:,})</div>
    <hr class="pcard-divider">
    <div class="pcard-sub">Distribuição por carga de morbidade (Charlson)</div>
    <div class="pchart-wrap"><canvas id="c-ch"></canvas></div>
  </div>
</div>

<div class="pnav">
  <span class="parrow" onclick="pPrev()">&#9664;</span>
  <span class="pdot" id="pdot-0" onclick="pGoTo(0)"></span>
  <span class="pdot" id="pdot-1" onclick="pGoTo(1)"></span>
  <span class="pdot" id="pdot-2" onclick="pGoTo(2)"></span>
  <span class="parrow" onclick="pNext()">&#9654;</span>
  <span class="pcounter" id="pcounter">1 / 3</span>
</div>
</div>

<script>
(function(){{
  var cur=0, n=3, timer=null;
  var charts={{}};

  var MORB_LABELS = {_json.dumps(morb_labels)};
  var MORB_VALS   = {_json.dumps(morb_vals)};
  var MORB_CORES  = {_json.dumps(morb_cores)};

  var TOP8_LABELS = {_json.dumps(top8_labels)};
  var TOP8_PCTS   = {_json.dumps(top8_pcts)};

  var LAC_LABELS  = {_json.dumps(lac_labels)};
  var LAC_VALS    = {_json.dumps(lac_vals)};

  var AC_LABELS   = ['Sem consulta >365d','Alto risco / baixo acesso','Acomp. regular'];
  var AC_VALS     = [{pct_sem},{pct_arba},{pct_reg}];
  var AC_CORES    = ['#E74C3C','#E67E22','#2ECC71'];

  var POLI_LABELS = ['0 meds','1-2 meds','3-4 meds','Polifarmácia (5-9)','Hiperpoli (≥10)'];
  var POLI_VALS   = [{n_zero},{n_1a2},{n_3a4},{n_poli},{n_hiper}];
  var POLI_CORES  = ['#4A90D9','#5BA85A','#F4D03F','#E67E22','#C0392B'];

  var CH_LABELS   = {_json.dumps(ch_labels)};
  var CH_VALS     = {_json.dumps(ch_vals)};
  var CH_CORES    = {_json.dumps(ch_cores)};

  var CFG = {{responsive:true,maintainAspectRatio:false,
    plugins:{{legend:{{display:false}}}},
    scales:{{x:{{ticks:{{color:'{T.TEXT_MUTED}',font:{{size:10}}}},grid:{{color:'{T.GRID}'}}}},
             y:{{ticks:{{color:'{T.TEXT_MUTED}',font:{{size:10}}}},grid:{{color:'{T.GRID}'}}}}}}}};

  function mkBar(id,labels,data,colors,horiz){{
    var ctx=document.getElementById(id);
    if(!ctx||charts[id]) return;
    var scales=horiz
      ? {{x:{{ticks:{{color:'{T.TEXT_MUTED}',font:{{size:9}}}},grid:{{color:'{T.GRID}'}}}},
          y:{{ticks:{{color:'{T.TEXT}',font:{{size:9}}}},grid:{{display:false}}}}}}
      : {{x:{{ticks:{{color:'{T.TEXT_MUTED}',font:{{size:9}}}},grid:{{color:'{T.GRID}'}}}},
          y:{{ticks:{{color:'{T.TEXT_MUTED}',font:{{size:9}}}},grid:{{color:'{T.GRID}'}}}}}};
    charts[id]=new Chart(ctx,{{
      type:'bar',
      data:{{labels:labels,datasets:[{{data:data,backgroundColor:colors,borderRadius:3}}]}},
      options:{{
        indexAxis:horiz?'y':'x',
        responsive:true,maintainAspectRatio:false,
        plugins:{{legend:{{display:false}}}},
        scales:scales
      }}
    }});
  }}

  function initCharts(slide){{
    setTimeout(function(){{
      if(slide===0){{
        mkBar('c-morb',MORB_LABELS,MORB_VALS,MORB_CORES,false);
        mkBar('c-top',TOP8_LABELS,TOP8_PCTS,
          ['#4f8ef7','#4f8ef7','#4f8ef7','#4f8ef7','#4f8ef7','#4f8ef7','#4f8ef7','#4f8ef7'],true);
      }} else if(slide===1){{
        mkBar('c-lac',LAC_LABELS,LAC_VALS,
          ['#E74C3C','#E74C3C','#E74C3C','#E74C3C','#E74C3C'],true);
        mkBar('c-ac',AC_LABELS,AC_VALS,AC_CORES,false);
      }} else if(slide===2){{
        mkBar('c-poli',POLI_LABELS,POLI_VALS,POLI_CORES,false);
        mkBar('c-ch',CH_LABELS,CH_VALS,CH_CORES,false);
      }}
    }},80);
  }}

  function resetProg(){{
    var b=document.getElementById('pprog-bar');
    if(!b) return;
    b.style.transition='none'; b.style.width='0%';
    setTimeout(function(){{b.style.transition='width 6s linear';b.style.width='100%';}},50);
  }}

  function show(k){{
    for(var i=0;i<n;i++){{
      var s=document.getElementById('pslide-'+i);
      var d=document.getElementById('pdot-'+i);
      if(s){{s.className=(i===k)?'pslide active':'pslide';}}
      if(d){{d.className=(i===k)?'pdot active':'pdot';}}
    }}
    document.getElementById('pcounter').innerText=(k+1)+' / '+n;
    cur=k; resetProg(); initCharts(k);
  }}

  function resetTimer(){{
    if(timer) clearInterval(timer);
    timer=setInterval(function(){{show((cur+1)%n);}},6000);
  }}

  window.pNext=function(){{show((cur+1)%n);resetTimer();}};
  window.pPrev=function(){{show((cur-1+n)%n);resetTimer();}};
  window.pGoTo=function(k){{show(k);resetTimer();}};

  show(0); resetTimer();
}})();
</script>
"""

    st.markdown("#### Painel de Situação — dados do seu território")
    st.caption("Auto-avança a cada 6 segundos · clique nas bolinhas para navegar")
    st.components.v1.html(_painel_html, height=400, scrolling=False)
    st.markdown("---")


# Ferramentas na sidebar
st.sidebar.markdown("---")
st.sidebar.markdown("### 🔧 Ferramentas")
if st.sidebar.button("🔄 Limpar Cache"):
    limpar_cache()
    st.sidebar.success("✅ Cache limpo!")

# Rodapé
st.markdown("---")
st.caption("SMS-RJ | Superintendência de Atenção Primária")