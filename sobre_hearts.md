# Sobre a calculadora de risco cardiovascular HEARTS (OMS/OPAS)

## O que é o HEARTS

O **HEARTS** é um pacote técnico da Organização Mundial da Saúde (OMS) para o manejo do risco cardiovascular na **atenção primária à saúde (APS)**. Nas Américas, é conduzido pela **Organização Pan-Americana da Saúde (OPAS)** sob a iniciativa **HEARTS in the Americas**, com foco na padronização da medida da pressão arterial, no uso racional de medicamentos e na estratificação do risco cardiovascular (RCV) por uma calculadora simples e aplicável em larga escala.

No Brasil, essa é a ferramenta de estratificação de RCV adotada pelo **PCDT de Hipertensão Arterial Sistêmica** (Portaria SECTICS/MS nº 49, de 23/07/2025).

## As cartas de risco da OMS (2019) e a calculadora

A calculadora se baseia nas **cartas de risco cardiovascular revisadas da OMS de 2019**, publicadas por Kaptoge et al. (*Lancet Global Health*), que estimam a **incidência em 10 anos de evento cardiovascular fatal ou não fatal** (infarto do miocárdio, AVC ou morte por causa cardiovascular). Os modelos foram recalibrados para **21 regiões globais**; a OPAS transformou essas cartas em calculadora eletrônica (app e web), ajustando a estimativa para **seis sub-regiões das Américas**.

O Brasil está na região **Tropical Latin America** (`tropical_latin_america`), que é o parâmetro de calibração que a aplicação utiliza.

## Como o escore é calculado

A calculadora opera com **dois modelos em cascata**:

- **Versão laboratorial (prioritária):** usa sexo, idade, tabagismo, diabetes, **pressão arterial sistólica (PAS)** e **colesterol total**.
- **Versão não laboratorial (alternativa):** usa sexo, idade, tabagismo, PAS e **IMC** (peso e altura) no lugar do colesterol — dispensa exame de sangue.

Essa arquitetura em cascata é o principal ganho operacional para a APS: **a ausência de colesterol não impede a estratificação**, embora a versão laboratorial seja mais precisa e deva ser preferida quando o dado estiver disponível.

- **Desfecho estimado:** risco em 10 anos de evento cardiovascular fatal ou não fatal.
- **Faixa etária de aplicação de rotina:** 40 a 74 anos. Fora dessa faixa (≤ 39 e ≥ 75 anos), recomenda-se usar ferramentas apropriadas à idade e atentar para condições que já indicam alto risco.

## Categorias de risco e conduta

| Risco em 10 anos | Categoria | Conduta orientadora |
|---|---|---|
| < 5% | Baixo | Mudança de estilo de vida |
| 5–10% | Moderado | Reforçar MEV; considerar farmacoterapia |
| 10–20% | Alto | Tratamento farmacológico indicado |
| 20–30% | Muito alto | Tratamento intensivo |
| ≥ 30% | Crítico | Prioridade máxima; avaliar DCV estabelecida |

No PCDT, a categoria **crítico** segue as mesmas condutas do **muito alto**.

## Reclassificação direta (condições que dispensam o escore)

Alguns perfis já entram como risco elevado **por definição**, independentemente do resultado numérico:

- **Doença cardiovascular estabelecida** (cardiopatia isquêmica/IAM, AVC prévio, doença arterial periférica) → **muito alto**.
- Condições consideradas de alto risco pelo PCDT: **DRC estágio ≥ 3**, **LDL ≥ 190 mg/dL**, **diabetes em pessoa com ≥ 40 anos**, e HAS com lesão de órgão-alvo.

> **Nota de implementação:** a regra simplificada "qualquer DM ou DRC → alto" usada na aplicação é uma aproximação. Convém alinhá-la ao critério do PCDT (que qualifica DRC por estágio e DM por idade) antes de usá-la em produção, para evitar reclassificação excessiva.

