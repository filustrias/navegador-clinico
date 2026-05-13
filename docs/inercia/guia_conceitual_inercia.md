# Guia Conceitual — Inércia Terapêutica na Atenção Primária

**Versão:** V3 (refatoração de maio/2026 — nova taxonomia com 11 categorias)
**Última atualização:** 2026-05-13
**Autor:** Adelson / Sub-PAV-US — SMS-RJ
**Para quem é este documento:** gestores de saúde, equipes de Atenção Primária, técnicos das Áreas Programáticas. Para a referência técnica das variáveis e nomes de colunas, ver `dicionario_variaveis_inercia.md`.

**Para entender o que cada categoria significa, por que ela existe, e como agir clinicamente.**

---

## Introdução: o problema que estamos tentando enxergar

A definição clássica de **inércia terapêutica** (Phillips, 2001) é simples:

> *"Falha em iniciar ou intensificar a terapia quando as metas terapêuticas não foram alcançadas."*

Em outras palavras: paciente está descontrolado, médico não age.

Mas na prática da atenção primária brasileira, a inércia clássica é apenas a **ponta do iceberg**. Antes mesmo de poder falar em "inércia médica", precisamos enfrentar dois problemas anteriores:

1. **Inércia estrutural** — o paciente está diagnosticado mas não está sendo tratado (sem prescrição registrada)
2. **Inércia diagnóstica** — o paciente está em tratamento mas ninguém afere PA ou pede exame

Por isso, este pipeline divide o universo de pacientes hipertensos e diabéticos em **11 categorias** de status atual, cada uma representando uma situação clínica distinta. Apenas 4 são consideradas "inércia em sentido amplo" — as outras são situações de cuidado interrompido, controle bom, ou pacientes em manejo apropriado.

---

## Os 11 status — explicados em profundidade

### 🔴 1. `INERCIA_PERSISTENTE` — *"Descontrole confirmado, médico não agiu"*

**O que é:**
Paciente com PA (ou HbA1c) acima da meta na aferição mais recente (em 180d), **com persistência confirmada** do descontrole, e cujo esquema terapêutico foi **mantido** ou **desintensificado**.

A "persistência" pode vir de qualquer um dos 3 cenários:
- **(a)** ≥2 aferições descontroladas nos últimos 180 dias
- **(b)** 1 aferição descontrolada recente + nenhuma anterior no histórico (até 730d) — paciente novo, primeira medida alta, médico viu e não agiu
- **(c)** Aferição descontrolada agora + histórico (180-730d) também descontrolado — descontrole de longa data

**Por que esse critério é o mais rigoroso?**
Captura os casos onde temos evidência clara de **descontrole confirmado** e **não-ação médica documentada**. É a inércia no sentido mais clássico — sem ambiguidade, sem desculpa.

**Exemplo clínico:**
> Maria, 62 anos, hipertensa. Última PA aferida há 30 dias: 158/95 mmHg (meta 140/90). Antes disso, há 200 dias, tinha 162/98 (também acima da meta). Recebeu prescrição há 30 dias **mantendo Losartana 50mg + HCTZ 25mg**, mesmas doses do mês anterior. **Status: INERCIA_PERSISTENTE.**

**Ação esperada:**
Avaliar adesão, descartar causas secundárias, **intensificar tratamento** (aumentar dose, adicionar segunda droga, trocar classe).

**Volumetria no município RJ:** 27.609 hipertensos (2,26%) e 4.610 diabéticos (0,86%).

---

### 🟠 2. `INERCIA_POR_FALTA_DE_TRATAMENTO` — *"Diagnosticado, mas sem prescrição"*

**O que é:**
Paciente diagnosticado com HAS ou DM, **mas sem nenhuma prescrição registrada em 365 dias** no Vitacare ou no episódio assistencial.

