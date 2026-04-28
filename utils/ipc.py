"""
IPC — Índice de Prioridade de Cuidado
=====================================

Composto de 4 dimensões clínicas mapeadas para [0, 1] por bandas
absolutas (não dependem da amostra), permitindo comparação entre
ESFs, clínicas e APs.

Dimensões e pesos default:
  - Charlson (carga de morbidade):     30%
  - ACB (carga anticolinérgica):       20%
  - Dias sem consulta médica:          20%
  - Total de lacunas de cuidado:       30%

Bônus de +0,10 quando o paciente tem DCV estabelecida (CI/AVC/DAP)
e mantém lacunas de prevenção secundária pendentes (sem AAS ou sem
estatina). O resultado final é cortado em 1,0.

Fonte das colunas (tabela fato): charlson_score, acb_score_total,
dias_desde_ultima_medica, CI, stroke, vascular_periferica,
lacuna_CI_sem_AAS, lacuna_CI_sem_estatina_qualquer e o conjunto
de 41 colunas booleanas de lacunas (vide utils/lacunas_config.py).
"""
import pandas as pd
from utils.lacunas_config import LACUNAS

# ═══════════════════════════════════════════════════════════════
# PARÂMETROS
# ═══════════════════════════════════════════════════════════════

PESOS_DEFAULT = {
    'charlson': 0.30,
    'acb':      0.20,
    'acesso':   0.20,
    'lacunas':  0.30,
}

BONUS_DCV_SEM_PREV = 0.10

# Bandas clínicas — cada uma mapeia o valor bruto em [0, 1]
BANDAS_CHARLSON = [
    (3,   0.00),   # 0–3 → 0
    (6,   0.33),   # 4–6 → 0.33
    (9,   0.67),   # 7–9 → 0.67
    (1e9, 1.00),   # ≥10 → 1
]

BANDAS_ACB = [
    (0,   0.00),
    (1,   0.33),
    (2,   0.67),
    (1e9, 1.00),
]

BANDAS_ACESSO = [
    (180, 0.00),
    (365, 0.50),
    (730, 0.85),
    (1e9, 1.00),
]

BANDAS_LACUNAS = [
    (0,   0.00),
    (3,   0.33),
    (7,   0.67),
    (1e9, 1.00),
]

CATEGORIAS_IPC = [
    (0.75, 'Crítico'),
    (0.50, 'Alto'),
    (0.25, 'Moderado'),
    (0.00, 'Baixo'),
]

CORES_IPC = {
    'Crítico':  '#7B0000',
    'Alto':     '#F44336',
    'Moderado': '#FF9800',
    'Baixo':    '#4CAF50',
}


# ═══════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════

def _aplicar_banda(valor, bandas, default_quando_nulo=0.0):
    """Aplica tabela de bandas (lista de (limite_superior_inclusivo, score))."""
    if pd.isna(valor):
        return default_quando_nulo
    for limite, score in bandas:
        if valor <= limite:
            return score
    return bandas[-1][1]


def _categorizar(ipc):
    if pd.isna(ipc):
        return 'Indefinido'
    for limiar, nome in CATEGORIAS_IPC:
        if ipc >= limiar:
            return nome
    return 'Baixo'


def gerar_sql_total_lacunas(alias: str = "total_lacunas") -> str:
    """
    Retorna fragmento SQL que soma as 41 colunas booleanas de
    lacunas em uma única coluna agregada.

    Uso típico:
        sql = f"SELECT cpf, {gerar_sql_total_lacunas()} FROM ..."
    """
    cols = [info['coluna_fato'] for info in LACUNAS.values()]
    parcelas = " + ".join(f"IF({c} = TRUE, 1, 0)" for c in cols)
    return f"({parcelas}) AS {alias}"


# ═══════════════════════════════════════════════════════════════
# CÁLCULO PRINCIPAL
# ═══════════════════════════════════════════════════════════════