## Por que HEARTS no Brasil (e no PCDT)

O escore de **Framingham**, historicamente recomendado pelas diretrizes brasileiras, foi construído em uma população específica dos EUA e tende a **superestimar** o risco quando aplicado à população brasileira. Fontes de síntese clínica nacional apontam a calculadora **HEARTS OMS/OPAS como a de melhor acurácia para a população brasileira, com menor superestimativa** do que Framingham e do que os escores das sociedades norte-americana (ACC/AHA) e europeia (ESC), com base em dados prospectivos brasileiros. Estudos em APS (por exemplo, o projeto CardioRisco, em Minas Gerais) mostram que o Framingham classifica proporção substancialmente maior de pacientes em estratos muito alto/crítico do que a HEARTS na versão não laboratorial.

Na prática, a adoção da HEARTS pelo PCDT tende a **reduzir sobretratamento** por superestimação e a **viabilizar a estratificação na APS** mesmo sem exames laboratoriais.

## Limitações e cuidados

- A calculadora estima risco populacional; não substitui o julgamento clínico nem contempla todas as condições de alto risco (ex.: hipercolesterolemia familiar, doenças autoimunes, HIV).
- O principal gargalo reconhecido não é a ferramenta, e sim a **implementação e capacitação profissional** na APS.
- A versão não laboratorial é conveniente, mas menos precisa; prefira a laboratorial quando houver colesterol.

## Links úteis

- Calculadora de risco cardiovascular HEARTS (OPAS/OMS): https://www.paho.org/en/hearts-americas/cardiovascular-risk-calculator-app
- HEARTS in the Americas (OPAS): https://www.paho.org/en/hearts-americas
- PCDT HAS (versão integral, Portaria SECTICS/MS nº 49/2025): https://www.gov.br/conitec/pt-br/midias/protocolos/pcdt-hipertensao-arterial-sistemica.pdf

## Referências

1. Kaptoge S, Pennells L, De Bacquer D, et al. World Health Organization cardiovascular disease risk charts: revised models to estimate risk in 21 global regions. *Lancet Glob Health*. 2019;7(10):e1332–e1345. doi:10.1016/S2214-109X(19)30318-3.
2. Organização Pan-Americana da Saúde. *HEARTS in the Americas — Cardiovascular Risk Calculator App*. Washington: OPAS; 2023. Disponível em: https://www.paho.org/en/hearts-americas/cardiovascular-risk-calculator-app
3. Brasil. Ministério da Saúde. Secretaria de Ciência, Tecnologia, Inovação e Complexo Econômico-Industrial da Saúde. *Portaria SECTICS/MS nº 49, de 23 de julho de 2025 — Protocolo Clínico e Diretrizes Terapêuticas da Hipertensão Arterial Sistêmica*. Brasília: MS; 2025. Disponível em: https://www.gov.br/conitec/pt-br/midias/protocolos/pcdt-hipertensao-arterial-sistemica.pdf
4. GBD 2021 Risk Factors Collaborators. Global burden of 87 risk factors in 204 countries and territories, 1990–2021: a systematic analysis for the Global Burden of Disease Study 2021. *Lancet*. 2023;402(10397):2160–2248.
5. D'Agostino RB, Vasan RS, Pencina MJ, et al. General cardiovascular risk profile for use in primary care: the Framingham Heart Study. *Circulation*. 2008;117(6):743–753.
6. *Análise comparativa das ferramentas de estratificação de risco cardiovascular na APS (projeto CardioRisco)*. SciELO Preprints. doi:10.1590/SciELOPreprints.9190.
7. Artmed. *Calculadoras de risco cardiovascular: para que e qual utilizar*. Disponível em: https://artmed.com.br/artigos/calculadoras-de-risco-cardiovascular-para-que-e-qual-utilizar

---

*As condutas por categoria de risco têm caráter orientador e devem ser interpretadas em conjunto com o PCDT HAS vigente e o julgamento clínico.*
