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
        "api": "lotofacil", "price": 3.50
    },
    "Mega-Sena": {
        "min": 1, "max": 60, "draw": 6,
        "fields": [f"bola{i}" for i in range(1, 7)],
        "api": "megasena", "price": 6.00
    },
}

def load_history(upload, lottery):
    cfg = LOTTERIES[lottery]
    df = pd.read_csv(upload)
    required = cfg["fields"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError("Colunas ausentes: " + ", ".join(missing) +
                         ". Use concurso,data," + ",".join(required) + ".")
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
        df = df.sort_values("concurso")
    return df, required

@st.cache_data(ttl=3600, show_spinner=False)
def get_latest_result(lottery):
    cfg = LOTTERIES[lottery]
    url = f"https://servicebus2.caixa.gov.br/portaldeloterias/api/{cfg['api']}"
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; LotoInteligenciaIA/1.0)",
        "Accept": "application/json, text/plain, */*",
    }
    response = requests.get(url, headers=headers, timeout=20)
    response.raise_for_status()
    data = response.json()
    numbers = data.get("listaDezenas") or data.get("dezenasSorteadasOrdemSorteio")
    if not numbers:
        raise ValueError("A resposta da Caixa não trouxe as dezenas do concurso.")
    return {
        "contest": data.get("numero", "—"),
        "date": data.get("dataApuracao", "—"),
        "numbers": sorted([int(n) for n in numbers]),
        "next_contest": data.get("numeroConcursoProximo"),
        "estimated_prize": data.get("valorEstimadoProximoConcurso"),
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
st.caption("Painel de análise estatística e simulação — versão 2")
st.info(
    "Importante: sorteios são independentes. Frequências e atrasos descrevem "
    "o passado e não aumentam a chance de uma dezena sair no próximo concurso."
)

with st.sidebar:
    st.header("Configurações")
    lottery = st.selectbox("Modalidade", list(LOTTERIES.keys()), key="lottery_choice")
    uploaded = st.file_uploader("Carregar histórico CSV", type=["csv"])
    st.caption(
        "O arquivo precisa ter as colunas concurso,data e bola1 até bola15 "
        "(Lotofácil) ou bola1 até bola6 (Mega-Sena)."
    )

cfg = LOTTERIES[lottery]
df = None
fields = cfg["fields"]
if uploaded is not None:
    try:
        df, fields = load_history(uploaded, lottery)
        if df.empty:
            st.warning("O arquivo foi lido, mas nenhuma linha válida foi encontrada.")
            df = None
    except Exception as e:
        st.error(f"Não foi possível importar o histórico: {e}")

st.subheader(f"Resultado mais recente — {lottery}")
refresh_col, info_col = st.columns([1, 5])
with refresh_col:
    if st.button("Atualizar resultado"):
        get_latest_result.clear()
with info_col:
    st.caption("Consulta automática ao serviço de resultados do Portal Loterias CAIXA. Cache de até 1 hora.")

try:
    latest = get_latest_result(lottery)
    st.markdown(
        f"**Concurso {latest['contest']}** · Data do sorteio: **{latest['date']}**"
    )
    balls = st.columns(cfg["draw"])
    for col, number in zip(balls, latest["numbers"]):
        col.markdown(
            f"<div style='background:#f0f2f6;border-radius:50%;width:46px;height:46px;"
            f"display:flex;align-items:center;justify-content:center;font-weight:700;"
            f"font-size:17px;margin:auto'>{number:02d}</div>",
            unsafe_allow_html=True,
        )
    st.caption("Dezenas em ordem crescente. Confira sempre o resultado no portal oficial da CAIXA.")
except Exception as e:
    latest = None
    st.warning(
        "Não foi possível consultar o resultado automaticamente neste momento. "
        "Tente novamente em instantes ou confira no site das Loterias CAIXA. "
        f"Detalhe técnico: {e}"
    )

if df is None:
    st.subheader(f"Análise: {lottery}")
    st.write("Para ver frequências históricas, carregue um arquivo CSV com os concursos anteriores.")
    c1, c2, c3 = st.columns(3)
    c1.metric("Dezenas possíveis", cfg["max"])
    c2.metric("Dezenas por sorteio", cfg["draw"])
    c3.metric("Concursos no histórico carregado", "0")
    freq = pd.Series(0, index=range(1, cfg["max"] + 1))
else:
    freq = count_numbers(df, fields, cfg["max"])
    c1, c2, c3 = st.columns(3)
    c1.metric("Concursos analisados", len(df))
    c2.metric("Dezenas por sorteio", cfg["draw"])
    c3.metric("Dezenas possíveis", cfg["max"])
    st.subheader("Frequência histórica")
    stats = pd.DataFrame({"Dezena": freq.index, "Ocorrências": freq.values})
    st.bar_chart(stats.set_index("Dezena"))
    left, right = st.columns(2)
    with left:
        st.markdown("**10 dezenas mais frequentes**")
        st.dataframe(
            stats.sort_values("Ocorrências", ascending=False).head(10),
            hide_index=True, use_container_width=True
        )
    with right:
        st.markdown("**10 dezenas menos frequentes**")
        st.dataframe(
            stats.sort_values(["Ocorrências", "Dezena"]).head(10),
            hide_index=True, use_container_width=True
        )

st.divider()
st.subheader("Gerador de 10 jogos")
st.write(f"**Custo de 1 jogo simples:** {money(cfg['price'])}")
st.write(f"**Investimento total para 10 jogos:** {money(cfg['price'] * 10)}")
method = st.radio(
    "Método de simulação", ["Equilibrado", "Aleatório"], horizontal=True,
    help="Equilibrado usa uma ponderação muito leve das frequências históricas. "
         "Aleatório dá peso igual a todas as dezenas. Nenhum método prevê o sorteio."
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
    csv_games = pd.DataFrame(
        st.session_state["games"],
        columns=[f"dezena_{i}" for i in range(1, cfg["draw"] + 1)]
    )
    st.download_button(
        "Baixar jogos em CSV", csv_games.to_csv(index=False).encode("utf-8"),
        file_name=f"jogos_{lottery.lower().replace('-', '')}.csv",
        mime="text/csv"
    )

st.divider()
st.subheader("Probabilidade de acertar o prêmio principal")
total = comb(cfg["max"], cfg["draw"])
st.metric("Aposta simples", f"1 em {total:,}".replace(",", "."))
st.caption(
    "Probabilidade matemática de uma combinação simples, independentemente "
    "dos resultados anteriores."
)
st.caption(
    "Preços exibidos para apostas simples conforme as páginas da CAIXA consultadas. "
    "Podem mudar; confira o valor no canal oficial antes de apostar."
)
st.caption(
    "Projeto experimental e independente, sem vínculo com a CAIXA. "
    "Resultados e preços devem ser conferidos nos canais oficiais."
)
