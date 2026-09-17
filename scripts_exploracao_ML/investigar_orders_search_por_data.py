# scripts_exploracao_ML/investigar_orders_search_por_data.py
#
# Objetivo ÚNICO: testar GET /orders/search filtrado só por data (janela curta,
# ex: últimos 7 dias), pra ver na prática (a) quantos pedidos existem numa janela
# pequena, (b) se os campos de nome do comprador (first_name/last_name/nickname)
# e algum dado de endereço aparecem no corpo de cada pedido retornado -- mesmo que
# a documentação confirme que NÃO são pesquisáveis via parâmetro de busca -- e
# (c) QUANTO TEMPO a chamada leva pra responder.
#
# O item (c) decide uma coisa importante: se a chamada for rápida, dá pra pensar
# numa busca ao vivo (sem sincronizar/persistir nada -- chama a API na hora que
# a colega digitar o nome/endereço, filtra em memória, mostra candidatos). Se for
# lenta, essa opção cai fora também, e não sobra alternativa via API do ML.
#
# Isso é só levantamento de dados pra decidir o próximo passo -- não decide nada
# por conta própria, só mostra o que a API realmente devolve e em quanto tempo.
#
# Só leitura. Não toca no banco. Sobrescreve o arquivo de saída (nunca
# acrescenta) a cada execução.

import json
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

_RAIZ_DO_PROJETO = Path(__file__).resolve().parent.parent
if str(_RAIZ_DO_PROJETO) not in sys.path:
    sys.path.insert(0, str(_RAIZ_DO_PROJETO))

from api_mercado_livre.core.estrutura_api.cliente_api import chamar_api, ErroAPI, ErroAutenticacaoAPI

# ==== CONFIGURA AQUI ANTES DE RODAR ====
CONTA = "MB"    # "MB" (Magazine) ou "SV" (Samvale) -- troque pra investigar a outra conta
DIAS_ATRAS = 7  # tamanho da janela -- comece pequeno mesmo, é só pra ver a forma do dado
LIMITE = 50     # quantos pedidos trazer no máximo (o "paging.total" mostra se tem mais que isso)
# ========================================

PASTA_LOGS = Path(__file__).resolve().parent / "logs"
CAMINHO_SAIDA = Path(__file__).resolve().parent / f"investigacao_orders_search_por_data_{CONTA}.json"
FUSO_HORARIO_EXIBICAO = ZoneInfo("America/Sao_Paulo")


def formatar_data_para_filtro(instante):
    """Mesmo formato já usado nos outros scripts pra filtro de data/range da API:
    milissegundos obrigatórios, offset sem dois-pontos (ex: 2026-09-10T00:00:00.000-0300).
    NOTA: a doc que consultamos não confirmou esse formato especificamente pra
    'order.date_created.from/to' -- se a API recusar com erro de formato, é o
    primeiro lugar a suspeitar."""
    texto = instante.isoformat(timespec="milliseconds")
    return texto[:-6] + texto[-6:].replace(":", "")


agora = datetime.now(FUSO_HORARIO_EXIBICAO)
inicio_janela = agora - timedelta(days=DIAS_ATRAS)

tempo_inicio_total = time.perf_counter()

try:
    # Passo 1 (pré-requisito): descobrir o próprio user_id -- o filtro "seller"
    # do /orders/search exige esse número.
    tempo_inicio_me = time.perf_counter()
    resposta_me = chamar_api(
        "GET", "/users/me",
        pasta_logs=PASTA_LOGS, conta=CONTA,
        nome_log="investigar_orders_search_por_data",
    )
    tempo_users_me = time.perf_counter() - tempo_inicio_me
    user_id = resposta_me.json()["id"]
    print(f"Conta {CONTA} -- user_id descoberto: {user_id} (levou {tempo_users_me:.2f}s)")
    print(f"Janela de busca: {inicio_janela.strftime('%d/%m/%Y %H:%M')} até {agora.strftime('%d/%m/%Y %H:%M')} ({DIAS_ATRAS} dias)")

    # Passo 2 (o que interessa, incluindo QUANTO TEMPO leva): buscar os pedidos
    # criados nessa janela.
    tempo_inicio_search = time.perf_counter()
    resposta_orders = chamar_api(
        "GET", "/orders/search",
        pasta_logs=PASTA_LOGS, conta=CONTA,
        params={
            "seller": user_id,
            "order.date_created.from": formatar_data_para_filtro(inicio_janela),
            "order.date_created.to": formatar_data_para_filtro(agora),
            "sort": "date_desc",
            "limit": LIMITE,
        },
        nome_log="investigar_orders_search_por_data",
    )
    tempo_orders_search = time.perf_counter() - tempo_inicio_search
except (ErroAPI, ErroAutenticacaoAPI) as erro:
    tempo_total = time.perf_counter() - tempo_inicio_total
    print(f"Erro ao chamar a API (depois de {tempo_total:.2f}s no total): {erro}")
else:
    tempo_total = time.perf_counter() - tempo_inicio_total
    resultado_cru = resposta_orders.json()
    pedidos = resultado_cru.get("results", [])
    total_na_janela = (resultado_cru.get("paging") or {}).get("total")

    print(f"\n/orders/search levou {tempo_orders_search:.2f}s pra responder (janela de {DIAS_ATRAS} dias, limite {LIMITE}).")
    print(f"Tempo total do script (users/me + orders/search): {tempo_total:.2f}s.")
    print(f"\nTotal de pedidos na janela (segundo a API): {total_na_janela}")
    print(f"Pedidos trazidos nesta chamada: {len(pedidos)}\n")

    # Preview rápido no terminal -- só pra ver de cara se nome/endereço aparecem.
    for pedido in pedidos:
        comprador = pedido.get("buyer") or {}
        nome = f"{comprador.get('first_name', '')} {comprador.get('last_name', '')}".strip()
        envio = pedido.get("shipping") or {}
        print(
            f"- pedido {pedido.get('id')} | {pedido.get('date_created')} | "
            f"nickname={comprador.get('nickname')} | nome={nome or '(vazio)'} | "
            f"shipping_id={envio.get('id')}"
        )

    # Salva o retorno cru completo (sem reduzir campos, já que ainda estamos
    # descobrindo a forma do dado) -- só oculta o seu próprio user_id, e guarda
    # os tempos medidos junto pra referência futura.
    resultado_com_tempos = {
        "tempo_users_me_segundos": round(tempo_users_me, 3),
        "tempo_orders_search_segundos": round(tempo_orders_search, 3),
        "tempo_total_segundos": round(tempo_total, 3),
        "dias_atras": DIAS_ATRAS,
        "limite": LIMITE,
        "resultado_api": resultado_cru,
    }
    texto_json = json.dumps(resultado_com_tempos, ensure_ascii=False, indent=2)
    texto_json_oculto = texto_json.replace(str(user_id), "SEU_USER_ID_OCULTO")

    with open(CAMINHO_SAIDA, "w", encoding="utf-8") as f:
        f.write(texto_json_oculto)

    print(f"\nRetorno completo (com os tempos medidos) salvo em: {CAMINHO_SAIDA}")
    print("Suba esse arquivo (ou cola o preview acima) na conversa pra eu analisar.")