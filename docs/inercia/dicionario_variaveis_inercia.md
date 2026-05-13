# Dicionário de Variáveis — Inércia Terapêutica

**Versão:** V3 (refatoração de maio/2026 — nova taxonomia com 11 categorias)
**Última atualização:** 2026-05-13
**Autor:** Adelson / Sub-PAV-US — SMS-RJ
**Escopo:** Variáveis derivadas do pipeline de inércia (5 etapas) integradas em duas tabelas-destino:
- `MM_2026_novos_cadastros_stopp_start` (grão **paciente** — 50 colunas adicionadas)
- `MM_consultas_agregado` (grão **sexo × faixa etária × AP × clínica × ESF** — 36 colunas adicionadas)

**Para o Claude Code:** este documento é a referência canônica das variáveis. Antes de escrever qualquer query envolvendo inércia, leia a seção 0 ("Pegadinhas comuns") — ela evita 90% dos erros frequentes.

---

## 0. ⚠️ Pegadinhas comuns (LEIA ANTES DE ESCREVER QUERIES)

### 0.1 Os 4 nomes de coluna que diferem entre HAS e DM

A categoria "sem nenhuma aferição" usa **nomes diferentes** para HAS (PA) e DM (HbA1c). Quem espera simetria (`_PA_DM`) escreve queries que silenciosamente retornam zero.

| HAS | DM |
|---|---|
| `paciente_sem_nenhuma_PA_HAS` | `paciente_sem_nenhuma_HbA1c_DM` |
| `n_sem_nenhuma_PA_HAS` | `n_sem_nenhuma_HbA1c_DM` |
| `n_consultas_sem_nenhuma_PA_HAS` | `n_consultas_sem_nenhuma_HbA1c_DM` |
| `texto_sem_nenhuma_PA_HAS_*` | `texto_sem_nenhuma_HbA1c_DM_*` |

E o **valor do `status_atual`** também:
- `status_atual_HAS = 'TRATAMENTO_SEM_NENHUMA_PA'`
- `status_atual_DM  = 'TRATAMENTO_SEM_NENHUMA_HbA1c'` ← não é `_PA`

### 0.2 Denominadores diferentes para cada métrica

Cada taxa de inércia tem um denominador **clinicamente correto**. Usar o errado leva a números enviesados.

| Numerador | Denominador correto | Por quê |
|---|---|---|
| `n_inercia_persistente_HAS` | `n_HAS_tratados` | Só faz sentido falar em inércia para quem tem tratamento ativo |
| `n_inercia_falta_aferi_HAS` | `n_HAS_tratados` | Idem |
| `n_descontrole_recente_HAS` | `n_HAS_tratados` | Idem |
| `n_inercia_falta_tratamento_HAS` | **`n_pacientes_HAS`** | Aqui o universo é TODOS os HAS, porque a flag dispara justamente para quem NÃO tem tratamento. Usar `n_HAS_tratados` daria 0. |
| `n_renovado_controlado_atrasado_HAS` | `n_HAS_tratados` | Exige tratamento ativo |
| `n_sem_nenhuma_PA_HAS` | `n_HAS_tratados` | Exige tratamento ativo |
| `n_manejo_apropriado_HAS` | `n_HAS_tratados` | Exige tratamento ativo |
| `n_controlado_HAS` | `n_HAS_tratados` | Exige tratamento ativo |

**Regra prática:** todas usam `n_HAS_tratados` EXCETO `n_inercia_falta_tratamento_HAS`, que usa `n_pacientes_HAS`.

### 0.3 `status_atual_*` é cascata hierárquica (não soma)

As 11 categorias do `status_atual_HAS` são **mutuamente exclusivas**. Um paciente recebe apenas UMA — a primeira que bate na cascata (seção 2.2).

Por isso:
- `COUNT(*) = SUM(COUNTIF(status_atual_HAS = '<cada categoria>'))` ✓ bate
- A flag-mestra `paciente_sem_nenhuma_PA_HAS` pode disparar TRUE mesmo quando `status_atual_HAS = 'INERCIA_PERSISTENTE'` (porque INERCIA_PERSISTENTE vem antes na cascata)

**Implicação:** se você quiser "todos os pacientes que NUNCA foram aferidos", use a flag (`paciente_sem_nenhuma_PA_HAS = TRUE`). Se quiser "pacientes cuja **categoria principal** é sem-nenhuma-PA", use o status atual.

