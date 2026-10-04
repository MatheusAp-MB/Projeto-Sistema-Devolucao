"""
core/estrutura_api/cliente_api.py

Camada única de comunicação com a API do Mercado Livre.
Todo app deve chamar a API através de chamar_api(), nunca via requests direto.

Reuso de conexão (04/10/2026): as duas chamadas HTTP daqui embaixo usam uma
requests.Session() persistente, com pool de conexão (HTTPAdapter), em vez da
função solta requests.request() (que abria 1 conexão TCP+TLS nova a cada
chamada). Mesmo padrão já validado no Sistema Interno V2 e medido aqui antes de
aplicar (scripts_exploracao_ML/testar_paralelismo_consultar_pedido.py, conta SV,
04/10/2026): a mesma chamada a /orders caiu de 389 ms pra 195 ms (mediana de
388 pra 174 ms). Mudança transversal: toda tela e todo script que passa por
chamar_api() ganha, sem mudar nada do lado de quem chama. requests.Session é
seguro pra uso concorrente entre threads (o pool do urllib3 por trás dela cuida
do próprio lock) — por isso 1 Session módulo-level basta.
"""

import re
import time
import json
import logging
import threading
from http.cookiejar import DefaultCookiePolicy
from pathlib import Path
from rich.logging import RichHandler

import requests
from requests.adapters import HTTPAdapter

from api_mercado_livre.core.auth.gerenciador_token import obter_token_valido
from api_mercado_livre.core.estrutura_api.protecao import (
    EspacadorChamadas, calcular_espera_backoff, INTERVALO_MINIMO_ENTRE_CHAMADAS_SEGUNDOS,
)

BASE_URL = "https://api.mercadolibre.com"

TIMEOUT_CONEXAO_SEGUNDOS = 10
TIMEOUT_LEITURA_SEGUNDOS = 30
ESPERA_RETRY_206_SEGUNDOS = 2

DADOS_SENSIVEIS = {"access_token", "refresh_token",
                   "client_secret", "password", "authorization"}

# * [EXPLICAÇÃO] → 50 é o tamanho usado e validado no Sistema Interno V2 (50 threads
#   simultâneas, sem saturar). Aqui a tela Consultar Pedido usa até ~6 threads por
#   consulta, então sobra folga. O retry continua 100% em chamar_api() — por isso o
#   HTTPAdapter fica com max_retries=0 (o padrão), pra não duplicar retry em 2 camadas.
TAMANHO_POOL_CONEXOES = 50

# * [EXPLICAÇÃO] → conexão parada há mais que isso é descartada antes da próxima
#   chamada. O V2 faz chamadas sem parar, mas este sistema fica minutos sem falar
#   com o ML (a Ana consulta um pedido, trabalha, consulta outro). Roteador ou
#   firewall podem derrubar em silêncio uma conexão ociosa — e aí a próxima chamada
#   esperaria até o timeout (30 s) numa conexão morta. Dentro de uma consulta
#   (rajada de ~10 chamadas em ~1 s) e entre consultas seguidas o reuso continua.
#   [NÃO CONFIRMADO] → 20 s é um valor conservador escolhido por mim; o tempo de
#   ociosidade que o ML tolera não é documentado.
OCIOSIDADE_MAXIMA_POOL_SEGUNDOS = 20

# Sessão persistente, módulo-level — criada 1 vez, reaproveitada por toda chamada.
_sessao = requests.Session()
_sessao.mount("https://", HTTPAdapter(pool_connections=10, pool_maxsize=TAMANHO_POOL_CONEXOES))
# * [EXPLICAÇÃO] → o requests.request() antigo criava uma sessão nova a cada chamada,
#   então nenhum cookie passava de uma chamada pra outra (nem de uma conta pra outra:
#   MB e SV rodam no mesmo processo). Esta política recusa todo cookie, pra manter
#   exatamente esse comportamento com a sessão persistente.
_sessao.cookies.set_policy(DefaultCookiePolicy(allowed_domains=[]))

_trava_pool = threading.Lock()
_trava_logger = threading.Lock()
_ultimo_uso_pool = time.monotonic()


def _renovar_pool_se_ocioso():
    """Descarta as conexões do pool se a última chamada foi há mais de
    OCIOSIDADE_MAXIMA_POOL_SEGUNDOS (ver nota acima). Seguro entre threads: a trava
    protege só esta checagem, nunca a chamada de rede."""
    global _ultimo_uso_pool
    agora = time.monotonic()
    with _trava_pool:
        if agora - _ultimo_uso_pool > OCIOSIDADE_MAXIMA_POOL_SEGUNDOS:
            _sessao.close()
        _ultimo_uso_pool = agora


def _enviar_requisicao(metodo, url, **kwargs):
    """Único ponto que faz HTTP de verdade: mesma assinatura do requests.request()."""
    _renovar_pool_se_ocioso()
    return _sessao.request(metodo, url, **kwargs)

