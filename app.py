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
    # CSV do LotoAgora, compilado a partir dos resultados divulgados pela CAIXA.
    file_name = "lotofacil.csv" if lottery == "Lotofácil" else "mega-sena.csv"
    url = f"https://lotoagora.com.br/downloads/{file_name}"
    response = requests.get(url, headers=HEADERS, timeout=90)
    response.raise_for_status()
    if not response.content:
        raise ValueError("O arquivo histórico retornou vazio.")
    try:
        raw = pd.read_csv(io.BytesIO(response.content), sep=";", encoding="utf-8-sig")
    except Exception:
        raw = pd.read_csv(io.BytesIO(response.content), sep=None, engine="python", encoding="utf-8-sig")
    history = validate_history(raw, lottery)
    if history.empty:
        raise ValueError("O arquivo foi recebido, mas nenhuma linha válida foi encontrada.")
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

def combination_patterns(df, fields, lottery):
    cfg = LOTTERIES[lottery]
    rows = []
    pair_counts = Counter()
    triple_counts = Counter()
    parity_counts = Counter()
    repeat_counts = Counter()
    consecutive_counts = Counter()
    previous = None
    for _, row in df.iterrows():
        nums = sorted(int(row[c]) for c in fields)
        evens = sum(n % 2 == 0 for n in nums)
        parity_counts[f"{evens} pares / {len(nums)-evens} ímpares"] += 1
        for i in range(len(nums)-1):
            if nums[i+1] == nums[i] + 1:
                consecutive_counts["Pelo menos uma sequência consecutiva"] += 1
                break
        for i in range(len(nums)):
            for j in range(i+1, len(nums)):
                pair_counts[(nums[i], nums[j])] += 1
                for k in range(j+1, len(nums)):
                    triple_counts[(nums[i], nums[j], nums[k])] += 1
        if previous is not None:
            repeat_counts[len(set(nums) & previous)] += 1
        previous = set(nums)
    pairs = pd.DataFrame(
        [{"Dezena 1": k[0], "Dezena 2": k[1], "Ocorrências": v}
         for k, v in pair_counts.most_common(15)]
    )
    triples = pd.DataFrame(
        [{"Dezenas": " - ".join(map(str, k)), "Ocorrências": v}
         for k, v in triple_counts.most_common(15)]
    )
    parity = pd.DataFrame(
        [{"Distribuição": k, "Concursos": v}
         for k, v in parity_counts.most_common()]
    )
    repeats = pd.DataFrame(
        [{"Dezenas repetidas do concurso anterior": k, "Concursos": v}
         for k, v in sorted(repeat_counts.items())]
    )
    consecutive = int(consecutive_counts["Pelo menos uma sequência consecutiva"])
    return pairs, triples, parity, repeats, consecutive, len(pair_counts), len(triple_counts)


@st.cache_data(show_spinner=False)
def run_backtest(history, lottery, test_draws=100, training_window=200, tickets=10):
    cfg = LOTTERIES[lottery]
    fields = cfg["fields"]
    history = history.reset_index(drop=True)
    min_train = 30
    if len(history) <= min_train:
        raise ValueError("São necessários pelo menos 31 concursos para realizar o teste.")
    n_test = min(test_draws, len(history) - min_train)
    start = len(history) - n_test
    records = []
    for idx in range(start, len(history)):
        train_start = max(0, idx - training_window)
        train = history.iloc[train_start:idx]
        actual = set(int(v) for v in history.iloc[idx][fields].tolist())
        freq = count_numbers(train, fields, cfg["max"])
        row = {"Concurso": int(history.iloc[idx]["concurso"]) if "concurso" in history.columns else idx + 1}
        for mode in ["Equilibrado", "Aleatório"]:
            portfolio = create_games(lottery, freq, tickets, mode)
            hits = [len(set(game) & actual) for game in portfolio]
            row[f"{mode} - melhor acerto"] = max(hits)
            row[f"{mode} - média por jogo"] = float(np.mean(hits))
            threshold = 11 if lottery == "Lotofácil" else 4
            row[f"{mode} - concursos com faixa de prêmio"] = int(max(hits) >= threshold)
        records.append(row)
    return pd.DataFrame(records)

