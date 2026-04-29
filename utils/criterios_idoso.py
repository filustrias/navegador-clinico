"""
Critérios STOPP / START / Beers para uso em idosos.

Fonte única de verdade — referência clínica + mapeamento da
coluna booleana correspondente na tabela MM_stopp_start.

STOPP  (Screening Tool of Older Persons' Prescriptions) — apontam
       medicamentos potencialmente inapropriados.
START  (Screening Tool to Alert to Right Treatment) — apontam
       medicamentos que deveriam ter sido prescritos mas estão
       ausentes.
Beers  (AGS Beers Criteria® 2023) — critérios complementares
       americanos.

Cada entrada: (codigo, categoria, medicamento_ou_indicado,
condicao, justificativa[, severidade]).
'codigo' é o sufixo da coluna no banco (ex.: 'stopp_cv_001' →
coluna 'stopp_cv_001_365d', com a única exceção 'stopp_cv_010'
que não tem sufixo _365d na fato).
"""

# ═══════════════════════════════════════════════════════════════
# STOPP — Screening Tool of Older Persons' Prescriptions
# Tupla: (codigo, categoria, medicamento, condicao, justificativa, severidade)
# ═══════════════════════════════════════════════════════════════
CRITERIOS_STOPP = [
    # Cardiovascular
    ("stopp_cv_001", "Cardiovascular", "Clonidina, Metildopa, Moxonidina",
     "HAS em idoso",
     "Risco de hipotensão ortostática, bradicardia e efeitos no SNC. Alternativas mais seguras disponíveis.",
     "Média"),
    ("stopp_cv_002", "Cardiovascular", "Doxazosina, Prazosina, Terazosina",
     "HAS em idoso",
     "Risco de hipotensão ortostática e síncope. Evitar como anti-hipertensivo.",
     "Média"),
    ("stopp_cv_003", "Cardiovascular", "Nifedipina liberação imediata",
     "HAS ou CI",
     "Risco de hipotensão reflexa e isquemia coronariana. Usar formulações de liberação lenta.",
     "Alta"),
    ("stopp_cv_004", "Cardiovascular", "Amiodarona como 1ª linha",
     "FA sem ICC",
     "Maior risco de efeitos adversos que BB, digoxina ou BCC não-DHP. Reservar para refratários.",
     "Média"),
    ("stopp_cv_005", "Cardiovascular", "Verapamil, Diltiazem",
     "ICC sistólica",
     "Efeito inotrópico negativo — pode descompensar ICC. Contraindicado.",
     "Alta"),
    ("stopp_cv_006", "Cardiovascular", "Furosemida",
     "HAS sem ICC ou IRC",
     "Alternativas mais seguras disponíveis para HAS. Diurético de alça não é 1ª linha.",
     "Baixa"),
    ("stopp_cv_007", "Cardiovascular", "Dronedarona",
     "ICC",
     "Associada a aumento de mortalidade em ICC. Contraindicada.",
     "Alta"),
    ("stopp_cv_008", "Cardiovascular", "Digoxina",
     "eGFR < 30 ml/min",
     "Risco de toxicidade digitálica por acúmulo. Reduzir dose ou suspender.",
     "Alta"),
    ("stopp_cv_009", "Cardiovascular", "Dabigatrana",
     "eGFR < 30 ml/min",
     "Acúmulo renal com risco de sangramento grave. Usar alternativa.",
     "Alta"),
    ("stopp_cv_010", "Cardiovascular", "Rivaroxabana, Apixabana",
     "eGFR < 15 ml/min",
     "Risco de sangramento por acúmulo. Contraindicado.",
     "Alta"),
    # SNC
    ("stopp_snc_001", "SNC", "Benzodiazepínicos (todos)",
     "Idoso ≥65 anos",
     "Risco de sedação, quedas, fraturas, acidentes e dependência. Evitar independente da indicação.",
     "Alta"),
    ("stopp_snc_002", "SNC", "Zolpidem, Zopiclona, Zaleplon",
     "Idoso ≥65 anos",
     "Mesmos riscos dos benzodiazepínicos para quedas e sedação prolongada.",
     "Alta"),
    ("stopp_snc_003", "SNC", "Amitriptilina, Nortriptilina, Imipramina",
     "Idoso ≥65 anos",
     "Efeitos anticolinérgicos, cardiotóxicos e sedativos. Risco de arritmia, hipotensão e queda.",
     "Alta"),
    ("stopp_snc_004", "SNC", "Tricíclicos (TCA)",
     "Com demência",
     "Piora do comprometimento cognitivo. Risco de delirium.",
     "Alta"),
    ("stopp_snc_005", "SNC", "Paroxetina",
     "Idoso ≥65 anos",
     "ISRS com maior carga anticolinérgica. Alternativas menos anticolinérgicas disponíveis.",
     "Média"),
    ("stopp_snc_006", "SNC", "Haloperidol, Clorpromazina, Levomepromazina",
     "Idoso ≥65 anos",
     "Risco de síndrome extrapiramidal, hipotensão e quedas.",
     "Alta"),
    ("stopp_snc_007", "SNC", "Antipsicóticos (típicos e atípicos)",
     "Parkinson ou demência",
     "Piora de sintomas extrapiramidais e aumento do risco de AVC em demência.",
     "Alta"),
    ("stopp_snc_008", "SNC", "Metoclopramida",
     "Parkinson",
     "Antagonista dopaminérgico — piora diretamente os sintomas parkinsonianos.",
     "Alta"),
    ("stopp_snc_009", "SNC", "Biperideno, Benzatropina",
     "Em uso de antipsicótico",
     "Cascata prescritiva: antipsicótico causa EPE → biperideno trata EPE. Rever antipsicótico.",
     "Média"),
    ("stopp_snc_010", "SNC", "Levodopa, agonistas dopaminérgicos",
     "Sem diagnóstico de Parkinson",
     "Uso inadequado sem indicação estabelecida.",
     "Baixa"),
    ("stopp_snc_011", "SNC", "Morfina, Oxicodona, Fentanil",
     "Sem indicação de dor severa",
     "Opioides fortes como 1ª linha em dor leve-moderada. Escalonamento inadequado (WHO).",
     "Média"),
    # Endócrino
    ("stopp_end_001", "Endócrino", "Glibenclamida, Glimepiride, Clorpropamida",
     "DM + idoso ≥65",
     "Hipoglicemia prolongada e grave — meia-vida longa. Usar agentes de ação curta.",
     "Alta"),
    ("stopp_end_002", "Endócrino", "Pioglitazona",
     "ICC + DM",
     "Retenção hídrica exacerba ICC. Contraindicado.",
     "Alta"),
    ("stopp_end_003", "Endócrino", "Metformina",
     "eGFR < 30 ml/min",
     "Risco de acidose lática por acúmulo. Suspender.",
     "Alta"),
    ("stopp_end_004", "Endócrino", "Insulina regular (sem basal)",
     "DM + idoso",
     "Escala móvel isolada — sem cobertura basal — aumenta risco de hipoglicemia.",
     "Alta"),
    # Musculoesquelético
    ("stopp_mus_001", "Musculoesquelético", "AINEs (todos)",
     "IRC eGFR < 50",
     "Piora da função renal. Contraindicado ou usar com monitoramento rigoroso.",
     "Alta"),
    ("stopp_mus_002", "Musculoesquelético", "AINEs (todos)",
     "ICC",
     "Retenção hídrica e piora da ICC. Evitar.",
     "Alta"),
    ("stopp_mus_003", "Musculoesquelético", "AINEs (todos)",
     "HAS não controlada",
     "Antagoniza efeito anti-hipertensivo e eleva PA.",
     "Alta"),
    ("stopp_mus_004", "Musculoesquelético", "AINE + Anticoagulante",
     "Uso concomitante",
     "Risco de sangramento gastrintestinal maior. Combinação a evitar.",
     "Alta"),
    ("stopp_mus_005", "Musculoesquelético", "Corticoide oral crônico",
     "Artrite reumatoide (M05/M06)",
     "DMARDs são preferíveis. Corticoide crônico causa osteoporose, infecção e DM.",
     "Alta"),
    ("stopp_mus_006", "Musculoesquelético", "Ciclobenzaprina, Carisoprodol, Baclofeno",
     "Idoso ≥65 anos",
     "Efeitos sedativos e anticolinérgicos. Risco de queda.",
     "Alta"),
    # ACB
    ("stopp_acb_001", "Anticolinérgico", "≥2 medicamentos com ACB > 0",
     "ACB total ≥ 4",
     "Carga anticolinérgica cumulativa — dois ou mais meds somam risco de confusão, delirium, quedas e comprometimento cognitivo.",
     "Alta"),
    ("stopp_acb_002", "Anticolinérgico", "Difenidramina, Prometazina, Hidroxizina",
     "Idoso ≥65 anos",
     "Anti-histamínicos 1ª geração com alta atividade anticolinérgica central.",
     "Alta"),
    ("stopp_acb_003", "Anticolinérgico", "Oxibutinina, Tolterodina, Solifenacina",
     "Idoso ≥65 anos",
     "Anticolinérgicos urinários — risco de retenção urinária, confusão e piora cognitiva.",
     "Alta"),
    # Renal
    ("stopp_ren_001", "Renal", "Gabapentina, Pregabalina",
     "eGFR < 60 ml/min",
     "Dose precisa ser ajustada à função renal. Acúmulo causa sedação e quedas.",
     "Alta"),
    ("stopp_ren_002", "Renal", "Espironolactona",
     "eGFR < 30 ml/min",
     "Risco de hipercalemia grave.",
     "Alta"),
    ("stopp_ren_003", "Renal", "Tramadol",
     "eGFR < 30 ml/min",
     "Acúmulo de metabólitos — risco de convulsão e sedação.",
     "Alta"),
]

