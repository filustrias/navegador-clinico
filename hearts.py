"""
hearts.py — Motor de risco cardiovascular WHO 2019 (HEARTS), calibrado para
Tropical Latin America (Brasil) contra o app da OPAS. Pronto para import no Streamlit.

    from hearts import calcular_risco, col_mgdl_para_mmol
    r = calcular_risco(sexo="male", idade=55, pas=130, fumante=False,
                       colesterol_mmol=col_mgdl_para_mmol(200))          # via laboratorial
    r = calcular_risco(sexo="male", idade=55, pas=130, fumante=False, imc=27.0)  # via IMC
    r["risco_cvd"], r["categoria"], r["conduta"]

Calibração: recalibração afim (2 parâmetros por estrato) do CVD combinado, ajustada
ao app da OPAS (região Tropical), estratificada por sexo, versão (lab/nonlab) e
tabagismo. Erro vs OPAS < 0,65pp em toda a grade. Faixa etária 40-74 (75 é clampado).

Overlay clínico (por cima do escore, alinhado à OPAS e ao PCDT HAS):
    DCV estabelecida -> Muito alto ; DRC -> ao menos Alto ; Diabetes -> ao menos Alto.
"""
from math import exp, log

# ---- centralização (Tabela 1.6) e conversão ----
CENTER_AGE, CENTER_SBP, CENTER_CHOL_MMOL, CENTER_BMI = 60.0, 120.0, 6.0, 25.0
MGDL_POR_MMOL = 38.67
_S0_MI, _S0_ST = 0.9540, 0.9849   # âncoras ERFC (absorvidas na recalibração)

# ---- coeficientes WHO 2019 (Tabela 1.6, verificados) ----
COEF = {
 "lab":{
  "mi":{"male":{"age":0.0719227,"chol":0.2284944,"sbp":0.0132183,"dm":0.6410114,"smk":0.5638109,"chol_age":-0.0045806,"sbp_age":-0.0001576,"dm_age":-0.0124966,"smk_age":-0.0182545},
        "female":{"age":0.1020713,"chol":0.2050377,"sbp":0.015823,"dm":1.070358,"smk":1.053223,"chol_age":-0.0051932,"sbp_age":-0.0001378,"dm_age":-0.0234174,"smk_age":-0.0332666}},
  "stroke":{"male":{"age":0.0986578,"chol":0.029526,"sbp":0.0222629,"dm":0.6268712,"smk":0.4981217,"chol_age":0.00142,"sbp_age":-0.0004147,"dm_age":-0.026302,"smk_age":-0.0150561},
        "female":{"age":0.1056632,"chol":0.0257782,"sbp":0.0206278,"dm":0.8581998,"smk":0.7443627,"chol_age":-0.0021387,"sbp_age":-0.0004897,"dm_age":-0.0209826,"smk_age":-0.0200822}}},
 "nonlab":{
  "mi":{"male":{"age":0.073593,"bmi":0.0337219,"sbp":0.0133937,"smk":0.5954767,"bmi_age":-0.0010432,"sbp_age":-0.0001837,"smk_age":-0.0200831},
        "female":{"age":0.1049418,"bmi":0.0257616,"sbp":0.016726,"smk":1.093132,"bmi_age":-0.0006537,"sbp_age":-0.0001966,"smk_age":-0.0343739}},
  "stroke":{"male":{"age":0.097674,"bmi":0.0159518,"sbp":0.0227294,"smk":0.4999862,"bmi_age":-0.0003516,"sbp_age":-0.0004374,"smk_age":-0.0153895},
        "female":{"age":0.1046105,"bmi":0.0036406,"sbp":0.0216741,"smk":0.7399405,"bmi_age":-0.0000129,"sbp_age":-0.0005311,"smk_age":-0.0203997}}},
}

# ---- calibração Tropical Latin America (2 params por estrato: recalibra o CVD combinado) ----
# Ajustada contra o app da OPAS (regiao Tropical). Erro < 0,65pp. Chave: [versao][sexo][tabagismo].
PARAMS_REGIAO = {
    "lab": {
        "male":   {"nao_fumante": (-0.531053, 0.751679), "fumante": (-0.532542, 0.768790)},
        "female": {"nao_fumante": (-1.682845, 0.476351), "fumante": (-1.430331, 0.616612)},
    },
    "nonlab": {
        "male":   {"nao_fumante": (-0.602359, 0.795735), "fumante": (-0.508410, 0.864896)},
        "female": {"nao_fumante": (-1.565871, 0.541745), "fumante": (-1.365575, 0.714981)},
    },
}