**Por que existe essa categoria?**
Esta é a forma de inércia mais comum no município RJ — e é **estrutural**, não médica. Reflete:
- Integração incompleta dos sistemas de saúde (paciente pega receita em farmácia popular, particular, outros municípios)
- Abandono efetivo do seguimento
- Pacientes que sumiram da rede
- Casos raros de manejo não-farmacológico

Independente da causa, o resultado é: **o sistema perde o controle sobre o tratamento desse paciente**.

**Exemplo clínico:**
> Roberto, 65 anos, diagnosticado com HAS em 2019. Última prescrição registrada no Vitacare: há 14 meses. Última PA conhecida: 160/98 mmHg, há 8 meses. **Status: INERCIA_POR_FALTA_DE_TRATAMENTO.**

**Ação esperada:**
**Busca ativa** via agente comunitário — entender por que o paciente sumiu da rede. Reativar seguimento se possível.

**Volumetria no município RJ:** 583.529 hipertensos (47,77%) e 284.150 diabéticos (52,81%).

**⚠️ Esse é o achado mais importante para gestão.** Quase metade dos hipertensos do município está nessa categoria.

---

### 🟠 3. `INERCIA_POR_FALTA_DE_AFERICAO` — *"Sabíamos que estava ruim, ninguém afere"*

**O que é:**
Paciente em tratamento ativo (recebeu prescrição em 365d), **sem aferição de PA em 180 dias**, com PA histórica (180-730d) **conhecida descontrolada**, e cujo esquema foi mantido.

**Por que essa categoria existe?**
Diferente da inércia clássica (que exige aferição recente), esta cobre o caso em que **a última PA conhecida estava ruim**, mas ninguém afere mais. O médico simplesmente renova a receita, mesmo sabendo (ou podendo saber) que o controle estava inadequado.

**Como difere de `TRATAMENTO_SEM_NENHUMA_PA`?**
Aqui o paciente **tem histórico** descontrolado. Em `TRATAMENTO_SEM_NENHUMA_PA`, **nunca foi aferido** em 730d.

**Exemplo clínico:**
> Carlos, 68 anos, em uso de Losartana 50mg. Última PA registrada há 240 dias: 156/94 mmHg (acima da meta). Sem aferições nos últimos 180 dias. Receita renovada há 60 dias, esquema mantido. **Status: INERCIA_POR_FALTA_DE_AFERICAO.**

**Ação esperada:**
**Aferir PA hoje.** Se confirmar descontrole, intensificar imediatamente. Se na meta, manter e reagendar.

**Volumetria no município RJ:** 97.499 hipertensos (7,98%) e 19.320 diabéticos (3,59%).

---

### 🟠 4. `DESCONTROLE_RECENTE_SEM_ACAO` — *"Estava bem, descontrolou agora"*

**O que é:**
Paciente com PA (ou HbA1c) descontrolada **agora** (única medida em 180d), mas histórico (180-730d) **na meta**, e esquema mantido.

**Por que separar da inércia persistente?**
Porque ainda não temos **confirmação** de persistência. O paciente estava bem 7 meses atrás, e agora teve uma medida alta. Pode ser:
- Início de descontrole verdadeiro (próxima medida vai confirmar inércia)
- Aferição pontual ruim (próxima medida vai voltar à meta)
- Médico esperando confirmar antes de mexer no esquema

**Clinicamente é diferente de INERCIA_PERSISTENTE.** Aqui há **dúvida**, e a próxima aferição vai resolvê-la.

**Exemplo clínico:**
> Pedro, 60 anos, hipertenso. PA hoje: 155/92 (descontrolada). Há 250 dias, PA estava 132/82 (na meta). Esquema mantido sem modificações. **Status: DESCONTROLE_RECENTE_SEM_ACAO.**

**Ação esperada:**
**Acompanhar de perto.** Reagendar nova aferição em 4-6 semanas. Se confirmar descontrole na próxima medida → vira inércia. Se voltar à meta → era pontual.

**Volumetria no município RJ:** 7.424 hipertensos (0,61%) e 182 diabéticos (0,03%).

---

