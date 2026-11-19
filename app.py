import io
import re
import unicodedata
import streamlit as st
import pandas as pd
import numpy as np
import requests
from collections import Counter
from math import comb

st.set_page_config(page_title="Loto Inteligência IA", page_icon="🎯", layout="wide")

LOTTERIES = {
    "Lotofácil": {
        "min": 1, "max": 25, "draw": 15,
        "fields": [f"bola{i}" for i in range(1, 16)],
        "api": "lotofacil", "price": 3.50, "download_name": "Lotofácil"
    },
    "Mega-Sena": {
        "min": 1, "max": 60, "draw": 6,
        "fields": [f"bola{i}" for i in range(1, 7)],
        "api": "megasena", "price": 6.00, "download_name": "Mega-Sena"
    },
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; LotoInteligenciaIA/1.0)",
    "Accept": "application/json, text/plain, */*",
}

def normalize_name(value):
    value = unicodedata.normalize("NFKD", str(value))
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]", "", value.lower())

def validate_history(df, lottery):
    cfg = LOTTERIES[lottery]
    required = cfg["fields"]
    rename = {}
    for col in df.columns:
        key = normalize_name(col)
        if key in ("concurso", "numero"):
            rename[col] = "concurso"
        elif key in ("data", "datasorteio", "dataapuracao"):
            rename[col] = "data"
        elif re.fullmatch(r"(bola|dezena|d)0?\d+", key):
            number = int(re.search(r"\d+", key).group())
            if 1 <= number <= cfg["draw"]:
                rename[col] = f"bola{number}"
    df = df.rename(columns=rename)
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError("Não encontrei as colunas das dezenas: " + ", ".join(missing))
    for c in required:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=required).copy()
    for c in required:
        df[c] = df[c].astype(int)
    valid = df[required].apply(
        lambda row: row.between(cfg["min"], cfg["max"]).all()
        and row.nunique() == cfg["draw"], axis=1
    )
    df = df[valid].copy()
    if "concurso" in df.columns:
        df["concurso"] = pd.to_numeric(df["concurso"], errors="coerce")
        df = df.dropna(subset=["concurso"]).sort_values("concurso")
        df["concurso"] = df["concurso"].astype(int)
    else:
        df = df.reset_index(drop=True)
    if "data" in df.columns:
        df["data"] = df["data"].astype(str)
    return df.drop_duplicates(subset=["concurso"] if "concurso" in df.columns else required)

@st.cache_data(ttl=86400, show_spinner=False)
def get_full_history(lottery):
    cfg = LOTTERIES[lottery]
    url = "https://servicebus2.caixa.gov.br/portaldeloterias/api/resultados/download"
    response = requests.get(
        url, params={"modalidade": cfg["download_name"]},
        headers=HEADERS, timeout=90
    )
    response.raise_for_status()
    if not response.content:
        raise ValueError("A CAIXA retornou um arquivo vazio.")
    try:
        raw = pd.read_excel(io.BytesIO(response.content), engine="xlrd")
    except Exception:
        try:
            raw = pd.read_excel(io.BytesIO(response.content), engine="openpyxl")
        except Exception:
            try:
                raw = pd.read_csv(io.BytesIO(response.content), sep=None, engine="python")
            except Exception as exc:
                raise ValueError(
                    "Não consegui interpretar o arquivo histórico enviado pelo serviço da CAIXA."
                ) from exc
    history = validate_history(raw, lottery)
    if history.empty:
        raise ValueError("O arquivo foi recebido, mas não continha concursos válidos.")
    return history

@st.cache_data(ttl=3600, show_spinner=False)
def get_latest_result(lottery):
    cfg = LOTTERIES[lottery]
    url = f"https://servicebus2.caixa.gov.br/portaldeloterias/api/{cfg['api']}"
    response = requests.get(url, headers=HEADERS, timeout=20)
    response.raise_for_status()
    data = response.json()
    numbers = data.get("listaDezenas") or data.get("dezenasSorteadasOrdemSorteio")
    if not numbers:
        raise ValueError("A resposta da CAIXA não trouxe as dezenas do concurso.")
    return {
        "contest": data.get("numero", "—"),
        "date": data.get("dataApuracao", "—"),
        "numbers": sorted([int(n) for n in numbers]),
    }