### 0.4 Tabela vs. fato vs. agregado — qual usar?

| Pergunta típica | Tabela correta |
|---|---|
| "Qual o status desse paciente específico (CPF)?" | `MM_2026_novos_cadastros_stopp_start` (fato) |
| "Quantos pacientes em inércia na clínica X?" | `MM_consultas_agregado` (agregado) |
| "Detalhes da trajetória das consultas?" | `MM_inercia_paciente` (intermediária — só se precisar das colunas de snapshot por consulta) |

A fato e o agregado já têm tudo que o Streamlit precisa. Evite usar `MM_inercia_consulta_nivel` ou `MM_inercia_paciente` diretamente — são intermediárias.

### 0.5 Aviso sobre a categoria `OUTRO`

Casos residuais que não se encaixam em nenhuma categoria. Devem ser ~1% — se crescer muito, há bug na cascata. Não confunda com `SEM_PRESCRICAO_RECENTE` (categoria que **deixou de existir** na V3 e virou `INERCIA_POR_FALTA_DE_TRATAMENTO`).

---

## 1. Conceitos fundamentais

### 1.1 As 6 categorias de "alerta" (inércia ou correlatas)

São **categorias mutuamente exclusivas** que capturam diferentes formas em que o cuidado pode "falhar":

| Categoria | Tipo | Definição operacional |
|---|---|---|
| 🔴 **INERCIA_PERSISTENTE** | Inércia clássica | Descontrole confirmado (atual + histórico OU ≥2 medidas altas em 180d OU única alta sem histórico), esquema mantido ou desintensificado. |
| 🟠 **INERCIA_POR_FALTA_DE_TRATAMENTO** | Inércia estrutural | Paciente diagnosticado HAS/DM **sem prescrição em 365d**. Cobre todos os casos, independente do status de aferição. |
| 🟠 **INERCIA_POR_FALTA_DE_AFERICAO** | Inércia estrutural | Paciente em tratamento, histórico (180-730d) descontrolado, sem aferição em 180d, esquema mantido. |
| 🟠 **DESCONTROLE_RECENTE_SEM_ACAO** | Pré-inércia | Estava controlado antes (180-730d), descontrolou agora (1 medida), esquema mantido. Não é inércia confirmada — próxima aferição definirá. |
| 🟡 **TRATAMENTO_RENOVADO_CONTROLADO_ATRASADO** | Continuidade | Histórico (180-730d) na meta, sem aferição em 180d, esquema mantido. "Estava bem, sumiu." |
| 🟠 **TRATAMENTO_SEM_NENHUMA_PA** / **_HbA1c** | Voando cego | Em tratamento ativo, mas **nenhuma aferição em até 730d**. Caso totalmente cego. |

**Distribuição municipal (RJ, hipertensos, n=1.221.413):**

| Categoria | Pacientes | % |
|---|---|---|
| Inércia por falta de tratamento | 583.529 | 47,77% |
| Inércia por falta de aferição | 97.499 | 7,98% |
| Inércia persistente (clássica) | 27.609 | 2,26% |
| Descontrole recente sem ação | 7.424 | 0,61% |
| Renovado controlado atrasado | 123.349 | 10,10% |
| Sem nenhuma PA aferida | 48.752 | 3,99% |

### 1.2 Janelas temporais

- **90d**: análise curta — consulta atual vs. consulta imediatamente anterior
- **180d**: análise longa — trajetória sobre prescrições
- **365d**: trajetória completa — todas as consultas do paciente
- **181-730d (HAS)** / **181-365d (DM)**: janela histórica para PA / HbA1c

### 1.3 Limiar de mudança de dose

- **Orais (HAS + DM oral):** ±20%
- **Insulina NPH:** ±10%

### 1.4 Critério de controle

- **PA:** `PAS ≤ meta_pas` E `PAD ≤ meta_pad`
- **HbA1c:** `interpretacao_hba1c = 'dm_controlado'`

### 1.5 Metas

- **PA:** 130/80 (HAS+DM), 150/x (≥80 anos), 140/90 (geral)
- **HbA1c:** 7,0% (<60a), 7,5% (60-69a), 8,0% (≥70a)

---

## 2. Colunas em `MM_2026_novos_cadastros_stopp_start` (grão paciente)

**Total: 50 colunas de inércia** integradas via LEFT JOIN com `MM_inercia_paciente`.

