# utils/anonimizador.py
"""
Sistema de Anonimização para Testes
- Áreas Programáticas → Continentes
- Clínicas → Deuses Mitológicos
- ESF → Bandas de Rock
- Pacientes → Nomes Chineses
"""

import hashlib
import os

# ═══════════════════════════════════════════════════════════════
# ✅ TOGGLE PRINCIPAL - CONTROLADO POR VARIÁVEL DE AMBIENTE
# ═══════════════════════════════════════════════════════════════
MODO_ANONIMO = os.getenv('MODO_ANONIMO', 'True').lower() == 'true'

# ═══════════════════════════════════════════════════════════════
# 🌍 ÁREAS PROGRAMÁTICAS → CONTINENTES
# ═══════════════════════════════════════════════════════════════
CONTINENTES = [
    "América do Norte",
    "América Central", 
    "Caribe",
    "América do Sul",
    "África",
    "Europa",
    "Ásia",
    "Oriente Médio",
    "Oceania",
    "Antártica"
]

# ═══════════════════════════════════════════════════════════════
# ⚡ CLÍNICAS → DEUSES MITOLÓGICOS
# ═══════════════════════════════════════════════════════════════
DEUSES = [
    # Grega
    "Zeus", "Hera", "Poseidon", "Atena", "Ares", "Afrodite", "Apolo", 
    "Ártemis", "Hefesto", "Hermes", "Dionísio", "Hades", "Deméter", "Perséfone",
    # Nórdica
    "Odin", "Thor", "Freya", "Loki", "Tyr", "Balder", "Heimdall", "Frigg", "Njord", "Skadi",
    # Egípcia
    "Rá", "Osíris", "Ísis", "Hórus", "Anúbis", "Thoth", "Set", "Bastet", "Sekhmet", "Hathor",
    # Hindu
    "Brahma", "Vishnu", "Shiva", "Ganesha", "Lakshmi", "Saraswati", "Durga", "Kali", "Hanuman",
    # Romana
    "Júpiter", "Juno", "Marte", "Vênus", "Mercúrio", "Netuno", "Plutão", "Minerva", "Ceres",
    # Japonesa
    "Amaterasu", "Susanoo", "Tsukuyomi", "Izanagi", "Izanami", "Inari", "Raijin", "Fujin",
    # Celta
    "Dagda", "Brigid", "Lugh", "Morrigan", "Cernunnos", "Danu", "Epona", "Belenus",
    # Africana/Yorubá
    "Olorun", "Obatalá", "Xangô", "Iemanjá", "Oxum", "Ogum", "Exu", "Oxóssi", "Nanã",
    # Chinesa
    "Jade", "Guanyin", "Nezha", "Erlang", "Mazu", "Guan Yu",
    # Maia/Asteca
    "Quetzalcoatl", "Tlaloc", "Itzamná", "Ixchel", "Kukulcán", "Chaac",
    # Mesopotâmia
    "Marduk", "Ishtar", "Enlil", "Enki", "Shamash", "Sin", "Tiamat"
]

# ═══════════════════════════════════════════════════════════════
# 🎸 ESF → BANDAS DE ROCK
# ═══════════════════════════════════════════════════════════════
BANDAS_ROCK = [
    # Clássicas
    "Led Zeppelin", "Pink Floyd", "The Beatles", "Rolling Stones", "Queen", 
    "AC/DC", "Deep Purple", "Black Sabbath", "The Who", "Aerosmith",
    # Anos 80
    "Guns N' Roses", "Bon Jovi", "Def Leppard", "Van Halen", "Whitesnake",
    "Scorpions", "Iron Maiden", "Metallica", "Megadeth", "Slayer",
    # Grunge/Alternativo
    "Nirvana", "Pearl Jam", "Soundgarden", "Alice in Chains", "Stone Temple Pilots",
    "Red Hot Chili Peppers", "Foo Fighters", "Radiohead", "Oasis", "Blur",
    # Rock Brasileiro
    "Legião Urbana", "Titãs", "Barão Vermelho", "Capital Inicial", "Paralamas",
    "Engenheiros do Hawaii", "RPM", "Skank", "Jota Quest", "Charlie Brown Jr",
    # Moderno
    "Linkin Park", "System of a Down", "Green Day", "Blink-182", "The Offspring",
    "Muse", "Arctic Monkeys", "The Strokes", "Kings of Leon", "Coldplay",
    # Prog/Art Rock
    "Genesis", "Yes", "Rush", "Tool", "Dream Theater", "Porcupine Tree",
    # Hard Rock
    "Kiss", "Motley Crue", "Poison", "Twisted Sister", "Quiet Riot",
    # Metal
    "Judas Priest", "Pantera", "Sepultura", "Anthrax", "Testament",
    # Punk
    "Ramones", "Sex Pistols", "The Clash", "Dead Kennedys", "Bad Religion",
    # Outros
    "U2", "REM", "The Cure", "Depeche Mode", "New Order"
]