def money(value):
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def count_numbers(df, fields, number_max):
    values = df[fields].to_numpy().ravel().tolist()
    return pd.Series(Counter(values)).reindex(range(1, number_max + 1), fill_value=0)

def create_games(lottery, freq, n_games=10, mode="Equilibrado"):
    cfg = LOTTERIES[lottery]
    nums = np.arange(cfg["min"], cfg["max"] + 1)
    games, seen = [], set()
    if mode == "Aleatório":
        weights = np.ones(len(nums), dtype=float)
    else:
        ranks = freq.reindex(nums).to_numpy(dtype=float)
        ranks = (ranks - ranks.mean()) / (ranks.std() + 1e-9)
        weights = np.exp(np.clip(ranks * 0.12, -0.25, 0.25))
    attempts = 0
    while len(games) < n_games and attempts < 20000:
        attempts += 1
        pick = tuple(sorted(np.random.choice(
            nums, size=cfg["draw"], replace=False, p=weights / weights.sum()
        ).tolist()))
        if pick not in seen:
            seen.add(pick)
            games.append(pick)
    return games

st.title("🎯 Loto Inteligência IA")
st.caption("Painel de análise estatística e simulação — versão 3")
st.info(
    "Importante: sorteios são independentes. Frequências e atrasos descrevem "
    "o passado e não aumentam a chance de uma dezena sair no próximo concurso."
)

with st.sidebar:
    st.header("Configurações")
    lottery = st.selectbox("Modalidade", list(LOTTERIES.keys()), key="lottery_choice")
    uploaded = st.file_uploader("Ou carregar histórico CSV manualmente", type=["csv"])
    if st.button("Atualizar histórico da CAIXA"):
        get_full_history.clear()
        get_latest_result.clear()
    st.caption(
        "O histórico é buscado automaticamente. O CSV manual fica disponível como alternativa."
    )

cfg = LOTTERIES[lottery]
fields = cfg["fields"]
history_source = "CAIXA"
try:
    if uploaded is not None:
        full_df = validate_history(pd.read_csv(uploaded), lottery)
        history_source = "Arquivo CSV enviado"
    else:
        with st.spinner(f"Buscando o histórico completo da {lottery} na CAIXA..."):
            full_df = get_full_history(lottery)
except Exception as e:
    full_df = None
    st.warning(
        "Não foi possível carregar automaticamente o histórico completo. "
        "Você pode tentar novamente pelo botão da lateral ou enviar um CSV. "
        f"Detalhe: {e}"
    )

st.subheader(f"Resultado mais recente — {lottery}")
refresh_col, info_col = st.columns([1, 5])
with refresh_col:
    if st.button("Atualizar resultado"):
        get_latest_result.clear()
with info_col:
    st.caption("Consulta ao serviço de resultados do Portal Loterias CAIXA; o histórico fica em cache por até 24 horas.")

try:
    latest = get_latest_result(lottery)
    st.markdown(f"**Concurso {latest['contest']}** · Data do sorteio: **{latest['date']}**")
    balls = st.columns(cfg["draw"])
    for col, number in zip(balls, latest["numbers"]):
        col.markdown(
            f"<div style='background:#f0f2f6;border-radius:50%;width:46px;height:46px;"
            f"display:flex;align-items:center;justify-content:center;font-weight:700;"
            f"font-size:17px;margin:auto'>{number:02d}</div>",
            unsafe_allow_html=True,
        )
except Exception as e:
    st.warning(f"Não foi possível consultar o último resultado agora: {e}")

