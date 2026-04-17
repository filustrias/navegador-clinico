"""
Configuração centralizada das 41 lacunas de cuidado.
Fonte única de verdade — usada por Lacunas_de_Cuidado.py e Meus_Pacientes.py.

Cada lacuna tem: grupo, coluna SQL (booleana na tabela fato),
alias de percentual, denominador SQL, descrição, regra e
justificativa clínica (exibida ao lado da lacuna na UI).
"""

# ═══════════════════════════════════════════════════════════════
# GRUPOS DE LACUNAS
# ═══════════════════════════════════════════════════════════════
GRUPOS_LACUNAS = {
    "Cardiopatia Isquêmica (CI)":       1,
    "ICC e IRC (manejo clínico)":       2,
    "Fibrilação Atrial (FA)":           3,
    "Diabetes Mellitus (DM)":           4,
    "Hipertensão (HAS)":                5,
    "Prescrições Inapropriadas":        6,
    "Rastreio":                         7,
}

# ═══════════════════════════════════════════════════════════════
# DEFINIÇÃO DAS 41 LACUNAS
# ═══════════════════════════════════════════════════════════════
# Cada entrada:
#   "grupo":                 str | list — grupo temático (list = lacuna multi-grupo)
#   "coluna_fato":           str  — coluna booleana na tabela fato
#   "alias_pct":             str  — alias do ROUND(COUNTIF(...)/NULLIF(...)) no SELECT
#   "denominador_sql":       str  — expressão SQL da população elegível (NULLIF(..., 0))
#   "descricao":             str  — texto curto para info box do dashboard
#   "regra":                 str  — regra de cálculo detalhada
#   "justificativa_clinica": str  — racional clínico exibido ao lado da lacuna

