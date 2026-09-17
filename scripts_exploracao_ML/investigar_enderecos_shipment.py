"""
scripts_exploracao_ML/investigar_enderecos_shipment.py

Investiga se a API do Mercado Livre expõe o endereço completo de cada ponto
da rota do envio — tanto na venda (NÓS -> CLIENTE) quanto na devolução física
(CLIENTE -> NÓS). Hoje o sistema só usa o histórico de status
(/shipments/{id}/history) e um campo destination.name genérico (ex:
"seller_address") vindo da resposta de devolução — nunca testamos se existe
endereço completo (rua, número, cidade) em algum lugar dessas respostas, ou
no recurso principal do shipment (/shipments/{id}), que ainda não é chamado
em lugar nenhum do sistema.

Uso:
    python scripts_exploracao_ML/investigar_enderecos_shipment.py --empresa MB --numero-pedido 2000018113512820
"""
import argparse
import json
import sys
from pathlib import Path
from rich import print

# scripts_exploracao_ML é uma subpasta — sem isso, o Python não acha o pacote
# api_mercado_livre, que fica na raiz do projeto, um nível acima daqui.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api_mercado_livre.core.estrutura_api.cliente_api import chamar_api, ErroAPI

PASTA_LOGS = Path("logs_exploracao")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--empresa", required=True, choices=["MB", "SV"])
    parser.add_argument("--numero-pedido", required=True)
    args = parser.parse_args()
    conta = args.empresa

    print(f"\n=== Pedido {args.numero_pedido} ({conta}) ===\n")

    pedido = chamar_api("GET", f"/orders/{args.numero_pedido}", pasta_logs=PASTA_LOGS, conta=conta).json()
    shipping_id_ida = (pedido.get("shipping") or {}).get("id")
    print(f"shipping_id (ida, venda): {shipping_id_ida}")

    if shipping_id_ida:
        print("\n--- /shipments/{id} (ida) — recurso completo, nunca chamado pelo sistema hoje ---")
        try:
            shipment_ida = chamar_api(
                "GET", f"/shipments/{shipping_id_ida}", pasta_logs=PASTA_LOGS, conta=conta,
            ).json()
            print(json.dumps(shipment_ida, ensure_ascii=False, indent=2))
        except ErroAPI as erro:
            print(f"Erro ao buscar /shipments/{shipping_id_ida}: {erro}")

    # ----- Reclamação/devolução -----
    resposta_claims = chamar_api(
        "GET", "/post-purchase/v1/claims/search", pasta_logs=PASTA_LOGS, conta=conta,
        params={"order_id": args.numero_pedido},
    )
    claims = resposta_claims.json().get("data", [])
    if not claims:
        print("\nNenhuma claim encontrada pra esse pedido — só dava pra investigar o lado da venda.")
        return

    for claim in claims:
        try:
            devolucao = chamar_api(
                "GET", f"/post-purchase/v2/claims/{claim['id']}/returns",
                pasta_logs=PASTA_LOGS, conta=conta,
            ).json()
        except ErroAPI:
            continue
        if not devolucao:
            continue

        print(f"\n--- /post-purchase/v2/claims/{claim['id']}/returns — resposta bruta completa ---")
        print(json.dumps(devolucao, ensure_ascii=False, indent=2))

        for envio in devolucao.get("shipments", []):
            shipment_id_volta = envio.get("shipment_id")
            if not shipment_id_volta:
                continue

            print(f"\n--- /shipments/{shipment_id_volta} (volta, devolução) — recurso completo ---")
            try:
                shipment_volta = chamar_api(
                    "GET", f"/shipments/{shipment_id_volta}", pasta_logs=PASTA_LOGS, conta=conta,
                ).json()
                print(json.dumps(shipment_volta, ensure_ascii=False, indent=2))
            except ErroAPI as erro:
                print(f"Erro ao buscar /shipments/{shipment_id_volta}: {erro}")

            print(f"\n--- /shipments/{shipment_id_volta}/history (volta) — eventos brutos, sem passar pela tradução ---")
            try:
                historico = chamar_api(
                    "GET", f"/shipments/{shipment_id_volta}/history", pasta_logs=PASTA_LOGS, conta=conta,
                    headers_extra={"x-format-new": "true"},
                ).json()
                print(json.dumps(historico, ensure_ascii=False, indent=2))
            except ErroAPI as erro:
                print(f"Erro ao buscar histórico: {erro}")


if __name__ == "__main__":
    main()