"""
Função Objetivo:
Reorganizar num único lugar os arquivos das fotos de conferência e de
reclamação do cliente que já existem no disco, movendo cada uma da
pasta antiga (upload_to antigo, tudo solto numa pasta só) pra estrutura
nova por pedido/peça:

    Devoluções/
        Pedido_<numero_pedido>/
            Fotos do cliente/
                foto_1.jpg, foto_2.jpg, ...
            Fotos da conferencia/
                <peca>_1.jpg, <peca>_2.jpg, ...

Usada tanto pela tela de manutenção "Reorganizar fotos" (dentro do
próprio sistema, sem precisar de terminal/Python/manage.py instalado —
pensada pra rodar direto no PC de quem for usar) quanto pelo comando de
terminal "reorganizar_fotos_devolucao" (mantido só como atalho pra quem
já tem o ambiente de desenvolvimento, ex: eu testando local).

Por que trabalha sempre com 1 alias de banco por vez, explícito: fora
do ciclo de uma requisição web (ex: rodando pelo terminal) o
EmpresaRouter não tem como saber qual empresa está "ativa" — isso só é
setado durante uma requisição de verdade (ver core/empresa.py). Dentro
de uma requisição (a tela de manutenção), a view já resolve o alias
certo sozinha, através da empresa que a pessoa tem selecionada no
sistema (o mesmo "trocar empresa" que já existe em toda tela).

Comportamento:
- aplicar=False (padrão): só SIMULA — mostra pra onde cada foto iria,
  sem mover nenhum arquivo e sem alterar nenhum registro no banco.
- aplicar=True: move o arquivo de verdade no disco e só DEPOIS de
  confirmar que o arquivo foi movido com sucesso, atualiza o campo
  "imagem" do registro (nunca atualiza o banco antes do arquivo estar
  no lugar novo).
- Nunca sobrescreve um arquivo existente: se já existe algo no
  caminho de destino, acrescenta "_dup2", "_dup3"... até achar um nome
  livre.
- Uma foto cujo arquivo já está no caminho novo correto é contada como
  "pulada" (idempotente — rodar de novo não faz nada de errado).
- Uma foto cujo arquivo não é encontrado no disco (path antigo não
  existe mais) é contada como "erro" e listada pra revisão manual —
  nunca derruba o processamento das outras fotos.
"""

import shutil
from pathlib import Path

from django.conf import settings
from django.utils.text import slugify

from .models import FotoConferenciaPeca, FotoReclamacaoCliente


def _caminho_absoluto(caminho_relativo):
    return Path(settings.MEDIA_ROOT) / caminho_relativo


def _destino_livre(caminho_absoluto_desejado):
    """Garante que nunca sobrescrevemos um arquivo já existente no
    destino — se "peca_1.jpg" já existir, tenta "peca_1_dup2.jpg",
    "peca_1_dup3.jpg"... até achar um nome livre."""
    if not caminho_absoluto_desejado.exists():
        return caminho_absoluto_desejado

    pasta = caminho_absoluto_desejado.parent
    nome_base = caminho_absoluto_desejado.stem
    extensao = caminho_absoluto_desejado.suffix
    contador = 2
    while True:
        candidato = pasta / f'{nome_base}_dup{contador}{extensao}'
        if not candidato.exists():
            return candidato
        contador += 1


