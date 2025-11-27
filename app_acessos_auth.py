import streamlit as st
import pandas as pd
import os
from itertools import combinations

# ---------------------------------------------------------
# CONFIGURAÇÃO GERAL DO APP
# ---------------------------------------------------------
st.set_page_config(
    page_title="Comparativo de Perfis de Acesso",
    layout="wide"
)

# 🔗 URLs dos arquivos no GitHub (use links RAW)
GITHUB_LUCASV_URL = "https://github.com/chaosmastersp/cta/blob/main/LUCASV.xlsx"
GITHUB_CONFLITOS_URL = "https://github.com/chaosmastersp/cta/blob/main/Perfis%20Conflitantes.xlsx"

# Helper para rerun compatível (novas/antigas versões do Streamlit)
def do_rerun():
    rerun = getattr(st, "rerun", None)
    if rerun is not None:
        rerun()
    else:
        st.experimental_rerun()

# ---------------------------------------------------------
# AUTENTICAÇÃO (usuário/senha)
# ---------------------------------------------------------
def get_credentials():
    """
    Recupera usuário e senha a partir de:
    1) st.secrets
    2) variáveis de ambiente
    3) valores padrão (apenas para desenvolvimento local)
    """
    user = None
    password = None

    # 1) Tenta pegar de st.secrets
    try:
        user = st.secrets.get("APP_USER", None)
        password = st.secrets.get("APP_PASSWORD", None)
    except Exception:
        pass

    # 2) Se não existir em secrets, tenta variáveis de ambiente
    if user is None:
        user = os.getenv("APP_USER")
    if password is None:
        password = os.getenv("APP_PASSWORD")

    # 3) Se ainda assim vier vazio, usa default (recomendado trocar)
    if user is None:
        user = "admin"
    if password is None:
        password = "1234"

    return user, password


def login_form():
    st.title("🔐 Login - Dashboard de Acessos por Perfil")

    with st.form("login_form"):
        username = st.text_input("Usuário")
        password = st.text_input("Senha", type="password")
        submitted = st.form_submit_button("Entrar")

    if submitted:
        valid_user, valid_pass = get_credentials()
        if username == valid_user and password == valid_pass:
            st.session_state["authenticated"] = True
            st.session_state["username"] = username
            st.success("Login realizado com sucesso!")
            do_rerun()
        else:
            st.error("Usuário ou senha inválidos.")


def require_login():
    if "authenticated" not in st.session_state:
        st.session_state["authenticated"] = False

    if not st.session_state["authenticated"]:
        login_form()
        st.stop()


# ---------------------------------------------------------
# LEITURA DE DADOS DIRETO DO GITHUB
# ---------------------------------------------------------
@st.cache_data
def carregar_base_lucasv() -> pd.DataFrame:
    # Lê a planilha de acessos (LUCASV.xlsx) direto do GitHub
    df = pd.read_excel(GITHUB_LUCASV_URL)
    cols_esperadas = ["Grupo", "Tp.Sistema", "Sistema", "Módulo", "Menu"]
    faltando = [c for c in cols_esperadas if c not in df.columns]
    if faltando:
        raise ValueError(f"Colunas faltando na base LUCASV: {faltando}")
    return df[cols_esperadas].drop_duplicates()


@st.cache_data
def carregar_conflitos() -> pd.DataFrame:
    """
    Lê a planilha Perfis Conflitantes direto do GitHub:
    - Localiza a linha em que aparecem "PERFIL I" e "PERFIL II"
    - Considera as linhas abaixo como: PERFIL I, PERFIL II, MOTIVO
    """
    conf_raw = pd.read_excel(GITHUB_CONFLITOS_URL, header=None)
    # Localiza cabeçalho
    header_idx = conf_raw.index[
        (conf_raw[1] == "PERFIL I") & (conf_raw[2] == "PERFIL II")
    ][0]

    conf = conf_raw.loc[header_idx+1:, [1, 2, 3]].copy()
    conf.columns = ["Perfil1", "Perfil2", "Motivo"]
    conf = conf.dropna(subset=["Perfil1", "Perfil2"])
    return conf