### 2.1 Flags-mestras booleanas (12 colunas)

Booleanas, mutuamente exclusivas dentro de cada linha (HAS/DM). Úteis para filtragem rápida no Streamlit.

| Coluna | Tipo | Descrição |
|---|---|---|
| `paciente_inercia_persistente_HAS` | BOOL | Inércia confirmada na última consulta HAS |
| `paciente_inercia_persistente_DM` | BOOL | Inércia confirmada na última consulta DM |
| `paciente_inercia_falta_tratamento_HAS` | BOOL | HAS diagnosticada, sem prescrição em 365d |
| `paciente_inercia_falta_tratamento_DM` | BOOL | DM diagnosticada, sem prescrição em 365d |
| `paciente_inercia_falta_aferi_HAS` | BOOL | PA histórica descontrolada, sem aferir, mantido |
| `paciente_inercia_falta_aferi_DM` | BOOL | HbA1c histórica descontrolada, sem aferir, mantido |
| `paciente_descontrole_recente_sem_acao_HAS` | BOOL | Estava controlado, descontrolou agora, mantido |
| `paciente_descontrole_recente_sem_acao_DM` | BOOL | Idem para DM |
| `paciente_renovado_controlado_atrasado_HAS` | BOOL | PA histórica na meta, sem aferir, mantido |
| `paciente_renovado_controlado_atrasado_DM` | BOOL | HbA1c histórica na meta, sem aferir, mantido |
| `paciente_sem_nenhuma_PA_HAS` | BOOL | Em tratamento, sem nenhuma PA em 730d |
| `paciente_sem_nenhuma_HbA1c_DM` | BOOL | Em tratamento, sem nenhuma HbA1c em 730d |

### 2.2 Status atual — snapshot da última consulta (2 colunas)

A **cascata hierárquica** decide qual categoria o paciente recebe (a primeira que bate vence):

```
1. INERCIA_PERSISTENTE
2. INERCIA_POR_FALTA_DE_TRATAMENTO
3. INERCIA_POR_FALTA_DE_AFERICAO
4. DESCONTROLE_RECENTE_SEM_ACAO
5. TRATAMENTO_SEM_NENHUMA_PA (HAS) / TRATAMENTO_SEM_NENHUMA_HbA1c (DM)
6. MANEJO_APROPRIADO
7. CONTROLADO_COM_LACUNA_CONSULTA
8. CONTROLADO
9. TRATAMENTO_RENOVADO_CONTROLADO_ATRASADO
10. DESCONTROLE_SEM_COMPARACAO
(11. OUTRO — residual, deve ser ~1%)
```

| Coluna | Tipo | Valores possíveis |
|---|---|---|
| `status_atual_HAS` | STRING | Uma das 11 categorias acima |
| `status_atual_DM` | STRING | Idem (com `TRATAMENTO_SEM_NENHUMA_HbA1c` em vez de `_PA`) |

### 2.3 Padrão de manejo — trajetória 365d (2 colunas)

| Coluna | Tipo | Valores |
|---|---|---|
| `padrao_manejo_HAS` | STRING | `PROATIVO`, `INERTE`, `ESTAGNADO`, `CONTROLADO`, `MISTO`, `MENOS_DE_2_CONSULTAS` |
| `padrao_manejo_DM` | STRING | Idem |

### 2.4 Textos prontos (2 colunas)

| Coluna | Tipo | Uso |
|---|---|---|
| `texto_meus_pacientes_HAS` | STRING | Texto pré-formatado para card "Meus Pacientes". Prioridade: persistente → falta_aferi → descontrole_recente → sem_nenhuma → renovado_atrasado. NULL se nenhum se aplica. |
| `texto_meus_pacientes_DM` | STRING | Idem |

### 2.5 Contadores de trajetória HAS (14 colunas)

Contam consultas com prescrição HAS nos últimos 365d.

