# utils/lacunas_config.py
"""
Configuração centralizada das 39 lacunas de cuidado.
Cada lacuna tem: grupo, nome legível, coluna SQL (booleana na tabela fato),
alias de percentual, descrição e regra de cálculo.
"""

# ═══════════════════════════════════════════════════════════════
# GRUPOS DE LACUNAS
# ═══════════════════════════════════════════════════════════════
GRUPOS_LACUNAS = {
    "Cardiopatia Isquêmica (CI)":       1,
    "Insuficiência Cardíaca (ICC)":      2,
    "Doença Renal Crônica (IRC)":        3,
    "Fibrilação Atrial (FA)":            4,
    "Diabetes Mellitus (DM)":            5,
    "Exames Laboratoriais":              6,
    "Antropometria":                     7,
    "Controle de PA":                    8,
    "Rastreio de DM":                    9,
}

# ═══════════════════════════════════════════════════════════════
# DEFINIÇÃO DAS 39 LACUNAS
# ═══════════════════════════════════════════════════════════════
# Cada entrada: {
#   "grupo": str,
#   "coluna_fato": str (nome da coluna booleana na tabela fato),
#   "alias_pct": str (alias do ROUND(COUNTIF(...)) no SELECT),
#   "descricao": str (texto curto explicativo),
#   "regra": str (regra de cálculo detalhada),
# }

