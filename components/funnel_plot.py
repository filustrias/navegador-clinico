"""Funnel plot (controle estatístico de processo) para comparar clínicas.

Cada ponto é uma clínica: x = nº de pacientes elegíveis (denominador),
y = proporção (%). As bandas são limites de controle binomiais em torno
da proporção municipal agregada ``p0``. Opcionalmente corrige
sobredispersão (Spiegelhalter, Stat Med 2005). Cores e símbolos são
fixos por classificação — nenhuma cor sem significado, sem rainbow.

Contrato do DataFrame de entrada (uma linha por clínica × condição):
``ap, clinica, condicao, n_numerador, n_denominador, prev_municipio``.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go

# Cores fixas por classificação / referência
_COR_ACIMA = "#D85A30"
_COR_ABAIXO = "#1D9E75"
_COR_DENTRO = "#B4B2A9"
_COR_P0 = "#378ADD"
_COR_95 = "#888780"
_COR_998 = "#5F5E5A"

_Z_95 = 1.96
_Z_998 = 3.09
_N_MIN = 5  # clínicas com denominador menor são excluídas


def _limites(p0: float, n: np.ndarray, z: float, phi: float = 1.0):
    """Limites de controle binomiais (inferior, superior), truncados em [0, 1].

    ``phi`` (>= 1) infla os limites quando há sobredispersão."""
    se = np.sqrt(phi * p0 * (1.0 - p0) / n)
    sup = np.clip(p0 + z * se, 0.0, 1.0)
    inf = np.clip(p0 - z * se, 0.0, 1.0)
    return inf, sup


def calcular_phi_spiegelhalter(prop, n, p0: float) -> float:
    """Fator de sobredispersão de Spiegelhalter (2005).

    z-scores winsorizados a 10%; phi = média dos z². Retorna >= 1.0."""
    prop = np.asarray(prop, dtype=float)
    n = np.asarray(n, dtype=float)
    se = np.sqrt(p0 * (1.0 - p0) / n)
    z = (prop - p0) / np.where(se > 0, se, np.nan)
    z = z[np.isfinite(z)]
    if z.size == 0:
        return 1.0
    lo, hi = np.percentile(z, [10, 90])
    zw = np.clip(z, lo, hi)
    return float(np.mean(zw ** 2))


def classificar(prop, n, p0: float, z: float = _Z_998, phi: float = 1.0) -> np.ndarray:
    """Classifica cada clínica como 'acima', 'abaixo' ou 'dentro' dos limites."""
    inf, sup = _limites(p0, np.asarray(n, dtype=float), z, phi)
    prop = np.asarray(prop, dtype=float)
    out = np.full(prop.shape, "dentro", dtype=object)
    out[prop > sup] = "acima"
    out[prop < inf] = "abaixo"
    return out


def _pt(v: float, casas: int = 1) -> str:
    """Número em formato pt-BR (vírgula decimal)."""
    return f"{v:.{casas}f}".replace(".", ",")


def plot_funnel(
    df: pd.DataFrame,
    condicao: str,
    p0: float | None = None,
    ajustar_sobredispersao: bool = False,
    titulo_y: str = "Prevalência (%)",
) -> go.Figure | None:
    """Constrói o funnel plot da ``condicao`` a partir de ``df`` (todas as
    clínicas). Retorna ``None`` se não houver clínicas elegíveis."""
    d = df[df["condicao"] == condicao].copy()
    d = d[d["n_denominador"] >= _N_MIN]
    if d.empty:
        return None

    d["prop"] = d["n_numerador"] / d["n_denominador"]

    if p0 is None:
        tot_den = float(d["n_denominador"].sum())
        p0 = float(d["n_numerador"].sum()) / tot_den if tot_den > 0 else 0.0

    phi = 1.0
    if ajustar_sobredispersao:
        phi = max(1.0, calcular_phi_spiegelhalter(d["prop"], d["n_denominador"], p0))

    d["classe"] = classificar(d["prop"], d["n_denominador"], p0, _Z_998, phi)

    # Grade de denominadores para desenhar as bandas
    n_min = max(_N_MIN, int(d["n_denominador"].min()))
    n_max = int(d["n_denominador"].max() * 1.05)
    grade = np.linspace(n_min, max(n_max, n_min + 1), 200)
    inf95, sup95 = _limites(p0, grade, _Z_95, phi)
    inf998, sup998 = _limites(p0, grade, _Z_998, phi)

    fig = go.Figure()

    # Bandas de controle
    for y, dash, cor, nome in [
        (sup998 * 100, "solid", _COR_998, "Limite 99,8%"),
        (inf998 * 100, "solid", _COR_998, None),
        (sup95 * 100, "dash", _COR_95, "Limite 95%"),
        (inf95 * 100, "dash", _COR_95, None),
    ]:
        fig.add_trace(go.Scatter(
            x=grade, y=y, mode="lines",
            line=dict(color=cor, dash=dash, width=1.2),
            name=nome, showlegend=nome is not None, hoverinfo="skip",
        ))

    # Linha do município (p0)
    fig.add_trace(go.Scatter(
        x=[grade.min(), grade.max()], y=[p0 * 100, p0 * 100], mode="lines",
        line=dict(color=_COR_P0, width=2),
        name=f"Município ({_pt(p0 * 100)}%)", hoverinfo="skip",
    ))

    # Pontos por classificação (cor + símbolo; nunca só cor)
    cfg = {
        "dentro": (_COR_DENTRO, "circle", "dentro da variação esperada", "Dentro"),
        "abaixo": (_COR_ABAIXO, "circle",
                   "abaixo do limite — possível boa prática ou subnotificação", "Abaixo"),
        "acima": (_COR_ACIMA, "diamond",
                  "acima do limite de 99,8% — investigar", "Acima"),
    }
    contagem = d["classe"].value_counts().to_dict()
    for classe in ("dentro", "abaixo", "acima"):
        sub = d[d["classe"] == classe]
        if sub.empty:
            continue
        cor, simb, desc, rotulo = cfg[classe]
        custom = list(zip(
            sub["clinica"].astype(str),
            sub["ap"].astype(str),
            [_pt(v) for v in (sub["prop"] * 100)],
            [desc] * len(sub),
        ))
        fig.add_trace(go.Scatter(
            x=sub["n_denominador"], y=sub["prop"] * 100, mode="markers",
            marker=dict(color=cor, symbol=simb, size=9, opacity=0.75,
                        line=dict(width=0.5, color="white")),
            name=f"{rotulo} ({contagem.get(classe, 0)})",
            customdata=custom,
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>%{customdata[1]}<br>"
                "n=%{x:,} · %{customdata[2]}%<br>"
                "<i>%{customdata[3]}</i><extra></extra>"
            ),
        ))

    fig.update_layout(
        separators=",.",
        xaxis_title="Pacientes elegíveis na clínica",
        yaxis_title=titulo_y,
        height=460,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        margin=dict(l=60, r=30, t=60, b=50),
        hovermode="closest",
    )
    return fig