### 🟠 5. `TRATAMENTO_SEM_NENHUMA_PA` / `TRATAMENTO_SEM_NENHUMA_HbA1c` — *"Voando cego total"*

**O que é:**
Paciente em tratamento ativo, mas **nenhuma aferição** de PA (ou HbA1c) nos últimos 730 dias. Esquema mantido.

**Por que existe?**
Captura o cenário mais extremo: paciente que recebe receita sistematicamente, mas **nunca foi aferido**. Não temos NENHUM dado sobre o controle.

**Exemplo clínico:**
> José, 70 anos, diabético há 5 anos. Em uso contínuo de Metformina 1g 2x/dia (várias renovações). Nenhuma HbA1c nos últimos 730 dias. **Status: TRATAMENTO_SEM_NENHUMA_HbA1c.**

**Ação esperada:**
**Solicitar exame ou aferição imediatamente.** Sem dado clínico, qualquer decisão é cega.

**Volumetria no município RJ:** 48.752 hipertensos (3,99%) e 137.763 diabéticos (25,60% — **bem alto, refletindo a baixa cobertura de HbA1c**).

---

### 🟢 6. `MANEJO_APROPRIADO` — *"O médico atuou diante do descontrole"*

**O que é:**
Paciente com PA (ou HbA1c) acima da meta, mas em que o médico **intensificou** ou **trocou** o esquema na última consulta.

**Por que essa categoria existe?**
Para **distinguir o médico que age do que não age**. Um paciente continuar descontrolado **apesar** da intervenção médica é diferente de um paciente continuar descontrolado **sem** intervenção médica. O primeiro pode ser:
- Resposta terapêutica lenta
- Não adesão do paciente
- Causa secundária ainda não tratada

Mas **não é inércia do médico** — ele fez sua parte.

**Exemplo clínico:**
> Carlos, 55 anos, hipertenso. Última PA: 152/92. Há 30 dias, médico **aumentou Anlodipino de 5mg para 10mg** e **adicionou Hidroclorotiazida 25mg**. **Status: MANEJO_APROPRIADO.**

**Ação esperada:**
Aguardar 4-6 semanas para reavaliar resposta. Reforçar adesão. Não é caso de alerta.

**Volumetria no município RJ:** 17.200 hipertensos (1,41%) e 3.127 diabéticos (0,58%).

---

### 🟢 7. `CONTROLADO` — *"Tudo bem por aqui"*

**O que é:**
Paciente com PA (ou HbA1c) **na meta ou abaixo** na última aferição em 180d, com consulta recente da linha terapêutica.

**Exemplo:**
> Ana, 70 anos, hipertensa. PA aferida há 45 dias: 138/86 (meta 140/90). Receita renovada há 30 dias. **Status: CONTROLADO.**

**Volumetria no município RJ:** 147.670 hipertensos (12,09%) e 21.738 diabéticos (4,04%).

---

### 🟡 8. `CONTROLADO_COM_LACUNA_CONSULTA` — *"Estava bem, mas sumiu"*

**O que é:**
Paciente cuja **última aferição estava na meta**, mas que **não tem consulta com prescrição há mais de 180 dias**.

Possíveis razões:
- Mudou de endereço, ESF não sabe
- Está usando médico particular ou outra rede
- Suspendeu o tratamento por conta própria
- Pegou receita fora da rede pública

**Exemplo:**
> Antônio, 60 anos. Última PA: 132/82 (controlada). Mas foi aferida há 300 dias, e a última consulta com prescrição também foi há 300 dias. **Status: CONTROLADO_COM_LACUNA_CONSULTA.**

**Ação esperada:**
**Busca ativa.** Não assumir que está tudo bem só porque a última aferição estava boa.

**Volumetria no município RJ:** 50.185 hipertensos (4,11%).

---

### 🟡 9. `TRATAMENTO_RENOVADO_CONTROLADO_ATRASADO` — *"Estava bem, sumiu, esquema renovado"*