| Coluna | Descrição |
|---|---|
| `n_consultas_HAS_365d` | Total de consultas com prescrição HAS em 365d |
| `n_consultas_inercia_persistente_HAS` | Consultas marcadas com flag de inércia persistente (90d) |
| `n_consultas_descontrole_recente_HAS` | Consultas marcadas como descontrole recente sem ação (90d) |
| `n_consultas_renovado_controlado_atrasado_HAS` | Consultas marcadas como renovado controlado atrasado (90d) |
| `n_consultas_inercia_falta_aferi_HAS` | Consultas marcadas como inércia por falta de aferição (90d) |
| `n_consultas_sem_nenhuma_PA_HAS` | Consultas com tratamento sem nenhuma PA (90d) |
| `n_consultas_intensificou_HAS` | Consultas com `status_acao = INTENSIFICOU` |
| `n_consultas_trocou_HAS` | Consultas com `status_acao = TROCOU` |
| `n_consultas_desintensificou_HAS` | Consultas com `status_acao = DESINTENSIFICOU` |
| `n_consultas_mantido_HAS` | Consultas com `status_acao = MANTIDO` |
| `n_consultas_sem_comparacao_HAS` | Consultas com `status_acao = SEM_COMPARACAO` |
| `n_consultas_pa_controlada` | Consultas em que a PA estava controlada |
| `n_consultas_pa_descontrolada` | Consultas em que a PA estava descontrolada |
| `n_consultas_pa_sem_aferi` | Consultas sem PA aferida em 180d |

### 2.6 Contadores de trajetória DM (14 colunas)

Análogos aos de HAS, com `HbA1c` em vez de `PA` quando aplicável.

| Coluna | Descrição |
|---|---|
| `n_consultas_DM_365d` | Total de consultas com prescrição DM em 365d |
| `n_consultas_inercia_persistente_DM` | Consultas em inércia persistente (90d) |
| `n_consultas_descontrole_recente_DM` | Consultas em descontrole recente sem ação (90d) |
| `n_consultas_renovado_controlado_atrasado_DM` | Consultas em renovado controlado atrasado (90d) |
| `n_consultas_inercia_falta_aferi_DM` | Consultas em inércia por falta de aferição (90d) |
| `n_consultas_sem_nenhuma_HbA1c_DM` | Consultas com tratamento sem nenhuma HbA1c (90d) |
| `n_consultas_intensificou_DM` | Consultas com `status_acao = INTENSIFICOU` |
| `n_consultas_trocou_DM` | Consultas com `status_acao = TROCOU` |
| `n_consultas_desintensificou_DM` | Consultas com `status_acao = DESINTENSIFICOU` |
| `n_consultas_mantido_DM` | Consultas com `status_acao = MANTIDO` |
| `n_consultas_sem_comparacao_DM` | Consultas com `status_acao = SEM_COMPARACAO` |
| `n_consultas_dm_controlado` | Consultas em que a HbA1c estava controlada |
| `n_consultas_dm_descontrolado` | Consultas em que a HbA1c estava descontrolada |
| `n_consultas_dm_sem_aferi` | Consultas sem HbA1c em 180d |

---

## 3. Colunas em `MM_consultas_agregado` (grão equipe)

**Grão:** `(área programática × clínica × ESF × faixa etária × gênero)`, filtro de ESF ≥100 pacientes.
**Total: 36 contadores de inércia** (18 HAS + 18 DM).

### 3.1 Denominadores HAS (2 colunas)

| Coluna | Descrição |
|---|---|
| `n_pacientes_HAS` | Total de pacientes HAS na célula |
| `n_HAS_tratados` | Pacientes HAS com `n_consultas_HAS_365d > 0` (denominador correto para taxa de inércia) |

### 3.2 Contadores de status atual HAS (10 colunas, mutuamente exclusivas)

| Coluna | Descrição |
|---|---|
| `n_inercia_persistente_HAS` | Pacientes com inércia persistente |
| `n_inercia_falta_tratamento_HAS` | Pacientes sem prescrição em 365d |
| `n_inercia_falta_aferi_HAS` | Pacientes em inércia por falta de aferição |
| `n_descontrole_recente_HAS` | Pacientes em descontrole recente sem ação |
| `n_renovado_controlado_atrasado_HAS` | Pacientes em renovado controlado atrasado |
| `n_sem_nenhuma_PA_HAS` | Pacientes sem nenhuma PA em 730d |
| `n_manejo_apropriado_HAS` | Pacientes em manejo apropriado |
| `n_controlado_HAS` | Pacientes controlados, seguimento regular |
| `n_controlado_lacuna_HAS` | Pacientes controlados com lacuna de consulta |
| `n_descontrole_sem_comp_HAS` | Descontrole sem comparação |

### 3.3 Contadores de padrão de manejo HAS (6 colunas)

