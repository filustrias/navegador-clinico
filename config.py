# config.py
"""
Configurações do Dashboard de Multimorbidade
SMS-RJ
"""

# ============================================
# CREDENCIAIS BIGQUERY
# ============================================
PROJECT_ID = "rj-sms-sandbox"
DATASET_ID = "sub_pav_us"

# ============================================
# TABELAS PRINCIPAIS
# ============================================
TABELA_FATO = "MM_exames_e_risco_A1C"

# ============================================
# TABELAS DIMENSÕES
# ============================================
TABELA_DIM_MORBIDADES = "MM_dim_morbidades"
TABELA_DIM_LACUNAS = "MM_dim_lacunas"
TABELA_DIM_CLINICAS = "MM_dim_clinicas"
TABELA_DIM_ESF = "MM_dim_esf"
TABELA_DIM_AREAS = "MM_dim_areas"

# ============================================
# TABELAS AUXILIARES
# ============================================
TABELA_PIRAMIDES = "MM_piramides_populacionais"

# ============================================
# VIEWS (caso precise no futuro)
# ============================================
# VW_PREVALENCIAS = "MM_prevalencias_ESF"
# VW_PIRAMIDE_MORBIDADES = "MM_piramide_morbidades"
# VW_PIRAMIDE_CHARLSON = "MM_charlson"
# VW_PIRAMIDE_CHARLSON_CAT = "MM_charlson_cat"
# VW_PIRAMIDE_CMMS_CAT = "MM_CMMS_cat"
