"""
Varredura de "quem respondeu e quando" numa reclamação/mediação — mostra o
histórico como um chat de verdade.

O QUE FAZ:
  Dado --empresa (MB/SV) e --numero_pedido, acha sozinho a reclamação
  associada ao pedido (mesma busca do consultar_linha_tempo_devolucao.py:
  GET /post-purchase/v1/claims/search?order_id=...), busca
  GET /post-purchase/v1/claims/{claim_id}/messages e imprime cada mensagem
  como um chat, na ordem em que aconteceram, com o texto limpo (sem o HTML
  cru que a API devolve) e 3 rótulos coloridos:
    - "O ML RESPONDEU"          -> sender_role == "mediator"
    - "VOCÊ RESPONDEU"          -> sender_role == o papel que bate com o SEU user_id
    - "A CONTRAPARTE RESPONDEU" -> qualquer outro (comprador ou vendedor, o que não for você)

  Pensado pra virar o "botão de varredura" que você comentou, não pra rodar
  sozinho agendado (webhook fica de fora por decisão sua).

  Se o pedido tiver mais de 1 reclamação, o script tenta desempatar sozinho
  escolhendo a que está em mediação (tem mediador nos players OU
  stage == "dispute"). Se ainda sobrar mais de uma (ou nenhuma) candidata em
  mediação, ele lista todas as reclamações encontradas e pede pra você rodar
  de novo passando --claim_id=<a certa> pra desempatar manualmente.

  Usa a mesma camada robusta de API do resto do projeto
  (api_mercado_livre.core.estrutura_api.cliente_api.chamar_api): retry com
  backoff em 429, renovação automática de token via gerenciador_token,
  log em arquivo por chamada — igual ao consultar_linha_tempo_devolucao.py.

NÃO TESTADO AINDA — é rascunho. Rode você, na sua máquina, e cola o resultado
(ou o erro) de volta que eu ajusto.

COMO USAR:
  python varredura_respostas_mediacao.py --empresa=SV --numero_pedido=2000017788033354

  Se o pedido tiver mais de 1 reclamação e o script não conseguir desempatar
  sozinho (ver acima), ele imprime a lista e você roda de novo com:
  python varredura_respostas_mediacao.py --empresa=SV --numero_pedido=2000017788033354 --claim_id=5564889989

  Se quiser ver o sender_role e o date_created crus de cada mensagem (além
  do texto limpo), rode com --bruto:
  python varredura_respostas_mediacao.py --empresa=SV --numero_pedido=2000017788033354 --bruto

PENDENTE (de propósito, pra não estourar o tempo agora):
  - Critério de desempate quando há múltiplas reclamações em mediação ao
    mesmo tempo (nunca vimos esse caso ainda) — hoje ele só lista e pede
    --claim_id manual nesse cenário, não arrisca escolher sozinho.
  - "A CONTRAPARTE RESPONDEU" assume que quem não é você nem o mediador é
    sempre o comprador — já documentado que em cancel_sale os papéis
    complainant/respondent podem inverter, então isso não é garantido.
"""

import argparse
import html
import re
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from rich.console import Console
from rich.markup import escape

from api_mercado_livre.core.estrutura_api.cliente_api import chamar_api, ErroAPI, ErroAutenticacaoAPI
from api_mercado_livre.core.auth.gerenciador_token import FalhaAutenticacao

PASTA_LOGS = Path(__file__).resolve().parent / "logs"
NOME_LOG = "varredura_respostas_mediacao"
FUSO_HORARIO_EXIBICAO = ZoneInfo("America/Sao_Paulo")

console = Console()

# Cor de cada rótulo — mesma linguagem visual do consultar_linha_tempo_devolucao.py.
COR_MEDIADOR = "blue"
COR_VOCE = "green"
COR_CONTRAPARTE = "magenta"

EXPLICACAO_PAPEL = {
    "respondent": "quem precisa responder à reclamação — normalmente o vendedor, seu lado, "
                  "quando o comprador abre uma reclamação",
    "complainant": "quem abriu a reclamação — normalmente o comprador",
}


