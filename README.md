# Navegador Clínico - Multimorbidade SMS-RJ

Dashboard interativo para análise de multimorbidade e qualidade do cuidado na Atenção Primária à Saúde do município do Rio de Janeiro.

## 🚀 Instalação

### Pré-requisitos
- Python 3.9 ou superior
- Conta no Google Cloud Platform com acesso ao BigQuery
- Credenciais do BigQuery configuradas

### Configuração

1. Clone o repositório:
```bash
git clone [URL_DO_SEU_REPOSITORIO]
cd navegador_clinico
```

2. Crie e ative o ambiente virtual:
```bash
# Windows
python -m venv venv
venv\Scripts\activate

# Linux/Mac
python -m venv venv
source venv/bin/activate
```

3. Instale as dependências:
```bash
pip install -r requirements.txt
```

4. Configure as credenciais do BigQuery:
   - Coloque seu arquivo de credenciais JSON na raiz do projeto
   - Configure a variável de ambiente (ou autentique via gcloud CLI)

## 🎯 Execução
```bash
streamlit run Home.py
```

O dashboard abrirá automaticamente no navegador em `http://localhost:8501`

## 📊 Estrutura do Projeto
```
navegador_clinico/
├── Home.py                          # Página inicial
├── pages/                           # Páginas do dashboard
│   ├── 2_👥_Minha_Populacao.py
│   ├── 3_🔍_Meus_Pacientes.py
│   ├── 4_🏥_Morbidades_Especificas.py
│   ├── 5_💊_Polifarmacia_STOPP_START.py
│   ├── 6_⚠️_Lacunas_de_Cuidado.py
│   ├── 7_📊_Qualidade_e_Benchmarks.py
│   └── 8_📚_Pilulas_Conhecimento.py
├── components/                      # Componentes reutilizáveis
├── utils/                          # Utilitários e queries
├── assets/                         # Imagens e estilos
└── config.py                       # Configurações do projeto
```

## 🏥 Funcionalidades

- **Visão Populacional**: Pirâmides etárias estratificadas por multimorbidade
- **Gestão de Pacientes**: Cards individuais com informações clínicas detalhadas
- **Análise de Morbidades**: Foco em condições específicas
- **Polifarmácia**: Identificação de critérios STOPP-START
- **Lacunas de Cuidado**: Monitoramento de indicadores de qualidade
- **Benchmarks**: Comparações entre equipes e territórios
- **Base de Conhecimento**: Pílulas educativas sobre manejo clínico

## 👥 Perfis de Usuário

- **Gestor Municipal/Distrital**: Visão completa de todos os territórios
- **Gestor de Clínica**: Dados da sua unidade
- **Equipe ESF**: Informações da sua população adscrita

## 📝 Licença

SMS-RJ - Secretaria Municipal de Saúde do Rio de Janeiro

## 👨‍💻 Desenvolvedores

Desenvolvido para a Subsecretaria de Promoção, Atenção Primária e Vigilância em Saúde (SUBPAV)