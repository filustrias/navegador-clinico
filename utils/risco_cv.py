# utils/risco_cv.py
"""
Cálculo de risco cardiovascular — WHO HEARTS 2019
Região: tropical_latin_america
Referência: Kaptoge et al., Lancet Global Health 2019
Validação: pacote R WHORiskCalculator v1.0.0 (CRAN, 2026-04-07)
"""
import math

# ═══════════════════════════════════════════════════════════════
# INCIDÊNCIAS BASELINE — tropical_latin_america (por 100.000/ano)
# ═══════════════════════════════════════════════════════════════
INCIDENCIAS = {
    'masculino': {
        'mi':     {40: 61, 45: 99, 50: 155, 55: 235, 60: 347, 65: 498, 70: 695, 75: 943},
        'stroke': {40: 43, 45: 72, 50: 116, 55: 181, 60: 275, 65: 406, 70: 583, 75: 815},
    },
    'feminino': {
        'mi':     {40: 20, 45: 35, 50: 61, 55: 101, 60: 163, 65: 254, 70: 383, 75: 562},
        'stroke': {40: 32, 45: 54, 50: 89, 55: 141, 60: 219, 65: 330, 70: 484, 75: 692},
    },
}

# ═══════════════════════════════════════════════════════════════
# COEFICIENTES BETA — LAB-BASED
# ═══════════════════════════════════════════════════════════════
BETA_LAB = {
    'masculino': {
        'mi': {
            'idade': 0.0719227, 'chol': 0.2284944, 'pas': 0.0132183,
            'dm': 0.6410114, 'tabaco': 0.5638109,
            'chol_idade': -0.0045806, 'pas_idade': -0.0001576,
            'dm_idade': -0.0124966, 'tabaco_idade': -0.0182545,
        },
        'stroke': {
            'idade': 0.0986578, 'chol': 0.029526, 'pas': 0.0222629,
            'dm': 0.6268712, 'tabaco': 0.4981217,
            'chol_idade': 0.00142, 'pas_idade': -0.0004147,
            'dm_idade': -0.026302, 'tabaco_idade': -0.0150561,
        },
    },
    'feminino': {
        'mi': {
            'idade': 0.1020713, 'chol': 0.2050377, 'pas': 0.015823,
            'dm': 1.070358, 'tabaco': 1.053223,
            'chol_idade': -0.0051932, 'pas_idade': -0.0001378,
            'dm_idade': -0.0234174, 'tabaco_idade': -0.0332666,
        },
        'stroke': {
            'idade': 0.1056632, 'chol': 0.0257782, 'pas': 0.0206278,
            'dm': 0.8581998, 'tabaco': 0.7443627,
            'chol_idade': -0.0021387, 'pas_idade': -0.0004897,
            'dm_idade': -0.0209826, 'tabaco_idade': -0.0200822,
        },
    },
}

# ═══════════════════════════════════════════════════════════════
# COEFICIENTES BETA — NON-LAB-BASED
# ═══════════════════════════════════════════════════════════════
BETA_NONLAB = {
    'masculino': {
        'mi': {
            'idade': 0.073593, 'imc': 0.0337219, 'pas': 0.0133937,
            'tabaco': 0.5954767,
            'imc_idade': -0.0010432, 'pas_idade': -0.0001837,
            'tabaco_idade': -0.0200831,
        },
        'stroke': {
            'idade': 0.097674, 'imc': 0.0159518, 'pas': 0.0227294,
            'tabaco': 0.4999862,
            'imc_idade': -0.0003516, 'pas_idade': -0.0004374,
            'tabaco_idade': -0.0153895,
        },
    },
    'feminino': {
        'mi': {
            'idade': 0.1049418, 'imc': 0.0257616, 'pas': 0.016726,
            'tabaco': 1.093132,
            'imc_idade': -0.0006537, 'pas_idade': -0.0001966,
            'tabaco_idade': -0.0343739,
        },
        'stroke': {
            'idade': 0.1046105, 'imc': 0.0036406, 'pas': 0.0216741,
            'tabaco': 0.7399405,
            'imc_idade': -0.0000129, 'pas_idade': -0.0005311,
            'tabaco_idade': -0.0203997,
        },
    },
}


def _get_faixa_etaria(idade):
    """Retorna a faixa etária de 5 em 5 anos para lookup de incidências."""
    if idade < 40:
        return None
    for limiar in [75, 70, 65, 60, 55, 50, 45, 40]:
        if idade >= limiar:
            return limiar
    return None