def calcular_conflitos_para_selecionados(base, conf_df, perfis_selecionados):
    """
    base: DataFrame com colunas [Grupo, Tp.Sistema, Sistema, Módulo, Menu]
    conf_df: DataFrame com colunas [Perfil1, Perfil2, Motivo]
    perfis_selecionados: lista de perfis (grupos) escolhidos no painel

    Retorna:
    - matriz (DataFrame) com colunas dos perfis selecionados + info de conflito
    - perfil_to_set
    - exclusivos_por_perfil
    - acessos_comuns_set
    - conflicts_df (DataFrame) detalhado dos conflitos para os perfis selecionados
    """
    # Todas as combinações possíveis
    combos = base[["Tp.Sistema", "Sistema", "Módulo", "Menu"]].drop_duplicates().reset_index(drop=True)
    combos["combo_key"] = combos[["Tp.Sistema", "Sistema", "Módulo", "Menu"]].astype(str).agg("||".join, axis=1)

    # Mapeia combo_key -> perfis (Grupos) que têm esse acesso
    base_combo = base.copy()
    base_combo["combo_key"] = base_combo[["Tp.Sistema", "Sistema", "Módulo", "Menu"]].astype(str).agg("||".join, axis=1)
    combo_to_perfis = base_combo.groupby("combo_key")["Grupo"].unique()

    # Mapeia perfil -> conjunto de combos
    perfil_to_set = {}
    for perfil in perfis_selecionados:
        df_p = base[base["Grupo"] == perfil]
        perfil_to_set[perfil] = set(
            tuple(row)
            for row in df_p[["Tp.Sistema", "Sistema", "Módulo", "Menu"]].to_numpy()
        )

    # Acessos comuns a TODOS os perfis
    acessos_comuns_set = set.intersection(*perfil_to_set.values())

    # Exclusivos por perfil
    exclusivos_por_perfil = {}
    for perfil in perfis_selecionados:
        outros = [p for p in perfis_selecionados if p != perfil]
        union_outros = set().union(*(perfil_to_set[p] for p in outros))
        exclusivos_por_perfil[perfil] = perfil_to_set[perfil] - union_outros

    # Matriz de presença (✔️ / vazio)
    matriz = combos[["Tp.Sistema", "Sistema", "Módulo", "Menu"]].copy()
    for perfil in perfis_selecionados:
        s = perfil_to_set[perfil]
        matriz[perfil] = matriz[["Tp.Sistema", "Sistema", "Módulo", "Menu"]].apply(
            lambda r: "✔️" if tuple(r) in s else "",
            axis=1
        )

    # ----------------- Lógica de conflitos -----------------
    selected_set = set(perfis_selecionados)

    conf_filtered = conf_df[
        conf_df["Perfil1"].isin(selected_set) &
        conf_df["Perfil2"].isin(selected_set)
    ].copy()

    if conf_filtered.empty:
        matriz["Conflito?"] = ""
        matriz["Perfis em Conflito"] = ""
        conflicts_df = pd.DataFrame(columns=[
            "Perfil1", "Perfil2", "Motivo",
            "Tp.Sistema", "Sistema", "Módulo", "Menu"
        ])
        return matriz, perfil_to_set, exclusivos_por_perfil, acessos_comuns_set, conflicts_df

    # Mapeia par de perfis em conflito -> motivo(s)
    conf_pair_motivo = {}
    for _, row in conf_filtered.iterrows():
        key = frozenset({row["Perfil1"], row["Perfil2"]})
        conf_pair_motivo.setdefault(key, set()).add(str(row["Motivo"]))

    # Para cada combo, verifica se há algum par de perfis em conflito com esse acesso
    combo_conflicts = {}  # combo_key -> lista de dicts {Perfil1, Perfil2, Motivo}
    from itertools import combinations
    for combo_key, perfis in combo_to_perfis.items():
        perfis_sel = [p for p in perfis if p in selected_set]
        if len(perfis_sel) < 2:
            continue
        for p1, p2 in combinations(perfis_sel, 2):
            key = frozenset({p1, p2})
            if key in conf_pair_motivo:
                motivos = " | ".join(sorted(conf_pair_motivo[key]))
                combo_conflicts.setdefault(combo_key, []).append(
                    {"Perfil1": p1, "Perfil2": p2, "Motivo": motivos}
                )

    # Monta colunas de conflito na matriz
    conflito_flag = []
    conflito_descr = []
    for _, row in combos.iterrows():
        ck = row["combo_key"]
        if ck in combo_conflicts:
            conflito_flag.append("⚠️")
            pair_strings = sorted(
                set(f"{c['Perfil1']} x {c['Perfil2']}" for c in combo_conflicts[ck])
            )
            conflito_descr.append("; ".join(pair_strings))
        else:
            conflito_flag.append("")
            conflito_descr.append("")

    matriz["Conflito?"] = conflito_flag
    matriz["Perfis em Conflito"] = conflito_descr

    # DataFrame detalhado de conflitos
    registros = []
    for _, row in combos.iterrows():
        ck = row["combo_key"]
        if ck not in combo_conflicts:
            continue
        for c in combo_conflicts[ck]:
            registros.append({
                "Perfil1": c["Perfil1"],
                "Perfil2": c["Perfil2"],
                "Motivo": c["Motivo"],
                "Tp.Sistema": row["Tp.Sistema"],
                "Sistema": row["Sistema"],
                "Módulo": row["Módulo"],
                "Menu": row["Menu"],
            })

    conflicts_df = pd.DataFrame(registros)

    return matriz, perfil_to_set, exclusivos_por_perfil, acessos_comuns_set, conflicts_df


