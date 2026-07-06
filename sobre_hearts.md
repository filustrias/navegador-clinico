### Sobre o HEARTS

O **HEARTS** é a estratégia técnica da OMS/OPAS para prevenção e manejo das
doenças cardiovasculares na atenção primária, adotada pelo Ministério da Saúde
brasileiro. O eixo **R** ("Risk-based management") organiza a conduta a partir
do **risco cardiovascular global em 10 anos**, e não de fatores isolados.

#### O escore de risco

A calculadora usa as **cartas de risco da OMS 2019** (Kaptoge et al., *Lancet
Global Health* 2019), na calibração para a **América Latina tropical**
(`tropical_latin_america`, que inclui o Brasil). O modelo estima a
probabilidade de um evento cardiovascular (infarto ou AVC) nos próximos 10 anos.

Há **duas versões** do escore, aplicadas em cascata:

- **Versão laboratorial** — usada quando há **colesterol total**. Combina sexo,
  idade, tabagismo, diabetes, PA sistólica e colesterol.
- **Versão não-laboratorial** — usada quando **não há colesterol**. Substitui o
  colesterol pelo **IMC**, permitindo estimar o risco mesmo sem exames de sangue.

#### Reclassificação direta

Alguns pacientes já são de alto risco independentemente do escore e, por isso,
são classificados **diretamente**, sem cálculo:

- **Doença cardiovascular estabelecida** (cardiopatia isquêmica, AVC prévio ou
  doença arterial periférica) → **Muito alto**.
- **Diabetes ou doença renal crônica** → **Alto**.

> A regra de reclassificação por diabetes/DRC usada aqui é uma simplificação. O
> PCDT de Hipertensão qualifica esses critérios (DRC por estágio, diabetes por
> idade e lesão de órgão-alvo) — o refinamento clínico está em avaliação.

#### Faixas de risco

| Risco em 10 anos | Categoria |
|---|---|
| < 5% | Baixo |
| 5–10% | Moderado |
| 10–20% | Alto |
| 20–30% | Muito alto |
| ≥ 30% | Crítico |

O risco é um apoio à **decisão compartilhada** entre profissional e paciente —
não substitui o julgamento clínico nem a avaliação individual.