def _mover_arquivo(foto, alias, caminho_relativo_novo, aplicar):
    """Move um único arquivo (ou só simula) e devolve um dict descrevendo
    o que aconteceu, pra montar o relatório na tela/terminal."""
    caminho_antigo_relativo = foto.imagem.name
    caminho_antigo_absoluto = _caminho_absoluto(caminho_antigo_relativo)

    if caminho_antigo_relativo == caminho_relativo_novo:
        # * [ATENÇÃO] → não basta o banco já achar que está no caminho
        #   novo — se o arquivo não existir ali de verdade (ex: alguém
        #   restaurou uma pasta de backup antiga por cima depois do banco
        #   já ter sido atualizado num teste anterior), isso é um erro de
        #   sincronia disco x banco, nunca pode ser relatado
        #   silenciosamente como "já estava certa".
        if caminho_antigo_absoluto.exists():
            return {'situacao': 'pulada', 'de': caminho_antigo_relativo, 'para': caminho_relativo_novo}
        return {
            'situacao': 'erro',
            'de': caminho_antigo_relativo,
            'para': caminho_relativo_novo,
            'motivo': (
                'o banco já registra esse caminho, mas o arquivo não existe nele — '
                'o disco está fora de sincronia com o banco (ex: uma pasta antiga foi '
                'restaurada por cima depois de já ter reorganizado). Revise manualmente.'
            ),
        }

    if not caminho_antigo_absoluto.exists():
        return {
            'situacao': 'erro',
            'de': caminho_antigo_relativo,
            'para': caminho_relativo_novo,
            'motivo': 'arquivo não encontrado no disco',
        }

    caminho_novo_absoluto = _caminho_absoluto(caminho_relativo_novo)
    caminho_novo_absoluto = _destino_livre(caminho_novo_absoluto)
    caminho_relativo_novo_final = str(caminho_novo_absoluto.relative_to(settings.MEDIA_ROOT)).replace('\\', '/')

    if not aplicar:
        return {'situacao': 'moveria', 'de': caminho_antigo_relativo, 'para': caminho_relativo_novo_final}

    caminho_novo_absoluto.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(caminho_antigo_absoluto), str(caminho_novo_absoluto))

    foto.imagem.name = caminho_relativo_novo_final
    foto.save(using=alias, update_fields=['imagem'])

    return {'situacao': 'movida', 'de': caminho_antigo_relativo, 'para': caminho_relativo_novo_final}


def _processar_fotos_conferencia(alias, aplicar):
    movimentos = []
    contador_por_conferencia = {}

    fotos = (
        FotoConferenciaPeca.objects
        .using(alias)
        .select_related('conferencia__devolucao', 'conferencia__peca')
        .order_by('conferencia_id', 'criada_em', 'id')
    )
    for foto in fotos:
        conferencia = foto.conferencia
        devolucao = conferencia.devolucao

        numero = contador_por_conferencia.get(conferencia.id, 0) + 1
        contador_por_conferencia[conferencia.id] = numero

        peca_slug = slugify(conferencia.peca.nome_generico) or 'peca'
        pedido_slug = slugify(devolucao.numero_pedido) or str(devolucao.pk)
        extensao = foto.imagem.name.rsplit('.', 1)[-1].lower() if '.' in foto.imagem.name else 'jpg'

        caminho_relativo_novo = (
            f'Devoluções/Pedido_{pedido_slug}/Fotos da conferencia/{peca_slug}_{numero}.{extensao}'
        )
        movimentos.append(_mover_arquivo(foto, alias, caminho_relativo_novo, aplicar))

    return movimentos


def _processar_fotos_reclamacao_cliente(alias, aplicar):
    movimentos = []
    contador_por_devolucao = {}

    fotos = (
        FotoReclamacaoCliente.objects
        .using(alias)
        .select_related('devolucao')
        .order_by('devolucao_id', 'criada_em', 'id')
    )
    for foto in fotos:
        devolucao = foto.devolucao

        numero = contador_por_devolucao.get(devolucao.id, 0) + 1
        contador_por_devolucao[devolucao.id] = numero

        pedido_slug = slugify(devolucao.numero_pedido) or str(devolucao.pk)
        extensao = foto.imagem.name.rsplit('.', 1)[-1].lower() if '.' in foto.imagem.name else 'jpg'

        caminho_relativo_novo = f'Devoluções/Pedido_{pedido_slug}/Fotos do cliente/foto_{numero}.{extensao}'
        movimentos.append(_mover_arquivo(foto, alias, caminho_relativo_novo, aplicar))

    return movimentos


def reorganizar_fotos_devolucao(alias, aplicar=False):
    """Roda a reorganização (simulada ou de verdade) num único banco e
    devolve um dict pronto pra exibir numa tela ou imprimir no terminal:

        {'alias': 'magazine', 'movimentos': [...], 'movidas': 2,
         'puladas': 0, 'erros': []}
    """
    movimentos = (
        _processar_fotos_conferencia(alias, aplicar)
        + _processar_fotos_reclamacao_cliente(alias, aplicar)
    )
    return {
        'alias': alias,
        'movimentos': movimentos,
        'movidas': sum(1 for m in movimentos if m['situacao'] in ('movida', 'moveria')),
        'puladas': sum(1 for m in movimentos if m['situacao'] == 'pulada'),
        'erros': [m for m in movimentos if m['situacao'] == 'erro'],
    }