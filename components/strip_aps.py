"""Strip plot por Área Programática (substituto do violino).

Uma linha por AP em **ordem fixa** (alfabética pelo rótulo), para manter
referência estável ao trocar de condição. Cada clínica é um ponto cinza
com jitter vertical determinístico; a mediana da AP é um traço; o
benchmark municipal é uma linha vertical tracejada única. Sem KDE/violino,
sem box plot, sem cor categórica por AP — cor só quando codifica significado.

Contrato do DataFrame (uma linha por clínica × condição):
``ap, clinica, condicao, n_numerador, n_denominador, prev_municipio``.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go

_COR_PONTO = "#B4B2A9"
_COR_MEDIANA = "#0C447C"
_COR_BENCH = "#D85A30"
_N_MIN = 5


def _pt(v: float, casas: int) -> str:
    return f"{v:.{casas}f}".replace(".", ",")


def plot_strip_aps(
    df: pd.DataFrame,
    condicao: str,
    titulo_x: str = "Prevalência (%)",
) -> go.Figure | None:
    """Strip plot da ``condicao``, uma linha por AP em ordem fixa."""
    d = df[df["condicao"] == condicao].copy()
    d = d[d["n_denominador"] >= _N_MIN]
    if d.empty:
        return None

    d["prop"] = d["n_numerador"] / d["n_denominador"] * 100.0
    if "prev_municipio" in d.columns and pd.notna(d["prev_municipio"].iloc[0]):
        bench = float(d["prev_municipio"].iloc[0]) * 100.0
    else:
        bench = float(d["prop"].mean())

    # Casas decimais adaptativas: prevalências baixas (condições raras)
    # precisam de mais precisão para não virarem "0,0%".
    escala = max(float(d["prop"].max()), bench)
    casas = 2 if escala < 5 else 1
    fmt_eixo = f".{casas}f"

    medianas = d.groupby("ap")["prop"].median()
    aps = sorted(medianas.index)  # ordem FIXA (alfabética) — referência estável
    rng = np.random.default_rng(42)  # jitter reprodutível entre reruns

    fig = go.Figure()
    y_ticks: list[float] = []
    y_labels: list[str] = []
    n_aps = len(aps)

    for i, ap in enumerate(aps):
        sub = d[d["ap"] == ap]
        y0 = float(n_aps - i)  # primeira AP (alfabética) no topo
        jit = (rng.random(len(sub)) - 0.5) * 0.6
        custom = list(zip(
            sub["clinica"].astype(str),
            [_pt(v, casas) for v in sub["prop"]],
            [_pt(v, casas) for v in (sub["prop"] - bench)],
        ))
        fig.add_trace(go.Scatter(
            x=sub["prop"], y=np.full(len(sub), y0) + jit, mode="markers",
            marker=dict(color=_COR_PONTO, size=6, opacity=0.65),
            customdata=custom,
            hovertemplate=("<b>%{customdata[0]}</b><br>%{customdata[1]}%<br>"
                           "%{customdata[2]} pp vs município<extra></extra>"),
            showlegend=False,
        ))
        m = float(medianas[ap])
        fig.add_trace(go.Scatter(
            x=[m, m], y=[y0 - 0.32, y0 + 0.32], mode="lines",
            line=dict(color=_COR_MEDIANA, width=4),
            showlegend=False, hoverinfo="skip",
        ))
        y_ticks.append(y0)
        y_labels.append(f"{ap} · {len(sub)} clín.")

    fig.add_vline(x=bench, line=dict(color=_COR_BENCH, dash="dash", width=2))
    fig.add_annotation(
        x=bench, y=n_aps + 0.6, yref="y",
        text=f"Município {_pt(bench, casas)}%", showarrow=False,
        font=dict(color=_COR_BENCH, size=11),
    )

    fig.update_layout(
        separators=",.",
        xaxis=dict(title=titulo_x, tickformat=fmt_eixo),
        yaxis=dict(tickvals=y_ticks, ticktext=y_labels, title="",
                   range=[0.3, n_aps + 1.2]),
        height=max(360, 40 * n_aps + 90),
        margin=dict(l=140, r=30, t=40, b=50),
        hovermode="closest",
    )
    return fig
