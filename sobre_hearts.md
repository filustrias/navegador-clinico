# Sobre a calculadora de risco cardiovascular HEARTS (OMS/OPAS)

## O que é o HEARTS

O **HEARTS** é um pacote técnico da Organização Mundial da Saúde (OMS) para o manejo do risco cardiovascular na **atenção primária à saúde (APS)**. O pacote completo tem seis módulos (H-E-A-R-T-S) mais um guia de implementação; o que trata da estratificação de risco é o módulo **"Risk-based CVD management"** (HEARTS-R, OMS, 2020, ISBN 978-92-4-000136-7). Nas Américas, é conduzido pela **Organização Pan-Americana da Saúde (OPAS)** sob a iniciativa **HEARTS in the Americas**, com foco na padronização da medida da pressão arterial, no uso racional de medicamentos e na estratificação do risco cardiovascular (RCV) por uma calculadora simples e aplicável em larga escala.

No Brasil, essa é a ferramenta de estratificação de RCV adotada pelo **PCDT de Hipertensão Arterial Sistêmica** (Portaria SECTICS/MS nº 49, de 23/07/2025).

## As cartas de risco da OMS (2019) e a calculadora

A calculadora se baseia nas **cartas de risco cardiovascular revisadas da OMS de 2019**, publicadas por Kaptoge et al. (*Lancet Global Health*), que estimam a **incidência em 10 anos de evento cardiovascular fatal ou não fatal** (infarto do miocárdio, AVC ou morte por causa cardiovascular). Os modelos originais foram derivados de 85 estudos de coorte prospectivos (Emerging Risk Factors Collaboration) e recalibrados usando incidência e fatores de risco específicos por idade/sexo do GBD Study e do NCD-RisC, com validação externa em 19 coortes adicionais. Os modelos foram recalibrados para **21 regiões globais** (grupos GBD); a OPAS transformou essas cartas em calculadora eletrônica (app e web), ajustando a estimativa para **seis sub-regiões das Américas**.

O Brasil está na região **Tropical Latin America** (`tropical_latin_america`, junto com o Paraguai), que é o parâmetro de calibração que a aplicação utiliza.

## Como o escore é calculado

A calculadora opera com **dois modelos em cascata**:

- **Versão laboratorial (prioritária):** usa sexo, idade, tabagismo, diabetes (presença/ausência), **pressão arterial sistólica (PAS)** e **colesterol total**.
- **Versão não laboratorial (alternativa):** usa sexo, idade, tabagismo, PAS e **IMC** (peso e altura) no lugar de colesterol/diabetes — dispensa exame de sangue.

Essa arquitetura em cascata é o principal ganho operacional para a APS: **a ausência de colesterol não impede a estratificação**, embora a versão laboratorial seja mais precisa e deva ser preferida quando o dado estiver disponível. Segundo o próprio documento da OMS, em amostras populacionais há concordância apenas moderada entre as duas versões: dos indivíduos classificados em >20% de risco pela versão laboratorial, ~97% também eram identificados em >10% pela não laboratorial — mas no limiar de 20%, só ~65% dos homens e ~35% das mulheres coincidiam entre as duas versões, principalmente porque a versão não laboratorial **subestima substancialmente o risco em pessoas com diabetes**.

- **Desfecho estimado:** risco em 10 anos de evento cardiovascular fatal ou não fatal (IAM ou AVC).
- **Faixa etária de aplicação de rotina:** 40 a 74 anos (conforme as cartas fornecidas). Fora dessa faixa, recomenda-se usar ferramentas apropriadas à idade e atentar para condições que já indicam alto risco.
- **Uso recomendado da calculadora:** indicado para maiores de 40 anos, tabagistas, obesos, pessoas com HAS ou DM conhecidas, e pessoas com histórico familiar (1º grau) de DCV precoce ou de DM/doença renal.

## Categorias de risco (cartas) e conduta terapêutica

O documento da OMS usa duas granularidades diferentes para dois propósitos diferentes, e vale entender por que elas não coincidem antes de olhar os números. As **cartas de risco** (Anexos 2 e 3 do módulo *Risk-based CVD management*, que são as tabelas coloridas por idade/sexo/tabagismo/PA/colesterol ou IMC) classificam o resultado em **5 faixas coloridas**, porque essa granularidade é útil para comunicação visual rápida na consulta e para comparação entre pacientes. Já a **orientação de manejo clínico** que acompanha essas cartas — construída a partir de um protocolo anterior da OMS, o *WHO Package of Essential NCD interventions* (Protocolo 1), e apenas adaptada no documento de 2020 para refletir os novos limiares de risco — usa **3 faixas mais largas**, porque a decisão terapêutica (iniciar anti-hipertensivo, iniciar estatina, intervalo de reavaliação) não muda a cada 10 pontos percentuais de risco, mas sim em patamares mais amplos. Ou seja: a calculadora informa o risco em 5 faixas, mas a conduta recomendada pela própria OMS é decidida em apenas 3 patamares — isso não é uma inconsistência da ferramenta, é assim que o documento original já separa as duas coisas.