def _calcular_risco(lp_mi, lp_stroke, inc_mi, inc_stroke):
    """Converte linear predictors em probabilidade de evento em 10 anos."""
    try:
        p_base_mi = 1 - math.exp(-10 * inc_mi / 100000)
        p_base_stroke = 1 - math.exp(-10 * inc_stroke / 100000)
        p_mi = 1 - (1 - p_base_mi) ** math.exp(lp_mi)
        p_stroke = 1 - (1 - p_base_stroke) ** math.exp(lp_stroke)
        p_cvd = 1 - (1 - p_mi) * (1 - p_stroke)
        return round(p_cvd * 100, 2)
    except (OverflowError, ValueError):
        return None


def calcular_who_lab(genero, idade, pressao_sistolica,
                     colesterol_total_mgdl, dm, tabaco):
    """
    Calcula risco CV 10 anos pelo modelo WHO lab-based.
    Região: tropical_latin_america.

    Retorna: dict com 'risco_pct', 'categoria', 'modelo'
             ou None se dados insuficientes.
    """
    if any(v is None for v in [genero, idade, pressao_sistolica, colesterol_total_mgdl]):
        return None
    if not (40 <= idade <= 80):
        return None

    sexo = genero.lower().strip()
    if sexo in ('m', 'masculino'):
        sexo = 'masculino'
    elif sexo in ('f', 'feminino'):
        sexo = 'feminino'
    else:
        return None

    faixa = _get_faixa_etaria(idade)
    if faixa is None:
        return None

    chol_mmol = colesterol_total_mgdl / 38.67
    idade_c = idade - 60
    pas_c = pressao_sistolica - 120
    chol_c = chol_mmol - 6
    dm_v = 1 if dm else 0
    tab_v = 1 if tabaco else 0

    beta = BETA_LAB[sexo]

    lp_mi = (beta['mi']['idade'] * idade_c
             + beta['mi']['chol'] * chol_c
             + beta['mi']['pas'] * pas_c
             + beta['mi']['dm'] * dm_v
             + beta['mi']['tabaco'] * tab_v
             + beta['mi']['chol_idade'] * chol_c * idade_c
             + beta['mi']['pas_idade'] * pas_c * idade_c
             + beta['mi']['dm_idade'] * dm_v * idade_c
             + beta['mi']['tabaco_idade'] * tab_v * idade_c)

    lp_stroke = (beta['stroke']['idade'] * idade_c
                 + beta['stroke']['chol'] * chol_c
                 + beta['stroke']['pas'] * pas_c
                 + beta['stroke']['dm'] * dm_v
                 + beta['stroke']['tabaco'] * tab_v
                 + beta['stroke']['chol_idade'] * chol_c * idade_c
                 + beta['stroke']['pas_idade'] * pas_c * idade_c
                 + beta['stroke']['dm_idade'] * dm_v * idade_c
                 + beta['stroke']['tabaco_idade'] * tab_v * idade_c)

    inc = INCIDENCIAS[sexo]
    risco = _calcular_risco(lp_mi, lp_stroke, inc['mi'][faixa], inc['stroke'][faixa])
    if risco is None:
        return None

    return {
        'risco_pct': risco,
        'categoria': _categorizar_who(risco),
        'modelo': 'lab',
    }


def calcular_who_nonlab(genero, idade, pressao_sistolica, imc, tabaco):
    """
    Calcula risco CV 10 anos pelo modelo WHO non-lab-based.
    Região: tropical_latin_america.

    Retorna: dict com 'risco_pct', 'categoria', 'modelo'
             ou None se dados insuficientes.
    """
    if any(v is None for v in [genero, idade, pressao_sistolica, imc]):
        return None
    if not (40 <= idade <= 80):
        return None

    sexo = genero.lower().strip()
    if sexo in ('m', 'masculino'):
        sexo = 'masculino'
    elif sexo in ('f', 'feminino'):
        sexo = 'feminino'
    else:
        return None

    faixa = _get_faixa_etaria(idade)
    if faixa is None:
        return None

    idade_c = idade - 60
    pas_c = pressao_sistolica - 120
    imc_c = imc - 25
    tab_v = 1 if tabaco else 0

    beta = BETA_NONLAB[sexo]

    lp_mi = (beta['mi']['idade'] * idade_c
             + beta['mi']['imc'] * imc_c
             + beta['mi']['pas'] * pas_c
             + beta['mi']['tabaco'] * tab_v
             + beta['mi']['imc_idade'] * imc_c * idade_c
             + beta['mi']['pas_idade'] * pas_c * idade_c
             + beta['mi']['tabaco_idade'] * tab_v * idade_c)

    lp_stroke = (beta['stroke']['idade'] * idade_c
                 + beta['stroke']['imc'] * imc_c
                 + beta['stroke']['pas'] * pas_c
                 + beta['stroke']['tabaco'] * tab_v
                 + beta['stroke']['imc_idade'] * imc_c * idade_c
                 + beta['stroke']['pas_idade'] * pas_c * idade_c
                 + beta['stroke']['tabaco_idade'] * tab_v * idade_c)

    inc = INCIDENCIAS[sexo]
    risco = _calcular_risco(lp_mi, lp_stroke, inc['mi'][faixa], inc['stroke'][faixa])
    if risco is None:
        return None

    return {
        'risco_pct': risco,
        'categoria': _categorizar_who(risco),
        'modelo': 'non-lab',
    }


