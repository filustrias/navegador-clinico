# 📊 Mapeamento Geral: Gráficos, Regras e Queries (V3)

Este documento centraliza a inteligência de dados do dashboard. Para cada visualização, descrevemos a **Regra de Negócio** aplicada e a **Query SQL** correspondente para execução no BigQuery (`rj-sms-sandbox.sub_pav_us.MM_2026_novos_cadastros`).

---

## 🏗️ 1. Visão Geral (Dashboard Macro)

### 📈 1.1 KPIs de Linha de Frente
- **Regras:**
    - **Total de Pacientes:** Contagem total de cadastros ativos.
    - **Multimorbidade:** Pacientes com `total_morbidades >= 2`.
    - **Muito Alto Risco:** Pacientes com `charlson_categoria = 'Muito Alto'`.
- **Query:**
```sql
SELECT 
    COUNT(*) as total_pacientes,
    COUNTIF(total_morbidades >= 2) as multimorbidade,
    COUNTIF(charlson_categoria = 'Muito Alto') as muito_alto_risco,
    COUNTIF(polifarmacia = TRUE) as polifarmacia,
    COUNTIF(consultas_365d = 0) as sem_acompanhamento
FROM `rj-sms-sandbox.sub_pav_us.MM_2026_novos_cadastros`
```

### 📊 1.2 Distribuição de Gravidade por AP
- **Regra:** Distribuição percentual das 4 categorias de Charlson dentro de cada Área Programática.
- **Tipo:** Bar Chart Stacked 100%.
- **Query:**
```sql
SELECT 
    area_programatica_cadastro as ap,
    charlson_categoria as categoria,
    COUNT(*) as total
FROM `rj-sms-sandbox.sub_pav_us.MM_2026_novos_cadastros`
GROUP BY 1, 2
ORDER BY 1, 2
```

---

## 👥 2. Faixa Etária e Polifarmácia

### 📈 2.1 Pirâmide Populacional
- **Regra:** Distribuição por sexo e faixas etárias de 5 em 5 anos, calculada dinamicamente para permitir filtros regionais.
- **Tabela:** `rj-sms-sandbox.sub_pav_us.MM_2026_novos_cadastros`.
- **Query:**
```sql
SELECT 
    CASE 
        WHEN idade < 5 THEN '00-04'
        WHEN idade BETWEEN 5 AND 9 THEN '05-09'
        WHEN idade BETWEEN 10 AND 14 THEN '10-14'
        WHEN idade BETWEEN 15 AND 19 THEN '15-19'
        WHEN idade BETWEEN 20 AND 24 THEN '20-24'
        WHEN idade BETWEEN 25 AND 29 THEN '25-29'
        WHEN idade BETWEEN 30 AND 34 THEN '30-34'
        WHEN idade BETWEEN 35 AND 39 THEN '35-39'
        WHEN idade BETWEEN 40 AND 44 THEN '40-44'
        WHEN idade BETWEEN 45 AND 49 THEN '45-49'
        WHEN idade BETWEEN 50 AND 54 THEN '50-54'
        WHEN idade BETWEEN 55 AND 59 THEN '55-59'
        WHEN idade BETWEEN 60 AND 64 THEN '60-64'
        WHEN idade BETWEEN 65 AND 69 THEN '65-69'
        WHEN idade BETWEEN 70 AND 74 THEN '70-74'
        WHEN idade BETWEEN 75 AND 79 THEN '75-79'
        WHEN idade BETWEEN 80 AND 84 THEN '80-84'
        WHEN idade BETWEEN 85 AND 89 THEN '85-89'
        WHEN idade BETWEEN 90 AND 94 THEN '90-94'
        ELSE '95+'
    END as faixa_etaria,
    genero,
    COUNT(*) as total
FROM `rj-sms-sandbox.sub_pav_us.MM_2026_novos_cadastros`
GROUP BY 1, 2
ORDER BY 1
```

### 📉 2.2 Gráfico de Carga de Polifarmácia (Área)
- **Regra:** Evolução do uso de medicamentos por idade.
- **Faixas:** `< 40`, `40-49`, `50-59`, `60-69`, `70-79`, `≥ 80`.
- **Query:**
```sql
SELECT 
    CASE 
        WHEN idade < 40 THEN '< 40'
        WHEN idade BETWEEN 40 AND 49 THEN '40-49'
        WHEN idade BETWEEN 50 AND 59 THEN '50-59'
        WHEN idade BETWEEN 60 AND 69 THEN '60-69'
        WHEN idade BETWEEN 70 AND 79 THEN '70-79'
        ELSE '≥ 80'
    END as faixa_etaria,
    COUNTIF(polifarmacia = FALSE AND hiperpolifarmacia = FALSE) * 100.0 / COUNT(*) as pct_sem_poli,
    COUNTIF(polifarmacia = TRUE AND hiperpolifarmacia = FALSE) * 100.0 / COUNT(*) as pct_poli,
    COUNTIF(hiperpolifarmacia = TRUE) * 100.0 / COUNT(*) as pct_hiper
FROM `rj-sms-sandbox.sub_pav_us.MM_2026_novos_cadastros`
GROUP BY 1
ORDER BY 1
```

---

## 🤒 3. Doenças Prevalentes

### 📊 3.1 Ranking Top de Morbidades
- **Regra:** Contagem de pacientes por condição crônica identificada.
- **Variáveis:** HAS, DM, IRC, ICC, CI, stroke, obesidade, dislipidemia.
- **Query:**
```sql
SELECT 'Hipertensão (HAS)' as doenca, COUNT(HAS) as total FROM `rj-sms-sandbox.sub_pav_us.MM_2026_novos_cadastros` WHERE HAS IS NOT NULL
UNION ALL
SELECT 'Diabetes (DM)', COUNT(DM) FROM `rj-sms-sandbox.sub_pav_us.MM_2026_novos_cadastros` WHERE DM IS NOT NULL
UNION ALL
SELECT 'Doença Renal (IRC)', COUNT(IRC) FROM `rj-sms-sandbox.sub_pav_us.MM_2026_novos_cadastros` WHERE IRC IS NOT NULL
UNION ALL
SELECT 'Insuf. Cardíaca (ICC)', COUNT(ICC) FROM `rj-sms-sandbox.sub_pav_us.MM_2026_novos_cadastros` WHERE ICC IS NOT NULL
ORDER BY total DESC
```

---

## ⚠️ 4. Lacunas de Cuidado e Controle

### 🛡️ 4.1 Painel de Lacunas por Território
- **Regra:** Identificar alertas ativos (flags binárias).
- **Query:**
```sql
SELECT 
    area_programatica_cadastro as ap,
    COUNTIF(lacuna_DM_sem_HbA1c_recente = TRUE) as dm_sem_exame,
    COUNTIF(lacuna_DM_descontrolado = TRUE) as dm_descontrolado,
    COUNTIF(lacuna_HAS_descontrolado_menor80 = TRUE OR lacuna_HAS_descontrolado_80mais = TRUE) as has_descontrolado
FROM `rj-sms-sandbox.sub_pav_us.MM_2026_novos_cadastros`
GROUP BY 1
```

---

> [!IMPORTANT]
> **Nota sobre Filtros Regionais:** Todas as queries acima devem ser filtradas dinamicamente no Python (Streamlit) caso o usuário selecione uma Unidade ou Equipe específica, adicionando a cláusula `WHERE nome_clinica_cadastro = '...'`.