LACUNAS = {

    # ── Grupo 1 — Cardiopatia Isquêmica ──────────────────────

    "CI sem AAS": {
        "grupo": "Cardiopatia Isquêmica (CI)",
        "coluna_fato": "lacuna_CI_sem_AAS",
        "alias_pct": "pct_CI_sem_AAS",
        "denominador_sql": "COUNTIF(CI IS NOT NULL)",
        "descricao": "Prevalência de pacientes com cardiopatia isquêmica que não receberam prescrição de AAS (nem de anticoagulante) nos últimos 365 dias.",
        "regra": "CI ativa + sem AAS e sem anticoagulante nos últimos 365 dias.",
        "justificativa_clinica": "Antiagregação plaquetária reduz eventos isquêmicos recorrentes em prevenção secundária; anticoagulação substitui AAS quando há indicação própria.",
    },
    "CI sem estatina de alta intensidade": {
        "grupo": "Cardiopatia Isquêmica (CI)",
        "coluna_fato": "lacuna_CI_sem_estatina_alta",
        "alias_pct": "pct_CI_sem_estatina_alta",
        "denominador_sql": "COUNTIF(CI IS NOT NULL)",
        "descricao": "Prevalência de pacientes com CI que não receberam estatina de alta intensidade (atorvastatina ≥40 mg ou rosuvastatina ≥20 mg) nos últimos 365 dias.",
        "regra": "CI ativa + sem atorvastatina ≥40 mg ou rosuvastatina ≥20 mg nos últimos 365 dias.",
        "justificativa_clinica": "Estatina de alta potência é padrão-ouro em doença aterosclerótica estabelecida para reduzir LDL e mortalidade cardiovascular.",
    },
    "CI sem qualquer estatina": {
        "grupo": "Cardiopatia Isquêmica (CI)",
        "coluna_fato": "lacuna_CI_sem_estatina_qualquer",
        "alias_pct": "pct_CI_sem_estatina_qualquer",
        "denominador_sql": "COUNTIF(CI IS NOT NULL)",
        "descricao": "Prevalência de pacientes com CI que não receberam nenhum tipo de estatina nos últimos 365 dias.",
        "regra": "CI ativa + sem nenhuma estatina nos últimos 365 dias.",
        "justificativa_clinica": "Qualquer estatina é melhor que nenhuma em prevenção secundária — ausência total indica falha grave no manejo.",
    },
    "CI + ICC sem betabloqueador": {
        "grupo": "Cardiopatia Isquêmica (CI)",
        "coluna_fato": "lacuna_CI_ICC_sem_BB",
        "alias_pct": "pct_CI_ICC_sem_BB",
        "denominador_sql": "COUNTIF(CI IS NOT NULL AND ICC IS NOT NULL)",
        "descricao": "Prevalência de pacientes com CI e ICC simultâneas que não receberam betabloqueador nos últimos 365 dias.",
        "regra": "CI e ICC ativas + sem betabloqueador nos últimos 365 dias.",
        "justificativa_clinica": "Betabloqueador reduz mortalidade tanto na cardiopatia isquêmica quanto na insuficiência cardíaca com fração de ejeção reduzida.",
    },

    # ── Grupo 2 — ICC e IRC (manejo clínico) ─────────────────

    "ICC sem SGLT-2": {
        "grupo": "ICC e IRC (manejo clínico)",
        "coluna_fato": "lacuna_ICC_sem_SGLT2",
        "alias_pct": "pct_ICC_sem_SGLT2",
        "denominador_sql": "COUNTIF(ICC IS NOT NULL)",
        "descricao": "Prevalência de pacientes com ICC que não receberam inibidor de SGLT-2 nos últimos 365 dias.",
        "regra": "ICC ativa + sem SGLT-2 nos últimos 365 dias.",
        "justificativa_clinica": "iSGLT2 reduz hospitalização e mortalidade em ICC independentemente de diabetes — hoje é pilar terapêutico.",
    },
    "ICC sem IECA/BRA": {
        "grupo": "ICC e IRC (manejo clínico)",
        "coluna_fato": "lacuna_ICC_sem_IECA_BRA",
        "alias_pct": "pct_ICC_sem_IECA_BRA",
        "denominador_sql": "COUNTIF(ICC IS NOT NULL)",
        "descricao": "Prevalência de pacientes com ICC que não receberam IECA nem BRA nos últimos 365 dias.",
        "regra": "ICC ativa + sem IECA e sem BRA nos últimos 365 dias.",
        "justificativa_clinica": "Bloqueio do SRAA reduz remodelamento ventricular e mortalidade em ICC com fração de ejeção reduzida.",
    },
    "ICC sem INRA (sacubitril)": {
        "grupo": "ICC e IRC (manejo clínico)",
        "coluna_fato": "lacuna_ICC_sem_INRA",
        "alias_pct": "pct_ICC_sem_INRA",
        "denominador_sql": "COUNTIF(ICC IS NOT NULL)",
        "descricao": "Prevalência de pacientes com ICC que não receberam sacubitril/valsartana nos últimos 365 dias.",
        "regra": "ICC ativa + sem sacubitril/valsartana nos últimos 365 dias.",
        "justificativa_clinica": "INRA (sacubitril/valsartana) é superior ao IECA em ICC com FE reduzida, reduzindo mortalidade e internações.",
    },
    "ICC sem antagonista mineralocorticoide": {
        "grupo": "ICC e IRC (manejo clínico)",
        "coluna_fato": "lacuna_ICC_sem_ARM",
        "alias_pct": "pct_ICC_sem_ARM",
        "denominador_sql": "COUNTIF(ICC IS NOT NULL)",
        "descricao": "Prevalência de pacientes com ICC que não receberam espironolactona ou eplerenona nos últimos 365 dias.",
        "regra": "ICC ativa + sem espironolactona/eplerenona nos últimos 365 dias.",
        "justificativa_clinica": "Espironolactona/eplerenona reduzem mortalidade em ICC com FE reduzida, complementando IECA/BRA e betabloqueador.",
    },
    "ICC com INRA + IECA simultâneos": {
        "grupo": "ICC e IRC (manejo clínico)",
        "coluna_fato": "lacuna_ICC_INRA_IECA_concomitante",
        "alias_pct": "pct_ICC_INRA_IECA_concomitante",
        "denominador_sql": "COUNTIF(ICC IS NOT NULL)",
        "descricao": "Prevalência de pacientes com ICC que estão recebendo sacubitril e IECA simultaneamente — combinação perigosa.",
        "regra": "ICC ativa + sacubitril e IECA ambos nos últimos 180 dias.",
        "justificativa_clinica": "Associação aumenta risco de angioedema grave; INRA deve substituir o IECA, nunca ser associado.",
    },
    "ICC com BCC não-diidropiridínico": {
        "grupo": "ICC e IRC (manejo clínico)",
        "coluna_fato": "lacuna_ICC_uso_BCC_nao_DHP",
        "alias_pct": "pct_ICC_uso_BCC_nao_DHP",
        "denominador_sql": "COUNTIF(ICC IS NOT NULL)",
        "descricao": "Prevalência de pacientes com ICC que estão recebendo verapamil ou diltiazem — contraindicado na ICC.",
        "regra": "ICC ativa + verapamil ou diltiazem nos últimos 180 dias.",
        "justificativa_clinica": "Verapamil e diltiazem têm efeito inotrópico negativo e pioram ICC com FE reduzida.",
    },
    "ICC sem nenhum modulador do SRAA": {
        "grupo": "ICC e IRC (manejo clínico)",
        "coluna_fato": "lacuna_ICC_sem_SRAA_e_sem_hidralazina_nitrato",
        "alias_pct": "pct_ICC_sem_SRAA",
        "denominador_sql": "COUNTIF(ICC IS NOT NULL)",
        "descricao": "Prevalência de pacientes com ICC que não receberam nenhum modulador do SRAA (IECA, BRA, INRA) nem hidralazina + nitrato nos últimos 365 dias.",
        "regra": "ICC ativa + sem IECA, BRA, INRA, hidralazina e sem nitrato nos últimos 365 dias.",
        "justificativa_clinica": "Mesmo quando SRAA é contraindicado, hidralazina+nitrato é alternativa com benefício de sobrevida comprovado.",
    },
    "IRC sem SGLT-2": {
        "grupo": "ICC e IRC (manejo clínico)",
        "coluna_fato": "lacuna_IRC_sem_SGLT2",
        "alias_pct": "pct_IRC_sem_SGLT2",
        "denominador_sql": "COUNTIF(IRC IS NOT NULL)",
        "descricao": "Prevalência de pacientes com doença renal crônica que não receberam inibidor de SGLT-2 nos últimos 365 dias.",
        "regra": "IRC ativa + sem SGLT-2 nos últimos 365 dias.",
        "justificativa_clinica": "iSGLT2 retarda progressão da DRC e reduz desfechos renais compostos mesmo em não-diabéticos.",
    },
    "IRC sem IECA ou BRA": {
        "grupo": "ICC e IRC (manejo clínico)",
        "coluna_fato": "lacuna_IRC_sem_iECA_ou_BRA",
        "alias_pct": "pct_IRC_sem_IECA_BRA",
        "denominador_sql": "COUNTIF(IRC IS NOT NULL)",
        "descricao": "Prevalência de pacientes com doença renal crônica que não receberam IECA nem BRA nos últimos 365 dias.",
        "regra": "IRC ativa + sem IECA e sem BRA nos últimos 365 dias.",
        "justificativa_clinica": "IECA/BRA reduzem proteinúria e retardam progressão da DRC, sendo primeira linha na nefroproteção.",
    },
    "DM complicado sem SGLT-2": {
        "grupo": "ICC e IRC (manejo clínico)",
        "coluna_fato": "lacuna_DM_complicado_sem_SGLT2",
        "alias_pct": "pct_DM_complicado_sem_SGLT2",
        "denominador_sql": "COUNTIF(DM IS NOT NULL AND (ICC IS NOT NULL OR IRC IS NOT NULL OR CI IS NOT NULL))",
        "descricao": "Prevalência de pacientes diabéticos com complicação macrovascular (ICC, IRC ou CI) que não receberam SGLT-2 nos últimos 365 dias.",
        "regra": "DM ativa + ICC ou IRC ou CI + sem SGLT-2 nos últimos 365 dias.",
        "justificativa_clinica": "DM com doença cardiovascular ou renal estabelecida tem indicação prioritária para iSGLT2, independentemente do controle glicêmico.",
    },

    # ── Grupo 3 — Fibrilação Atrial ──────────────────────────

    "FA sem anticoagulação": {
        "grupo": "Fibrilação Atrial (FA)",
        "coluna_fato": "lacuna_FA_sem_anticoagulacao",
        "alias_pct": "pct_FA_sem_anticoag",
        "denominador_sql": "COUNTIF(arritmia IS NOT NULL)",
        "descricao": "Prevalência de pacientes com fibrilação atrial que não receberam anticoagulante oral nos últimos 365 dias.",
        "regra": "Arritmia ativa + sem varfarina, rivaroxabana, apixabana, dabigatrana ou edoxabana nos últimos 365 dias.",
        "justificativa_clinica": "Anticoagulação reduz em ~65% o risco de AVC isquêmico em FA com CHA2DS2-VASc elevado.",
    },
    "FA sem controle de FC": {
        "grupo": "Fibrilação Atrial (FA)",
        "coluna_fato": "lacuna_FA_sem_controle_FC",
        "alias_pct": "pct_FA_sem_controle_FC",
        "denominador_sql": "COUNTIF(arritmia IS NOT NULL)",
        "descricao": "Prevalência de pacientes com FA que não receberam medicação para controle de frequência cardíaca (betabloqueador ou digoxina) nos últimos 365 dias.",
        "regra": "Arritmia ativa + sem betabloqueador e sem digoxina nos últimos 365 dias.",
        "justificativa_clinica": "Controle da frequência ventricular previne cardiomiopatia taquicardia-induzida e melhora sintomas.",
    },
    "FA + ICC sem digoxina": {
        "grupo": "Fibrilação Atrial (FA)",
        "coluna_fato": "lacuna_FA_ICC_sem_digoxina",
        "alias_pct": "pct_FA_ICC_sem_digoxina",
        "denominador_sql": "COUNTIF(arritmia IS NOT NULL AND ICC IS NOT NULL)",
        "descricao": "Prevalência de pacientes com FA e ICC simultâneas que não receberam digoxina nos últimos 365 dias.",
        "regra": "Arritmia e ICC ativas + sem digoxina nos últimos 365 dias.",
        "justificativa_clinica": "Digoxina é opção útil para controle de FC em FA associada a ICC quando betabloqueador é insuficiente ou contraindicado.",
    },

    # ── Grupo 4 — Diabetes Mellitus ──────────────────────────

    "DM sem HbA1c recente": {
        "grupo": "Diabetes Mellitus (DM)",
        "coluna_fato": "lacuna_DM_sem_HbA1c_recente",
        "alias_pct": "pct_DM_sem_HbA1c",
        "denominador_sql": "COUNTIF(DM IS NOT NULL)",
        "descricao": "Prevalência de pacientes diabéticos que não tiveram resultado de HbA1c registrado nos últimos 180 dias.",
        "regra": "DM ativa + HbA1c ausente ou último resultado há >180 dias.",
        "justificativa_clinica": "HbA1c a cada 3-6 meses é o padrão para monitorar controle glicêmico e ajustar terapia.",
    },
    "DM descontrolado": {
        "grupo": "Diabetes Mellitus (DM)",
        "coluna_fato": "lacuna_DM_descontrolado",
        "alias_pct": "pct_DM_descontrolado",
        "denominador_sql": "COUNTIF(DM IS NOT NULL AND hba1c_atual IS NOT NULL AND dias_desde_ultima_hba1c <= 180)",
        "descricao": "Prevalência de pacientes diabéticos cujo último resultado de HbA1c está acima da meta para sua faixa etária.",
        "regra": "DM ativa + HbA1c recente (≤180 dias) acima da meta: <60a → >7,0%; 60–69a → >7,5%; ≥70a → >8,0%.",
        "justificativa_clinica": "Descontrole glicêmico sustentado acelera complicações micro e macrovasculares.",
    },
    "DM sem exame do pé (365 dias)": {
        "grupo": "Diabetes Mellitus (DM)",
        "coluna_fato": "lacuna_DM_sem_exame_pe_365d",
        "alias_pct": "pct_DM_sem_exame_pe_365d",
        "denominador_sql": "COUNTIF(DM IS NOT NULL)",
        "descricao": "Prevalência de pacientes diabéticos que não tiveram exame do pé diabético realizado (ou registrado) nos últimos 365 dias.",
        "regra": "DM ativa + sem exame do pé diabético nos últimos 365 dias.",
        "justificativa_clinica": "Exame anual do pé previne úlceras e amputações — complicações graves e evitáveis do DM.",
    },
    "DM sem exame do pé (180 dias)": {
        "grupo": "Diabetes Mellitus (DM)",
        "coluna_fato": "lacuna_DM_sem_exame_pe_180d",
        "alias_pct": "pct_DM_sem_exame_pe_180d",
        "denominador_sql": "COUNTIF(DM IS NOT NULL)",
        "descricao": "Prevalência de pacientes diabéticos que não tiveram exame do pé diabético realizado (ou registrado) nos últimos 180 dias.",
        "regra": "DM ativa + sem exame do pé diabético nos últimos 180 dias.",
        "justificativa_clinica": "Pacientes de maior risco (neuropatia, doença vascular) demandam reavaliação semestral dos pés.",
    },
    "DM nunca teve exame do pé": {
        "grupo": "Diabetes Mellitus (DM)",
        "coluna_fato": "lacuna_DM_nunca_teve_exame_pe",
        "alias_pct": "pct_DM_nunca_exame_pe",
        "denominador_sql": "COUNTIF(DM IS NOT NULL AND DATE_DIFF(CURRENT_DATE(), DM, DAY) > 365)",
        "descricao": "Prevalência de pacientes diabéticos há mais de 1 ano que nunca tiveram nenhum registro de exame do pé diabético.",
        "regra": "DM ativa há >365 dias + nenhum registro histórico de exame do pé.",
        "justificativa_clinica": "Ausência completa de exame do pé é falha grave de seguimento com risco direto de amputação não detectada.",
    },
    "DM sem HbA1c solicitada": {
        "grupo": "Diabetes Mellitus (DM)",
        "coluna_fato": "lacuna_DM_hba1c_nao_solicitado",
        "alias_pct": "pct_DM_hba1c_nao_solicitado",
        "denominador_sql": "COUNTIF(DM IS NOT NULL)",
        "descricao": "Prevalência de pacientes diabéticos para os quais não foi solicitada HbA1c nos últimos 365 dias.",
        "regra": "DM ativa + sem solicitação de HbA1c nos últimos 365 dias.",
        "justificativa_clinica": "Não solicitar A1C há mais de um ano indica falha de seguimento, mesmo que o paciente tenha resultado antigo.",
    },
    "DM sem microalbuminúria solicitada": {
        "grupo": "Diabetes Mellitus (DM)",
        "coluna_fato": "lacuna_DM_microalbuminuria_nao_solicitado",
        "alias_pct": "pct_DM_microalb_nao_solic",
        "denominador_sql": "COUNTIF(DM IS NOT NULL)",
        "descricao": "Prevalência de pacientes diabéticos para os quais não foi solicitada microalbuminúria nos últimos 365 dias.",
        "regra": "DM ativa + sem solicitação de microalbuminúria nos últimos 365 dias.",
        "justificativa_clinica": "Microalbuminúria é o primeiro marcador de nefropatia diabética e deve ser rastreada anualmente.",
    },
    "DM sem CID registrado": {
        "grupo": "Diabetes Mellitus (DM)",
        "coluna_fato": "DM_sem_CID",
        "alias_pct": "pct_DM_sem_CID",
        "denominador_sql": "COUNTIF(DM IS NOT NULL)",
        "descricao": "Prevalência de pacientes diabéticos sem o CID correspondente registrado no prontuário.",
        "regra": "DM ativa + ausência de CID E10/E11/E13/E14 no prontuário.",
        "justificativa_clinica": "Diagnóstico sem CID compromete notificação, pagamento por performance, vigilância epidemiológica e inclusão em linhas de cuidado.",
    },

    # ── Lacunas compartilhadas HAS/DM (pertencem a ambos os grupos) ──

    "HAS/DM sem creatinina": {
        "grupo": ["Diabetes Mellitus (DM)", "Hipertensão (HAS)"],
        "coluna_fato": "lacuna_creatinina_HAS_DM",
        "alias_pct": "pct_sem_creatinina",
        "denominador_sql": "COUNTIF(HAS IS NOT NULL OR DM IS NOT NULL)",
        "descricao": "Prevalência de pacientes hipertensos ou diabéticos para os quais não foi solicitada creatinina nos últimos 365 dias.",
        "regra": "HAS ou DM ativa + sem creatinina solicitada nos últimos 365 dias.",
        "justificativa_clinica": "Monitoramento anual da função renal é essencial para rastreio de nefropatia diabética/hipertensiva e ajuste posológico.",
    },
    "HAS/DM sem perfil lipídico": {
        "grupo": ["Diabetes Mellitus (DM)", "Hipertensão (HAS)"],
        "coluna_fato": "lacuna_colesterol_HAS_DM",
        "alias_pct": "pct_sem_colesterol",
        "denominador_sql": "COUNTIF(HAS IS NOT NULL OR DM IS NOT NULL)",
        "descricao": "Prevalência de pacientes hipertensos ou diabéticos para os quais não foi solicitado perfil lipídico nos últimos 365 dias.",
        "regra": "HAS ou DM ativa + sem colesterol/HDL/LDL/TG solicitados nos últimos 365 dias.",
        "justificativa_clinica": "Perfil lipídico anual orienta uso de estatina e estratificação de risco cardiovascular.",
    },
    "HAS/DM sem EAS (urina)": {
        "grupo": ["Diabetes Mellitus (DM)", "Hipertensão (HAS)"],
        "coluna_fato": "lacuna_eas_HAS_DM",
        "alias_pct": "pct_sem_eas",
        "denominador_sql": "COUNTIF(HAS IS NOT NULL OR DM IS NOT NULL)",
        "descricao": "Prevalência de pacientes hipertensos ou diabéticos para os quais não foi solicitado exame de urina (EAS) nos últimos 365 dias.",
        "regra": "HAS ou DM ativa + sem exame de urina solicitado nos últimos 365 dias.",
        "justificativa_clinica": "EAS detecta proteinúria e infecções urinárias silenciosas, comuns e agravantes em HAS e DM.",
    },
    "HAS/DM sem ECG": {
        "grupo": ["Diabetes Mellitus (DM)", "Hipertensão (HAS)"],
        "coluna_fato": "lacuna_ecg_HAS_DM",
        "alias_pct": "pct_sem_ecg",
        "denominador_sql": "COUNTIF(HAS IS NOT NULL OR DM IS NOT NULL)",
        "descricao": "Prevalência de pacientes hipertensos ou diabéticos para os quais não foi solicitado eletrocardiograma nos últimos 365 dias.",
        "regra": "HAS ou DM ativa + sem ECG solicitado nos últimos 365 dias.",
        "justificativa_clinica": "ECG anual rastreia isquemia silenciosa, arritmias e hipertrofia ventricular em paciente de alto risco.",
    },
    "HAS/DM sem IMC calculável": {
        "grupo": ["Diabetes Mellitus (DM)", "Hipertensão (HAS)"],
        "coluna_fato": "lacuna_IMC_HAS_DM",
        "alias_pct": "pct_sem_IMC",
        "denominador_sql": "COUNTIF(HAS IS NOT NULL OR DM IS NOT NULL)",
        "descricao": "Prevalência de pacientes hipertensos ou diabéticos que não possuem altura ou peso registrados, impossibilitando o cálculo do IMC.",
        "regra": "HAS ou DM ativa + altura ou peso ausentes no cadastro.",
        "justificativa_clinica": "IMC orienta conduta nutricional, escolha farmacológica e rastreio de obesidade — comorbidade frequente em HAS e DM.",
    },

    # ── Grupo 5 — Hipertensão (HAS) ──────────────────────────

    "HAS sem PA em 180 dias": {
        "grupo": "Hipertensão (HAS)",
        "coluna_fato": "lacuna_PA_hipertenso_180d",
        "alias_pct": "pct_HAS_sem_PA_180d",
        "denominador_sql": "COUNTIF(HAS IS NOT NULL)",
        "descricao": "Prevalência de pacientes hipertensos que não tiveram pressão arterial aferida nos últimos 180 dias.",
        "regra": "HAS ativa + última PA há >180 dias.",
        "justificativa_clinica": "Aferição regular da PA é o mínimo para avaliar resposta terapêutica e detectar descontrole.",
    },
    "HAS descontrolada (<80 anos)": {
        "grupo": "Hipertensão (HAS)",
        "coluna_fato": "lacuna_HAS_descontrolado_menor80",
        "alias_pct": "pct_HAS_desc_menor80",
        "denominador_sql": "COUNTIF(HAS IS NOT NULL AND idade < 80 AND dias_desde_ultima_pa <= 180)",
        "descricao": "Prevalência de pacientes hipertensos com menos de 80 anos cuja última PA está acima da meta (PAS ≥140 ou PAD ≥90 mmHg).",
        "regra": "HAS ativa + idade <80 anos + PA recente (≤180 dias) com PAS ≥140 ou PAD ≥90 mmHg.",
        "justificativa_clinica": "Meta 140/90 reduz AVC, IAM e insuficiência cardíaca em adultos hipertensos até 80 anos.",
    },
    "HAS descontrolada (≥80 anos)": {
        "grupo": "Hipertensão (HAS)",
        "coluna_fato": "lacuna_HAS_descontrolado_80mais",
        "alias_pct": "pct_HAS_desc_80mais",
        "denominador_sql": "COUNTIF(HAS IS NOT NULL AND idade >= 80 AND dias_desde_ultima_pa <= 180)",
        "descricao": "Prevalência de pacientes hipertensos com 80 anos ou mais cuja última PA está acima da meta (PAS ≥150 ou PAD ≥90 mmHg).",
        "regra": "HAS ativa + idade ≥80 anos + PA recente (≤180 dias) com PAS ≥150 ou PAD ≥90 mmHg.",
        "justificativa_clinica": "Em idosos muito idosos, meta 150/90 equilibra benefício cardiovascular e risco de quedas/hipoperfusão.",
    },
    "DM + HAS com PA acima da meta": {
        "grupo": "Hipertensão (HAS)",
        "coluna_fato": "lacuna_DM_HAS_PA_descontrolada",
        "alias_pct": "pct_DM_HAS_PA_desc",
        "denominador_sql": "COUNTIF(DM IS NOT NULL AND HAS IS NOT NULL AND dias_desde_ultima_pa <= 180)",
        "descricao": "Prevalência de pacientes diabéticos e hipertensos cuja última PA está acima da meta restrita (PAS >135 ou PAD >80 mmHg).",
        "regra": "DM e HAS ativas + PA recente (≤180 dias) com PAS >135 ou PAD >80 mmHg.",
        "justificativa_clinica": "DM+HAS demanda meta pressórica mais restrita para reduzir progressão de nefropatia e desfechos cardiovasculares.",
    },
    "HAS sem CID registrado": {
        "grupo": "Hipertensão (HAS)",
        "coluna_fato": "HAS_sem_CID",
        "alias_pct": "pct_HAS_sem_CID",
        "denominador_sql": "COUNTIF(HAS IS NOT NULL)",
        "descricao": "Prevalência de pacientes hipertensos sem o CID correspondente registrado no prontuário.",
        "regra": "HAS ativa + ausência de CID I10–I15 no prontuário.",
        "justificativa_clinica": "Diagnóstico sem CID compromete notificação, pagamento por performance, vigilância epidemiológica e inclusão em linhas de cuidado.",
    },

    # ── Grupo 6 — Prescrições Inapropriadas ──────────────────

    "IECA + BRA simultâneos": {
        "grupo": "Prescrições Inapropriadas",
        "coluna_fato": "lacuna_IECA_BRA_concomitante",
        "alias_pct": "pct_IECA_BRA_concomitante",
        "denominador_sql": "COUNT(*)",
        "descricao": "Prevalência de pacientes que estão recebendo IECA e BRA simultaneamente — combinação contraindicada.",
        "regra": "IECA e BRA ambos prescritos nos últimos 180 dias.",
        "justificativa_clinica": "Duplo bloqueio aumenta risco de hiperpotassemia, hipotensão e lesão renal sem ganho clínico consistente.",
    },
    "Diurético de alça sem ICC": {
        "grupo": "Prescrições Inapropriadas",
        "coluna_fato": "lacuna_diur_alca_sem_ICC",
        "alias_pct": "pct_diur_alca_sem_ICC",
        "denominador_sql": "COUNT(*)",
        "descricao": "Prevalência de pacientes que receberam furosemida ou bumetanida sem ter diagnóstico de ICC — uso potencialmente inadequado.",
        "regra": "Diurético de alça nos últimos 180 dias + sem diagnóstico de ICC.",
        "justificativa_clinica": "Diurético de alça para HAS isolada é inadequado por distúrbios eletrolíticos e ausência de benefício cardiovascular documentado.",
    },
    "ICC com uso de AINE": {
        "grupo": "Prescrições Inapropriadas",
        "coluna_fato": "lacuna_ICC_uso_AINE",
        "alias_pct": "pct_ICC_uso_AINE",
        "denominador_sql": "COUNTIF(ICC IS NOT NULL)",
        "descricao": "Prevalência de pacientes com ICC que estão recebendo anti-inflamatório não esteroidal — uso inadequado que pode agravar a ICC.",
        "regra": "ICC ativa + AINE nos últimos 180 dias.",
        "justificativa_clinica": "AINEs causam retenção hídrica, pioram função renal e podem descompensar ICC.",
    },

    # ── Grupo 7 — Rastreio ───────────────────────────────────

    "Adulto sem rastreio de PA": {
        "grupo": "Rastreio",
        "coluna_fato": "lacuna_rastreio_PA_adulto",
        "alias_pct": "pct_rastreio_PA_adulto",
        "denominador_sql": "COUNTIF(idade >= 18 AND HAS IS NULL)",
        "descricao": "Prevalência de adultos (≥18 anos) sem hipertensão que não tiveram pressão arterial aferida nos últimos 365 dias.",
        "regra": "Idade ≥18 anos + sem HAS + última PA há >365 dias (ou ausente).",
        "justificativa_clinica": "Aferição anual da PA identifica hipertensão silenciosa, condição altamente prevalente e subdiagnosticada.",
    },
    "Hipertenso sem rastreio de DM": {
        "grupo": "Rastreio",
        "coluna_fato": "lacuna_rastreio_DM_hipertenso",
        "alias_pct": "pct_rastreio_DM_hipertenso",
        "denominador_sql": "COUNTIF(HAS IS NOT NULL AND DM IS NULL)",
        "descricao": "Prevalência de pacientes hipertensos (sem DM) que não tiveram glicemia ou HbA1c solicitada nos últimos 365 dias para rastreio de diabetes.",
        "regra": "HAS ativa + sem DM + glicemia ou HbA1c ausentes ou há >365 dias.",
        "justificativa_clinica": "HAS e DM compartilham fatores de risco; rastreio anual detecta disglicemia precoce e reduz risco cardiovascular global.",
    },
    "Adulto ≥45a sem rastreio de DM": {
        "grupo": "Rastreio",
        "coluna_fato": "lacuna_rastreio_DM_45mais",
        "alias_pct": "pct_rastreio_DM_45mais",
        "denominador_sql": "COUNTIF(idade >= 45 AND DM IS NULL)",
        "descricao": "Prevalência de adultos com 45 anos ou mais (sem DM) que não tiveram glicemia ou HbA1c solicitada nos últimos 3 anos para rastreio de diabetes.",
        "regra": "Idade ≥45 anos + sem DM + glicemia ou HbA1c ausentes ou há >3 anos.",
        "justificativa_clinica": "Rastreio trienal a partir dos 45 anos detecta DM assintomático em fase precoce, quando a intervenção muda história natural.",
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
    """Retorna nomes das lacunas de um grupo específico.
    Suporta grupo como string ou lista de strings."""
    result = []
    for nome, info in LACUNAS.items():
        g = info["grupo"]
        if isinstance(g, list):
            if grupo in g:
                result.append(nome)
        elif g == grupo:
            result.append(nome)
    return result


def gerar_countif_sql() -> str:
    """
    Gera todas as cláusulas COUNTIF para o SELECT da query do violin.

    Formato gerado por lacuna:
        ROUND(
            COUNTIF(coluna_fato = TRUE) * 100.0
            / NULLIF(denominador_sql, 0),
        1) AS alias_pct
    """
    linhas = []
    for nome, info in LACUNAS.items():
        col   = info["coluna_fato"]
        alias = info["alias_pct"]
        den   = info["denominador_sql"]
        linhas.append(
            f"        ROUND(\n"
            f"            COUNTIF({col} = TRUE) * 100.0\n"
            f"            / NULLIF({den}, 0),\n"
            f"        1) AS {alias}"
        )
    return ",\n".join(linhas)


def gerar_num_den_sql() -> str:
    """
    Gera pares de colunas absolutas (numerador + denominador) para cada lacuna.
    Usado pelo Python para calcular médias ponderadas por território.
    """
    linhas = []
    for nome, info in LACUNAS.items():
        col    = info["coluna_fato"]
        alias  = info["alias_pct"]
        den    = info["denominador_sql"]
        sufixo = alias[len("pct_"):]

        linhas.append(
            f"        COUNTIF({col} = TRUE)          AS n_num_{sufixo}"
        )
        linhas.append(
            f"        NULLIF({den}, 0)               AS n_den_{sufixo}"
        )
    return ",\n".join(linhas)