| Coluna | Descrição |
|---|---|
| `n_padrao_proativo_HAS` | Pacientes com padrão proativo |
| `n_padrao_inerte_HAS` | Pacientes com padrão inerte |
| `n_padrao_estagnado_HAS` | Pacientes com padrão estagnado |
| `n_padrao_controlado_HAS` | Pacientes com padrão controlado |
| `n_padrao_misto_HAS` | Pacientes com padrão misto |
| `n_padrao_menos_2_consultas_HAS` | <2 consultas em 365d |

### 3.4 Análogos para DM (18 colunas)

Mesmas categorias acima, trocando sufixo `_HAS` por `_DM`. Importante: `n_sem_nenhuma_HbA1c_DM` em vez de `n_sem_nenhuma_PA_DM`.

---

## 4. Padrões de uso recomendados no Streamlit

### 4.1 Card "Meus Pacientes" (grão paciente)

```python
# Buscar pacientes em qualquer alerta clínico de uma equipe
flags_alerta = [
    'paciente_inercia_persistente_HAS',
    'paciente_inercia_persistente_DM',
    'paciente_inercia_falta_tratamento_HAS',
    'paciente_inercia_falta_tratamento_DM',
    'paciente_inercia_falta_aferi_HAS',
    'paciente_inercia_falta_aferi_DM',
    'paciente_descontrole_recente_sem_acao_HAS',
    'paciente_descontrole_recente_sem_acao_DM',
]

filtro = (
    (df['nome_esf_cadastro'] == esf_selecionada) &
    (df[flags_alerta].any(axis=1))
)
pacientes_alerta = df[filtro][[
    'cpf', 'nome', 'idade',
    'status_atual_HAS', 'status_atual_DM',
    'texto_meus_pacientes_HAS', 'texto_meus_pacientes_DM'
]]
# Exibir texto_meus_pacientes_* diretamente — já vem formatado
```

### 4.2 Taxa de inércia por clínica (grão equipe)

```python
df_clinica = (
    df_agreg.groupby(['area_programatica_cadastro', 'nome_clinica_cadastro'])
            .agg({
                'n_pacientes_HAS': 'sum',
                'n_HAS_tratados': 'sum',
                'n_inercia_persistente_HAS': 'sum',
                'n_inercia_falta_aferi_HAS': 'sum',
                'n_inercia_falta_tratamento_HAS': 'sum',
                'n_descontrole_recente_HAS': 'sum',
                'n_controlado_HAS': 'sum'
            })
            .reset_index()
)

# Taxa de inércia persistente (entre os tratados — denominador correto)
df_clinica['pct_inercia_persistente'] = (
    100 * df_clinica['n_inercia_persistente_HAS'] / df_clinica['n_HAS_tratados']
)

# Taxa de inércia por falta de aferição (entre os tratados)
df_clinica['pct_inercia_falta_aferi'] = (
    100 * df_clinica['n_inercia_falta_aferi_HAS'] / df_clinica['n_HAS_tratados']
)

# Taxa de inércia por falta de tratamento (entre todos os HAS — denominador diferente)
df_clinica['pct_inercia_falta_tratamento'] = (
    100 * df_clinica['n_inercia_falta_tratamento_HAS'] / df_clinica['n_pacientes_HAS']
)
```

### 4.3 IC95% Wilson em Python

```python
import numpy as np
from scipy.stats import norm

def wilson_ci(x, n, alpha=0.05):
    """IC95% Wilson Score para proporção."""
    if n == 0:
        return (np.nan, np.nan)
    z = norm.ppf(1 - alpha/2)
    p = x / n
    center = (p + z**2/(2*n)) / (1 + z**2/n)
    margin = z * np.sqrt(p*(1-p)/n + z**2/(4*n**2)) / (1 + z**2/n)
    return (max(0, 100*(center - margin)), min(100, 100*(center + margin)))

df_clinica[['ic95_low', 'ic95_high']] = df_clinica.apply(
    lambda r: wilson_ci(r['n_inercia_persistente_HAS'], r['n_HAS_tratados']),
    axis=1, result_type='expand'
)
```

### 4.4 Distribuição de status por equipe (stacked bar)