# ═══════════════════════════════════════════════════════════════
# START — Screening Tool to Alert to Right Treatment
# Tupla: (codigo, categoria, medicamento_indicado, condicao, justificativa)
# ═══════════════════════════════════════════════════════════════
CRITERIOS_START = [
    ("start_cv_001", "Cardiovascular", "Anti-hipertensivo (qualquer classe)",
     "HAS descontrolada PAS ≥160 sem tto",
     "Hipertensão não tratada — principal causa evitável de AVC e IAM."),
    ("start_cv_002", "Cardiovascular", "Estatina",
     "Cardiopatia isquêmica (CI)",
     "Redução de mortalidade cardiovascular comprovada em DCV estabelecida."),
    ("start_cv_003", "Cardiovascular", "AAS ou Clopidogrel",
     "DCV estabelecida (CI/AVC/DAP)",
     "Antiplaquetário reduz eventos isquêmicos recorrentes em DCV estabelecida."),
    ("start_cv_004", "Cardiovascular", "IECA ou BRA",
     "ICC sistólica",
     "Reduz mortalidade e hospitalizações em ICC. Pilar do tratamento."),
    ("start_cv_005", "Cardiovascular", "Anticoagulante (warfarina ou DOAC)",
     "Fibrilação atrial",
     "Prevenção de AVC cardioembólico — risco elevado sem anticoagulação."),
    ("start_cv_006", "Cardiovascular", "IECA ou BRA",
     "DM + IRC (nefroproteção)",
     "Retarda progressão da doença renal diabética. Indicado independente da PA."),
    ("start_snc_001", "SNC", "Levodopa ou agonista dopaminérgico",
     "Parkinson com incapacidade funcional",
     "Tratamento de primeira linha — melhora qualidade de vida e função motora."),
    ("start_snc_002", "SNC", "ISRS ou IRSN (não TCA)",
     "Depressão/ansiedade moderada-grave",
     "Antidepressivos não-tricíclicos são mais seguros em idosos. TCA deve ser evitado."),
    ("start_snc_003", "SNC", "Donepezila, Rivastigmina, Galantamina",
     "Demência leve-moderada",
     "Inibidores da colinesterase — modesta melhora cognitiva e funcional."),
    ("start_resp_001", "Respiratório", "Broncodilatador inalatório",
     "DPOC ou asma",
     "Alívio sintomático e prevenção de exacerbações. Indicado em qualquer grau."),
]

