import streamlit as st
import pandas as pd
import os

# ---------------------------------------------------------
# Configuração básica do app
# ---------------------------------------------------------
st.set_page_config(
    page_title="Comparativo de Perfis de Acesso",
    layout="wide"
)

# ---------------------------------------------------------
# Autenticação simples por usuário/senha
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
            st.experimental_rerun()
        else:
            st.error("Usuário ou senha inválidos.")


def require_login():
    if "authenticated" not in st.session_state:
        st.session_state["authenticated"] = False

    if not st.session_state["authenticated"]:
        login_form()
        st.stop()


# ---------------------------------------------------------
# Funções de dados / dashboard
# ---------------------------------------------------------

@st.cache_data
def carregar_base(file) -> pd.DataFrame:
    df = pd.read_excel(file)
    # Garante colunas esperadas
    cols_esperadas = ["Grupo", "Tp.Sistema", "Sistema", "Módulo", "Menu"]
    faltando = [c for c in cols_esperadas if c not in df.columns]
    if faltando:
        raise ValueError(f"Colunas faltando na base: {faltando}")
    # Tira duplicados por segurança
    df = df[cols_esperadas].drop_duplicates()
    return df


def mostrar_dashboard():
    st.title("🔐 Dashboard de Acessos por Perfil (Grupo)")

    st.markdown(
        """
        Este painel utiliza a base **LUCASV.xlsx** para comparar acessos entre perfis (coluna **Grupo**), 
        considerando as combinações de **Tp.Sistema, Sistema, Módulo, Menu**.
        """
    )

    # Barra superior com usuário logado e botão de logout
    with st.sidebar:
        st.markdown("### 👤 Usuário logado")
        st.write(st.session_state.get("username", ""))
        if st.button("Sair"):
            st.session_state["authenticated"] = False
            st.session_state["username"] = ""
            st.experimental_rerun()

    # -----------------------------
    # Leitura da base
    # -----------------------------
    st.sidebar.header("📂 Arquivo de Dados")

    upload = st.sidebar.file_uploader(
        "Envie o arquivo LUCASV.xlsx",
        type=["xlsx"],
        help="Use a mesma estrutura de colunas: Grupo, Tp.Sistema, Sistema, Módulo, Menu."
    )

    if upload is None:
        st.info("Envie o arquivo **LUCASV.xlsx** na barra lateral para iniciar a análise.")
        return

    try:
        base = carregar_base(upload)
    except Exception as e:
        st.error(f"Erro ao ler o arquivo: {e}")
        return

    # -----------------------------
    # Seleção de perfis
    # -----------------------------
    st.sidebar.header("🎯 Seleção de Perfis (Grupo)")

    todos_perfis = sorted(base["Grupo"].unique())
    if len(todos_perfis) == 0:
        st.warning("Nenhum perfil encontrado na coluna 'Grupo'.")
        return

    perfis_selecionados = st.sidebar.multiselect(
        "Selecione 2 ou mais perfis para comparar:",
        options=todos_perfis,
        default=todos_perfis[:2] if len(todos_perfis) >= 2 else None
    )

    if len(perfis_selecionados) < 2:
        st.warning("Selecione **pelo menos 2 perfis** para realizar o comparativo.")
        return

    # -----------------------------
    # Preparação das combinações
    # -----------------------------
    # Cada combinação é: (Tp.Sistema, Sistema, Módulo, Menu)
    combos = base[["Tp.Sistema", "Sistema", "Módulo", "Menu"]].drop_duplicates().reset_index(drop=True)

    # Mapeia perfil -> conjunto de combinações
    perfil_to_set = {}
    for perfil in perfis_selecionados:
        df_p = base[base["Grupo"] == perfil]
        perfil_to_set[perfil] = set(
            tuple(row)
            for row in df_p[["Tp.Sistema", "Sistema", "Módulo", "Menu"]].to_numpy()
        )

    # Interseção: acessos comuns a TODOS os perfis selecionados
    acessos_comuns_set = set.intersection(*perfil_to_set.values())

    # Exclusivos por perfil: o que só ele tem entre os selecionados
    exclusivos_por_perfil = {}
    for perfil in perfis_selecionados:
        outros = [p for p in perfis_selecionados if p != perfil]
        union_outros = set().union(*(perfil_to_set[p] for p in outros))
        exclusivos_por_perfil[perfil] = perfil_to_set[perfil] - union_outros

    # Matriz de presença (✔️ / vazio)
    matriz = combos.copy()
    for perfil in perfis_selecionados:
        s = perfil_to_set[perfil]
        matriz[perfil] = matriz[["Tp.Sistema", "Sistema", "Módulo", "Menu"]].apply(
            lambda r: "✔️" if tuple(r) in s else "",
            axis=1
        )

    # -----------------------------
    # Resumo numérico
    # -----------------------------
    st.subheader("📊 Resumo dos Perfis Selecionados")

    cols_resumo = st.columns(len(perfis_selecionados) + 1)

    # Caixa de resumo por perfil
    for i, perfil in enumerate(perfis_selecionados):
        total = len(perfil_to_set[perfil])
        exclusivos = len(exclusivos_por_perfil[perfil])
        cols_resumo[i].metric(
            label=f"{perfil}",
            value=f"{total} acessos",
            delta=f"{exclusivos} exclusivos"
        )

    # Métrica de acessos comuns
    cols_resumo[-1].metric(
        label="Acessos Iguais (Comuns a todos)",
        value=len(acessos_comuns_set)
    )

    st.markdown("---")

    # -----------------------------
    # Tabs de visualização
    # -----------------------------
    tab_geral, tab_iguais, tab_exclusivos, tab_matriz = st.tabs(
        ["🔎 Visão Geral", "✅ Acessos Iguais", "🧩 Acessos Exclusivos", "📋 Matriz Completa"]
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
            ✔️ indica que o perfil possui aquela combinação de **Tp.Sistema, Sistema, Módulo, Menu**.
            """
        )
        st.dataframe(
            matriz.sort_values(["Tp.Sistema", "Sistema", "Módulo", "Menu"]).reset_index(drop=True),
            use_container_width=True
        )


# ---------------------------------------------------------
# Fluxo principal
# ---------------------------------------------------------
def main():
    require_login()
    mostrar_dashboard()


if __name__ == "__main__":
    main()
