# scripts_exploracao_ML/investigar_review_devolucao.py
#
# Objetivo ÚNICO: pegar a(s) revisão(ões) de uma devolução específica, via
# GET /post-purchase/v1/returns/$RETURN_ID/reviews — só existe quando o
# recurso /post-purchase/v2/claims/$CLAIM_ID/returns já trouxe "reviews"
# dentro de related_entities. NENHUM outro endpoint é chamado além deste.
#
# Objetivo real: ver o campo "method" ("none" = revisão pelo vendedor,
# "triage" = revisão pela própria Meli) e o que mais vem junto — pode
# revelar o que acontece depois de um item chegar num centro de triagem,
# e ajudar a entender por que o "return_from_triage" nunca apareceu.
#
# Só leitura. Não toca no banco, não grava nada além do arquivo de saída.
#
# Uso:
#   poetry run python scripts_exploracao_ML/investigar_review_devolucao.py --empresa MB --return-id 161381681

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
        description="Consulta GET /post-purchase/v1/returns/$RETURN_ID/reviews pra uma devolução específica.",
    )
    parser.add_argument(
        "--empresa", type=str, required=True, choices=["MB", "SV"],
        help="Conta a consultar: MB (Magazine) ou SV (Samvale) — obrigatório.",
    )
    parser.add_argument(
        "--return-id", type=int, required=True, dest="return_id",
        help="ID da devolução (return_id, campo 'id' do investigar_detalhe_devolucao.py) — obrigatório.",
    )
    args = parser.parse_args()
    return args.empresa, args.return_id


CONTA, RETURN_ID = ler_argumentos()

PASTA_LOGS = Path(__file__).resolve().parent / "logs"
CAMINHO_SAIDA = Path(__file__).resolve().parent / f"investigacao_review_{RETURN_ID}.json"


try:
    resposta = chamar_api(
        "GET", f"/post-purchase/v1/returns/{RETURN_ID}/reviews",
        pasta_logs=PASTA_LOGS, conta=CONTA,
        nome_log="investigar_review_devolucao",
    )
except (ErroAPI, ErroAutenticacaoAPI) as erro:
    print(f"Erro ao chamar a API: {erro}")
else:
    resultado_cru = resposta.json()  # sem tocar em nada — cru, do jeito que a API mandou

    with open(CAMINHO_SAIDA, "w", encoding="utf-8") as f:
        json.dump(resultado_cru, f, ensure_ascii=False, indent=2)

    print(f"Retorno bruto salvo em: {CAMINHO_SAIDA}")
    print("Suba esse arquivo na conversa pra eu analisar — nenhum campo foi filtrado.")