```python
# 10 categorias do status_atual com cores semafóricas
categorias = [
    ('Inércia persistente', 'n_inercia_persistente_HAS'),
    ('Inércia por falta de aferição', 'n_inercia_falta_aferi_HAS'),
    ('Inércia por falta de tratamento', 'n_inercia_falta_tratamento_HAS'),
    ('Descontrole recente', 'n_descontrole_recente_HAS'),
    ('Sem nenhuma PA', 'n_sem_nenhuma_PA_HAS'),
    ('Renovado controlado atrasado', 'n_renovado_controlado_atrasado_HAS'),
    ('Controlado com lacuna', 'n_controlado_lacuna_HAS'),
    ('Manejo apropriado', 'n_manejo_apropriado_HAS'),
    ('Controlado', 'n_controlado_HAS'),
    ('Descontrole sem comparação', 'n_descontrole_sem_comp_HAS'),
]

cores = {
    'Inércia persistente': '#c0392b',
    'Inércia por falta de aferição': '#e67e22',
    'Inércia por falta de tratamento': '#d35400',
    'Descontrole recente': '#e74c3c',
    'Sem nenhuma PA': '#f39c12',
    'Renovado controlado atrasado': '#f1c40f',
    'Controlado com lacuna': '#bdc3c7',
    'Manejo apropriado': '#27ae60',
    'Controlado': '#16a085',
    'Descontrole sem comparação': '#95a5a6',
}
```

### 4.5 Benchmarks dinâmicos

```python
# Mediana das taxas das clínicas (filtro n≥50 para evitar outliers)
n_min = 50
benchmark_municipio = df_clinica[df_clinica['n_HAS_tratados'] >= n_min]['pct_inercia_persistente'].median()

benchmark_ap = (
    df_clinica[df_clinica['n_HAS_tratados'] >= n_min]
    .groupby('area_programatica_cadastro')['pct_inercia_persistente'].median()
    .to_dict()
)
```

---

## 5. Achados clínicos relevantes (validações)

Distribuição municipal RJ — todos os 1.221.413 hipertensos do município:

| Categoria | % do total | Pacientes |
|---|---|---|
| Inércia por falta de tratamento | 47,77% | 583.529 |
| Controlado | 12,09% | 147.670 |
| Renovado controlado atrasado | 10,10% | 123.349 |
| Descontrole sem comparação | 8,80% | 107.497 |
| Inércia por falta de aferição | 7,98% | 97.499 |
| Controlado com lacuna de consulta | 4,11% | 50.185 |
| Sem nenhuma PA | 3,99% | 48.752 |
| Inércia persistente | 2,26% | 27.609 |
| Manejo apropriado | 1,41% | 17.200 |
| Outro (residual) | 0,88% | 10.699 |
| Descontrole recente sem ação | 0,61% | 7.424 |

**Total em alguma forma de inércia:** 708.637 pacientes (58,01%)

**Insight chave:** o problema dominante no RJ não é inércia clássica (apenas 2,26% têm inércia persistente). O grosso é:
- Inércia por falta de tratamento (~48%) — pacientes diagnosticados sem prescrição registrada
- Inércia por falta de aferição (~8%) — pacientes em tratamento sem PA conhecida

Isso reposiciona o foco da intervenção: antes de "treinar médico", é preciso **estruturar a coleta de dados e a busca ativa**.

---

## 6. Glossário rápido

| Termo | Definição em uma frase |
|---|---|
| INERCIA_PERSISTENTE | Paciente descontrolado, médico não agiu, descontrole confirmado |
| INERCIA_POR_FALTA_DE_TRATAMENTO | Diagnosticado, mas sem prescrição registrada em 365d |
| INERCIA_POR_FALTA_DE_AFERICAO | Sabíamos que estava ruim, ninguém afere, nada mudou |
| DESCONTROLE_RECENTE_SEM_ACAO | Estava bem, descontrolou agora, médico ainda não agiu |
| TRATAMENTO_SEM_NENHUMA_PA / _HbA1c | Em tratamento, nunca foi aferido em 730d (cego total) |
| TRATAMENTO_RENOVADO_CONTROLADO_ATRASADO | Estava na meta, sumiu, esquema renovado sem aferir |
| MANEJO_APROPRIADO | Descontrolado, médico intensificou ou trocou |
| CONTROLADO | Na meta, seguimento regular |
| CONTROLADO_COM_LACUNA_CONSULTA | Na meta, mas >180d sem consulta |
| DESCONTROLE_SEM_COMPARACAO | Descontrolado, sem prescrição anterior para classificar |