# ---------------------------------------------------------
# DASHBOARD PRINCIPAL
# ---------------------------------------------------------
def mostrar_dashboard():
    st.title("🔐 Dashboard de Acessos por Perfil (Grupo) com Conflitos")

    # Barra lateral: usuário logado + logout
    with st.sidebar:
        st.markdown("### 👤 Usuário logado")
        st.write(st.session_state.get("username", ""))
        if st.button("Sair"):
            st.session_state["authenticated"] = False
            st.session_state["username"] = ""
            do_rerun()

        st.markdown("---")
        st.markdown("### 📂 Fontes de dados")
        st.caption("Lendo automaticamente de:")
        st.code(f"LUCASV: {GITHUB_LUCASV_URL}", language="text")
        st.code(f"Conflitos: {GITHUB_CONFLITOS_URL}", language="text")

    st.markdown(
        """
        Este painel compara acessos entre perfis (coluna **Grupo** da base LUCASV) 
        e destaca **conflitos de segregação de funções** com base na planilha 
        **Perfis Conflitantes**, ambas lidas diretamente do GitHub.
        """
    )

    # -----------------------------
    # Carrega dados direto do GitHub
    # -----------------------------
    try:
        base = carregar_base_lucasv()
    except Exception as e:
        st.error(f"Erro ao ler LUCASV do GitHub: {e}")
        return

    try:
        conf_df = carregar_conflitos()
    except Exception as e:
        st.error(f"Erro ao ler Perfis Conflitantes do GitHub: {e}")
        conf_df = pd.DataFrame(columns=["Perfil1", "Perfil2", "Motivo"])

    # -----------------------------
    # Seleção de perfis
    # -----------------------------
    st.sidebar.header("🎯 Seleção de Perfis (Grupo)")
    todos_perfis = sorted(base["Grupo"].unique())

    perfis_selecionados = st.sidebar.multiselect(
        "Selecione 2 ou mais perfis para comparar:",
        options=todos_perfis,
        default=todos_perfis[:2] if len(todos_perfis) >= 2 else None
    )

    if len(perfis_selecionados) < 2:
        st.warning("Selecione **pelo menos 2 perfis** para realizar o comparativo.")
        return

    # -----------------------------
    # Cálculos de matriz e conflitos
    # -----------------------------
    matriz, perfil_to_set, exclusivos_por_perfil, acessos_comuns_set, conflicts_df = \
        calcular_conflitos_para_selecionados(base, conf_df, perfis_selecionados)

    # -----------------------------
    # Resumo numérico
    # -----------------------------
    st.subheader("📊 Resumo dos Perfis Selecionados")

    cols_resumo = st.columns(len(perfis_selecionados) + 2)

    # Caixa de resumo por perfil
    for i, perfil in enumerate(perfis_selecionados):
        total = len(perfil_to_set[perfil])
        exclusivos = len(exclusivos_por_perfil[perfil])
        cols_resumo[i].metric(
            label=f"{perfil}",
            value=f"{total} acessos",
            delta=f"{exclusivos} exclusivos"
        )

    # Acessos comuns
    cols_resumo[len(perfis_selecionados)].metric(
        label="Acessos Iguais (Comuns a todos)",
        value=len(acessos_comuns_set)
    )

    # Total de linhas com conflito
    total_conflitos = 0 if conflicts_df is None or conflicts_df.empty else conflicts_df.shape[0]
    cols_resumo[len(perfis_selecionados)+1].metric(
        label="Registros em Conflito (combinações)",
        value=total_conflitos
    )

    st.markdown("---")

    # -----------------------------
    # Tabs de visualização
    # -----------------------------
    tab_geral, tab_iguais, tab_exclusivos, tab_matriz, tab_conflitos = st.tabs(
        [
            "🔎 Visão Geral",
            "✅ Acessos Iguais",
            "🧩 Acessos Exclusivos",
            "📋 Matriz Completa",
            "⚠️ Conflitos"
        ]
    )

    # ---- Tab Visão Geral ----
    with tab_geral:
        st.markdown("### 🔎 Amostra da Base Filtrada por Perfis Selecionados")
        st.dataframe(
            base[base["Grupo"].isin(perfis_selecionados)]
            .sort_values(["Grupo", "Tp.Sistema", "Sistema", "Módulo", "Menu"])
            .reset_index(drop=True),
            use_container_width=True
        )

    # ---- Tab Acessos Iguais ----
    with tab_iguais:
        st.markdown("### ✅ Acessos Iguais entre TODOS os perfis selecionados")
        if len(acessos_comuns_set) == 0:
            st.info("Não há acessos comuns a todos os perfis selecionados.")
        else:
            df_comuns = pd.DataFrame(
                list(acessos_comuns_set),
                columns=["Tp.Sistema", "Sistema", "Módulo", "Menu"]
            ).sort_values(["Tp.Sistema", "Sistema", "Módulo", "Menu"])
            st.dataframe(df_comuns, use_container_width=True)

    # ---- Tab Acessos Exclusivos ----
    with tab_exclusivos:
        st.markdown("### 🧩 Acessos Exclusivos por Perfil (ausentes nos demais)")
        for perfil in perfis_selecionados:
            st.markdown(f"#### Perfil: **{perfil}**")
            exclusivos_set = exclusivos_por_perfil[perfil]
            if len(exclusivos_set) == 0:
                st.info("Nenhum acesso exclusivo para este perfil entre os selecionados.")
            else:
                df_exc = pd.DataFrame(
                    list(exclusivos_set),
                    columns=["Tp.Sistema", "Sistema", "Módulo", "Menu"]
                ).sort_values(["Tp.Sistema", "Sistema", "Módulo", "Menu"])
                st.dataframe(df_exc, use_container_width=True)

    # ---- Tab Matriz Completa ----
    with tab_matriz:
        st.markdown(
            """
            ### 📋 Matriz Completa de Acessos  
            - ✔️ indica que o perfil possui aquela combinação de **Tp.Sistema, Sistema, Módulo, Menu**  
            - Coluna **Conflito?**: ⚠️ quando há pelo menos um par de perfis em conflito nessa linha  
            - Coluna **Perfis em Conflito**: exibe os pares de perfis conflitantes
            """
        )
        matriz_exibe = matriz.sort_values(
            ["Tp.Sistema", "Sistema", "Módulo", "Menu"]
        ).reset_index(drop=True)
        st.dataframe(matriz_exibe, use_container_width=True)

    # ---- Tab Conflitos ----
    with tab_conflitos:
        st.markdown("### ⚠️ Detalhamento dos Conflitos de Acesso")

        if conflicts_df is None or conflicts_df.empty:
            st.info("Nenhum conflito encontrado para os perfis selecionados (com base na matriz enviada).")
        else:
            df_conf_show = conflicts_df.sort_values(
                ["Perfil1", "Perfil2", "Tp.Sistema", "Sistema", "Módulo", "Menu"]
            ).reset_index(drop=True)
            st.dataframe(df_conf_show, use_container_width=True)

            st.markdown("#### Resumo por Par de Perfis em Conflito")
            resumo_pares = (
                df_conf_show
                .groupby(["Perfil1", "Perfil2"])["Menu"]
                .count()
                .reset_index()
                .rename(columns={"Menu": "Qtd Combinações em Conflito"})
                .sort_values("Qtd Combinações em Conflito", ascending=False)
            )
            st.dataframe(resumo_pares, use_container_width=True)


# ---------------------------------------------------------
# MAIN
# ---------------------------------------------------------
def main():
    require_login()
    mostrar_dashboard()


if __name__ == "__main__":
    main()
