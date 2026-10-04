# scripts_exploracao_ML/painel_html.py
#
# Preenche o modelo HTML (modelo_analise_pedido.html) com os dados de uma
# análise de pedido e grava em logs/analise_pedido.html (sempre o mesmo
# arquivo, sobrescrito a cada chamada de gravar_painel). O Python nunca
# escreve HTML: só troca marcadores do modelo pelos valores.
#
# Marcadores no modelo:
#   {{CHAVE}}   -> valor simples, escapado pra HTML. Se a chave termina em
#                  _HTML, entra cru (usado só em ABRIR_HTML).
#   <!--BLOCO:NOME-->...<!--/BLOCO:NOME-->
#               -> repetido uma vez por item da lista dados["NOME"]. Lista
#                  vazia = o bloco some (serve de "se tiver"). Blocos podem
#                  ficar dentro de blocos, e cada item enxerga também as
#                  chaves dos níveis de fora.
#
# Chave que o modelo pede e os dados não têm aparece na própria página como
# [FALTA:CHAVE] — assim erro de digitação não passa em branco.

import html
import re
from collections import ChainMap
from pathlib import Path

PASTA = Path(__file__).resolve().parent
MODELO = PASTA / "modelo_analise_pedido.html"
SAIDA = PASTA / "logs" / "analise_pedido.html"  # logs/ já está no .gitignore (tem dado real de comprador)

# Um bloco inteiro OU um {{campo}}, numa passada só (o que entra no lugar de
# um marcador nunca é reprocessado como se fosse marcador).
_PADRAO = re.compile(r"<!--BLOCO:(\w+)-->(.*?)<!--/BLOCO:\1-->|\{\{(\w+)\}\}", re.S)


def preencher(modelo, dados):
    def trocar(m):
        if m.group(1):  # bloco repetido
            itens = dados.get(m.group(1), [])
            return "".join(preencher(m.group(2), ChainMap(item, dados)) for item in itens)
        chave = m.group(3)  # campo simples
        if chave not in dados:
            return f"[FALTA:{chave}]"
        valor = "—" if dados[chave] is None else str(dados[chave])
        return valor if chave.endswith("_HTML") else html.escape(valor)

    return _PADRAO.sub(trocar, modelo)


def gravar_painel(dados):
    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    SAIDA.write_text(preencher(MODELO.read_text(encoding="utf-8"), dados), encoding="utf-8")
    return SAIDA


# ---------------------------------------------------------------------------
# EXEMPLO FICTÍCIO — só pra ver o painel funcionando. Nada aqui veio da API.
# No script real, estes dicionários são montados a partir das respostas.
# ---------------------------------------------------------------------------

def chamada(**campos):
    base = {"METODO": "GET", "ABRIR_HTML": "", "ORIGEM_ANCORA": "topo", "PARAMS": [{"TEXTO": "nenhum"}],
            "NOTA": [], "DADOS": [], "ERRO_CORPO": []}
    base.update(campos)
    return base