# ═══════════════════════════════════════════════════════════════
# BEERS — AGS Beers Criteria® 2023 (apenas itens exclusivos do Beers,
# não cobertos pelo STOPP)
# Tupla: (codigo, tabela_beers, medicamento, condicao, justificativa)
# ═══════════════════════════════════════════════════════════════
CRITERIOS_BEERS = [
    ("beers_001", "Tabela 2", "Sulfonilureias (todas)",
     "DM + idoso ≥65",
     "Beers 2023 expande além das de longa ação — inclui gliclazida e glipizida. Toda a classe aumenta risco de hipoglicemia em idosos."),
    ("beers_002", "Box 1", "Warfarina",
     "FA — sem tentativa prévia de DOAC",
     "Beers 2023 recomenda DOACs como 1ª escolha em FA. Warfarina tem janela terapêutica estreita e maior risco de sangramento."),
    ("beers_003", "Box 1", "Rivaroxabana",
     "FA de longa duração",
     "Beers 2023 recomenda apixabana em detrimento de rivaroxabana, por perfil de segurança superior em função renal reduzida."),
    ("beers_004", "Tabela 2", "AAS",
     "Prevenção primária ≥60 anos (sem DCV)",
     "Novo em 2023: movido de 'cautela' para 'evitar'. Risco de sangramento supera benefício em prevenção primária. Manter apenas se DCV estabelecida."),
    ("beers_005", "Tabela 3", "Antipsicóticos atípicos (clozapina, olanzapina)",
     "Epilepsia",
     "Reduzem limiar convulsivo. Usar com extrema cautela ou evitar em pacientes com epilepsia."),
    ("beers_006", "Tabela 5", "Opioide + Benzodiazepínico",
     "Uso concomitante",
     "Combinação sinérgica de depressão do SNC — risco de depressão respiratória, sedação grave e overdose."),
    ("beers_007", "Tabela 5", "ISRS + Tramadol",
     "Uso concomitante",
     "Risco de síndrome serotonérgica (agitação, tremor, hipertermia, rigidez)."),
]


