from django.db import models


class ModeloAnotacao(models.Model):
    """Modelo/preset de anotação pronta pra usar na Conferência de Peças
    (campo "Anotação" de cada peça) — em vez de digitar "riscada" toda
    vez, a pessoa cadastra esse texto uma vez aqui e escolhe num
    autocomplete (ver script_autocomplete_anotacao.js). Lista GLOBAL
    (não é por peça, nem por produto) — e digitar um texto livre no
    campo continua sempre aceito mesmo que não esteja nessa lista; um
    modelo só entra aqui quando alguém cadastra deliberadamente na tela
    "Modelos de anotação" (link a partir da tela "Peças"). Excluir um
    modelo não afeta anotações já salvas com aquele texto — é só um
    atalho pra digitar, não um vínculo de banco."""
    texto = models.CharField(max_length=255, unique=True)

    class Meta:
        ordering = ['texto']

    def __str__(self):
        return self.texto