---

## 7. Queries SQL prontas (templates BigQuery)

Cole e adapte conforme necessário. Todas as queries usam o dataset `rj-sms-sandbox.sub_pav_us`.

### 7.1 Distribuição completa do município por status_atual

```sql
SELECT
    status_atual_HAS,
    COUNT(*) AS n_pacientes,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER(), 2) AS pct
FROM `rj-sms-sandbox.sub_pav_us.MM_2026_novos_cadastros_stopp_start`
WHERE HAS IS NOT NULL
GROUP BY status_atual_HAS
ORDER BY n_pacientes DESC;
```

Trocar `HAS` por `DM` para a linha diabética.

### 7.2 Pacientes em alerta de uma ESF específica (card "Meus Pacientes")

```sql
SELECT
    cpf,
    nome,
    idade,
    status_atual_HAS,
    status_atual_DM,
    texto_meus_pacientes_HAS,
    texto_meus_pacientes_DM
FROM `rj-sms-sandbox.sub_pav_us.MM_2026_novos_cadastros_stopp_start`
WHERE nome_esf_cadastro = 'NOME_DA_ESF_AQUI'
  AND (
      paciente_inercia_persistente_HAS = TRUE
   OR paciente_inercia_persistente_DM  = TRUE
   OR paciente_inercia_falta_aferi_HAS = TRUE
   OR paciente_inercia_falta_aferi_DM  = TRUE
   OR paciente_descontrole_recente_sem_acao_HAS = TRUE
   OR paciente_descontrole_recente_sem_acao_DM  = TRUE
  )
ORDER BY
    -- Prioridade clínica
    CASE
        WHEN paciente_inercia_persistente_HAS OR paciente_inercia_persistente_DM THEN 1
        WHEN paciente_inercia_falta_aferi_HAS OR paciente_inercia_falta_aferi_DM THEN 2
        WHEN paciente_descontrole_recente_sem_acao_HAS OR paciente_descontrole_recente_sem_acao_DM THEN 3
        ELSE 4
    END;
```

### 7.3 Taxa de inércia persistente por clínica (ranking)

Usa o agregado, com filtro de clínica ≥100 pacientes HAS tratados.

```sql
SELECT
    area_programatica_cadastro AS ap,
    nome_clinica_cadastro AS clinica,
    SUM(n_HAS_tratados) AS pacientes_HAS_tratados,
    SUM(n_inercia_persistente_HAS) AS em_inercia_persistente,
    ROUND(100.0 * SUM(n_inercia_persistente_HAS)
                / NULLIF(SUM(n_HAS_tratados), 0), 2) AS pct_inercia_persistente
FROM `rj-sms-sandbox.sub_pav_us.MM_consultas_agregado`
GROUP BY ap, clinica
HAVING SUM(n_HAS_tratados) >= 100
ORDER BY pct_inercia_persistente DESC
LIMIT 20;
```

### 7.4 Taxa de inércia por falta de tratamento (denominador é diferente!)

```sql
SELECT
    area_programatica_cadastro AS ap,
    nome_clinica_cadastro AS clinica,
    SUM(n_pacientes_HAS) AS total_pacientes_HAS,
    SUM(n_inercia_falta_tratamento_HAS) AS sem_tratamento,
    ROUND(100.0 * SUM(n_inercia_falta_tratamento_HAS)
                / NULLIF(SUM(n_pacientes_HAS), 0), 2) AS pct_sem_tratamento
FROM `rj-sms-sandbox.sub_pav_us.MM_consultas_agregado`
GROUP BY ap, clinica
HAVING SUM(n_pacientes_HAS) >= 100
ORDER BY pct_sem_tratamento DESC
LIMIT 20;
```

Note o denominador `n_pacientes_HAS` (não `n_HAS_tratados`).

### 7.5 Distribuição completa por equipe (stacked bar)

