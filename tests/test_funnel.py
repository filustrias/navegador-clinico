"""Testes mínimos dos limites de controle e da classificação do funnel."""
import numpy as np
import pandas as pd

from components.funnel_plot import _limites, classificar, plot_funnel


def test_limite_superior_998():
    # p0 = 0.26, n = 100 → limite superior de 99,8% ≈ 0.3955
    _inf, sup = _limites(0.26, np.array([100.0]), 3.09)
    assert abs(float(sup[0]) - 0.3955) < 0.001


def test_limites_truncados():
    inf, sup = _limites(0.02, np.array([10.0]), 3.09)
    assert float(inf[0]) >= 0.0
    assert float(sup[0]) <= 1.0


def test_classificacao_acima_dentro():
    # n=10 / 50% com p0=26% → dentro; n=200 / 40% → acima
    classe = classificar([0.50, 0.40], [10, 200], 0.26)
    assert classe[0] == "dentro"
    assert classe[1] == "acima"


def test_classificacao_abaixo():
    # n=500 / 10% com p0=26% → abaixo do limite inferior
    classe = classificar([0.10], [500], 0.26)
    assert classe[0] == "abaixo"


def test_plot_funnel_retorna_figura():
    df = pd.DataFrame({
        "ap": ["AP 1", "AP 2", "AP 3"],
        "clinica": ["A", "B", "C"],
        "condicao": ["HAS", "HAS", "HAS"],
        "n_numerador": [5, 80, 50],
        "n_denominador": [10, 200, 100],
        "prev_municipio": [0.26, 0.26, 0.26],
    })
    fig = plot_funnel(df, "HAS", p0=0.26)
    assert fig is not None
    # clínica com n<5 é excluída
    df_excl = df.copy()
    df_excl.loc[0, "n_denominador"] = 3
    fig2 = plot_funnel(df_excl, "HAS", p0=0.26)
    assert fig2 is not None