def ler_argumentos():
    parser = argparse.ArgumentParser(
        description="Varredura de respostas (ML x você) numa reclamação/mediação"
    )
    parser.add_argument(
        "--numero_pedido", type=int, required=True,
        help="Número do pedido a consultar (obrigatório).",
    )
    parser.add_argument(
        "--empresa", type=str, required=True, choices=["MB", "SV"],
        help="Conta a consultar: MB (Magazine) ou SV (Samvale) — obrigatório.",
    )
    parser.add_argument(
        "--claim_id", type=int, required=False, default=None,
        help="Opcional — pula a busca automática e varre direto essa reclamação "
             "(use quando o script pedir pra você desempatar entre várias).",
    )
    parser.add_argument(
        "--bruto", action="store_true",
        help="Além do chat limpo, mostra o sender_role e o date_created crus de cada "
             "mensagem — pra conferir contra a tela da Central de Vendedores quando "
             "a classificação parecer estranha.",
    )
    args = parser.parse_args()
    return args.numero_pedido, args.empresa, args.claim_id, args.bruto


NUMERO_PEDIDO, CONTA, CLAIM_ID_FORCADO, BRUTO = ler_argumentos()


def formatar_data(data_iso):
    """'2026-08-24T16:02:00.000-04:00' -> '24/08/2026 16:02'"""
    if not data_iso or not isinstance(data_iso, str):
        return "—"
    try:
        instante = datetime.fromisoformat(data_iso)
    except ValueError:
        return data_iso
    instante = instante.astimezone(FUSO_HORARIO_EXIBICAO)
    return instante.strftime("%d/%m/%Y %H:%M")


def limpar_html_mensagem(texto):
    """Converte o HTML cru que o ML manda no campo 'message' (parágrafos,
    negrito, links) em texto simples e legível: <p> vira quebra de
    parágrafo, <br> vira quebra de linha, tags somem, entidades HTML
    (&nbsp; etc.) são decodificadas. Mensagens sem HTML (as suas e as da
    contraparte, normalmente texto puro) passam direto, sem alteração."""
    if not texto:
        return "(sem texto — mensagem só com anexo, ou campo vazio)"
    texto = re.sub(r"<br\s*/?>", "\n", texto, flags=re.IGNORECASE)
    texto = re.sub(r"</p\s*>", "\n\n", texto, flags=re.IGNORECASE)
    texto = re.sub(r"<[^>]+>", "", texto)
    texto = html.unescape(texto)
    linhas = [linha.strip() for linha in texto.split("\n")]
    texto_limpo = "\n".join(linhas).strip()
    texto_limpo = re.sub(r"\n{3,}", "\n\n", texto_limpo)
    return texto_limpo or "(sem texto — mensagem só com anexo, ou campo vazio)"


def buscar_claim_detalhe(claim_id):
    resposta = chamar_api(
        "GET", f"/post-purchase/v1/claims/{claim_id}",
        pasta_logs=PASTA_LOGS, conta=CONTA, nome_log=NOME_LOG,
    )
    return resposta.json()


def resolver_claim_id(numero_pedido):
    """Acha a reclamação certa a partir do número do pedido — mesma busca do
    consultar_linha_tempo_devolucao.py (claims/search por order_id). O
    desempate aqui é 'está em mediação' (mediador nos players OU
    stage == dispute), já que é isso que importa pra essa varredura de
    mensagens — diferente do outro script, que desempata por 'tem devolução
    física', que não é o critério certo aqui."""
    resposta_claims = chamar_api(
        "GET", "/post-purchase/v1/claims/search",
        pasta_logs=PASTA_LOGS, conta=CONTA, nome_log=NOME_LOG,
        params={"order_id": numero_pedido},
    )
    claims = resposta_claims.json().get("data", [])
    if not claims:
        console.print(f"Nenhuma reclamação encontrada pro pedido {numero_pedido}.")
        sys.exit(1)

    if len(claims) == 1:
        return claims[0]["id"]

    detalhes = [buscar_claim_detalhe(c["id"]) for c in claims]
    em_mediacao = [
        d for d in detalhes
        if d.get("stage") == "dispute" or any(p.get("role") == "mediator" for p in d.get("players", []))
    ]

    if len(em_mediacao) == 1:
        return em_mediacao[0]["id"]

    console.print(f"Pedido {numero_pedido} tem {len(claims)} reclamações e não deu pra escolher 1 só automaticamente:")
    ids_em_mediacao = {d.get("id") for d in em_mediacao}
    for d in detalhes:
        marca_mediacao = " [EM MEDIAÇÃO]" if d.get("id") in ids_em_mediacao else ""
        console.print(
            f"  claim_id={d.get('id')}  tipo={d.get('type')}  stage={d.get('stage')}  "
            f"status={d.get('status')}  aberta em {formatar_data(d.get('date_created'))}{marca_mediacao}",
            markup=False,
        )
    console.print("Rode de novo passando --claim_id=<a certa> pra desempatar.")
    sys.exit(1)