_ORDEM = ["Baixo", "Moderado", "Alto", "Muito alto", "Crítico"]
_CONDUTA = {"Baixo":"Mudança de estilo de vida","Moderado":"Reforçar MEV; considerar farmacoterapia",
            "Alto":"Tratamento farmacológico indicado","Muito alto":"Tratamento intensivo",
            "Crítico":"Prioridade máxima; avaliar DCV"}


def col_mgdl_para_mmol(mgdl: float) -> float:
    return mgdl / MGDL_POR_MMOL

def _lp(modelo, desf, sexo, idade, pas, fumante, colesterol_mmol, diabetes, imc):
    c = COEF[modelo][desf][sexo]; ac, sc = idade-CENTER_AGE, pas-CENTER_SBP; smk = 1.0 if fumante else 0.0
    if modelo == "lab":
        cc = colesterol_mmol-CENTER_CHOL_MMOL; dm = 1.0 if diabetes else 0.0
        return (c["age"]*ac + c["chol"]*cc + c["sbp"]*sc + c["dm"]*dm + c["smk"]*smk
                + c["chol_age"]*ac*cc + c["sbp_age"]*ac*sc + c["dm_age"]*ac*dm + c["smk_age"]*ac*smk)
    bc = imc-CENTER_BMI
    return (c["age"]*ac + c["bmi"]*bc + c["sbp"]*sc + c["smk"]*smk
            + c["bmi_age"]*ac*bc + c["sbp_age"]*ac*sc + c["smk_age"]*ac*smk)

def _recal_cvd(lp_mi, lp_st, A, B):
    theta_core = 1.0 - (_S0_MI**exp(lp_mi)) * (_S0_ST**exp(lp_st))   # CVD combinado do núcleo
    return 1.0 - exp(-exp(A + B * log(-log(1.0 - theta_core))))       # recalibração afim (cloglog)

def _categoria(risco):
    r = risco*100
    return "Baixo" if r<5 else "Moderado" if r<10 else "Alto" if r<20 else "Muito alto" if r<30 else "Crítico"

def _maior(a, b):
    return a if _ORDEM.index(a) >= _ORDEM.index(b) else b


def calcular_risco(sexo, idade, pas, fumante,
                   colesterol_mmol=None, diabetes=False, imc=None,
                   dcv_estabelecida=False, drc=False):
    """
    sexo: "male"|"female". Sem colesterol_mmol -> via não-laboratorial (exige imc).
    Overlay: DCV -> Muito alto; DRC ou Diabetes -> ao menos Alto.
    Retorna: risco_cvd (0..1, escore calculado), categoria_escore, categoria (após overlay),
             conduta, modelo, motivo_override, idade_usada.
    """
    modelo = "lab" if colesterol_mmol is not None else "nonlab"
    if modelo == "nonlab" and imc is None:
        raise ValueError("Sem colesterol_mmol é preciso informar imc (via não-laboratorial).")
    idade_c = min(max(float(idade), 40.0), 74.0)          # 40-74 (OPAS clampa 75 no topo)

    lp_mi = _lp(modelo, "mi", sexo, idade_c, pas, fumante, colesterol_mmol, diabetes, imc)
    lp_st = _lp(modelo, "stroke", sexo, idade_c, pas, fumante, colesterol_mmol, diabetes, imc)
    A, B = PARAMS_REGIAO[modelo][sexo]["fumante" if fumante else "nao_fumante"]
    risco = _recal_cvd(lp_mi, lp_st, A, B)
    cat_escore = _categoria(risco)

    # overlay clínico (pega a maior categoria aplicável)
    cat, motivo = cat_escore, None
    if diabetes: cat, motivo = _maior(cat, "Alto"), "Diabetes"
    if drc:      cat, motivo = _maior(cat, "Alto"), "DRC" if motivo is None else motivo + " + DRC"
    if dcv_estabelecida: cat, motivo = "Muito alto", "DCV estabelecida"

    return {"risco_cvd": risco, "categoria_escore": cat_escore, "categoria": cat,
            "conduta": _CONDUTA[cat], "modelo": modelo,
            "motivo_override": motivo, "idade_usada": idade_c}