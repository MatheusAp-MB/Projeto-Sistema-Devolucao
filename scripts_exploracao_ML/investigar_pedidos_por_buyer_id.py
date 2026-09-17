# scripts_exploracao_ML/investigar_pedidos_por_buyer_id.py
#
# Objetivo ÚNICO: usar o buyer_id suspeito (achado testando GET /users/{id})
# como filtro "buyer" no GET /orders/search da própria conta, pra ver se
# existe(m) pedido(s) reais desse comprador pra MB -- e comparar o endereço
# de entrega de cada um com o da etiqueta física (Rua Ubirajara Sávio Torres
# 354, Fazenda Velha, Araucária-PR), pra confirmar de ponta a ponta se
# "#443851581" na etiqueta É o buyer.id do comprador.
#
# Só leitura. Não toca no banco.

import json
import sys
from pathlib import Path

_RAIZ_DO_PROJETO = Path(__file__).resolve().parent.parent
if str(_RAIZ_DO_PROJETO) not in sys.path:
    sys.path.insert(0, str(_RAIZ_DO_PROJETO))

from api_mercado_livre.core.estrutura_api.cliente_api import chamar_api, ErroAPI, ErroAutenticacaoAPI

# ==== CONFIGURA AQUI ANTES DE RODAR ====
CONTA = "MB"                     # a etiqueta é da Magazine Brasileiro -- mantém MB
BUYER_ID_SUSPEITO = "443851581"  # o código da etiqueta, já confirmado como user_id real (RAPHA048)
# ========================================

PASTA_LOGS = Path(__file__).resolve().parent / "logs"


def buscar_endereco_do_envio(shipping_id, conta):
    """Busca o endereço de destino do envio, pra comparar com o da etiqueta física."""
    if not shipping_id:
        return None
    try:
        resposta = chamar_api(
            "GET", f"/shipments/{shipping_id}",
            pasta_logs=PASTA_LOGS, conta=conta,
            nome_log="investigar_pedidos_por_buyer_id",
        )
    except (ErroAPI, ErroAutenticacaoAPI):
        return None
    return resposta.json().get("receiver_address")


try:
    resposta_me = chamar_api(
        "GET", "/users/me",
        pasta_logs=PASTA_LOGS, conta=CONTA,
        nome_log="investigar_pedidos_por_buyer_id",
    )
    seller_id = resposta_me.json()["id"]

    resposta_orders = chamar_api(
        "GET", "/orders/search",
        pasta_logs=PASTA_LOGS, conta=CONTA,
        params={
            "seller": seller_id,
            "buyer": BUYER_ID_SUSPEITO,
            "sort": "date_desc",
        },
        nome_log="investigar_pedidos_por_buyer_id",
    )
except (ErroAPI, ErroAutenticacaoAPI) as erro:
    print(f"Erro ao chamar a API: {erro}")
else:
    resultado = resposta_orders.json()
    pedidos = resultado.get("results", [])
    total = (resultado.get("paging") or {}).get("total")

    print(f"Total de pedidos desse buyer_id pra essa conta: {total}\n")

    for pedido in pedidos:
        item = (pedido.get("order_items") or [{}])[0]
        titulo = (item.get("item") or {}).get("title", "—")
        shipping_id = (pedido.get("shipping") or {}).get("id")
        endereco = buscar_endereco_do_envio(shipping_id, CONTA)

        print(f"- pedido {pedido.get('id')} | {pedido.get('date_created')} | item: {titulo}")
        if endereco:
            print(
                f"  endereço de entrega: {endereco.get('address_line')}, "
                f"{endereco.get('city', {}).get('name')} - {endereco.get('state', {}).get('name')}, "
                f"CEP {endereco.get('zip_code')}"
            )
        else:
            print("  (não foi possível obter o endereço desse envio)")

    print(f"\nCompare o(s) endereço(s) acima com o da etiqueta: "
          f"Rua Ubirajara Sávio Torres 354, Fazenda Velha, Araucária, BR-PR, CEP 83704901.")