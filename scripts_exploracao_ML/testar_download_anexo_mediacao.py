"""
scripts_exploracao_ML/testar_download_anexo_mediacao.py

Script standalone de exploração -- SEM nenhuma integração ao sistema Django, roda
sozinho com `python -u testar_download_anexo_mediacao.py --empresa MB --claim-id 5573730744`.

Objetivo original: testar candidatos de endpoint pra baixar anexo de mensagem de
reclamação do Mercado Livre com Bearer token (em vez do link antigo que exige
cookie de sessão do navegador). Confirmados 2 candidatos funcionais, byte-idênticos
entre si:
  - post-purchase/v1/claims/{claim_id}/attachments/{filename}/download
  - marketplace/v2/claims/{claim_id}/attachments/{filename}/download

Atualização 1 (21/09/2026): adicionado teste de retenção (status/stage/idade do claim)
e comparação entre o Content-Type real do download e o campo 'type' do endpoint de
metadados -- CONFIRMADO no teste real (claim 5573730744, ainda aberto, 12 dias):
type declarado bate 100% com o Content-Type real dos dois candidatos.

Atualização 2 (21/09/2026): teste de retenção em claim fechado ainda pendente --
tentativa manual (pedido 2000017939871998, claim 5565476693, status=closed,
stage=dispute, 27 dias) confirmou os valores reais de status/stage, mas esse claim
específico não tinha nenhum anexo. Em vez de ficar tentando pedido por pedido às
cegas, adicionado modo de busca automática: --buscar-fechado-com-anexo pagina em
/post-purchase/v1/claims/search?status=closed até achar um claim fechado que tenha
pelo menos uma mensagem com anexo, e usa esse pro resto do teste. A forma exata de
paginação desse endpoint (nomes dos parâmetros offset/limit) não está confirmada na
doc -- se a primeira chamada falhar, o erro cru do ML aparece no console e ajusta a
partir daí, igual fizemos com os candidatos de download.

Uso:
    python -u testar_download_anexo_mediacao.py --empresa MB --pedido 2000018262061202
    python -u testar_download_anexo_mediacao.py --empresa SV --claim-id 5573730744
    python -u testar_download_anexo_mediacao.py --empresa MB --buscar-fechado-com-anexo
"""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

# raiz do projeto, pra importar api_mercado_livre/ igual o resto do sistema faz
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api_mercado_livre.core.auth.gerenciador_token import obter_token_valido, mascarar
from api_mercado_livre.core.estrutura_api.cliente_api import chamar_api, ErroAPI, ErroAutenticacaoAPI

PASTA_LOGS = Path(__file__).resolve().parent / "logs"
PASTA_SAIDA = Path(__file__).resolve().parent


def ler_argumentos():
    parser = argparse.ArgumentParser(
        description="Teste standalone de download de anexo de mediação ML (sem integração ao sistema)."
    )
    parser.add_argument("--empresa", required=True, choices=["MB", "SV"], help="Conta a usar (MB ou SV)")
    grupo = parser.add_mutually_exclusive_group(required=True)
    grupo.add_argument("--pedido", help="Número do pedido (tenta resolver o claim_id automaticamente)")
    grupo.add_argument("--claim-id", dest="claim_id", help="claim_id direto -- mais confiável que --pedido")
    grupo.add_argument("--buscar-fechado-com-anexo", action="store_true",
                        help="Ignora --pedido/--claim-id -- pagina em claims fechados (status=closed) "
                             "até achar um que tenha mensagem com anexo")
    parser.add_argument("--max-paginas", type=int, default=10,
                         help="Limite de páginas na busca automática (default: 10)")
    parser.add_argument("--tamanho-pagina", type=int, default=25,
                         help="Claims por página na busca automática (default: 25)")
    return parser.parse_args()


def resolver_claim_id(pedido, conta):
    """Tenta resolver o claim_id a partir do número do pedido. A forma exata dos
    filtros de /post-purchase/v1/claims/search não está 100% confirmada na doc --
    se isso falhar ou vier vazio, rode de novo passando --claim-id direto."""
    print(f"Resolvendo claim_id a partir do pedido {pedido}...")
    resposta = chamar_api(
        "GET", "/post-purchase/v1/claims/search", PASTA_LOGS, conta,
        params={"resource_id": pedido, "resource": "order"}, nome_log="teste_anexo",
    )
    dados = resposta.json()
    resultados = dados.get("data", dados) if isinstance(dados, dict) else dados
    if not resultados:
        raise SystemExit(
            f"Nenhum claim encontrado pro pedido {pedido} via /claims/search. "
            f"Rode de novo passando --claim-id direto, se souber o valor."
        )
    claim_id = str(resultados[0]["id"])
    print(f"  claim_id encontrado: {claim_id}")
    return claim_id


