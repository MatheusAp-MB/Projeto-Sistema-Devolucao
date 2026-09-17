# scripts_exploracao_ML/investigar_pack.py
#
# Objetivo ÚNICO: testar se um número que falhou em GET /orders/$ID (404,
# "order_not_found") é na verdade um Pack ID -- chamando GET /packs/$ID, que
# nunca foi tentado nessa investigação. Se funcionar, a resposta deve trazer
# os pedidos individuais reais agrupados nesse pack.
#
# Só leitura. Não toca no banco.

import argparse
import json
import sys
from pathlib import Path

_RAIZ_DO_PROJETO = Path(__file__).resolve().parent.parent
if str(_RAIZ_DO_PROJETO) not in sys.path:
    sys.path.insert(0, str(_RAIZ_DO_PROJETO))

from api_mercado_livre.core.estrutura_api.cliente_api import chamar_api, ErroAPI, ErroAutenticacaoAPI


def ler_argumentos():
    parser = argparse.ArgumentParser(description="Testa GET /packs/$ID pra um número que falhou como pedido.")
    parser.add_argument("--empresa", type=str, required=True, choices=["MB", "SV"])
    parser.add_argument("--id", type=str, required=True, dest="id_testado")
    args = parser.parse_args()
    return args.empresa, args.id_testado


CONTA, ID_TESTADO = ler_argumentos()
PASTA_LOGS = Path(__file__).resolve().parent / "logs"

try:
    resposta = chamar_api(
        "GET", f"/packs/{ID_TESTADO}",
        pasta_logs=PASTA_LOGS, conta=CONTA,
        nome_log="investigar_pack",
    )
except (ErroAPI, ErroAutenticacaoAPI) as erro:
    print(f"Erro ao chamar /packs/{ID_TESTADO} -- indício de que também NÃO é um pack_id válido: {erro}")
else:
    print(json.dumps(resposta.json(), ensure_ascii=False, indent=2))