def calcular_ipc(df: pd.DataFrame, pesos: dict = None) -> pd.DataFrame:
    """
    Calcula IPC para cada paciente do DataFrame.

    Espera as colunas:
        - charlson_score              (numérica)
        - acb_score_total             (numérica)
        - dias_desde_ultima_medica    (numérica, NaN = nunca consultou)
        - total_lacunas               (numérica, soma das 41 lacunas)
        - CI, stroke, vascular_periferica (datas; NaN = sem condição)
        - lacuna_CI_sem_AAS, lacuna_CI_sem_estatina_qualquer (boolean)

    Adiciona ao DataFrame:
        - ipc_charlson_band, ipc_acb_band, ipc_acesso_band, ipc_lacunas_band
        - ipc_base                  (soma ponderada das bandas, antes do bônus)
        - ipc_dcv_sem_prev          (bool — paciente recebe bônus?)
        - ipc_bonus                 (0 ou BONUS_DCV_SEM_PREV)
        - ipc                       (final, cortado em 1.0)
        - ipc_categoria             ('Crítico', 'Alto', 'Moderado', 'Baixo')
    """
    pesos = pesos or PESOS_DEFAULT
    out = df.copy()

    # Bandas — acesso usa default 1.0 quando NaN (paciente nunca consultou)
    out['ipc_charlson_band'] = out.get('charlson_score', pd.Series(dtype=float)).apply(
        lambda v: _aplicar_banda(v, BANDAS_CHARLSON, default_quando_nulo=0.0)
    )
    out['ipc_acb_band'] = out.get('acb_score_total', pd.Series(dtype=float)).apply(
        lambda v: _aplicar_banda(v, BANDAS_ACB, default_quando_nulo=0.0)
    )
    out['ipc_acesso_band'] = out.get('dias_desde_ultima_medica', pd.Series(dtype=float)).apply(
        lambda v: _aplicar_banda(v, BANDAS_ACESSO, default_quando_nulo=1.0)
    )
    out['ipc_lacunas_band'] = out.get('total_lacunas', pd.Series(dtype=float)).apply(
        lambda v: _aplicar_banda(v, BANDAS_LACUNAS, default_quando_nulo=0.0)
    )

    out['ipc_base'] = (
        pesos['charlson'] * out['ipc_charlson_band']
        + pesos['acb']    * out['ipc_acb_band']
        + pesos['acesso'] * out['ipc_acesso_band']
        + pesos['lacunas']* out['ipc_lacunas_band']
    )

    # Bônus: DCV estabelecida (CI/AVC/DAP) sem prevenção secundária
    def _col_bool(name):
        if name not in out.columns:
            return pd.Series(False, index=out.index)
        return out[name].apply(lambda v: v in [True, 1, '1', 'True', 'true', 'TRUE'])

    def _col_notnull(name):
        if name not in out.columns:
            return pd.Series(False, index=out.index)
        return out[name].notna()

    tem_dcv = _col_notnull('CI') | _col_notnull('stroke') | _col_notnull('vascular_periferica')
    sem_prev = _col_bool('lacuna_CI_sem_AAS') | _col_bool('lacuna_CI_sem_estatina_qualquer')

    out['ipc_dcv_sem_prev'] = tem_dcv & sem_prev
    out['ipc_bonus'] = out['ipc_dcv_sem_prev'].astype(float) * BONUS_DCV_SEM_PREV

    out['ipc'] = (out['ipc_base'] + out['ipc_bonus']).clip(upper=1.0)
    out['ipc_categoria'] = out['ipc'].apply(_categorizar)

    return out


def explicar_ipc_paciente(row: pd.Series) -> str:
    """
    Retorna texto curto explicando como o IPC daquele paciente foi
    montado — útil para tooltip/expander no top-N.
    """
    partes = []
    if row.get('charlson_score') is not None and not pd.isna(row.get('charlson_score')):
        partes.append(
            f"Charlson {int(row['charlson_score'])} → banda {row['ipc_charlson_band']:.2f}"
        )
    if row.get('acb_score_total') is not None and not pd.isna(row.get('acb_score_total')):
        partes.append(
            f"ACB {int(row['acb_score_total'])} → banda {row['ipc_acb_band']:.2f}"
        )
    dias = row.get('dias_desde_ultima_medica')
    if pd.notna(dias):
        partes.append(f"{int(dias)}d s/ médico → banda {row['ipc_acesso_band']:.2f}")
    else:
        partes.append("nunca consultou → banda 1.00")
    if pd.notna(row.get('total_lacunas')):
        partes.append(
            f"{int(row['total_lacunas'])} lacunas → banda {row['ipc_lacunas_band']:.2f}"
        )
    if row.get('ipc_dcv_sem_prev'):
        partes.append(f"+0.10 (DCV sem prevenção secundária)")
    return " · ".join(partes)
