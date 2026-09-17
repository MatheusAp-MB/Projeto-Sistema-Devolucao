# scripts_exploracao_ML/testar_fluxo_bloco_cliente.py
#
# Objetivo ÚNICO: validar de ponta a ponta a ideia levantada em 17/09/2026
# pra preencher o bloco "ESSE CLIENTE" da tela de desambiguação (Consultar
# Pedido, busca por ID do Cliente): já confirmamos que /orders/search NÃO
# traz nome real do comprador (só id/nickname em cada resultado -- ver
# investigacao_orders_search_por_data_MB.json), mas /orders/{id} (busca por
# 1 pedido específico) confirmadamente traz (print da tela real: "Rafael
# Ramos Machado · RAPHA048").
#
# Como todos os pedidos de uma busca por buyer_id pertencem ao MESMO
# comprador, a ideia é: buscar a lista normal (/orders/search), pegar
# QUALQUER 1 pedido dela, buscar esse 1 pedido específico (/orders/{id})
# e extrair os dados do comprador de lá -- só 1 chamada extra pra tela
# inteira, não 1 por pedido.
#
# Este script reproduz esse fluxo completo e imprime no console como
# ficaria o bloco "ESSE CLIENTE" + "TEM ESSES PEDIDOS", pra confirmar
# que os dados batem antes de mexer em views.py de verdade.
#
# Só leitura. Não toca no banco. Sobrescreve o arquivo de saída (nunca
# acrescenta) a cada execução.

import argparse
import json
import sys
from pathlib import Path

from rich import box
from rich.console import Console
from rich.table import Table

_RAIZ_DO_PROJETO = Path(__file__).resolve().parent.parent
if str(_RAIZ_DO_PROJETO) not in sys.path:
    sys.path.insert(0, str(_RAIZ_DO_PROJETO))

from api_mercado_livre.core.estrutura_api.cliente_api import chamar_api, ErroAPI, ErroAutenticacaoAPI


def ler_argumentos():
    parser = argparse.ArgumentParser(
        description="Testa o fluxo completo: busca pedidos por buyer_id, pega 1 pedido "
                     "qualquer da lista, busca esse pedido específico e extrai os dados "
                     "do cliente de lá -- pra validar o bloco 'ESSE CLIENTE' da tela.",
    )
    parser.add_argument("--empresa", type=str, required=True, choices=["MB", "SV"],
                         help="Conta a consultar (MB ou SV).")
    parser.add_argument("--buyer-id", type=str, required=True, dest="buyer_id",
                         help="ID do cliente (código visto ao lado do nome na etiqueta).")
    args = parser.parse_args()
    return args.empresa, args.buyer_id


CONTA, BUYER_ID = ler_argumentos()

PASTA_LOGS = Path(__file__).resolve().parent / "logs"
PASTA_LOGS.mkdir(parents=True, exist_ok=True)
NOME_LOG = "testar_fluxo_bloco_cliente"
CAMINHO_SAIDA = Path(__file__).resolve().parent / f"fluxo_bloco_cliente_{BUYER_ID}_{CONTA}.json"

console = Console()


try:
    # Passo 1: descobrir o próprio seller_id -- pré-requisito do /orders/search.
    resposta_me = chamar_api(
        "GET", "/users/me",
        pasta_logs=PASTA_LOGS, conta=CONTA, nome_log=NOME_LOG,
    )
    seller_id = resposta_me.json()["id"]

    # Passo 2: buscar a lista de pedidos do cliente -- mesma chamada que
    # _listar_pedidos_do_cliente() já faz hoje em produção. Só a 1ª página
    # (limit padrão) -- suficiente pra esse teste de conceito, já que só
    # precisamos de 1 pedido qualquer da lista.
    resposta_busca = chamar_api(
        "GET", "/orders/search",
        pasta_logs=PASTA_LOGS, conta=CONTA, nome_log=NOME_LOG,
        params={"seller": seller_id, "buyer": BUYER_ID},
    )
    resultados = resposta_busca.json().get("results", [])

    if not resultados:
        console.print(f"\nNenhum pedido encontrado pra esse buyer_id ({BUYER_ID}) na conta {CONTA}.")
        sys.exit(0)

    console.print(f"\n{len(resultados)} pedido(s) encontrado(s) pra esse cliente na conta {CONTA}.")

    # Passo 3: pegar QUALQUER 1 pedido da lista -- o primeiro serve, já que
    # todos pertencem ao mesmo comprador (filtro buyer=BUYER_ID garante isso).
    numero_pedido_escolhido = resultados[0].get("id")
    console.print(f"Pedido escolhido pra buscar os dados do cliente: {numero_pedido_escolhido}\n")

    # Passo 4: buscar esse 1 pedido específico -- é aqui que o nome real
    # do comprador deve aparecer (confirmado no print da tela de detalhe).
    resposta_pedido = chamar_api(
        "GET", f"/orders/{numero_pedido_escolhido}",
        pasta_logs=PASTA_LOGS, conta=CONTA, nome_log=NOME_LOG,
    )
    pedido_completo = resposta_pedido.json()
    comprador = pedido_completo.get("buyer") or {}
    nome_comprador = f"{comprador.get('first_name', '')} {comprador.get('last_name', '')}".strip() or "—"
    nickname_comprador = comprador.get("nickname") or "—"
    id_comprador = comprador.get("id")

except (ErroAPI, ErroAutenticacaoAPI) as erro:
    console.print(f"\nErro ao chamar a API: {erro}")
else:
    # ----- Monta a visão de console, no mesmo formato do mockup -----
    console.print("[bold]ESSE CLIENTE:[/bold]")
    console.print(f"  Nome: {nome_comprador}")
    console.print(f"  Nickname: {nickname_comprador}")
    console.print(f"  ID: {id_comprador}")

    console.print("\n[bold]TEM ESSES PEDIDOS:[/bold]\n")

    tabela = Table(box=box.SIMPLE_HEAVY)
    tabela.add_column("Pedido")
    tabela.add_column("Data da compra")
    tabela.add_column("Item")
    tabela.add_column("Pack ID")

    lista_para_salvar = []
    for pedido in resultados:
        item = (pedido.get("order_items") or [{}])[0]
        titulo = (item.get("item") or {}).get("title", "—")
        pack_id = pedido.get("pack_id")
        tabela.add_row(
            str(pedido.get("id")),
            (pedido.get("date_created") or "—")[:19],
            titulo[:50],
            str(pack_id) if pack_id else "—",
        )
        lista_para_salvar.append({
            "numero_pedido": pedido.get("id"),
            "data_created": pedido.get("date_created"),
            "titulo_item": titulo,
            "pack_id": pack_id,
        })

    console.print(tabela)

    resultado_final = {
        "cliente": {
            "id": id_comprador,
            "nome": nome_comprador,
            "nickname": nickname_comprador,
            "pedido_usado_pra_buscar": numero_pedido_escolhido,
        },
        "pedidos": lista_para_salvar,
    }
    texto_json = json.dumps(resultado_final, ensure_ascii=False, indent=2)
    with open(CAMINHO_SAIDA, "w", encoding="utf-8") as f:
        f.write(texto_json)

    console.print(f"\nResultado completo salvo em: {CAMINHO_SAIDA}")
    console.print("Cola a tabela + o bloco do cliente acima na conversa pra eu conferir.")