# Instância única, compartilhada por todo o processo — garante que chamadas
# vindas de pontos diferentes do código (ex: um loop que classifica vários
# pedidos em sequência) respeitem o mesmo intervalo mínimo entre si, por
# conta (MB e SV são independentes).
_espacador = EspacadorChamadas(INTERVALO_MINIMO_ENTRE_CHAMADAS_SEGUNDOS)


def _mascarar_endpoint(endpoint: str) -> str:
    """Mascara qualquer ID numérico de usuário dentro da URL, antes de logar."""
    return re.sub(r"(/users/)\d+", r"\1***", endpoint)


class ErroAPI(Exception):
    """Erro genérico após esgotar tentativas ou erro não recuperável."""
    pass


class ErroAutenticacaoAPI(Exception):
    """401 mesmo com token considerado válido. Caso grave e distinto — não tenta de novo sozinho."""
    pass


def _configurar_logger(pasta_logs: Path, nome_log: str = "api"):
    pasta_logs = Path(pasta_logs)
    pasta_logs.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(f"cliente_api.{pasta_logs}.{nome_log}")
    # * [EXPLICAÇÃO] → a trava evita que 2 threads, na 1ª chamada de um logger (ex.: as
    #   chamadas em paralelo da tela Consultar Pedido), criem os handlers ao mesmo
    #   tempo e dupliquem cada linha do log.
    with _trava_logger:
        if not logger.handlers:
            logger.setLevel(logging.INFO)
            logger.propagate = False  # não deixa vazar pro logger raiz do Django (settings.py LOGGING)

            # Arquivo recebe tudo (INFO) — histórico completo de cada chamada,
            # útil pra depurar depois. Console só mostra WARNING+ (429, timeout,
            # erro real) — silêncio em requisição OK, que colidia com o redraw
            # ao vivo da barra de progresso (rich.Progress) e criava a enxurrada
            # de texto repetido.
            handler_arquivo = logging.FileHandler(
                pasta_logs / f"{nome_log}.log", encoding="utf-8")
            handler_arquivo.setLevel(logging.INFO)
            handler_arquivo.setFormatter(logging.Formatter(
                "%(asctime)s [%(levelname)s] %(message)s"))

            handler_console = RichHandler(rich_tracebacks=True, show_path=False)
            handler_console.setLevel(logging.WARNING)

            logger.addHandler(handler_arquivo)
            logger.addHandler(handler_console)
    return logger


def _log_seguro(logger, mensagem: str, dados: dict = None):
    if dados:
        dados_limpos = {k: ("***" if k.lower() in DADOS_SENSIVEIS else v)
                        for k, v in dados.items()}
        logger.info(f"{mensagem} | {dados_limpos}")
    else:
        logger.info(mensagem)


