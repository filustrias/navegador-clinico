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
# Lido em tempo de execução (não no import) para garantir que
# mudanças na variável de ambiente sejam sempre respeitadas.
# ═══════════════════════════════════════════════════════════════

def _is_modo_anonimo() -> bool:
    """Lê MODO_ANONIMO da variável de ambiente a cada chamada."""
    import os as _os
    return _os.getenv('MODO_ANONIMO', 'false').lower() == 'true'

# Alias para compatibilidade com código existente que importa MODO_ANONIMO
# Nota: este valor é fixado no import — use _is_modo_anonimo() para leitura dinâmica
MODO_ANONIMO = _is_modo_anonimo()

# ═══════════════════════════════════════════════════════════════
# 🌍 ÁREAS PROGRAMÁTICAS → CONTINENTES
# Mapeamento fixo e explícito — garante unicidade (sem colisões)
# Formato das APs no banco: "10", "21", "22", "31", etc.
# ═══════════════════════════════════════════════════════════════

_MAP_AP_CONTINENTE = {
    "10": "África",
    "21": "Ásia",
    "22": "América do Norte",
    "31": "América Central",
    "32": "América do Sul",
    "33": "Europa",
    "40": "Antártica",
    "51": "Oriente Médio",
    "52": "Oceania",
    "53": "Caribe",
}

CONTINENTES = list(_MAP_AP_CONTINENTE.values())

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

def _normalizar_ap(ap_str: str) -> str:
    """Extrai o código numérico da AP em qualquer formato.

    Exemplos:
        '10'                     → '10'
        'AP 10'                  → '10'
        'AP 3.1'                 → '31'   (remove o ponto)
        'Área Programática 3.1'  → '31'
        '3.1'                    → '31'
    """
    import re as _re
    # Extrair todos os dígitos (ignorar pontos e espaços)
    digits = _re.sub(r'[^\d]', '', str(ap_str).strip())
    return digits if digits else ap_str


def anonimizar_ap(ap_real: str) -> str:
    """Área Programática → Continente.
    
    Mapeamento fixo e explícito — sem colisões.
    Aceita qualquer formato: '1.0', 'AP 1.0', 'Área Programática 1.0', etc.
    """
    if not _is_modo_anonimo() or not ap_real:
        return ap_real

    ap_norm = _normalizar_ap(str(ap_real).strip())

    if ap_norm in _MAP_AP_CONTINENTE:
        return _MAP_AP_CONTINENTE[ap_norm]

    # Fallback para APs não mapeadas
    if ap_norm not in _cache_ap:
        _cache_ap[ap_norm] = f"Região {ap_norm}"
    return _cache_ap[ap_norm]

def anonimizar_clinica(clinica_real: str) -> str:
    """Clínica → Deus Mitológico"""
    if not _is_modo_anonimo() or not clinica_real:
        return clinica_real
    
    clinica_str = str(clinica_real).strip()
    
    if clinica_str not in _cache_clinica:
        idx = _hash_to_index(clinica_str, DEUSES)
        _cache_clinica[clinica_str] = f"Templo de {DEUSES[idx]}"
    
    return _cache_clinica[clinica_str]

def anonimizar_esf(esf_real: str) -> str:
    """ESF → Banda de Rock"""
    if not _is_modo_anonimo() or not esf_real:
        return esf_real
    
    esf_str = str(esf_real).strip()
    
    if esf_str not in _cache_esf:
        idx = _hash_to_index(esf_str, BANDAS_ROCK)
        _cache_esf[esf_str] = BANDAS_ROCK[idx]
    
    return _cache_esf[esf_str]

def anonimizar_nome(identificador: str, genero: str = None) -> str:
    """Nome do paciente → Nome Chinês em Pinyin.
    
    identificador deve ser o CPF (estável) — nunca o nome próprio,
    que pode variar em maiúsculas/minúsculas/acentos entre chamadas.
    """
    if not _is_modo_anonimo() or not identificador:
        return identificador

    id_str = str(identificador).strip()

    if id_str not in _cache_nomes:
        idx_sobrenome = _hash_to_index(id_str + "_sobrenome", SOBRENOMES_CHINESES)
        sobrenome = SOBRENOMES_CHINESES[idx_sobrenome]

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
    if not _is_modo_anonimo():
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
    if not _is_modo_anonimo():
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
    if _is_modo_anonimo():
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