def buscar_claims_fechados(conta, max_paginas, tamanho_pagina):
    """Pagina em /post-purchase/v1/claims/search?status=closed procurando o primeiro
    claim fechado que tenha pelo menos uma mensagem com anexo. Confirma pra cada um
    checando /messages -- mais lento (1 chamada extra por claim), mas usa o
    espaçador/backoff que já existe em chamar_api, então não precisa de cuidado
    manual com rate limit aqui."""
    offset = 0
    for pagina in range(1, max_paginas + 1):
        print(f"\nPágina {pagina}/{max_paginas} de claims fechados (offset={offset})...")
        resposta = chamar_api(
            "GET", "/post-purchase/v1/claims/search", PASTA_LOGS, conta,
            params={"status": "closed", "limit": tamanho_pagina, "offset": offset},
            nome_log="teste_anexo",
        )
        dados = resposta.json()
        resultados = dados.get("data", dados) if isinstance(dados, dict) else dados
        if not resultados:
            print("  não veio mais nenhum resultado -- parei a busca aqui.")
            return None

        for item in resultados:
            claim_id = str(item["id"])
            print(f"  checando claim {claim_id}...", end=" ")
            try:
                resposta_msgs = chamar_api(
                    "GET", f"/post-purchase/v1/claims/{claim_id}/messages", PASTA_LOGS, conta,
                    nome_log="teste_anexo",
                )
            except (ErroAPI, ErroAutenticacaoAPI) as erro:
                print(f"falhou ao buscar mensagens ({erro})")
                continue

            mensagens = resposta_msgs.json()
            if any(msg.get("attachments") for msg in mensagens):
                print("TEM ANEXO -- usando esse claim.")
                return claim_id
            print("sem anexo.")

        offset += tamanho_pagina

    print(f"\nNão achei nenhum claim fechado com anexo em {max_paginas} páginas. "
          f"Tenta de novo com --max-paginas maior.")
    return None


def buscar_detalhes_claim(claim_id, conta):
    """Busca status/stage/data de criação do claim -- contexto pro teste de retenção:
    um claim antigo e fechado prova mais sobre disponibilidade do anexo do que um recente."""
    print(f"\nBuscando detalhes do claim {claim_id}...")
    resposta = chamar_api(
        "GET", f"/post-purchase/v1/claims/{claim_id}", PASTA_LOGS, conta, nome_log="teste_anexo",
    )
    dados = resposta.json()
    status = dados.get("status")
    stage = dados.get("stage")
    date_created = dados.get("date_created")
    print(f"  status: {status} | stage: {stage} | date_created: {date_created}")

    if date_created:
        try:
            criado_em = datetime.fromisoformat(date_created.replace("Z", "+00:00"))
            dias = (datetime.now(timezone.utc) - criado_em).days
            print(f"  idade do claim: {dias} dias")
        except ValueError:
            print(f"  (não consegui interpretar a data '{date_created}' pra calcular a idade)")

    return dados


def achar_primeiro_anexo(claim_id, conta):
    """Busca as mensagens do claim e devolve o primeiro anexo encontrado."""
    print(f"\nBuscando mensagens do claim {claim_id}...")
    resposta = chamar_api(
        "GET", f"/post-purchase/v1/claims/{claim_id}/messages", PASTA_LOGS, conta, nome_log="teste_anexo",
    )
    mensagens = resposta.json()
    for msg in mensagens:
        anexos = msg.get("attachments") or []
        if anexos:
            anexo = anexos[0]
            print(f"  anexo encontrado: {anexo['filename']} ({anexo['type']}, {anexo['size']} bytes)")
            return anexo
    raise SystemExit(f"Nenhuma mensagem do claim {claim_id} tem anexo.")


