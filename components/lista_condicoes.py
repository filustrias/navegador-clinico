"""Lista compacta seletora de condições (master-detail).

Substitui o ranking top-20 de barras. Uma linha por condição, com: nome,
n e prevalência da unidade selecionada, mini-barra da prevalência (com o
município como referência em coluna ao lado) e razão (unidade ÷ município)
com indicador de faixa. A linha selecionada define a ``condicao`` passada
ao funnel e ao strip.

Preparação dos dados fica em ``montar_tabela`` (sem lógica de dados nos
callbacks de UI); ``render_lista`` apenas desenha e devolve a seleção.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

# Faixas de razão (prevalência da unidade ÷ município, em %) → indicador.
# ≥105 azul · 85–104 verde-teal · 65–84 âmbar · <65 coral.
_FAIXAS = [
    (105, "🔵"),
    (85, "🟢"),
    (65, "🟡"),
    (0, "🟠"),
]


def _indicador_faixa(razao: float | None) -> str:
    if razao is None:
        return "⚪"
    for limite, emoji in _FAIXAS:
        if razao >= limite:
            return emoji
    return "🟠"


def montar_tabela(
    df_unidade: pd.DataFrame,
    bench_municipio: dict[str, float],
) -> pd.DataFrame:
    """Monta a tabela de exibição a partir das prevalências da unidade.

    ``df_unidade`` vem de ``criar_visualizacao_morbidades_prevalentes`` e
    tem as colunas: Condição, N, ``Prevalência (%)``, Categoria, Coluna.
    ``bench_municipio`` é ``{coluna: prevalência_municipio_%}``.
    Razão indefinida (município 0) vira ``None`` → exibida como "—".
    """
    linhas = []
    for _, r in df_unidade.iterrows():
        col = r["Coluna"]
        prev_un = float(r["Prevalência (%)"])
        prev_mun = bench_municipio.get(col)
        if prev_mun is None or prev_mun == 0:
            razao = None
        else:
            razao = prev_un / prev_mun * 100.0
        linhas.append({
            "Coluna": col,
            "Grupo": r.get("Categoria", "—"),
            "Condição": r["Condição"],
            "Pacientes": int(r["N"]),
            "Prev. unidade (%)": round(prev_un, 1),
            "Município (%)": round(prev_mun, 1) if prev_mun is not None else None,
            "Razão": f"{_indicador_faixa(razao)} {razao:.0f}%" if razao is not None else "—",
        })
    df = pd.DataFrame(linhas)
    if not df.empty:
        df = df.sort_values("Prev. unidade (%)", ascending=False).reset_index(drop=True)
    return df


def render_lista(df_tab: pd.DataFrame, filtro_ativo: bool = False,
                 key: str = "lista_cond") -> str | None:
    """Renderiza filtro de grupo + tabela seletável. Devolve a ``Coluna``
    da condição selecionada (persistida em ``session_state``).

    As colunas de benchmark (Município, Razão) só aparecem quando há filtro
    territorial ativo (``filtro_ativo``) — sem filtro, o escopo já é o
    município e a comparação seria redundante."""
    if df_tab.empty:
        st.info("Sem condições para listar.")
        return None

    sel_key = f"{key}_sel"
    if sel_key not in st.session_state or \
            st.session_state[sel_key] not in set(df_tab["Coluna"]):
        # Default: condição de maior prevalência (df_tab vem ordenado).
        st.session_state[sel_key] = df_tab.iloc[0]["Coluna"]

    grupos = ["Todos"] + sorted(df_tab["Grupo"].dropna().unique().tolist())
    grupo_sel = st.pills("Grupo", grupos, selection_mode="single",
                         default="Todos", key=f"{key}_grupo") or "Todos"

    df_view = df_tab if grupo_sel == "Todos" else df_tab[df_tab["Grupo"] == grupo_sel]
    df_view = df_view.reset_index(drop=True)
    if df_view.empty:
        st.info("Nenhuma condição neste grupo.")
        return st.session_state[sel_key]

    cols_show = ["Grupo", "Condição", "Pacientes", "Prev. unidade (%)"]
    col_cfg = {
        "Grupo": st.column_config.TextColumn("Grupo", width="small"),
        "Condição": st.column_config.TextColumn("Condição", width="medium"),
        "Pacientes": st.column_config.NumberColumn("Pacientes", format="%d"),
        "Prev. unidade (%)": st.column_config.ProgressColumn(
            "Prevalência", format="%.1f%%", min_value=0,
            max_value=float(max(df_view["Prev. unidade (%)"].max(), 1.0))),
    }
    if filtro_ativo:
        cols_show += ["Município (%)", "Razão"]
        col_cfg["Município (%)"] = st.column_config.NumberColumn(
            "Município", format="%.1f%%")
        col_cfg["Razão"] = st.column_config.TextColumn("Razão vs município",
                                                       width="small")

    evento = st.dataframe(
        df_view[cols_show],
        hide_index=True,
        use_container_width=True,
        height=min(430, 40 + 35 * len(df_view)),
        on_select="rerun",
        selection_mode="single-row",
        key=f"{key}_tbl_{grupo_sel}",
        column_config=col_cfg,
    )

    sel_rows = evento.selection.rows if evento and evento.selection else []
    if sel_rows:
        st.session_state[sel_key] = df_view.iloc[sel_rows[0]]["Coluna"]

    return st.session_state[sel_key]
