# scripts_exploracao_ML/testar_preco_unitario_pedido.py
#
# Objetivo: testar SÓ o retorno da API pro campo de preço do pedido, antes
# de implementar de verdade o campo "Preço do produto" (pedido de Ana,
# 19/09/2026 -- conta "preço do produto - valor reembolsado").
#
# A doc oficial (Orders.html, conferida em 19/09/2026) diz que o campo é
# order_items[0].unit_price -- no MESMO nível de "quantity" e "currency_id",
# não dentro de order_items[0].item (que é onde title/seller_sku ficam).
# Esse script só confere isso contra um pedido real: imprime o bloco
# order_items inteiro (cru) e depois a extração específica que o código de
# verdade vai usar, lado a lado, pra bater o olho e confirmar.
#
# Só leitura. Não toca no banco. Não salva nada em disco -- só imprime.

import argparse
import json
import sys
from pathlib import Path

_RAIZ_DO_PROJETO = Path(__file__).resolve().parent.parent
if str(_RAIZ_DO_PROJETO) not in sys.path:
    sys.path.insert(0, str(_RAIZ_DO_PROJETO))

from api_mercado_livre.core.estrutura_api.cliente_api import chamar_api, ErroAPI, ErroAutenticacaoAPI


def ler_argumentos():
    parser = argparse.ArgumentParser(
        description="Testa o campo unit_price de um pedido real contra a API do ML."
    )
    parser.add_argument("--empresa", type=str, required=True, choices=["MB", "SV"],
                         help="Conta a consultar (MB ou SV).")
    parser.add_argument("--pedido", type=str, required=True,
                         help="Número do pedido (numero_pedido / order id).")
    args = parser.parse_args()
    return args.empresa, args.pedido


CONTA, NUMERO_PEDIDO = ler_argumentos()

PASTA_LOGS = Path(__file__).resolve().parent / "logs"
PASTA_LOGS.mkdir(parents=True, exist_ok=True)

try:
    resposta = chamar_api(
        "GET", f"/orders/{NUMERO_PEDIDO}",
        pasta_logs=PASTA_LOGS, conta=CONTA, nome_log="testar_preco_unitario_pedido",
    )
    pedido = resposta.json()
except (ErroAPI, ErroAutenticacaoAPI) as erro:
    print(f"Erro ao chamar a API: {erro}")
    sys.exit(1)

order_items = pedido.get("order_items") or []

print(f"\n=== order_items bruto (pedido {NUMERO_PEDIDO}, conta {CONTA}) ===\n")
print(json.dumps(order_items, ensure_ascii=False, indent=2))

if not order_items:
    print("\nEsse pedido não tem order_items -- não dá pra testar o campo de preço com ele.")
    sys.exit(0)

item = order_items[0]

print("\n=== Extração que o código de verdade vai usar (item = order_items[0]) ===\n")
print(f"unit_price ..... {item.get('unit_price')!r}")
print(f"currency_id ..... {item.get('currency_id')!r}")
print(f"quantity ..... {item.get('quantity')!r}")
print(f"gross_price ..... {item.get('gross_price', '(campo não veio nessa resposta)')!r}")
print(f"titulo (pra conferir que é o pedido certo) ..... {(item.get('item') or {}).get('title')!r}")