### Faixas de risco nas cartas (5 bandas, com cor)

| Risco em 10 anos | Cor | Categoria |
|---|---|---|
| < 5% | Verde | Baixo |
| 5–<10% | Amarelo | Moderado |
| 10–<20% | Laranja | Alto |
| 20–<30% | Vermelho | Muito alto |
| ≥ 30% | Vermelho-escuro | Crítico |

No Protocolo Clínico e Diretrizes Terapêuticas da Hipertensão Arterial Sistêmica, publicado pelo Ministério da Saúde do Brasil, a categoria **crítico** segue as mesmas condutas da categoria **muito alto** — ou seja, na prática brasileira as 5 faixas acabam se comportando como 4 patamares de conduta.

### Conduta proposta pela WHO HEARTS

Esta é a orientação de manejo que a própria Organização Mundial da Saúde publica junto com as cartas de risco, no documento *HEARTS technical package for cardiovascular disease management in primary health care: risk-based CVD management* (2020). Ela é organizada em três patamares de risco, cada um com uma combinação diferente de intensidade de aconselhamento, limiar para início de fármacos e intervalo de reavaliação:

**Risco < 10%**
Aconselhar sobre dieta, atividade física, cessação do tabagismo e sobre evitar o uso nocivo de álcool — para todos os pacientes desta faixa, independentemente do valor exato. Dentro dela, o intervalo de reavaliação já muda: se o risco for menor que 5%, a reavaliação pode ser em 12 meses; se estiver entre 5% e 10%, a reavaliação deve ser a cada 3 meses até que as metas de estilo de vida e pressão arterial sejam atingidas, passando então para intervalos de 6 a 9 meses. Não há indicação de estatina motivada pelo risco cardiovascular nesta faixa.

**Risco entre 10% e 20%**
Mantém o mesmo aconselhamento de estilo de vida da faixa anterior. Se a pressão arterial permanecer persistentemente igual ou acima de 140/90 mmHg, deve-se considerar o início de fármacos anti-hipertensivos. A reavaliação passa a ser mais frequente, a cada 3 a 6 meses. É importante notar que, segundo o documento da OMS, **não há recomendação de estatina de rotina nesta faixa** — isso é diferente do que constava em uma versão anterior deste resumo, que havia especulado (sem fonte primária confirmada) que a estatina já seria "considerada" nesse patamar.

**Risco acima de 20%**
Mesmo aconselhamento de estilo de vida. O limiar para considerar fármacos anti-hipertensivos cai para uma pressão arterial persistentemente igual ou acima de 130/80 mmHg. É nesta faixa, e só nela, que o documento recomenda **iniciar estatina**. A reavaliação deve ser a cada 3 meses; se não houver redução mensurável do risco cardiovascular após 6 meses de acompanhamento, o paciente deve ser encaminhado a um nível de atenção mais especializado.

### Situações que já indicam tratamento farmacológico, independentemente do risco calculado

Além dos três patamares acima, o mesmo trecho do documento da OMS lista um conjunto de situações clínicas que justificam considerar tratamento farmacológico por si só, sem precisar esperar o resultado do escore:

- Pacientes com diabetes mellitus estabelecido **e** doença cardiovascular já manifesta (doença coronariana, infarto prévio, ataque isquêmico transitório, doença cerebrovascular ou doença arterial periférica) ou doença renal — se já estiverem estáveis em tratamento, devem continuar o esquema já prescrito e ser tratados, para fins de conduta, como se estivessem na faixa de risco acima de 20%.
- Pessoas com albuminúria, retinopatia ou hipertrofia ventricular esquerda.
- Qualquer pessoa com pressão arterial persistentemente igual ou acima de 160/100 mmHg.
- Qualquer pessoa com colesterol total igual ou acima de 8 mmol/L (320 mg/dL).

Para o manejo detalhado de hipertensão e de diabetes mellitus tipo 2 propriamente ditos — doses, escalonamento terapêutico, metas específicas — o próprio documento não entra nesses detalhes e remete a dois outros módulos do mesmo pacote técnico da OMS: o módulo de protocolos de tratamento baseados em evidência (que padroniza o manejo clínico da hipertensão) e o módulo específico de diagnóstico e manejo do diabetes. Esses dois módulos não fizeram parte do PDF consultado aqui.

> **Nota:** o módulo consultado não menciona uso de antiplaquetários (ácido acetilsalicílico) para prevenção primária. Uma afirmação de uma versão anterior deste resumo — de que "o AAS não é recomendado em nenhuma faixa de risco na prevenção primária" — não pôde ser confirmada nesta fonte primária e foi removida até que se verifique isso em outro módulo do pacote HEARTS (provavelmente o módulo de protocolos de tratamento baseados em evidência, mencionado acima).

## Reclassificação direta (condições que dispensam o escore)

Alguns perfis já entram como risco elevado **por definição**, independentemente do resultado numérico:

