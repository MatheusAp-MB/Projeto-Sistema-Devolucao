# scripts_exploracao_ML/investigar_shipment_history.py
#
# Objetivo ÚNICO: pegar a linha do tempo completa de status/substatus de
# um envio específico (GET /shipments/$SHIPPING_ID/history) — o
# /shipments/$ID comum só traz o status atual + last_updated, sem
# histórico. NENHUM outro endpoint é chamado além deste.
#
# Reusa o mesmo headers_extra (x-format-new: true) já adicionado no
# chamar_api() pro investigar_shipment.py — nenhuma mudança de código
# nova aqui.
#
# Só leitura. Não toca no banco, não grava nada além do arquivo de saída.
#
# Uso:
#   poetry run python scripts_exploracao_ML/investigar_shipment_history.py --empresa MB --shipping-id 47752794916

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
        description="Consulta GET /shipments/$SHIPPING_ID/history pra um envio específico.",
    )
    parser.add_argument(
        "--empresa", type=str, required=True, choices=["MB", "SV"],
        help="Conta a consultar: MB (Magazine) ou SV (Samvale) — obrigatório.",
    )
    parser.add_argument(
        "--shipping-id", type=int, required=True, dest="shipping_id",
        help="ID do envio (shipment_id) a investigar — obrigatório.",
    )
    args = parser.parse_args()
    return args.empresa, args.shipping_id


CONTA, SHIPPING_ID = ler_argumentos()

PASTA_LOGS = Path(__file__).resolve().parent / "logs"
CAMINHO_SAIDA = Path(__file__).resolve().parent / f"investigacao_shipment_history_{SHIPPING_ID}.json"


try:
    resposta_me = chamar_api(
        "GET", "/users/me",
        pasta_logs=PASTA_LOGS, conta=CONTA,
        nome_log="investigar_shipment_history",
    )
    user_id = resposta_me.json()["id"]

    resposta_history = chamar_api(
        "GET", f"/shipments/{SHIPPING_ID}/history",
        pasta_logs=PASTA_LOGS, conta=CONTA,
        headers_extra={"x-format-new": "true"},
        nome_log="investigar_shipment_history",
    )
except (ErroAPI, ErroAutenticacaoAPI) as erro:
    print(f"Erro ao chamar a API: {erro}")
else:
    resultado_cru = resposta_history.json()

    texto_json = json.dumps(resultado_cru, ensure_ascii=False, indent=2)
    texto_json_oculto = texto_json.replace(str(user_id), "SEU_USER_ID_OCULTO")

    with open(CAMINHO_SAIDA, "w", encoding="utf-8") as f:
        f.write(texto_json_oculto)

    print(f"Retorno (com seu user_id oculto) salvo em: {CAMINHO_SAIDA}")
    print("Suba esse arquivo na conversa pra eu analisar.")