def classificar_risco_direto(dm=False, irc=False, ci=False, avc=False, dap=False):
    """
    Reclassificação direta SEM cálculo de score.
    - DCV estabelecida (CI, AVC, DAP) → MUITO ALTO
    - DM ou IRC → ALTO
    Retorna dict com resultado ou None se não se aplica.
    """
    if ci or avc or dap:
        motivos = []
        if ci: motivos.append("Cardiopatia isquêmica")
        if avc: motivos.append("AVC prévio")
        if dap: motivos.append("Doença arterial periférica")
        return {
            'risco_pct': None,
            'categoria': 'MUITO ALTO',
            'modelo': 'reclassificação direta',
            'motivo': f"DCV estabelecida: {', '.join(motivos)}",
        }
    if dm or irc:
        motivos = []
        if dm: motivos.append("Diabetes mellitus")
        if irc: motivos.append("Doença renal crônica")
        return {
            'risco_pct': None,
            'categoria': 'ALTO',
            'modelo': 'reclassificação direta',
            'motivo': f"{', '.join(motivos)}",
        }
    return None


def calcular_risco_completo(genero, idade, pressao_sistolica,
                            colesterol_total_mgdl=None, imc=None,
                            dm=False, tabaco=False,
                            irc=False, ci=False, avc=False, dap=False):
    """
    Função principal: aplica reclassificação direta primeiro,
    depois calcula WHO se aplicável.
    Retorna dict com risco, categoria, modelo e motivo.
    """
    # Passo 1: Reclassificação direta (DCV, DM, IRC)
    reclass = classificar_risco_direto(dm=dm, irc=irc, ci=ci, avc=avc, dap=dap)

    # Passo 2: Calcular WHO (mesmo se reclassificado, para comparação)
    who_result = None
    if colesterol_total_mgdl and colesterol_total_mgdl > 0:
        who_result = calcular_who_lab(genero, idade, pressao_sistolica,
                                       colesterol_total_mgdl, dm, tabaco)
    if who_result is None and imc and imc > 0:
        who_result = calcular_who_nonlab(genero, idade, pressao_sistolica, imc, tabaco)

    # Passo 3: Resultado final — reclassificação prevalece sobre score
    if reclass:
        # Se WHO calculou, e o risco é MAIOR que a reclassificação, usar o maior
        if who_result and who_result['risco_pct'] is not None:
            reclass['risco_who_pct'] = who_result['risco_pct']
            reclass['categoria_who'] = who_result['categoria']
            reclass['modelo_who'] = who_result['modelo']
            # Se WHO deu >=30% e reclassificação é ALTO, promover para MUITO ALTO
            if reclass['categoria'] == 'ALTO' and who_result['risco_pct'] >= 20:
                reclass['categoria'] = 'MUITO ALTO'
                reclass['motivo'] += f" + WHO {who_result['risco_pct']:.1f}%"
        return reclass

    # Sem reclassificação — usar WHO puro
    if who_result:
        return who_result

    return None


def _categorizar_who(risco_pct):
    """Categoriza o risco WHO em faixas."""
    if risco_pct < 5:
        return '<5%'
    elif risco_pct < 10:
        return '5-10%'
    elif risco_pct < 20:
        return '10-20%'
    elif risco_pct < 30:
        return '20-30%'
    else:
        return '>=30%'


def cor_categoria_completa(categoria):
    """Retorna cor para qualquer categoria (WHO ou SBC)."""
    return {
        '<5%':         '#2ECC71',
        '5-10%':       '#F39C12',
        '10-20%':      '#E74C3C',
        '20-30%':      '#C0392B',
        '>=30%':       '#8E44AD',
        'BAIXO':       '#2ECC71',
        'INTERMEDIÁRIO': '#F39C12',
        'ALTO':        '#E74C3C',
        'MUITO ALTO':  '#8E44AD',
    }.get(categoria, '#999999')


def cor_categoria_who(categoria):
    """Retorna cor para a categoria WHO."""
    return {
        '<5%':    '#2ECC71',
        '5-10%':  '#F39C12',
        '10-20%': '#E74C3C',
        '20-30%': '#C0392B',
        '>=30%':  '#8E44AD',
    }.get(categoria, '#999999')