def buscar_metadados_anexo(claim_id, filename, conta):
    """Endpoint de metadados (SEM /download) -- devolve o 'type' declarado pelo ML,
    sem baixar o binário. Usado pra comparar contra o Content-Type real do download."""
    print(f"\nBuscando metadados do anexo (sem baixar o binário)...")
    resposta = chamar_api(
        "GET", f"/post-purchase/v1/claims/{claim_id}/attachments/{filename}", PASTA_LOGS, conta,
        nome_log="teste_anexo",
    )
    dados = resposta.json()
    print(f"  type declarado nos metadados: {dados.get('type')}")
    return dados


def testar_download(numero, nome_candidato, endpoint, claim_id, filename, conta):
    """Baixa o anexo por um candidato de endpoint (auth Bearer via chamar_api).
    Devolve (sucesso, content_type_real, caminho_salvo) pra alimentar a comparação
    de Content-Type e o resumo final."""
    print(f"\n--- Candidato {numero}: {nome_candidato} ---")
    print(f"  GET {endpoint}")
    try:
        resposta = chamar_api("GET", endpoint, PASTA_LOGS, conta, nome_log="teste_anexo")
    except ErroAutenticacaoAPI as erro:
        print(f"  FALHOU (autenticação): {erro}")
        return False, None, None
    except ErroAPI as erro:
        print(f"  FALHOU: {erro}")
        return False, None, None

    content_type = resposta.headers.get("Content-Type", "")
    tamanho = len(resposta.content)
    print(f"  HTTP 200 | Content-Type real: {content_type} | tamanho: {tamanho} bytes")

    if not content_type.startswith("image/"):
        print(f"  AVISO: Content-Type não é image/* -- não vou salvar como imagem. Corpo (início): {resposta.text[:300]!r}")
        return True, content_type, None

    caminho_salvo = PASTA_SAIDA / f"teste_retencao_candidato_{numero}_{filename}"
    caminho_salvo.write_bytes(resposta.content)
    print(f"  salvo em: {caminho_salvo.name}")
    return True, content_type, caminho_salvo


def main():
    args = ler_argumentos()
    conta = args.empresa

    token = obter_token_valido(conta)
    print(f"Token da conta {conta}: {mascarar(token)}\n")

    if args.buscar_fechado_com_anexo:
        claim_id = buscar_claims_fechados(conta, args.max_paginas, args.tamanho_pagina)
        if not claim_id:
            raise SystemExit(1)
    else:
        claim_id = args.claim_id or resolver_claim_id(args.pedido, conta)

    detalhes_claim = buscar_detalhes_claim(claim_id, conta)
    anexo = achar_primeiro_anexo(claim_id, conta)
    filename = anexo["filename"]

    resultados = {}
    for numero, nome, endpoint in [
        (3, "post-purchase/v1", f"/post-purchase/v1/claims/{claim_id}/attachments/{filename}/download"),
        (4, "marketplace/v2", f"/marketplace/v2/claims/{claim_id}/attachments/{filename}/download"),
    ]:
        sucesso, content_type, caminho = testar_download(numero, nome, endpoint, claim_id, filename, conta)
        resultados[nome] = {"sucesso": sucesso, "content_type": content_type, "caminho": caminho}

    metadados = None
    try:
        metadados = buscar_metadados_anexo(claim_id, filename, conta)
    except (ErroAPI, ErroAutenticacaoAPI) as erro:
        print(f"\nFALHOU ao buscar metadados: {erro}")

    print("\n" + "=" * 70)
    print("RESUMO")
    print("=" * 70)
    print(f"claim_id: {claim_id} | status: {detalhes_claim.get('status')} | stage: {detalhes_claim.get('stage')}")
    print(f"anexo testado: {filename} ({anexo['type']}, {anexo['size']} bytes)")
    for nome, resultado in resultados.items():
        situacao = "OK" if resultado["sucesso"] else "FALHOU"
        print(f"  {nome}: {situacao} (Content-Type real: {resultado['content_type']})")

    if metadados:
        type_declarado = metadados.get("type")
        content_types_reais = {r["content_type"] for r in resultados.values() if r["sucesso"] and r["content_type"]}
        if content_types_reais:
            bate = content_types_reais == {type_declarado}
            print(f"type declarado nos metadados: {type_declarado}")
            print(f"Content-Type real do(s) download(s): {content_types_reais}")
            print(f"Batem entre si: {'SIM' if bate else 'NÃO'}")

    print("=" * 70)


if __name__ == "__main__":
    main()