**O que é:**
Paciente em tratamento ativo, com PA histórica (180-730d) **na meta**, mas **sem aferição em 180d**, esquema mantido.

**Como difere de `CONTROLADO_COM_LACUNA_CONSULTA`?**
- `CONTROLADO_COM_LACUNA` = sem consulta nova em 180d
- `RENOVADO_CONTROLADO_ATRASADO` = teve consulta nova (com prescrição renovada), mas a aferição não foi feita

**Exemplo:**
> Lucia, 58 anos. Última PA registrada há 250 dias: 130/82 (na meta). Receita renovada há 60 dias, sem aferição na consulta. **Status: TRATAMENTO_RENOVADO_CONTROLADO_ATRASADO.**

**Ação esperada:**
Aferir na próxima oportunidade para confirmar manutenção do controle. Não é urgente.

**Volumetria no município RJ:** 123.349 hipertensos (10,10%) e 66.493 diabéticos (12,36%).

---

### 🟡 10. `DESCONTROLE_SEM_COMPARACAO` — *"Descontrolado, mas paciente novo"*

**O que é:**
Paciente com PA (ou HbA1c) descontrolada, **mas sem prescrição anterior** na janela 90/180d para podermos classificar a ação do médico.

Possíveis cenários:
- **Paciente novo** na ESF
- **Hiato de tratamento** — paciente que não pegou receita por muito tempo
- **Paciente recém-diagnosticado**

**Exemplo:**
> João, 50 anos, recém-diagnosticado com HAS. PA hoje: 165/100. Recebeu primeira prescrição. Não havia prescrição anterior em 180d. **Status: DESCONTROLE_SEM_COMPARACAO.**

**Ação esperada:**
Acompanhamento padrão de paciente iniciando tratamento — reavaliar em 4-6 semanas. Não é alerta de inércia.

**Volumetria no município RJ:** 107.497 hipertensos (8,80%) e 13.824 diabéticos (2,57%).

---

### ⚪ 11. `OUTRO` — *"Casos residuais"*

Casos que não se encaixam em nenhuma das categorias acima. Devem ser raros (~1%). Tipicamente:
- `status_acao = NAO_AVALIAVEL` ou `MISTO` em combinações específicas
- Casos de borda com dados incompletos

**Volumetria no município RJ:** 10.699 hipertensos (0,88%).

Se essa categoria crescer muito numa rodada, é sinal de que precisamos investigar e ajustar a cascata.

---

## Tabela resumo: o que cada categoria diz, e o que fazer

| Status | Paciente | Ação esperada | Prioridade |
|---|---|---|---|
| 🔴 INERCIA_PERSISTENTE | Descontrole confirmado + esquema mantido | **Intensificar** | Alta |
| 🟠 INERCIA_POR_FALTA_DE_TRATAMENTO | Diagnosticado sem prescrição registrada | **Busca ativa** | Alta (em volume) |
| 🟠 INERCIA_POR_FALTA_DE_AFERICAO | Histórico ruim + sem aferir + mantido | **Aferir hoje** | Alta |
| 🟠 DESCONTROLE_RECENTE_SEM_ACAO | Estava bem, descontrolou, mantido | **Reagendar aferição em 4-6 sem.** | Média |
| 🟠 TRATAMENTO_SEM_NENHUMA_PA / HbA1c | Em tratamento, nunca aferido | **Aferir / Solicitar exame** | Alta |
| 🟡 TRATAMENTO_RENOVADO_CONTROLADO_ATRASADO | Estava bem, sumiu | **Aferir na próxima** | Baixa |
| 🟢 MANEJO_APROPRIADO | Descontrolado, médico agiu | Aguardar resposta | Mínima |
| 🟢 CONTROLADO | Na meta, seguimento regular | Manter | Mínima |
| 🟡 CONTROLADO_COM_LACUNA_CONSULTA | Na meta, mas sumiu | **Busca ativa** | Média |
| 🟡 DESCONTROLE_SEM_COMPARACAO | Descontrolado, paciente novo/hiato | Reagendar 4-6 sem. | Média |
| ⚪ OUTRO | Residual | Investigar | Baixa |