LACUNAS = {
    # ── Grupo 1 — Cardiopatia Isquêmica ──────────────────────
    "CI sem AAS": {
        "grupo": "Cardiopatia Isquêmica (CI)",
        "coluna_fato": "lacuna_CI_sem_AAS",
        "alias_pct": "pct_CI_sem_AAS",
        "descricao": "Prevalência de pacientes com cardiopatia isquêmica que não receberam prescrição de AAS (nem de anticoagulante) nos últimos 365 dias.",
        "regra": "CI ativa + sem AAS e sem anticoagulante nos últimos 365 dias.",
    },
    "CI sem estatina de alta intensidade": {
        "grupo": "Cardiopatia Isquêmica (CI)",
        "coluna_fato": "lacuna_CI_sem_estatina_alta",
        "alias_pct": "pct_CI_sem_estatina_alta",
        "descricao": "Prevalência de pacientes com CI que não receberam estatina de alta intensidade (atorvastatina ≥40 mg ou rosuvastatina ≥20 mg) nos últimos 365 dias.",
        "regra": "CI ativa + sem atorvastatina ≥40 mg ou rosuvastatina ≥20 mg nos últimos 365 dias.",
    },
    "CI sem qualquer estatina": {
        "grupo": "Cardiopatia Isquêmica (CI)",
        "coluna_fato": "lacuna_CI_sem_estatina_qualquer",
        "alias_pct": "pct_CI_sem_estatina_qualquer",
        "descricao": "Prevalência de pacientes com CI que não receberam nenhum tipo de estatina nos últimos 365 dias.",
        "regra": "CI ativa + sem nenhuma estatina nos últimos 365 dias.",
    },
    "CI + ICC sem betabloqueador": {
        "grupo": "Cardiopatia Isquêmica (CI)",
        "coluna_fato": "lacuna_CI_ICC_sem_BB",
        "alias_pct": "pct_CI_ICC_sem_BB",
        "descricao": "Prevalência de pacientes com CI e ICC simultâneas que não receberam betabloqueador nos últimos 365 dias.",
        "regra": "CI e ICC ativas + sem betabloqueador nos últimos 365 dias.",
    },

    # ── Grupo 2 — Insuficiência Cardíaca ─────────────────────
    "ICC sem SGLT-2": {
        "grupo": "Insuficiência Cardíaca (ICC)",
        "coluna_fato": "lacuna_ICC_sem_SGLT2",
        "alias_pct": "pct_ICC_sem_SGLT2",
        "descricao": "Prevalência de pacientes com ICC que não receberam inibidor de SGLT-2 nos últimos 365 dias.",
        "regra": "ICC ativa + sem SGLT-2 nos últimos 365 dias.",
    },
    "ICC sem IECA/BRA": {
        "grupo": "Insuficiência Cardíaca (ICC)",
        "coluna_fato": "lacuna_ICC_sem_IECA_BRA",
        "alias_pct": "pct_ICC_sem_IECA_BRA",
        "descricao": "Prevalência de pacientes com ICC que não receberam IECA nem BRA nos últimos 365 dias.",
        "regra": "ICC ativa + sem IECA e sem BRA nos últimos 365 dias.",
    },
    "ICC sem INRA (sacubitril)": {
        "grupo": "Insuficiência Cardíaca (ICC)",
        "coluna_fato": "lacuna_ICC_sem_INRA",
        "alias_pct": "pct_ICC_sem_INRA",
        "descricao": "Prevalência de pacientes com ICC que não receberam sacubitril/valsartana nos últimos 365 dias.",
        "regra": "ICC ativa + sem sacubitril/valsartana nos últimos 365 dias.",
    },
    "IECA + BRA simultâneos": {
        "grupo": "Insuficiência Cardíaca (ICC)",
        "coluna_fato": "lacuna_IECA_BRA_concomitante",
        "alias_pct": "pct_IECA_BRA_concomitante",
        "descricao": "Prevalência de pacientes que estão recebendo IECA e BRA simultaneamente — combinação contraindicada.",
        "regra": "IECA e BRA ambos prescritos nos últimos 180 dias.",
    },
    "Diurético de alça sem ICC": {
        "grupo": "Insuficiência Cardíaca (ICC)",
        "coluna_fato": "lacuna_diur_alca_sem_ICC",
        "alias_pct": "pct_diur_alca_sem_ICC",
        "descricao": "Prevalência de pacientes que receberam furosemida ou bumetanida sem ter diagnóstico de ICC — uso potencialmente inadequado.",
        "regra": "Diurético de alça nos últimos 180 dias + sem diagnóstico de ICC.",
    },
    "ICC sem antagonista mineralocorticoide": {
        "grupo": "Insuficiência Cardíaca (ICC)",
        "coluna_fato": "lacuna_ICC_sem_ARM",
        "alias_pct": "pct_ICC_sem_ARM",
        "descricao": "Prevalência de pacientes com ICC que não receberam espironolactona ou eplerenona nos últimos 365 dias.",
        "regra": "ICC ativa + sem espironolactona/eplerenona nos últimos 365 dias.",
    },
    "ICC com INRA + IECA simultâneos": {
        "grupo": "Insuficiência Cardíaca (ICC)",
        "coluna_fato": "lacuna_ICC_INRA_IECA_concomitante",
        "alias_pct": "pct_ICC_INRA_IECA_concomitante",
        "descricao": "Prevalência de pacientes com ICC que estão recebendo sacubitril e IECA simultaneamente — combinação perigosa.",
        "regra": "ICC ativa + sacubitril e IECA ambos nos últimos 180 dias.",
    },
    "ICC com BCC não-diidropiridínico": {
        "grupo": "Insuficiência Cardíaca (ICC)",
        "coluna_fato": "lacuna_ICC_uso_BCC_nao_DHP",
        "alias_pct": "pct_ICC_uso_BCC_nao_DHP",
        "descricao": "Prevalência de pacientes com ICC que estão recebendo verapamil ou diltiazem — contraindicado na ICC.",
        "regra": "ICC ativa + verapamil ou diltiazem nos últimos 180 dias.",
    },
    "ICC com uso de AINE": {
        "grupo": "Insuficiência Cardíaca (ICC)",
        "coluna_fato": "lacuna_ICC_uso_AINE",
        "alias_pct": "pct_ICC_uso_AINE",
        "descricao": "Prevalência de pacientes com ICC que estão recebendo anti-inflamatório não esteroidal — uso inadequado que pode agravar a ICC.",
        "regra": "ICC ativa + AINE nos últimos 180 dias.",
    },
    "ICC sem nenhum modulador do SRAA": {
        "grupo": "Insuficiência Cardíaca (ICC)",
        "coluna_fato": "lacuna_ICC_sem_SRAA_e_sem_hidralazina_nitrato",
        "alias_pct": "pct_ICC_sem_SRAA",
        "descricao": "Prevalência de pacientes com ICC que não receberam nenhum modulador do sistema renina-angiotensina (IECA, BRA, INRA) nem a alternativa hidralazina + nitrato nos últimos 365 dias.",
        "regra": "ICC ativa + sem IECA, BRA, INRA, hidralazina e sem nitrato nos últimos 365 dias.",
    },

    # ── Grupo 3 — Doença Renal Crônica ───────────────────────
    "IRC sem SGLT-2": {
        "grupo": "Doença Renal Crônica (IRC)",
        "coluna_fato": "lacuna_IRC_sem_SGLT2",
        "alias_pct": "pct_IRC_sem_SGLT2",
        "descricao": "Prevalência de pacientes com doença renal crônica que não receberam inibidor de SGLT-2 nos últimos 365 dias.",
        "regra": "IRC ativa + sem SGLT-2 nos últimos 365 dias.",
    },
    "IRC sem IECA ou BRA": {
        "grupo": "Doença Renal Crônica (IRC)",
        "coluna_fato": "lacuna_IRC_sem_iECA_ou_BRA",
        "alias_pct": "pct_IRC_sem_IECA_BRA",
        "descricao": "Prevalência de pacientes com doença renal crônica que não receberam IECA nem BRA nos últimos 365 dias.",
        "regra": "IRC ativa + sem IECA e sem BRA nos últimos 365 dias.",
    },

    # ── Grupo 4 — Fibrilação Atrial ──────────────────────────
    "FA sem anticoagulação": {
        "grupo": "Fibrilação Atrial (FA)",
        "coluna_fato": "lacuna_FA_sem_anticoagulacao",
        "alias_pct": "pct_FA_sem_anticoag",
        "descricao": "Prevalência de pacientes com fibrilação atrial que não receberam anticoagulante oral nos últimos 365 dias.",
        "regra": "Arritmia ativa + sem varfarina, rivaroxabana, apixabana, dabigatrana ou edoxabana nos últimos 365 dias.",
    },
    "FA sem controle de FC": {
        "grupo": "Fibrilação Atrial (FA)",
        "coluna_fato": "lacuna_FA_sem_controle_FC",
        "alias_pct": "pct_FA_sem_controle_FC",
        "descricao": "Prevalência de pacientes com FA que não receberam medicação para controle de frequência cardíaca (betabloqueador ou digoxina) nos últimos 365 dias.",
        "regra": "Arritmia ativa + sem betabloqueador e sem digoxina nos últimos 365 dias.",
    },
    "FA + ICC sem digoxina": {
        "grupo": "Fibrilação Atrial (FA)",
        "coluna_fato": "lacuna_FA_ICC_sem_digoxina",
        "alias_pct": "pct_FA_ICC_sem_digoxina",
        "descricao": "Prevalência de pacientes com FA e ICC simultâneas que não receberam digoxina nos últimos 365 dias.",
        "regra": "Arritmia e ICC ativas + sem digoxina nos últimos 365 dias.",
    },

    # ── Grupo 5 — Diabetes Mellitus ──────────────────────────
    "DM sem HbA1c recente": {
        "grupo": "Diabetes Mellitus (DM)",
        "coluna_fato": "lacuna_DM_sem_HbA1c_recente",
        "alias_pct": "pct_DM_sem_HbA1c",
        "descricao": "Prevalência de pacientes diabéticos que não tiveram resultado de HbA1c registrado nos últimos 180 dias.",
        "regra": "DM ativa + HbA1c ausente ou último resultado há >180 dias.",
    },
    "DM descontrolado": {
        "grupo": "Diabetes Mellitus (DM)",
        "coluna_fato": "lacuna_DM_descontrolado",
        "alias_pct": "pct_DM_descontrolado",
        "descricao": "Prevalência de pacientes diabéticos cujo último resultado de HbA1c está acima da meta para sua faixa etária.",
        "regra": "DM ativa + HbA1c recente (≤180 dias) acima da meta: <60a → >7,0%; 60–69a → >7,5%; ≥70a → >8,0%.",
    },
    "DM complicado sem SGLT-2": {
        "grupo": "Diabetes Mellitus (DM)",
        "coluna_fato": "lacuna_DM_complicado_sem_SGLT2",
        "alias_pct": "pct_DM_complicado_sem_SGLT2",
        "descricao": "Prevalência de pacientes diabéticos com complicação macrovascular (ICC, IRC ou CI) que não receberam SGLT-2 nos últimos 365 dias.",
        "regra": "DM ativa + ICC ou IRC ou CI + sem SGLT-2 nos últimos 365 dias.",
    },
    "DM sem exame do pé (365 dias)": {
        "grupo": "Diabetes Mellitus (DM)",
        "coluna_fato": "lacuna_DM_sem_exame_pe_365d",
        "alias_pct": "pct_DM_sem_exame_pe_365d",
        "descricao": "Prevalência de pacientes diabéticos que não tiveram exame do pé diabético realizado (ou registrado) nos últimos 365 dias.",
        "regra": "DM ativa + sem exame do pé diabético nos últimos 365 dias.",
    },
    "DM sem exame do pé (180 dias)": {
        "grupo": "Diabetes Mellitus (DM)",
        "coluna_fato": "lacuna_DM_sem_exame_pe_180d",
        "alias_pct": "pct_DM_sem_exame_pe_180d",
        "descricao": "Prevalência de pacientes diabéticos que não tiveram exame do pé diabético realizado (ou registrado) nos últimos 180 dias.",
        "regra": "DM ativa + sem exame do pé diabético nos últimos 180 dias.",
    },
    "DM nunca teve exame do pé": {
        "grupo": "Diabetes Mellitus (DM)",
        "coluna_fato": "lacuna_DM_nunca_teve_exame_pe",
        "alias_pct": "pct_DM_nunca_exame_pe",
        "descricao": "Prevalência de pacientes diabéticos há mais de 1 ano que nunca tiveram nenhum registro de exame do pé diabético.",
        "regra": "DM ativa há >365 dias + nenhum registro histórico de exame do pé.",
    },
    "DM sem HbA1c solicitada": {
        "grupo": "Diabetes Mellitus (DM)",
        "coluna_fato": "lacuna_DM_hba1c_nao_solicitado",
        "alias_pct": "pct_DM_hba1c_nao_solicitado",
        "descricao": "Prevalência de pacientes diabéticos para os quais não foi solicitada HbA1c nos últimos 365 dias.",
        "regra": "DM ativa + sem solicitação de HbA1c nos últimos 365 dias.",
    },
    "DM sem microalbuminúria solicitada": {
        "grupo": "Diabetes Mellitus (DM)",
        "coluna_fato": "lacuna_DM_microalbuminuria_nao_solicitado",
        "alias_pct": "pct_DM_microalb_nao_solic",
        "descricao": "Prevalência de pacientes diabéticos para os quais não foi solicitada microalbuminúria nos últimos 365 dias.",
        "regra": "DM ativa + sem solicitação de microalbuminúria nos últimos 365 dias.",
    },

    # ── Grupo 6 — Exames Laboratoriais ───────────────────────
    "HAS/DM sem creatinina": {
        "grupo": "Exames Laboratoriais",
        "coluna_fato": "lacuna_creatinina_HAS_DM",
        "alias_pct": "pct_sem_creatinina",
        "descricao": "Prevalência de pacientes hipertensos ou diabéticos para os quais não foi solicitada creatinina nos últimos 365 dias.",
        "regra": "HAS ou DM ativa + sem creatinina solicitada nos últimos 365 dias.",
    },
    "HAS/DM sem perfil lipídico": {
        "grupo": "Exames Laboratoriais",
        "coluna_fato": "lacuna_colesterol_HAS_DM",
        "alias_pct": "pct_sem_colesterol",
        "descricao": "Prevalência de pacientes hipertensos ou diabéticos para os quais não foi solicitado perfil lipídico nos últimos 365 dias.",
        "regra": "HAS ou DM ativa + sem colesterol/HDL/LDL/TG solicitados nos últimos 365 dias.",
    },
    "HAS/DM sem EAS (urina)": {
        "grupo": "Exames Laboratoriais",
        "coluna_fato": "lacuna_eas_HAS_DM",
        "alias_pct": "pct_sem_eas",
        "descricao": "Prevalência de pacientes hipertensos ou diabéticos para os quais não foi solicitado exame de urina (EAS) nos últimos 365 dias.",
        "regra": "HAS ou DM ativa + sem exame de urina solicitado nos últimos 365 dias.",
    },
    "HAS/DM sem ECG": {
        "grupo": "Exames Laboratoriais",
        "coluna_fato": "lacuna_ecg_HAS_DM",
        "alias_pct": "pct_sem_ecg",
        "descricao": "Prevalência de pacientes hipertensos ou diabéticos para os quais não foi solicitado eletrocardiograma nos últimos 365 dias.",
        "regra": "HAS ou DM ativa + sem ECG solicitado nos últimos 365 dias.",
    },

    # ── Grupo 7 — Antropometria ──────────────────────────────
    "HAS/DM sem IMC calculável": {
        "grupo": "Antropometria",
        "coluna_fato": "lacuna_IMC_HAS_DM",
        "alias_pct": "pct_sem_IMC",
        "descricao": "Prevalência de pacientes hipertensos ou diabéticos que não possuem altura ou peso registrados, impossibilitando o cálculo do IMC.",
        "regra": "HAS ou DM ativa + altura ou peso ausentes no cadastro.",
    },

    # ── Grupo 8 — Controle de PA ─────────────────────────────
    "Adulto sem rastreio de PA": {
        "grupo": "Controle de PA",
        "coluna_fato": "lacuna_rastreio_PA_adulto",
        "alias_pct": "pct_rastreio_PA_adulto",
        "descricao": "Prevalência de adultos (≥18 anos) sem hipertensão que não tiveram pressão arterial aferida nos últimos 365 dias.",
        "regra": "Idade ≥18 anos + sem HAS + última PA há >365 dias (ou ausente).",
    },
    "HAS sem PA em 180 dias": {
        "grupo": "Controle de PA",
        "coluna_fato": "lacuna_PA_hipertenso_180d",
        "alias_pct": "pct_HAS_sem_PA_180d",
        "descricao": "Prevalência de pacientes hipertensos que não tiveram pressão arterial aferida nos últimos 180 dias.",
        "regra": "HAS ativa + última PA há >180 dias.",
    },
    "HAS descontrolada (<80 anos)": {
        "grupo": "Controle de PA",
        "coluna_fato": "lacuna_HAS_descontrolado_menor80",
        "alias_pct": "pct_HAS_desc_menor80",
        "descricao": "Prevalência de pacientes hipertensos com menos de 80 anos cuja última PA está acima da meta (PAS ≥140 ou PAD ≥90 mmHg).",
        "regra": "HAS ativa + idade <80 anos + PA recente (≤180 dias) com PAS ≥140 ou PAD ≥90 mmHg.",
    },
    "HAS descontrolada (≥80 anos)": {
        "grupo": "Controle de PA",
        "coluna_fato": "lacuna_HAS_descontrolado_80mais",
        "alias_pct": "pct_HAS_desc_80mais",
        "descricao": "Prevalência de pacientes hipertensos com 80 anos ou mais cuja última PA está acima da meta (PAS ≥150 ou PAD ≥90 mmHg).",
        "regra": "HAS ativa + idade ≥80 anos + PA recente (≤180 dias) com PAS ≥150 ou PAD ≥90 mmHg.",
    },
    "DM + HAS com PA acima da meta": {
        "grupo": "Controle de PA",
        "coluna_fato": "lacuna_DM_HAS_PA_descontrolada",
        "alias_pct": "pct_DM_HAS_PA_desc",
        "descricao": "Prevalência de pacientes diabéticos e hipertensos cuja última PA está acima da meta restrita (PAS >135 ou PAD >80 mmHg).",
        "regra": "DM e HAS ativas + PA recente (≤180 dias) com PAS >135 ou PAD >80 mmHg.",
    },

    # ── Grupo 9 — Rastreio de DM ─────────────────────────────
    "Hipertenso sem rastreio de DM": {
        "grupo": "Rastreio de DM",
        "coluna_fato": "lacuna_rastreio_DM_hipertenso",
        "alias_pct": "pct_rastreio_DM_hipertenso",
        "descricao": "Prevalência de pacientes hipertensos (sem DM) que não tiveram glicemia ou HbA1c solicitada nos últimos 365 dias para rastreio de diabetes.",
        "regra": "HAS ativa + sem DM + glicemia ou HbA1c ausentes ou há >365 dias.",
    },
    "Adulto ≥45a sem rastreio de DM": {
        "grupo": "Rastreio de DM",
        "coluna_fato": "lacuna_rastreio_DM_45mais",
        "alias_pct": "pct_rastreio_DM_45mais",
        "descricao": "Prevalência de adultos com 45 anos ou mais (sem DM) que não tiveram glicemia ou HbA1c solicitada nos últimos 3 anos para rastreio de diabetes.",
        "regra": "Idade ≥45 anos + sem DM + glicemia ou HbA1c ausentes ou há >3 anos.",
    },
}


# ═══════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════

def get_mapa_lac_col() -> dict:
    """Retorna {nome_lacuna: alias_pct} para uso no seletor do violin."""
    return {nome: info["alias_pct"] for nome, info in LACUNAS.items()}


def get_grupos_ordenados() -> list:
    """Retorna lista de grupos ordenados por número."""
    return sorted(GRUPOS_LACUNAS.keys(), key=lambda g: GRUPOS_LACUNAS[g])


def get_lacunas_por_grupo(grupo: str) -> list:
    """Retorna nomes das lacunas de um grupo específico."""
    return [nome for nome, info in LACUNAS.items() if info["grupo"] == grupo]


def gerar_countif_sql() -> str:
    """Gera todas as cláusulas COUNTIF para o SELECT da query do violin."""
    linhas = []
    for nome, info in LACUNAS.items():
        col = info["coluna_fato"]
        alias = info["alias_pct"]
        linhas.append(
            f"        ROUND(COUNTIF({col} = TRUE)\n"
            f"              * 100.0 / COUNT(*), 1) AS {alias}"
        )
    return ",\n".join(linhas)
