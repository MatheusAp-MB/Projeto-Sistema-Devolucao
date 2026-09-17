# scripts_exploracao_ML/investigar_claims_do_pedido.py
#
# Objetivo ÚNICO: buscar TODAS as reclamações/claims associadas a um
# pedido específico, via GET /post-purchase/v1/claims/search?order_id=...
# — pra descobrir se existe uma 2ª reclamação/claim (além da original)
# criada depois que a Meli decide "product_destination: seller" na
# triagem, e que poderia carregar o shipment "return_from_triage".
#
# Só leitura. Não toca no banco, não grava nada além do arquivo de saída.
#
# Uso:
#   poetry run python scripts_exploracao_ML/investigar_claims_do_pedido.py --empresa MB --pedido 2000017749492836

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
        description="Consulta GET /post-purchase/v1/claims/search?order_id=... pra um pedido específico.",
    )
    parser.add_argument(
        "--empresa", type=str, required=True, choices=["MB", "SV"],
        help="Conta a consultar: MB (Magazine) ou SV (Samvale) — obrigatório.",
    )
    parser.add_argument(
        "--pedido", type=int, required=True,
        help="ID do pedido (order_id) — busca TODAS as reclamações ligadas a ele.",
    )
    args = parser.parse_args()
    return args.empresa, args.pedido


CONTA, ORDER_ID = ler_argumentos()

PASTA_LOGS = Path(__file__).resolve().parent / "logs"
CAMINHO_SAIDA = Path(__file__).resolve().parent / f"investigacao_claims_do_pedido_{ORDER_ID}.json"


try:
    resposta = chamar_api(
        "GET", "/post-purchase/v1/claims/search",
        pasta_logs=PASTA_LOGS, conta=CONTA,
        params={"order_id": ORDER_ID},
        nome_log="investigar_claims_do_pedido",
    )
except (ErroAPI, ErroAutenticacaoAPI) as erro:
    print(f"Erro ao chamar a API: {erro}")
else:
    resultado_cru = resposta.json()  # sem tocar em nada — cru, do jeito que a API mandou

    with open(CAMINHO_SAIDA, "w", encoding="utf-8") as f:
        json.dump(resultado_cru, f, ensure_ascii=False, indent=2)

    print(f"Retorno bruto salvo em: {CAMINHO_SAIDA}")
    print("Suba esse arquivo na conversa pra eu analisar — nenhum campo foi filtrado.")