def exemplo():
    c1 = chamada(
        NUM=1, NOME="Pedido", ENDPOINT_MODELO="/orders/{pedido}", ESTADO="ok", STATUS="200", TEMPO="318 ms",
        TROUXE="Pago · 1 item · 100,00 BRL · envio 40000000001",
        PARA_QUE="Dados da venda: comprador, itens, preço e id do envio de ida",
        ORIGEM="entrada (número do pedido)", URL="https://api.mercadolibre.com/orders/2000000000000000",
        DADOS=[{
            "FATOS": [
                {"ROTULO": "Status do pedido", "VALOR": "Pago", "CAMPO_API": "status = paid",
                 "SELO": [{"ESTADO": "ok", "TEXTO": "confirmado"}]},
                {"ROTULO": "Comprador", "VALOR": "Fulano <de> Tal & Cia (exemplo)",
                 "CAMPO_API": "buyer.first_name + buyer.last_name", "SELO": []},
                {"ROTULO": "ID do envio de ida", "VALOR": "40000000001", "CAMPO_API": "shipping.id", "SELO": []},
            ],
            "CAMPOS_QTD": 3,
            "CAMPOS": [
                {"CAMINHO": "status", "VALOR": "paid", "TRADUCAO": "Pago"},
                {"CAMINHO": "buyer.first_name", "VALOR": "Fulano", "TRADUCAO": "—"},
                {"CAMINHO": "shipping.id", "VALOR": "40000000001", "TRADUCAO": "—"},
            ],
            "JSON_CRU": '{\n  "status": "paid",\n  "shipping": {"id": 40000000001}\n}',
        }],
    )
    c2 = chamada(
        NUM=2, NOME="Detalhe da claim", ENDPOINT_MODELO="/post-purchase/v1/claims/{claim}",
        ESTADO="ok", STATUS="200", TEMPO="289 ms",
        TROUXE="Fechada · coberto pela política de proteção do ML · encerrada pelo mediador",
        PARA_QUE="Tipo, etapa, status, motivo e resolução da claim",
        ORIGEM="#1 → data[0].id", ORIGEM_ANCORA="c1", PARAMS=[{"TEXTO": "claim = 5000000001"}],
        URL="https://api.mercadolibre.com/post-purchase/v1/claims/5000000001",
        DADOS=[{
            "FATOS": [
                {"ROTULO": "Status", "VALOR": "Fechada", "CAMPO_API": "status = closed",
                 "SELO": [{"ESTADO": "ok", "TEXTO": "confirmado"}]},
                {"ROTULO": "Motivo", "VALOR": "XYZ_EXEMPLO", "CAMPO_API": "reason_id",
                 "SELO": [{"ESTADO": "av", "TEXTO": "sem tradução confirmada — código cru"}]},
            ],
            "CAMPOS_QTD": 2,
            "CAMPOS": [
                {"CAMINHO": "status", "VALOR": "closed", "TRADUCAO": "Fechada"},
                {"CAMINHO": "reason_id", "VALOR": "XYZ_EXEMPLO", "TRADUCAO": "sem tradução confirmada"},
            ],
            "JSON_CRU": '{\n  "status": "closed",\n  "reason_id": "XYZ_EXEMPLO"\n}',
        }],
    )
    c3 = chamada(
        NUM=3, NOME="Devolução", ENDPOINT_MODELO="/post-purchase/v2/claims/{claim}/returns",
        ESTADO="av", STATUS="404", TEMPO="334 ms", ABRIR_HTML=" open",
        TROUXE="A API respondeu que não existe devolução física para esta claim",
        PARA_QUE="Saber se existe devolução física, em que status e como está o dinheiro",
        ORIGEM="#2 → id", ORIGEM_ANCORA="c2", PARAMS=[{"TEXTO": "claim = 5000000001"}],
        URL="https://api.mercadolibre.com/post-purchase/v2/claims/5000000001/returns",
        NOTA=[{"ESTADO": "av", "TITULO": "404 confirmado.",
               "TEXTO": "Resposta válida da API, não falha. O status real aparece aqui para não ser confundido com 429 ou timeout."}],
        ERRO_CORPO=[{"TEXTO": "{ corpo do erro exatamente como a API devolveu }"}],
    )
    c4 = chamada(
        NUM=4, NOME="Envio de volta", ENDPOINT_MODELO="/shipments/{volta}",
        ESTADO="nd", STATUS="não executada", TEMPO="—",
        TROUXE="Depende de #3, que não trouxe dado", PARA_QUE="Endereços e status do envio de volta",
        ORIGEM="#3 → shipments[0].shipment_id", ORIGEM_ANCORA="c3", PARAMS=[{"TEXTO": "volta = ?"}],
        URL="(não chamada)",
        NOTA=[{"ESTADO": "nd", "TITULO": "Não executada.",
               "TEXTO": "Precisaria de shipments[0].shipment_id vindo do #3, e o #3 respondeu 404."}],
    )
    c5 = chamada(
        NUM=5, NOME="Usuário da conta", ENDPOINT_MODELO="/users/me", ESTADO="er", STATUS="erro",
        TEMPO="5 tentativas", ABRIR_HTML=" open",
        TROUXE="Falhou: timeout após 5 tentativas, nenhum dado recebido",
        PARA_QUE="Quem sou eu, para saber meu papel na claim", ORIGEM="conta SV",
        URL="https://api.mercadolibre.com/users/me",
        NOTA=[{"ESTADO": "er", "TITULO": "Falhou.",
               "TEXTO": "Timeout esgotado após 5 tentativas. Falha de rede, diferente de um 404."}],
    )

    # No script real, resumo, faixa e contagens são calculados a partir das chamadas.
    return {
        "PEDIDO": "2000000000000000", "CONTA": "SV", "GERADO_EM": "03/10/2026 às 20:15",
        "TOTAL_CHAMADAS": 5, "TEMPO_TOTAL": "1,9 s", "SITUACAO": "EXEMPLO FICTÍCIO — nada aqui veio da API",
        "RESUMO": [
            {"ESTADO": "ok", "TEXTO": "2 × 200"}, {"ESTADO": "av", "TEXTO": "1 × 404"},
            {"ESTADO": "er", "TEXTO": "1 × erro"}, {"ESTADO": "nd", "TEXTO": "1 não executada"},
        ],
        "FAIXA": [
            {"N": 1, "NOME": "Compra", "PONTOS": [{"ESTADO": "ok"}]},
            {"N": 2, "NOME": "Reclamação", "PONTOS": [{"ESTADO": "ok"}]},
            {"N": 3, "NOME": "Devolução física", "PONTOS": [{"ESTADO": "av"}, {"ESTADO": "nd"}]},
            {"N": 4, "NOME": "Apoio", "PONTOS": [{"ESTADO": "er"}]},
        ],
        "ETAPAS": [
            {"N": 1, "NOME": "Compra", "CONTAGEM": "1 chamada · 1 × 200", "CHAMADAS": [c1]},
            {"N": 2, "NOME": "Reclamação", "CONTAGEM": "1 chamada · 1 × 200", "CHAMADAS": [c2]},
            {"N": 3, "NOME": "Devolução física", "CONTAGEM": "2 chamadas · 1 × 404 · 1 não executada",
             "CHAMADAS": [c3, c4]},
            {"N": 4, "NOME": "Apoio", "CONTAGEM": "1 chamada · 1 erro", "CHAMADAS": [c5]},
        ],
    }


if __name__ == "__main__":
    caminho = gravar_painel(exemplo())
    print(f"Painel gravado em: {caminho}")