# core/imagens.py

# Função Objetivo: converter foto HEIC/HEIF (o formato padrão das fotos de
# iPhone) em JPEG, pra ela abrir em qualquer navegador. Decisão de Matheus,
# 04/10/2026, a partir do pedido 2000017788033354 (SV): o chat mostrava que a
# foto existia, mas sem miniatura e sem abrir -- o Chrome/Edge não mostram
# HEIC, e o Pillow (que o ImageField do Django usa) também não abre HEIC
# sozinho. A regra é uma só pro sistema inteiro: a Ana SEMPRE vê e guarda a
# foto já convertida (JPEG).
#
# [ATENÇÃO] → depende do pacote `pillow-heif` (poetry add pillow-heif). Se ele
# não estiver instalado (ou a parte nativa dele não carregar), o sistema NÃO
# quebra: HEIC_DISPONIVEL fica False, converter_heic_para_jpeg() levanta
# ConversaoHeicIndisponivel e quem chama cai no comportamento de antes
# (repassa o arquivo como veio / avisa que a foto não foi importada).

import io
import logging

from django.core.files.base import ContentFile
from PIL import Image, ImageOps

logger = logging.getLogger(__name__)

try:
    from pillow_heif import register_heif_opener
    register_heif_opener()  # ensina o Pillow a abrir HEIC/HEIF
    HEIC_DISPONIVEL = True
except Exception:  # biblioteca ausente ou parte nativa que não carregou
    HEIC_DISPONIVEL = False

# O ML devolveu 'image/heic' nas fotos reais do teste de 04/10/2026; os outros
# três tipos são as variações que existem pro mesmo formato.
TIPOS_DE_IMAGEM_HEIC = {'image/heic', 'image/heif', 'image/heic-sequence', 'image/heif-sequence'}
EXTENSOES_HEIC = ('.heic', '.heif')
# Marcas (bytes 8 a 12 do arquivo, logo depois de 'ftyp') dos arquivos HEIC/HEIF.
MARCAS_DE_ARQUIVO_HEIC = {b'heic', b'heix', b'hevc', b'hevx', b'heim', b'heis', b'hevm', b'hevs', b'mif1', b'msf1'}
# Qualidade alta de propósito: a foto do cliente é evidência de mediação, então
# a resolução original é mantida (nada de reduzir) e só a compressão muda.
QUALIDADE_JPEG_CONVERTIDO = 90


class ConversaoHeicIndisponivel(RuntimeError):
    """O pacote pillow-heif não está instalado/carregado nesta máquina."""


def parece_heic(cabecalho=b'', tipo='', nome=''):
    """True se o arquivo é HEIC/HEIF, por qualquer um dos 3 sinais: o tipo que
    o ML (ou o navegador) declarou, a extensão do nome, ou a assinatura nos
    primeiros bytes do arquivo ('cabecalho' = os primeiros 12 bytes ou mais).
    Olha os 3 porque nenhum sozinho é confiável (o tipo pode vir genérico, a
    extensão pode faltar)."""
    tipo = (tipo or '').split(';')[0].strip().lower()
    if tipo in TIPOS_DE_IMAGEM_HEIC:
        return True
    if (nome or '').strip().lower().endswith(EXTENSOES_HEIC):
        return True
    cabecalho = cabecalho or b''
    return len(cabecalho) >= 12 and cabecalho[4:8] == b'ftyp' and cabecalho[8:12] in MARCAS_DE_ARQUIVO_HEIC


def converter_heic_para_jpeg(conteudo):
    """Bytes de uma foto HEIC -> bytes de um JPEG (mesma resolução, na posição
    certa: o celular guarda a rotação da foto à parte, e ela é aplicada aqui).
    Levanta ConversaoHeicIndisponivel sem o pillow-heif, ou qualquer erro do
    Pillow se o arquivo estiver corrompido -- quem chama decide o que fazer."""
    if not HEIC_DISPONIVEL:
        raise ConversaoHeicIndisponivel('pillow-heif não está instalado')
    with Image.open(io.BytesIO(conteudo)) as imagem:
        imagem = ImageOps.exif_transpose(imagem).convert('RGB')
        saida = io.BytesIO()
        imagem.save(saida, format='JPEG', quality=QUALIDADE_JPEG_CONVERTIDO)
    return saida.getvalue()


def jpeg_se_for_heic(arquivo_enviado):
    """Pra foto que a pessoa anexou num formulário (request.FILES): se for
    HEIC, devolve um ContentFile JPEG com o mesmo nome base; senão (ou se a
    conversão não for possível), devolve o MESMO arquivo, sem mexer -- o
    comportamento de antes. Nunca levanta erro."""
    try:
        nome = getattr(arquivo_enviado, 'name', '') or ''
        tipo = getattr(arquivo_enviado, 'content_type', '') or ''
        arquivo_enviado.seek(0)
        cabecalho = arquivo_enviado.read(12)
        arquivo_enviado.seek(0)
        if not parece_heic(cabecalho, tipo, nome):
            return arquivo_enviado
        jpeg = converter_heic_para_jpeg(arquivo_enviado.read())
        base = nome.rsplit('.', 1)[0] if '.' in nome else (nome or 'foto')
        return ContentFile(jpeg, name=f'{base}.jpg')
    except Exception:
        logger.warning('Não consegui converter a foto HEIC enviada; salvando como veio.', exc_info=True)
        try:
            arquivo_enviado.seek(0)
        except Exception:
            pass
        return arquivo_enviado
