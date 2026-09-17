# scripts_exploracao_ML/descobrir_buyer_id_do_pedido.py
#
# Objetivo ÚNICO: dado um número de pedido que você já sabe ter devolução
# (relatório real), buscar GET /orders/$ORDER_ID e extrair o buyer.id --
# pra depois usar esse buyer_id em consultar_pedidos_por_cliente.py e testar
# a classificação em clientes diferentes do Rafael.
#
# Só leitura. Não toca no banco.

import argparse
import sys
from pathlib import Path

_RAIZ_DO_PROJETO = Path(__file__).resolve().parent.parent
if str(_RAIZ_DO_PROJETO) not in sys.path:
    sys.path.insert(0, str(_RAIZ_DO_PROJETO))

from api_mercado_livre.core.estrutura_api.cliente_api import chamar_api, ErroAPI, ErroAutenticacaoAPI


def ler_argumentos():
    parser = argparse.ArgumentParser(description="Descobre o buyer_id de um pedido conhecido.")
    parser.add_argument("--empresa", type=str, required=True, choices=["MB", "SV"])
    parser.add_argument("--pedido", type=str, required=True, dest="pedido")
    args = parser.parse_args()
    return args.empresa, args.pedido


CONTA, PEDIDO = ler_argumentos()
PASTA_LOGS = Path(__file__).resolve().parent / "logs"

try:
    resposta = chamar_api(
        "GET", f"/orders/{PEDIDO}",
        pasta_logs=PASTA_LOGS, conta=CONTA,
        nome_log="descobrir_buyer_id_do_pedido",
    )
except (ErroAPI, ErroAutenticacaoAPI) as erro:
    print(f"Erro ao chamar a API: {erro}")
else:
    pedido = resposta.json()
    comprador = pedido.get("buyer") or {}
    nome = f"{comprador.get('first_name', '')} {comprador.get('last_name', '')}".strip()

    print(f"Pedido {PEDIDO}")
    print(f"Cliente: {nome or '(nome vazio)'}")
    print(f"Nickname: {comprador.get('nickname')}")
    print(f"buyer_id: {comprador.get('id')}")