def chamar_api(metodo: str, endpoint: str, pasta_logs, conta: str, params: dict = None, json_body: dict = None, max_tentativas: int = 5, nome_log: str = "api", headers_extra: dict = None, espacador_ativo: bool = True, arquivos: dict = None, codigos_sucesso: set = None):
    """
    Ponto único de chamada à API do ML.

    metodo: "GET", "POST", etc.
    endpoint: caminho relativo, ex: "/items" (BASE_URL adicionado automaticamente)
    pasta_logs: Path da pasta de logs do app que está chamando (ex: integracao_mercado_livre/logs/<Empresa>)
    nome_log: nome do arquivo de log, sem ".log" — pra scripts diferentes que compartilham a mesma
              pasta_logs não sobrescreverem o log um do outro. Default "api" preserva o comportamento
              anterior, pra qualquer chamador que não especificar.
    headers_extra: headers adicionais além do Authorization (ex: {"x-format-new": "true"},
                   exigido por /shipments desde 12/10/2025; {"X-Api-Version": "2"}, exigido por
                   certos recursos de /orders). Opcional, default None preserva 100% do
                   comportamento anterior pra quem não especificar.
    espacador_ativo: se True (padrão), espera o intervalo mínimo entre chamadas (ver
                   protecao.EspacadorChamadas) antes de cada tentativa — proteção proativa
                   contra rajada, além do backoff reativo que já existia. Passar False só faz
                   sentido pra um chamador que já tem seu próprio controle de espaçamento.
    arquivos: dict pro upload multipart (ex: {"file": (nome, bytes, content_type)}), passado
                   direto pro requests como files=. Mutuamente exclusivo com json_body na
                   prática (o endpoint de anexo não usa corpo JSON). Default None preserva
                   100% do comportamento anterior pra quem não especificar. Adicionado
                   21/09/2026 pro envio de mensagem de mediação com foto.
    codigos_sucesso: quais status HTTP contam como sucesso (set). Default None vira {200} --
                   mesmo comportamento de sempre. Alguns endpoints do ML fogem do 200 (ex:
                   actions/send-message devolve 201 "created") -- passar {200, 201} nesses
                   casos. Adicionado 21/09/2026.
    """
    logger = _configurar_logger(pasta_logs, nome_log)
    url = f"{BASE_URL}{endpoint}"
    codigos_sucesso = codigos_sucesso or {200}

    for tentativa in range(max_tentativas):
        token = obter_token_valido(conta)
        headers = {"Authorization": f"Bearer {token}"}
        if headers_extra:
            headers.update(headers_extra)

        _log_seguro(logger, f"Chamando {metodo} {_mascarar_endpoint(endpoint)}", {
                    "params": params, "headers_extra": headers_extra, "tentativa": tentativa + 1})

        if espacador_ativo:
            _espacador.aguardar(conta)

        try:
            resposta = _enviar_requisicao(
                metodo, url, headers=headers, params=params, json=json_body, files=arquivos,
                timeout=(TIMEOUT_CONEXAO_SEGUNDOS, TIMEOUT_LEITURA_SEGUNDOS),
            )
        except requests.exceptions.Timeout:
            logger.error(
                f"Timeout em {metodo} {_mascarar_endpoint(endpoint)} (tentativa {tentativa + 1})")
            if tentativa == max_tentativas - 1:
                raise ErroAPI(
                    f"Timeout esgotado após {max_tentativas} tentativas em {_mascarar_endpoint(endpoint)}")
            continue

        if resposta.status_code in codigos_sucesso:
            logger.info(f"OK {metodo} {_mascarar_endpoint(endpoint)} ({resposta.status_code})")
            return resposta

        if resposta.status_code == 206:
            logger.warning(
                f"206 (parcial) em {_mascarar_endpoint(endpoint)}. Retentando em {ESPERA_RETRY_206_SEGUNDOS}s...")
            time.sleep(ESPERA_RETRY_206_SEGUNDOS)
            token = obter_token_valido(conta)
            headers = {"Authorization": f"Bearer {token}"}
            if headers_extra:
                headers.update(headers_extra)
            if espacador_ativo:
                _espacador.aguardar(conta)
            resposta_retry = _enviar_requisicao(
                metodo, url, headers=headers, params=params, json=json_body, files=arquivos,
                timeout=(TIMEOUT_CONEXAO_SEGUNDOS, TIMEOUT_LEITURA_SEGUNDOS),
            )
            if resposta_retry.status_code in codigos_sucesso:
                logger.info(
                    f"OK na 2ª tentativa após 206 em {_mascarar_endpoint(endpoint)}")
                return resposta_retry
            logger.warning(
                f"Ainda parcial após retry em {_mascarar_endpoint(endpoint)}. Retornando parcial.")
            return resposta_retry

        if resposta.status_code == 401:
            logger.error(
                f"401 em {_mascarar_endpoint(endpoint)} mesmo com token considerado válido.")
            raise ErroAutenticacaoAPI(
                f"API rejeitou o token (401) em {_mascarar_endpoint(endpoint)}, mesmo válido pelo gerenciador_token. "
                f"Possível revogação manual. Resposta: {resposta.text}"
            )

        if resposta.status_code == 429:
            espera = calcular_espera_backoff(tentativa, resposta)
            logger.warning(
                f"429 em {_mascarar_endpoint(endpoint)}. Aguardando {espera:.1f}s (tentativa {tentativa + 1}/{max_tentativas})")
            time.sleep(espera)
            continue

        logger.error(
            f"Erro {resposta.status_code} em {_mascarar_endpoint(endpoint)}: {resposta.text}")
        raise ErroAPI(
            f"Erro {resposta.status_code} em {_mascarar_endpoint(endpoint)}: {resposta.text}")

    raise ErroAPI(
        f"Número máximo de tentativas ({max_tentativas}) esgotado em {_mascarar_endpoint(endpoint)}")


# ─── CACHE LOCAL ──────────────────────────────────────────

def salvar_cache(chave: str, dados, pasta_cache):
    pasta_cache = Path(pasta_cache)
    pasta_cache.mkdir(parents=True, exist_ok=True)
    caminho = pasta_cache / f"{chave}.json"
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump({"timestamp": time.time(), "dados": dados},
                  f, ensure_ascii=False, indent=2)


def carregar_cache(chave: str, pasta_cache, max_idade_horas: float = 6):
    pasta_cache = Path(pasta_cache)
    caminho = pasta_cache / f"{chave}.json"
    if not caminho.exists():
        return None
    with open(caminho, "r", encoding="utf-8") as f:
        conteudo = json.load(f)
    idade_horas = (time.time() - conteudo["timestamp"]) / 3600
    if idade_horas > max_idade_horas:
        return None
    return conteudo["dados"]