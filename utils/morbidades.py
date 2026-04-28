"""
Mapeamento de morbidades — fonte única de verdade.

Cada entrada associa um nome legível em português ao nome da
coluna correspondente na tabela fato (data de diagnóstico ou NULL).
Usado por Meus Pacientes, Visão ESF e qualquer outra page que
precise listar/filtrar por morbidade.
"""

MORBIDADES_MAP = {
    # === CARDIOVASCULARES (8) ===
    'Hipertensão Arterial':              'HAS',
    'Cardiopatia Isquêmica':             'CI',
    'Insuficiência Cardíaca':            'ICC',
    'AVC':                               'stroke',
    'Arritmia':                          'arritmia',
    'Doença Valvular':                   'valvular',
    'Doença Vascular Periférica':        'vascular_periferica',
    'Doença Circulatória Pulmonar':      'circ_pulm',

    # === METABÓLICAS/ENDÓCRINAS (4) ===
    'Diabetes Mellitus':                 'DM',
    'Pré-diabetes':                      'pre_DM',
    'Dislipidemia':                      'dislipidemia',
    'Obesidade':                         'obesidade_consolidada',

    # === RENAIS (1) ===
    'Insuficiência Renal Crônica':       'IRC',

    # === RESPIRATÓRIAS (2) ===
    'DPOC':                              'COPD',
    'Asma':                              'asthma',

    # === NEUROLÓGICAS/PSIQUIÁTRICAS (8) ===
    'Demência':                          'dementia',
    'Doença Neurológica':                'neuro',
    'Epilepsia':                         'epilepsy',
    'Parkinsonismo':                     'parkinsonism',
    'Esclerose Múltipla':                'multiple_sclerosis',
    'Plegia':                            'plegia',
    'Psicose':                           'psicoses',
    'Depressão e Ansiedade':             'depre_ansiedade',

    # === NEOPLASIAS (8) ===
    'Neoplasia de Mama':                 'neoplasia_mama',
    'Neoplasia de Colo do Útero':        'neoplasia_colo_uterino',
    'Neoplasia Feminina (exceto mama/colo)': 'neoplasia_feminina_estrita',
    'Neoplasia Masculina':               'neoplasia_masculina_estrita',
    'Neoplasia (ambos os sexos)':        'neoplasia_ambos_os_sexos',
    'Leucemia':                          'leukemia',
    'Linfoma':                           'lymphoma',
    'Câncer Metastático':                'metastasis',

    # === GASTROINTESTINAIS/HEPÁTICAS (4) ===
    'Úlcera Péptica':                    'peptic',
    'Doença Hepática':                   'liver',
    'Doença Diverticular':               'diverticular_disease',
    'Doença Inflamatória Intestinal':    'ibd',

    # === INFECCIOSAS (1) ===
    'HIV/AIDS':                          'HIV',

    # === HEMATOLÓGICAS (2) ===
    'Distúrbio de Coagulação':           'coagulo',
    'Anemia':                            'anemias',

    # === REUMATOLÓGICAS (1) ===
    'Doença Reumatológica':              'reumato',

    # === SUBSTÂNCIAS (3) ===
    'Transtorno por Uso de Álcool':      'alcool',
    'Transtorno por Uso de Drogas':      'drogas',
    'Tabagismo':                         'tabaco',

    # === NUTRICIONAIS (1) ===
    'Desnutrição':                       'desnutricao',

    # === DEFICIÊNCIAS/SENSORIAIS (3) ===
    'Deficiência Intelectual':           'retardo_mental',
    'Doença Ocular':                     'olhos',
    'Doença Auditiva':                   'ouvidos',

    # === OUTRAS (4) ===
    'Malformação Congênita':             'ma_formacoes',
    'Doença de Pele':                    'pele',
    'Condição Dolorosa Crônica':         'painful_condition',
    'Doença de Próstata':                'prostate_disorder',
}


def gerar_sql_morbidades_lista(alias: str = "morbidades_lista") -> str:
    """
    Retorna fragmento SQL que produz uma lista textual com os
    nomes (português) das morbidades ativas do paciente, separados
    por vírgula. Inclui apenas as colunas com data preenchida.

    Uso:
        sql = f"SELECT cpf, {gerar_sql_morbidades_lista()} FROM ..."
    """
    linhas = [
        f"            IF({col} IS NOT NULL, '{nome}', NULL)"
        for nome, col in MORBIDADES_MAP.items()
    ]
    return (
        "ARRAY_TO_STRING(ARRAY(SELECT m FROM UNNEST([\n"
        + ",\n".join(linhas)
        + "\n        ]) AS m WHERE m IS NOT NULL), ', ') AS " + alias
    )


def extrair_morbidades_paciente(patient_data: dict) -> list:
    """
    Constrói lista de morbidades ativas a partir do registro do
    paciente. Aceita tanto colunas booleanas (CASE WHEN ... NOT NULL
    THEN TRUE — formato usado em Meus Pacientes) quanto colunas com
    a data de diagnóstico (formato cru da tabela fato).
    """
    out = []
    for nome, col in MORBIDADES_MAP.items():
        val = patient_data.get(col)
        if val is None or val is False or val == '':
            continue
        try:
            import pandas as pd
            if pd.isna(val):
                continue
        except Exception:
            pass
        out.append(nome)
    return out