```sql
SELECT
    area_programatica_cadastro AS ap,
    nome_clinica_cadastro AS clinica,
    nome_esf_cadastro AS esf,
    SUM(n_HAS_tratados) AS denominador,
    SUM(n_inercia_persistente_HAS)         AS n_inercia_persistente,
    SUM(n_inercia_falta_aferi_HAS)         AS n_inercia_falta_aferi,
    SUM(n_descontrole_recente_HAS)         AS n_descontrole_recente,
    SUM(n_sem_nenhuma_PA_HAS)              AS n_sem_nenhuma_PA,
    SUM(n_renovado_controlado_atrasado_HAS) AS n_renovado_atrasado,
    SUM(n_controlado_lacuna_HAS)           AS n_controlado_lacuna,
    SUM(n_manejo_apropriado_HAS)           AS n_manejo_apropriado,
    SUM(n_controlado_HAS)                  AS n_controlado,
    SUM(n_descontrole_sem_comp_HAS)        AS n_descontrole_sem_comp
FROM `rj-sms-sandbox.sub_pav_us.MM_consultas_agregado`
WHERE nome_esf_cadastro = 'NOME_DA_ESF_AQUI'
GROUP BY ap, clinica, esf;
```

### 7.6 Comparação clínica vs. mediana do município

```sql
WITH stats_clinicas AS (
    SELECT
        area_programatica_cadastro AS ap,
        nome_clinica_cadastro AS clinica,
        SUM(n_HAS_tratados) AS denominador,
        SUM(n_inercia_persistente_HAS) AS numerador,
        SAFE_DIVIDE(SUM(n_inercia_persistente_HAS), SUM(n_HAS_tratados)) * 100 AS pct
    FROM `rj-sms-sandbox.sub_pav_us.MM_consultas_agregado`
    GROUP BY ap, clinica
    HAVING SUM(n_HAS_tratados) >= 50
),
benchmark AS (
    SELECT
        APPROX_QUANTILES(pct, 100)[OFFSET(50)] AS mediana_municipio
    FROM stats_clinicas
)
SELECT
    s.ap,
    s.clinica,
    s.denominador,
    s.numerador,
    ROUND(s.pct, 2) AS pct_clinica,
    ROUND(b.mediana_municipio, 2) AS pct_mediana_municipio,
    ROUND(s.pct - b.mediana_municipio, 2) AS diferenca
FROM stats_clinicas s
CROSS JOIN benchmark b
ORDER BY diferenca DESC;
```

### 7.7 Spot-check: contagem total de cada flag-mestra (sanity)

Útil para validar que tudo bate após uma rodada do pipeline.

```sql
SELECT
    COUNT(*) AS n_total,
    COUNTIF(HAS IS NOT NULL) AS n_HAS,
    COUNTIF(DM IS NOT NULL)  AS n_DM,

    COUNTIF(paciente_inercia_persistente_HAS)         AS inercia_persistente_HAS,
    COUNTIF(paciente_inercia_falta_tratamento_HAS)    AS inercia_falta_tratamento_HAS,
    COUNTIF(paciente_inercia_falta_aferi_HAS)         AS inercia_falta_aferi_HAS,
    COUNTIF(paciente_descontrole_recente_sem_acao_HAS) AS descontrole_recente_HAS,
    COUNTIF(paciente_renovado_controlado_atrasado_HAS) AS renovado_HAS,
    COUNTIF(paciente_sem_nenhuma_PA_HAS)              AS sem_nenhuma_PA_HAS,

    COUNTIF(paciente_inercia_persistente_DM)          AS inercia_persistente_DM,
    COUNTIF(paciente_inercia_falta_tratamento_DM)     AS inercia_falta_tratamento_DM,
    COUNTIF(paciente_inercia_falta_aferi_DM)          AS inercia_falta_aferi_DM,
    COUNTIF(paciente_descontrole_recente_sem_acao_DM) AS descontrole_recente_DM,
    COUNTIF(paciente_renovado_controlado_atrasado_DM) AS renovado_DM,
    COUNTIF(paciente_sem_nenhuma_HbA1c_DM)            AS sem_nenhuma_HbA1c_DM  -- ← cuidado: _HbA1c_DM
FROM `rj-sms-sandbox.sub_pav_us.MM_2026_novos_cadastros_stopp_start`;
```

### 7.8 Cross-check: status_atual × padrão_manejo

Para entender a relação entre snapshot (status atual) e trajetória (padrão).

```sql
SELECT
    status_atual_HAS,
    padrao_manejo_HAS,
    COUNT(*) AS n_pacientes
FROM `rj-sms-sandbox.sub_pav_us.MM_2026_novos_cadastros_stopp_start`
WHERE HAS IS NOT NULL
GROUP BY status_atual_HAS, padrao_manejo_HAS
ORDER BY status_atual_HAS, n_pacientes DESC;
```