st.divider()
st.subheader(f"Análise estatística — {lottery}")
if full_df is not None and not full_df.empty:
    st.success(f"Histórico carregado: {len(full_df):,} concursos • Fonte: {history_source}".replace(",", "."))
    period = st.selectbox(
        "Período usado na análise",
        ["Todo o histórico", "Últimos 500 concursos", "Últimos 200 concursos", "Últimos 100 concursos"]
    )
    if period == "Todo o histórico":
        df = full_df.copy()
    else:
        limit = int(period.split()[1])
        df = full_df.tail(limit).copy()
    freq = count_numbers(df, fields, cfg["max"])
    c1, c2, c3 = st.columns(3)
    c1.metric("Concursos analisados", f"{len(df):,}".replace(",", "."))
    c2.metric("Dezenas por sorteio", cfg["draw"])
    c3.metric("Dezenas possíveis", cfg["max"])
    if "concurso" in df.columns:
        c4, c5 = st.columns(2)
        c4.metric("Concurso inicial", int(df["concurso"].min()))
        c5.metric("Concurso final", int(df["concurso"].max()))
    stats = pd.DataFrame({"Dezena": freq.index, "Ocorrências": freq.values})
    st.markdown("**Frequência das dezenas no período selecionado**")
    st.bar_chart(stats.set_index("Dezena"))
    left, right = st.columns(2)
    with left:
        st.markdown("**10 dezenas mais frequentes**")
        st.dataframe(stats.sort_values("Ocorrências", ascending=False).head(10), hide_index=True, use_container_width=True)
    with right:
        st.markdown("**10 dezenas menos frequentes**")
        st.dataframe(stats.sort_values(["Ocorrências", "Dezena"]).head(10), hide_index=True, use_container_width=True)
    with st.expander("Ver concursos carregados"):
        st.dataframe(df, hide_index=True, use_container_width=True)
    st.download_button(
        "Baixar histórico analisado em CSV",
        df.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"historico_{lottery.lower().replace('-', '')}.csv",
        mime="text/csv"
    )
else:
    st.info("A análise histórica ficará disponível quando a CAIXA liberar o arquivo ou quando você enviar um CSV.")
    freq = pd.Series(0, index=range(1, cfg["max"] + 1))

st.divider()
st.subheader("Gerador de 10 jogos")
st.write(f"**Custo de 1 jogo simples:** {money(cfg['price'])}")
st.write(f"**Investimento total para 10 jogos:** {money(cfg['price'] * 10)}")
method = st.radio(
    "Método de simulação", ["Equilibrado", "Aleatório"], horizontal=True,
    help="Equilibrado usa ponderação muito leve das frequências históricas. Aleatório dá peso igual a todas as dezenas. Nenhum método prevê o sorteio."
)
if st.button("Gerar 10 jogos", type="primary"):
    games = create_games(lottery, freq, 10, method)
    st.session_state["games"] = games
    st.session_state["games_lottery"] = lottery
    st.session_state["games_method"] = method

if st.session_state.get("games") and st.session_state.get("games_lottery") == lottery:
    st.caption(f"Método: {st.session_state.get('games_method')} • Combinações únicas")
    for i, game in enumerate(st.session_state["games"], 1):
        st.write(f"**Jogo {i:02d}:** " + " · ".join(f"{n:02d}" for n in game))
    csv_games = pd.DataFrame(st.session_state["games"], columns=[f"dezena_{i}" for i in range(1, cfg["draw"] + 1)])
    st.download_button(
        "Baixar jogos em CSV", csv_games.to_csv(index=False).encode("utf-8"),
        file_name=f"jogos_{lottery.lower().replace('-', '')}.csv", mime="text/csv"
    )

st.divider()
st.subheader("Probabilidade de acertar o prêmio principal")
total = comb(cfg["max"], cfg["draw"])
st.metric("Aposta simples", f"1 em {total:,}".replace(",", "."))
st.caption("Probabilidade matemática de uma combinação simples, independentemente dos resultados anteriores.")
st.caption("A fonte de dados histórica usa um endpoint público do Portal Loterias CAIXA, não documentado como API oficial e sujeito a mudanças. Confira resultados e preços nos canais oficiais.")
st.caption("Projeto experimental e independente, sem vínculo com a CAIXA.")