# ═══════════════════════════════════════════════════════════════
# 🇨🇳 NOMES CHINESES (PINYIN)
# ═══════════════════════════════════════════════════════════════
SOBRENOMES_CHINESES = [
    "Wang", "Li", "Zhang", "Liu", "Chen", "Yang", "Huang", "Zhao", "Wu", "Zhou",
    "Xu", "Sun", "Ma", "Zhu", "Hu", "Guo", "He", "Lin", "Luo", "Gao",
    "Zheng", "Liang", "Xie", "Song", "Tang", "Deng", "Han", "Feng", "Cao", "Peng",
    "Zeng", "Xiao", "Tian", "Dong", "Pan", "Yuan", "Cai", "Jiang", "Yu", "Du",
    "Ye", "Cheng", "Wei", "Su", "Lu", "Ding", "Ren", "Shen", "Yao", "Zhong"
]

NOMES_CHINESES_MASCULINOS = [
    "Wei", "Fang", "Jun", "Gang", "Qiang", "Ming", "Chao", "Long", "Bo", "Feng",
    "Tao", "Peng", "Hao", "Jian", "Wen", "Yong", "Dong", "Bin", "Lei", "Kai",
    "Yi", "Xin", "Zhi", "Yang", "Chen", "Huan", "Rui", "Ze", "Xuan", "Yu",
    "Jie", "Hang", "Yan", "Shuai", "Kun", "Cheng", "Biao", "Liang", "Zhong", "Nan"
]

NOMES_CHINESES_FEMININOS = [
    "Fang", "Na", "Min", "Jing", "Yan", "Xia", "Juan", "Ying", "Hong", "Yu",
    "Mei", "Li", "Hui", "Ping", "Xiu", "Lan", "Fen", "Qing", "Xue", "Hua",
    "Ling", "Yun", "Qian", "Shan", "Ting", "Rong", "Yue", "Dan", "Ning", "Jia",
    "Xiao", "Zi", "Lu", "Si", "Wan", "Qiong", "Shuang", "Ai", "Cui", "Zhen"
]

# ═══════════════════════════════════════════════════════════════
# 🔧 CACHES PARA CONSISTÊNCIA
# ═══════════════════════════════════════════════════════════════
_cache_ap = {}
_cache_clinica = {}
_cache_esf = {}
_cache_nomes = {}

# ═══════════════════════════════════════════════════════════════
# 🔧 FUNÇÕES DE ANONIMIZAÇÃO
# ═══════════════════════════════════════════════════════════════

def _hash_to_index(valor: str, lista: list) -> int:
    """Converte string em índice consistente para uma lista"""
    hash_val = int(hashlib.md5(str(valor).encode()).hexdigest(), 16)
    return hash_val % len(lista)

def anonimizar_ap(ap_real: str) -> str:
    """Área Programática → Continente"""
    if not MODO_ANONIMO or not ap_real:
        return ap_real
    
    ap_str = str(ap_real).strip()
    
    if ap_str not in _cache_ap:
        idx = _hash_to_index(ap_str, CONTINENTES)
        _cache_ap[ap_str] = CONTINENTES[idx]
    
    return _cache_ap[ap_str]

def anonimizar_clinica(clinica_real: str) -> str:
    """Clínica → Deus Mitológico"""
    if not MODO_ANONIMO or not clinica_real:
        return clinica_real
    
    clinica_str = str(clinica_real).strip()
    
    if clinica_str not in _cache_clinica:
        idx = _hash_to_index(clinica_str, DEUSES)
        _cache_clinica[clinica_str] = f"Templo de {DEUSES[idx]}"
    
    return _cache_clinica[clinica_str]

def anonimizar_esf(esf_real: str) -> str:
    """ESF → Banda de Rock"""
    if not MODO_ANONIMO or not esf_real:
        return esf_real
    
    esf_str = str(esf_real).strip()
    
    if esf_str not in _cache_esf:
        idx = _hash_to_index(esf_str, BANDAS_ROCK)
        _cache_esf[esf_str] = BANDAS_ROCK[idx]
    
    return _cache_esf[esf_str]