---

## Padrão de manejo — visão de TRAJETÓRIA (365 dias)

Enquanto o **status atual** é um snapshot da última consulta, o **padrão de manejo** olha o conjunto de **todas as consultas** do paciente nos últimos 365 dias.

A diferença é importante: um paciente pode ter **uma consulta** de inércia e várias de manejo apropriado — não é justo classificá-lo só pela última. O padrão captura **a tendência** do cuidado ao longo do ano.

| Categoria | Definição | Significado clínico |
|---|---|---|
| **PROATIVO** | ≥50% das consultas com descontrole tiveram intensificação ou troca | O médico/equipe age consistentemente diante do descontrole |
| **INERTE** | ≥50% das consultas com descontrole tiveram inércia persistente | Padrão sistemático de não agir diante do descontrole |
| **ESTAGNADO** | ≥50% das consultas foram em paciente sem aferição/exame, com tratamento mantido | Paciente vem renovar receita sem que ninguém afira |
| **CONTROLADO** | ≥50% das consultas com paciente na meta | Seguimento estável e eficaz |
| **MISTO** | Combinações que não atingem 50% em nenhuma categoria | Trajetória heterogênea — sem padrão dominante |
| **MENOS_DE_2_CONSULTAS** | <2 consultas em 365 dias | Sem trajetória avaliável |

**Exemplo de utilidade clínica:**
Um paciente classificado como `INERTE` na trajetória de 365d **precisa de revisão completa** do plano terapêutico, mesmo que a última consulta tenha sido de manejo apropriado. O problema é **recorrente**, não pontual.

---

## A grande narrativa do município

### O iceberg da inércia no RJ

Olhando os hipertensos do município (n=1.221.413):

```
┌─────────────────────────────────────────────────┐
│   INÉRCIA "VISÍVEL" (acima da linha d'água)    │
│   Inércia persistente: 2,26%                    │
│   = a inércia clássica, do médico               │
└─────────────────────────────────────────────────┘
            ↓ ↓ ↓ ABAIXO DA LINHA D'ÁGUA ↓ ↓ ↓
┌─────────────────────────────────────────────────┐
│   INÉRCIA "INVISÍVEL" (estrutural)             │
│   Falta de tratamento:  47,77%                  │
│   Falta de aferição:     7,98%                  │
│   Sem nenhuma PA:        3,99%                  │
│                                                  │
│   = problemas de SISTEMA, não de MÉDICO         │
└─────────────────────────────────────────────────┘
```

**Total de pacientes em alguma forma de inércia: 58% dos hipertensos do município.**

### Insight chave para gestão

A narrativa não deve ser:
> ~~"Precisamos treinar médicos a não ficar inertes"~~

A narrativa deve ser:
> *"Precisamos estruturar o cuidado para que (1) pacientes em tratamento sejam regularmente aferidos, (2) pacientes diagnosticados não saiam da rede sem detecção, (3) consultas com PA descontrolada gerem ação documentada."*

A inércia médica clássica (2,26%) é importante, mas é a **última peça do quebra-cabeça**. Antes dela, há um problema sistêmico de **continuidade e coleta de dados** que afeta 6 em cada 10 hipertensos.

---

## Como usar tudo isso no Streamlit

### 3 perguntas que o painel deve responder

**1. "Quem precisa de mim agora?"** — *Card "Meus Pacientes"*

Filtre pelo `status_atual_*`:
- `INERCIA_PERSISTENTE` → "Pacientes em inércia (alta prioridade)"
- `INERCIA_POR_FALTA_DE_AFERICAO` → "Pacientes sem exame, com histórico ruim"
- `DESCONTROLE_RECENTE_SEM_ACAO` → "Pacientes que descontrolaram agora"
- `INERCIA_POR_FALTA_DE_TRATAMENTO` → "Pacientes sumidos do tratamento"
- `CONTROLADO_COM_LACUNA_CONSULTA` → "Pacientes para busca ativa"
- `TRATAMENTO_SEM_NENHUMA_PA` → "Pacientes que nunca foram aferidos"

