"""
Cole este arquivo na pasta do projeto e rode:
    python testar_anonimizacao.py

Ele mostra se a variável de ambiente está sendo lida corretamente.
"""
import os
import sys

print("=" * 50)
print("DIAGNÓSTICO DE ANONIMIZAÇÃO")
print("=" * 50)

# 1. Variável de ambiente
modo = os.getenv('MODO_ANONIMO', 'NÃO DEFINIDA')
print(f"\n1. MODO_ANONIMO = '{modo}'")

if modo == 'NÃO DEFINIDA':
    print("   ❌ Variável não encontrada. Rode: set MODO_ANONIMO=true")
elif modo.lower() == 'true':
    print("   ✅ Variável definida corretamente")
else:
    print(f"   ⚠️  Variável definida mas valor '{modo}' não ativa o modo")

# 2. Importar anonimizador
print("\n2. Importando anonimizador...")
try:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from utils.anonimizador import MODO_ANONIMO, anonimizar_nome, anonimizar_ap, anonimizar_clinica, anonimizar_esf
    print(f"   ✅ Importado. MODO_ANONIMO = {MODO_ANONIMO}")
except ImportError as e:
    print(f"   ❌ Erro ao importar: {e}")
    sys.exit(1)

# 3. Testar funções
print("\n3. Testando funções:")
print(f"   anonimizar_ap('1.0')                    → '{anonimizar_ap('1.0')}'")
print(f"   anonimizar_clinica('CF Vitor Valla')     → '{anonimizar_clinica('CF Vitor Valla')}'")
print(f"   anonimizar_esf('ESF Teste')              → '{anonimizar_esf('ESF Teste')}'")
print(f"   anonimizar_nome('12345678901')           → '{anonimizar_nome('12345678901')}'")

print("\n" + "=" * 50)
if not MODO_ANONIMO:
    print("❌ MODO ANÔNIMO DESATIVADO")
    print("   Para ativar, rode ANTES de qualquer python/streamlit:")
    print("   set MODO_ANONIMO=true")
else:
    print("✅ MODO ANÔNIMO ATIVO — anonimização funcionando")
print("=" * 50)
