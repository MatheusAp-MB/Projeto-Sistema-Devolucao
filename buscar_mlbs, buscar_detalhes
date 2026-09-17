"""
core/estrutura_api/protecao.py

Camada de proteção contra chamada excessiva à API do Mercado Livre — 2
peças separadas e testáveis isoladamente, nunca fundidas numa classe só
(ver nota "Padrão de Robustez para Clientes de API Externa" no vault):

- EspacadorChamadas: proativo — garante um intervalo mínimo fixo entre
  uma chamada e a próxima, por conta (MB e SV têm tokens/limites
  independentes na API). Só sabe de tempo, nada de HTTP.
- calcular_espera_backoff: reativo — só entra em ação depois que a API
  já respondeu com erro passageiro (429). Usa Retry-After quando a API
  informa; senão cai pra exponencial com jitter, com teto.
"""

import time
import random
import threading

TETO_ESPERA_SEGUNDOS = 30
MARGEM_RETRY_AFTER_SEGUNDOS = 2

# Valor de partida conservador — ainda não temos confirmação empírica de
# como a API do Mercado Livre se comporta sob carga (achado de 17/09/2026:
# os tempos de espera observados batem com o fallback exponencial, não com
# um Retry-After confiável vindo do ML). Ajustável depois, observando o
# comportamento real.
INTERVALO_MINIMO_ENTRE_CHAMADAS_SEGUNDOS = 0.4


class EspacadorChamadas:
    """Espaçador proativo: garante um intervalo mínimo entre uma chamada
    e a próxima, por conta — não deixa uma rajada de chamadas sair antes
    mesmo de a API reclamar. Peça isolada e testável: só lida com tempo,
    não sabe nada de HTTP nem de erro."""

    def __init__(self, intervalo_minimo_segundos: float):
        self._intervalo_minimo = intervalo_minimo_segundos
        self._ultima_chamada_por_conta = {}
        self._lock = threading.Lock()

    def aguardar(self, conta: str):
        """Bloqueia (sleep) o tempo que falta pra completar o intervalo
        mínimo desde a última chamada dessa conta. Se já passou tempo
        suficiente (ex: a chamada anterior demorou por causa da rede),
        não espera nada."""
        with self._lock:
            agora = time.monotonic()
            ultima = self._ultima_chamada_por_conta.get(conta)
            if ultima is not None:
                decorrido = agora - ultima
                falta = self._intervalo_minimo - decorrido
                if falta > 0:
                    time.sleep(falta)
            self._ultima_chamada_por_conta[conta] = time.monotonic()


def calcular_espera_backoff(tentativa: int, resposta) -> float:
    """Backoff reativo: usa Retry-After se a API informar; senão backoff
    exponencial + jitter, com teto de 30s. Peça isolada e testável: só
    calcula o tempo de espera, não dorme e não sabe de conta nenhuma —
    quem chama decide o que fazer com o valor retornado."""
    retry_after = resposta.headers.get("Retry-After")
    if retry_after:
        try:
            return float(retry_after) + MARGEM_RETRY_AFTER_SEGUNDOS
        except ValueError:
            pass

    espera_calculada = (2 ** tentativa) + random.uniform(0, 1)
    return min(espera_calculada, TETO_ESPERA_SEGUNDOS)