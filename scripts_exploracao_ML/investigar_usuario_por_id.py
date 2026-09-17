# scripts_exploracao_ML/investigar_usuario_por_id.py
#
# Objetivo ÚNICO: testar a hipótese registrada no vault de que o código ao
# lado do nome do cliente na etiqueta (ex: "#443851581") é o buyer.id do
# comprador no Mercado Livre. Chama GET /users/{USER_ID} -- endpoint público
# de perfil, não exige que seja seu comprador nem pedido nenhum conhecido.
#
# Se vier um perfil real (nickname, cidade, etc.) e ele bater com o nome/
# cidade do cliente da etiqueta, é forte indício de que o número É o
# user_id/buyer.id certo. Se vier erro (404, "user not found"), a hipótese
# cai por terra -- o número é outra coisa.
#
# Só leitura. Não toca no banco.

import json
import sys
from pathlib import Path

_RAIZ_DO_PROJETO = Path(__file__).resolve().parent.parent
if str(_RAIZ_DO_PROJETO) not in sys.path:
    sys.path.insert(0, str(_RAIZ_DO_PROJETO))

from api_mercado_livre.core.estrutura_api.cliente_api import chamar_api, ErroAPI, ErroAutenticacaoAPI

# ==== CONFIGURA AQUI ANTES DE RODAR ====
CONTA = "MB"                # "MB" ou "SV" -- a conta que faz a chamada (não precisa ser o comprador)
USER_ID_A_TESTAR = "443851581"   # o número da etiqueta, sem o "#"
# ========================================

PASTA_LOGS = Path(__file__).resolve().parent / "logs"

try:
    resposta = chamar_api(
        "GET", f"/users/{USER_ID_A_TESTAR}",
        pasta_logs=PASTA_LOGS, conta=CONTA,
        nome_log="investigar_usuario_por_id",
    )
except (ErroAPI, ErroAutenticacaoAPI) as erro:
    print(f"Erro ao chamar a API -- provável indício de que '{USER_ID_A_TESTAR}' NÃO é um user_id válido: {erro}")
else:
    perfil = resposta.json()
    print(json.dumps(perfil, ensure_ascii=False, indent=2))
    print(f"\nCompare 'nickname', cidade/endereço acima com o nome real da etiqueta (Rafael Ramos Machado, Araucária-PR).")