# ═══════════════════════════════════════════════════════════════
# HELPERS — mapeamento código → coluna booleana na MM_stopp_start
# ═══════════════════════════════════════════════════════════════

# Critério → coluna booleana correspondente.
# Convenção da tabela: STOPP/START/Beers usam sufixo '_365d', com a
# única exceção 'stopp_cv_010' (sem sufixo).
_EXCECOES_SEM_SUFIXO = {'stopp_cv_010'}


def coluna_para_codigo(codigo: str) -> str:
    """Devolve o nome da coluna boolean em MM_stopp_start."""
    if codigo in _EXCECOES_SEM_SUFIXO:
        return codigo
    return f"{codigo}_365d"


def todos_codigos_stopp() -> list:
    return [t[0] for t in CRITERIOS_STOPP]


def todos_codigos_start() -> list:
    return [t[0] for t in CRITERIOS_START]


def todos_codigos_beers() -> list:
    return [t[0] for t in CRITERIOS_BEERS]


def gerar_select_countif() -> str:
    """
    Retorna fragmento SQL com COUNTIF de cada coluna booleana de
    STOPP/START/Beers. Alias = código do critério (ex.: stopp_cv_001).
    """
    linhas = []
    for codigo in (todos_codigos_stopp() + todos_codigos_start()
                   + todos_codigos_beers()):
        col = coluna_para_codigo(codigo)
        linhas.append(f"COUNTIF({col} = TRUE) AS {codigo}")
    return ",\n        ".join(linhas)


def gerar_select_flags_paciente() -> str:
    """
    Retorna fragmento SQL com cada coluna boolean (já com sufixo
    correto) projetada com alias = código do critério, para uso
    em queries nominais.
    """
    linhas = []
    for codigo in (todos_codigos_stopp() + todos_codigos_start()
                   + todos_codigos_beers()):
        col = coluna_para_codigo(codigo)
        linhas.append(f"{col} AS {codigo}")
    return ",\n        ".join(linhas)


def descricao_curta(codigo: str) -> str:
    """Retorna 'Medicamento — Condição' do critério."""
    bases = {t[0]: t for t in CRITERIOS_STOPP}
    bases.update({t[0]: t for t in CRITERIOS_START})
    bases.update({t[0]: t for t in CRITERIOS_BEERS})
    t = bases.get(codigo)
    if not t:
        return codigo
    # tuple shape: (codigo, categoria, medicamento, condicao, justificativa[, severidade])
    medicamento = t[2]
    condicao = t[3]
    return f"{medicamento} — {condicao}"


def justificativa(codigo: str) -> str:
    bases = {t[0]: t for t in CRITERIOS_STOPP}
    bases.update({t[0]: t for t in CRITERIOS_START})
    bases.update({t[0]: t for t in CRITERIOS_BEERS})
    t = bases.get(codigo)
    return t[4] if t else ""


def categoria(codigo: str) -> str:
    bases = {t[0]: t for t in CRITERIOS_STOPP}
    bases.update({t[0]: t for t in CRITERIOS_START})
    bases.update({t[0]: t for t in CRITERIOS_BEERS})
    t = bases.get(codigo)
    return t[1] if t else ""


def tipo(codigo: str) -> str:
    """Retorna 'STOPP', 'START' ou 'Beers'."""
    if codigo.startswith('stopp_'): return 'STOPP'
    if codigo.startswith('start_'): return 'START'
    if codigo.startswith('beers_'): return 'Beers'
    return ''