def anonimizar_nome(identificador: str, genero: str = None) -> str:
    """Nome do paciente → Nome Chinês em Pinyin"""
    if not MODO_ANONIMO or not identificador:
        return identificador
    
    id_str = str(identificador).strip()
    
    if id_str not in _cache_nomes:
        # Selecionar sobrenome
        idx_sobrenome = _hash_to_index(id_str + "_sobrenome", SOBRENOMES_CHINESES)
        sobrenome = SOBRENOMES_CHINESES[idx_sobrenome]
        
        # Selecionar nome baseado no gênero
        if genero and str(genero).lower() in ['f', 'feminino', 'female']:
            idx_nome = _hash_to_index(id_str + "_nome", NOMES_CHINESES_FEMININOS)
            nome = NOMES_CHINESES_FEMININOS[idx_nome]
        else:
            idx_nome = _hash_to_index(id_str + "_nome", NOMES_CHINESES_MASCULINOS)
            nome = NOMES_CHINESES_MASCULINOS[idx_nome]
        
        _cache_nomes[id_str] = f"{sobrenome} {nome}"
    
    return _cache_nomes[id_str]

def anonimizar_paciente(patient_data: dict) -> dict:
    """Anonimiza todos os campos sensíveis de um paciente"""
    if not MODO_ANONIMO:
        return patient_data
    
    # Cópia para não modificar original
    dados = patient_data.copy()
    
    # Identificador único (CPF ou nome original) - NÃO MASCARAR O CPF!
    identificador = dados.get('cpf') or dados.get('nome', '')
    genero = dados.get('genero')
    
    # Anonimizar nome
    if 'nome' in dados:
        dados['nome'] = anonimizar_nome(identificador, genero)
    
    # ═══════════════════════════════════════════════════════════════
    # ÁREAS PROGRAMÁTICAS (todos os nomes possíveis)
    # ═══════════════════════════════════════════════════════════════
    for campo_ap in ['area_programatica_cadastro', 'area_programatica', 'AP']:
        if campo_ap in dados and dados[campo_ap]:
            dados[campo_ap] = anonimizar_ap(dados[campo_ap])
    
    # ═══════════════════════════════════════════════════════════════
    # CLÍNICAS (todos os nomes possíveis)
    # ═══════════════════════════════════════════════════════════════
    for campo_clinica in ['nome_clinica_cadastro', 'clinica_familia', 'clinica', 'Clinica']:
        if campo_clinica in dados and dados[campo_clinica]:
            dados[campo_clinica] = anonimizar_clinica(dados[campo_clinica])
    
    # ═══════════════════════════════════════════════════════════════
    # ESF (todos os nomes possíveis)
    # ═══════════════════════════════════════════════════════════════
    for campo_esf in ['nome_esf_cadastro', 'ESF', 'esf', 'nome_esf']:
        if campo_esf in dados and dados[campo_esf]:
            dados[campo_esf] = anonimizar_esf(dados[campo_esf])
    
    # ═══════════════════════════════════════════════════════════════
    # MASCARAR DATA DE NASCIMENTO (mas NÃO o CPF - precisamos dele para keys)
    # ═══════════════════════════════════════════════════════════════
    if 'data_nascimento' in dados:
        dados['data_nascimento'] = '****-**-**'
    
    # NÃO mascarar CPF aqui - ele é usado para gerar keys únicas!
    
    return dados

def anonimizar_lista_territorios(tipo: str, lista_real: list) -> list:
    """Anonimiza lista de territórios para filtros dropdown"""
    if not MODO_ANONIMO:
        return lista_real
    
    if tipo == 'ap':
        return [anonimizar_ap(item) for item in lista_real]
    elif tipo == 'clinica':
        return [anonimizar_clinica(item) for item in lista_real]
    elif tipo == 'esf':
        return [anonimizar_esf(item) for item in lista_real]
    
    return lista_real

def mostrar_badge_anonimo():
    """Mostra badge na sidebar indicando modo anônimo"""
    import streamlit as st
    if MODO_ANONIMO:
        st.sidebar.markdown("""
        <div style="
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 10px 15px;
            border-radius: 10px;
            margin-bottom: 15px;
            text-align: center;
        ">
            <span style="font-size: 20px;">🔒</span><br>
            <span style="color: white; font-weight: bold; font-size: 14px;">MODO TESTE</span><br>
            <span style="color: #ddd; font-size: 11px;">Dados anonimizados</span>
        </div>
        """, unsafe_allow_html=True)

def get_modo_anonimo() -> bool:
    """Retorna se está em modo anônimo"""
    return MODO_ANONIMO