def descobrir_meu_papel(claim_id, meu_user_id):
    """Olha claims/{id}, acha qual papel (complainant/respondent) bate com o seu user_id.
    Importante por causa do achado de cancel_sale: o vendedor nem sempre é 'respondent'."""
    claim = buscar_claim_detalhe(claim_id)
    for player in claim.get("players", []):
        if player.get("user_id") == meu_user_id:
            return player.get("role")
    return None


def main():
    claim_id = CLAIM_ID_FORCADO or resolver_claim_id(NUMERO_PEDIDO)

    console.print(f"[bold]Pedido {NUMERO_PEDIDO}[/bold] — conta {CONTA} — reclamação {claim_id}")

    # 1) descobrir quem sou eu nessa reclamação (complainant ou respondent)
    me = chamar_api(
        "GET", "/users/me", pasta_logs=PASTA_LOGS, conta=CONTA, nome_log=NOME_LOG,
    ).json()
    meu_user_id = me.get("id")
    meu_papel = descobrir_meu_papel(claim_id, meu_user_id)
    if meu_papel is None:
        console.print("  [dim][aviso] Não achei seu user_id nos players dessa reclamação — "
                      "vou marcar tudo que não for 'mediator' como 'contraparte'.[/dim]")
    else:
        explicacao = EXPLICACAO_PAPEL.get(meu_papel, "papel não mapeado ainda")
        console.print(f"  Seu papel nessa reclamação: [bold]{meu_papel}[/bold]")
        console.print(f"  [dim]({explicacao} — atenção: em reclamações do tipo cancel_sale "
                      f"isso pode estar invertido, ainda não é garantido sempre ser você)[/dim]")

    # 2) buscar as mensagens
    mensagens = chamar_api(
        "GET", f"/post-purchase/v1/claims/{claim_id}/messages",
        pasta_logs=PASTA_LOGS, conta=CONTA, nome_log=NOME_LOG,
    ).json()
    if not mensagens:
        console.print("  Nenhuma mensagem encontrada.")
        return

    # ordena da mais antiga pra mais nova
    mensagens.sort(key=lambda m: m.get("date_created") or "")

    console.print()
    for m in mensagens:
        sender = m.get("sender_role")
        data = formatar_data(m.get("date_created"))
        status = m.get("status")

        if sender == "mediator":
            rotulo, cor = "O ML RESPONDEU", COR_MEDIADOR
        elif meu_papel is not None and sender == meu_papel:
            rotulo, cor = "VOCÊ RESPONDEU", COR_VOCE
        else:
            rotulo, cor = "A CONTRAPARTE RESPONDEU", COR_CONTRAPARTE

        aviso_status = "" if status == "available" else f"  [dim](status: {escape(str(status))})[/dim]"
        console.print(f"[bold {cor}]{rotulo}[/bold {cor}] em {data}{aviso_status}")
        if BRUTO:
            console.print(
                f"  [dim]bruto: sender_role={escape(repr(sender))}, "
                f"date_created={escape(repr(m.get('date_created')))}[/dim]"
            )

        texto_limpo = limpar_html_mensagem(m.get("message"))
        for linha in texto_limpo.split("\n"):
            if linha:
                console.print(f"  {linha}", markup=False, highlight=False)
            else:
                console.print()

        console.print()

    console.print("Fim.")


if __name__ == "__main__":
    try:
        main()
    except (ErroAPI, ErroAutenticacaoAPI, FalhaAutenticacao) as erro:
        console.print(f"[bold red]Erro ao chamar a API:[/bold red] {escape(str(erro))}")
        sys.exit(1)