- **Doença cardiovascular estabelecida** (cardiopatia isquêmica/IAM, AVC prévio, doença arterial periférica) → **muito alto** / tratada como risco >20% pela Tabela 3 da OMS.
- Condições consideradas de alto risco pelo PCDT brasileiro: **DRC estágio ≥ 3**, **LDL ≥ 190 mg/dL**, **diabetes em pessoa com ≥ 40 anos**, e HAS com lesão de órgão-alvo.

> **Nota de implementação:** a regra simplificada "qualquer DM ou DRC → alto" usada na aplicação é uma aproximação. Convém alinhá-la ao critério do PCDT (que qualifica DRC por estágio e DM por idade) e também à regra da OMS (DM + DCV/doença renal estável → tratar como >20%) antes de usá-la em produção, para evitar reclassificação excessiva ou insuficiente.

## Por que HEARTS no Brasil (e no PCDT)

O escore de **Framingham**, historicamente recomendado pelas diretrizes brasileiras, foi construído em uma população específica dos EUA e tende a **superestimar** o risco quando aplicado à população brasileira. Fontes de síntese clínica nacional apontam a calculadora **HEARTS OMS/OPAS como a de melhor acurácia para a população brasileira, com menor superestimativa** do que Framingham e do que os escores das sociedades norte-americana (ACC/AHA) e europeia (ESC), com base em dados prospectivos brasileiros. Estudos em APS (por exemplo, o projeto CardioRisco, em Minas Gerais) mostram que o Framingham classifica proporção substancialmente maior de pacientes em estratos muito alto/crítico do que a HEARTS na versão não laboratorial.

Na prática, a adoção da HEARTS pelo PCDT tende a **reduzir sobretratamento** por superestimação e a **viabilizar a estratificação na APS** mesmo sem exames laboratoriais.

## Limitações e cuidados (segundo a própria OMS)

- A calculadora estima risco populacional; não substitui o julgamento clínico nem contempla todas as condições de alto risco (ex.: hipercolesterolemia familiar, doenças autoimunes, HIV).
- O principal gargalo reconhecido não é a ferramenta, e sim a **implementação e capacitação profissional** na APS.
- A versão não laboratorial é conveniente, mas menos precisa — especialmente em pessoas com diabetes, cujo risco tende a ser subestimado por essa versão.
- Países podem definir limiares diferentes de início de tratamento conforme a distribuição de risco de sua população (Anexo 7 do documento da OMS mostra grande variação entre países — ex.: <5% da população de Uganda está acima de 10% de risco, contra ~50% no Egito).

## Links úteis

- Calculadora de risco cardiovascular HEARTS (OPAS/OMS): https://www.paho.org/en/hearts-americas/cardiovascular-risk-calculator-app
- HEARTS in the Americas (OPAS): https://www.paho.org/en/hearts-americas
- PCDT HAS (versão integral, Portaria SECTICS/MS nº 49/2025): https://www.gov.br/conitec/pt-br/midias/protocolos/pcdt-hipertensao-arterial-sistemica.pdf
- Cartas de risco por região (download OMS): https://www.who.int/news-room/detail/02-09-2019-who-updates-cardiovascular-risk-charts

## Referências

1. Kaptoge S, Pennells L, De Bacquer D, et al. World Health Organization cardiovascular disease risk charts: revised models to estimate risk in 21 global regions. *Lancet Glob Health*. 2019;7(10):e1332–e1345. doi:10.1016/S2214-109X(19)30318-3.
2. World Health Organization. *HEARTS technical package for cardiovascular disease management in primary health care: risk-based CVD management*. Geneva: WHO; 2020. ISBN 978-92-4-000136-7 (electronic).
3. Organização Pan-Americana da Saúde. *HEARTS in the Americas — Cardiovascular Risk Calculator App*. Washington: OPAS; 2023.
4. Brasil. Ministério da Saúde. Secretaria de Ciência, Tecnologia, Inovação e Complexo Econômico-Industrial da Saúde. *Portaria SECTICS/MS nº 49, de 23 de julho de 2025 — Protocolo Clínico e Diretrizes Terapêuticas da Hipertensão Arterial Sistêmica*. Brasília: MS; 2025.
5. GBD 2021 Risk Factors Collaborators. Global burden of 87 risk factors in 204 countries and territories, 1990–2021. *Lancet*. 2023;402(10397):2160–2248.
6. D'Agostino RB, Vasan RS, Pencina MJ, et al. General cardiovascular risk profile for use in primary care: the Framingham Heart Study. *Circulation*. 2008;117(6):743–753.
7. *Análise comparativa das ferramentas de estratificação de risco cardiovascular na APS (projeto CardioRisco)*. SciELO Preprints. doi:10.1590/SciELOPreprints.9190.
8. Artmed. *Calculadoras de risco cardiovascular: para que e qual utilizar*.

---

*As condutas por categoria de risco têm caráter orientador (Tabela 3 do documento HEARTS-R da OMS, adaptada do WHO PEN Protocol 1) e devem ser interpretadas em conjunto com o PCDT HAS vigente e o julgamento clínico. Documento atualizado após acesso ao PDF oficial da OMS (2020); a versão anterior continha uma especulação sobre 5 bandas de conduta terapêutica que foi corrigida para 3 bandas, conforme a fonte primária.*