Use o `texto_meus_pacientes_HAS` e `texto_meus_pacientes_DM` — vêm prontos para exibir.

**2. "Como minha equipe se compara com outras?"** — *Painel da clínica/ESF*

Use os agregados de `MM_consultas_agregado`:
- Taxa de inércia persistente = `n_inercia_persistente_HAS / n_HAS_tratados`
- Taxa de inércia por falta de aferição = `n_inercia_falta_aferi_HAS / n_HAS_tratados`
- Taxa de inércia por falta de tratamento = `n_inercia_falta_tratamento_HAS / n_pacientes_HAS` (denominador diferente!)
- Comparar com mediana das clínicas (município) e mediana das clínicas da AP

**3. "Esse paciente em particular — qual é a história?"** — *Detalhe individual*

Use os contadores de trajetória (`n_consultas_*`) para mostrar:
- "Nos últimos 12 meses, este paciente teve 8 consultas. Em 5 estava descontrolado; em 1 o esquema foi intensificado, em 4 foi mantido."

---

## Hierarquia de prioridade clínica (sugestão para o dashboard)

Quando precisar **priorizar** quais pacientes mostrar primeiro:

1. **INERCIA_PERSISTENTE** (vermelho) — ação clínica direta, evidência clara
2. **INERCIA_POR_FALTA_DE_AFERICAO** (laranja) — histórico ruim, ninguém afere
3. **TRATAMENTO_SEM_NENHUMA_PA** (laranja) — voando cego total
4. **DESCONTROLE_RECENTE_SEM_ACAO** (laranja) — descontrole novo
5. **INERCIA_POR_FALTA_DE_TRATAMENTO** (laranja) — fora do tratamento
6. **CONTROLADO_COM_LACUNA_CONSULTA** (amarelo) — busca ativa
7. **DESCONTROLE_SEM_COMPARACAO** (amarelo) — paciente novo
8. **TRATAMENTO_RENOVADO_CONTROLADO_ATRASADO** (amarelo) — sumiu mas estava bem
9. **MANEJO_APROPRIADO** (verde) — informativo, sem alerta
10. **CONTROLADO** (verde) — paciente estável

---

## Glossário rápido

| Termo | Definição |
|---|---|
| **Inércia clássica** | Não agir diante de evidência de descontrole |
| **Inércia estrutural** | Falha do sistema (sem prescrição registrada, sem aferição) |
| **Persistência (HAS)** | (a) ≥2 medidas em 180d, OU (b) 1 medida + sem histórico, OU (c) histórico (180-730d) também descontrolado |
| **Persistência (DM)** | Análogo, com janela histórica 181-365d |
| **Meta de PA** | 130/80 (DM+HAS), 150/x (≥80 anos), 140/90 (geral) |
| **Meta de HbA1c** | 7,0% (<60a), 7,5% (60-69a), 8,0% (≥70a) |
| **Tratamento ativo** | ≥1 prescrição da linha em 365d |
| **Janela curta (90d)** | Análise consulta atual vs. anterior |
| **Janela longa (180d)** | Análise da trajetória sobre prescrições |
| **Janela histórica HAS** | 181-730 dias atrás |
| **Janela histórica DM** | 181-365 dias atrás (HbA1c é colhida menos) |
| **Intensificou** | Aumentou dose (≥20% orais, ≥10% NPH) OU adicionou nova droga |
| **Trocou** | Tirou ao menos uma droga e adicionou ao menos outra |
| **Desintensificou** | Reduziu dose ou retirou droga, sem adicionar nada |
| **Mantido** | Mesmas drogas, mesmas doses (dentro dos limiares) |
| **Sem comparação** | Não havia prescrição anterior na janela para comparar |