def create_games(lottery, freq, n_games=10, mode="Equilibrado", even_range=None, sum_range=None):
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
        even_count = sum(n % 2 == 0 for n in pick)
        total_sum = sum(pick)
        if even_range is not None and not (even_range[0] <= even_count <= even_range[1]):
            continue
        if sum_range is not None and not (sum_range[0] <= total_sum <= sum_range[1]):
            continue
        if pick not in seen:
            seen.add(pick)
            games.append(pick)
    return games

st.title("🎯 Loto Inteligência IA")
st.caption("Painel de análise estatística e simulação — versão 5")
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
    st.caption("Último resultado: Portal Loterias CAIXA. Histórico: CSV do LotoAgora, compilado a partir dos resultados divulgados pela CAIXA; cache de até 24 horas.")

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
    st.divider()
    st.subheader("Padrões históricos dos sorteios")
    st.caption("Estas tabelas descrevem o histórico selecionado; não indicam quais dezenas serão sorteadas.")
    pairs, triples, parity, repeats, consecutive, pair_total, triple_total = combination_patterns(df, fields, lottery)
    p1, p2, p3 = st.columns(3)
    p1.metric("Concursos com dezenas consecutivas", f"{consecutive:,}".replace(",", "."))
    p2.metric("Pares distintos no histórico", f"{pair_total:,}".replace(",", "."))
    p3.metric("Trincas distintas no histórico", f"{triple_total:,}".replace(",", "."))
    st.caption("As tabelas abaixo mostram os 15 pares e as 15 trincas mais frequentes; os indicadores contam todas as combinações distintas encontradas.")
    tab1, tab2, tab3, tab4 = st.tabs(["Pares mais frequentes", "Trincas mais frequentes", "Pares e ímpares", "Repetições entre concursos"])
    with tab1:
        st.dataframe(pairs, hide_index=True, use_container_width=True)
    with tab2:
        st.dataframe(triples, hide_index=True, use_container_width=True)
    with tab3:
        st.dataframe(parity, hide_index=True, use_container_width=True)
    with tab4:
        st.dataframe(repeats, hide_index=True, use_container_width=True)
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
st.subheader("Gerador de jogos")
st.write(f"**Custo de 1 jogo simples:** {money(cfg['price'])}")
game_count = st.selectbox("Quantidade de jogos que deseja gerar", [5, 10, 20], index=1)
st.write(f"**Investimento total para {game_count} jogos:** {money(cfg['price'] * game_count)}")
method = st.radio(
    "Método de simulação", ["Equilibrado", "Aleatório"], horizontal=True,
    help="Equilibrado usa ponderação muito leve das frequências históricas. Aleatório dá peso igual a todas as dezenas. Nenhum método prevê o sorteio."
)
even_max = cfg["draw"]
default_even = [max(0, cfg["draw"] // 3), min(even_max, (2 * cfg["draw"]) // 3)]
even_range = st.slider(
    "Quantidade de dezenas pares por jogo",
    min_value=0, max_value=even_max, value=default_even
)
min_sum = sum(range(cfg["min"], cfg["min"] + cfg["draw"]))
max_sum = sum(range(cfg["max"] - cfg["draw"] + 1, cfg["max"] + 1))
sum_range = st.slider(
    "Soma mínima e máxima das dezenas",
    min_value=min_sum, max_value=max_sum, value=(min_sum, max_sum)
)
st.caption("Os filtros restringem as combinações geradas; não aumentam a probabilidade matemática de acerto.")
if st.button(f"Gerar {game_count} jogos", type="primary"):
    games = create_games(lottery, freq, game_count, method, even_range, sum_range)
    if len(games) < game_count:
        st.warning(f"Foram encontradas apenas {len(games)} combinações com esses filtros. Amplie os intervalos e tente novamente.")
    st.session_state["games"] = games
    st.session_state["games_lottery"] = lottery
    st.session_state["games_method"] = method
    st.session_state["games_count"] = len(games)
    st.session_state["games_price"] = cfg["price"]

if st.session_state.get("games") and st.session_state.get("games_lottery") == lottery:
    generated_count = len(st.session_state["games"])
    st.caption(f"{generated_count} jogo(s) gerado(s) • Método: {st.session_state.get('games_method')} • Combinações únicas")
    st.write(f"**Investimento calculado:** {money(cfg['price'] * generated_count)}")
    for i, game in enumerate(st.session_state["games"], 1):
        st.write(f"**Jogo {i:02d}:** " + " · ".join(f"{n:02d}" for n in game))
    csv_games = pd.DataFrame(st.session_state["games"], columns=[f"dezena_{i}" for i in range(1, cfg["draw"] + 1)])
    st.download_button(
        "Baixar jogos em CSV", csv_games.to_csv(index=False).encode("utf-8"),
        file_name=f"jogos_{lottery.lower().replace('-', '')}.csv", mime="text/csv"
    )

st.divider()
st.subheader("Teste retrospectivo (backtesting)")
st.write(
    "Este teste simula o que teria acontecido em concursos passados. "
    "Em cada rodada, os jogos são montados usando somente concursos anteriores ao sorteio testado, "
    "sem consultar o resultado futuro para escolher as dezenas."
)
if full_df is not None and len(full_df) > 30:
    test_count = st.select_slider(
        "Quantidade de concursos anteriores para testar",
        options=[30, 50, 100, 200],
        value=100
    )
    training_count = st.selectbox(
        "Histórico usado para montar cada rodada",
        [100, 200, 500],
        index=1
    )
    if st.button("Executar backtesting", type="primary"):
        with st.spinner("Testando as simulações nos concursos anteriores..."):
            try:
                result_test = run_backtest(full_df, lottery, test_count, training_count, 10)
                st.session_state["backtest_result"] = result_test
                st.session_state["backtest_lottery"] = lottery
            except Exception as e:
                st.error(f"Não foi possível executar o teste: {e}")
    if st.session_state.get("backtest_lottery") == lottery and st.session_state.get("backtest_result") is not None:
        result_test = st.session_state["backtest_result"]
        summary_rows = []
        threshold = 11 if lottery == "Lotofácil" else 4
        for mode in ["Equilibrado", "Aleatório"]:
            summary_rows.append({
                "Método": mode,
                "Média do melhor jogo": round(result_test[f"{mode} - melhor acerto"].mean(), 2),
                "Média de acertos por aposta": round(result_test[f"{mode} - média por jogo"].mean(), 2),
                f"Concursos com ao menos um jogo de {threshold}+ acertos": int(result_test[f"{mode} - concursos com faixa de prêmio"].sum())
            })
        st.markdown("**Comparação dos métodos**")
        st.dataframe(pd.DataFrame(summary_rows), hide_index=True, use_container_width=True)
        st.markdown("**Melhor quantidade de acertos em cada concurso testado**")
        st.line_chart(result_test.set_index("Concurso")[[
            "Equilibrado - melhor acerto", "Aleatório - melhor acerto"
        ]])
        with st.expander("Ver resultado de cada concurso"):
            st.dataframe(result_test, hide_index=True, use_container_width=True)
        st.download_button(
            "Baixar relatório do backtesting em CSV",
            result_test.to_csv(index=False).encode("utf-8-sig"),
            file_name=f"backtesting_{lottery.lower().replace('-', '')}.csv",
            mime="text/csv"
        )
    st.caption(
        "A faixa mínima mostrada é 11 acertos na Lotofácil e 4 na Mega-Sena. "
        "O teste não calcula lucro líquido nem reproduz todas as regras de premiação. "
        "Resultados históricos não indicam maior chance em concursos futuros."
    )
else:
    st.info("Carregue um histórico com pelo menos 31 concursos para habilitar o backtesting.")

st.divider()
st.subheader("Probabilidade de acertar o prêmio principal")
total = comb(cfg["max"], cfg["draw"])
st.metric("Aposta simples", f"1 em {total:,}".replace(",", "."))
st.caption("Probabilidade matemática de uma combinação simples, independentemente dos resultados anteriores.")
st.caption("Fonte do histórico: LotoAgora (compilação de resultados divulgados pela CAIXA). Consulte a atribuição e a licença em lotoagora.com.br. Confira os resultados no portal oficial da CAIXA.")
st.caption("Projeto experimental e independente, sem vínculo com a CAIXA.")
