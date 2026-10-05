from django.db import migrations, models


def preencher_ordem_alfabetica(apps, schema_editor):
    """Cada produto já tem suas peças vinculadas; a ordem de partida é a MESMA que a tela de
    conferência já mostrava (alfabética pelo nome genérico), então nada muda na tela até alguém
    arrastar uma peça. Grava explicitamente no banco que está sendo migrado (magazine ou samvale)."""
    Compatibilidade = apps.get_model('devolucoes', 'Compatibilidade')
    banco = schema_editor.connection.alias

    ids_produtos = set(Compatibilidade.objects.using(banco).values_list('produto_id', flat=True))
    for produto_id in ids_produtos:
        vinculos = list(
            Compatibilidade.objects.using(banco).filter(produto_id=produto_id).select_related('peca')
        )
        vinculos.sort(key=lambda vinculo: (vinculo.peca.nome_generico, vinculo.id))
        for posicao, vinculo in enumerate(vinculos, start=1):
            Compatibilidade.objects.using(banco).filter(pk=vinculo.pk).update(ordem=posicao)


class Migration(migrations.Migration):

    dependencies = [
        ('devolucoes', '0026_preferenciatela'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='compatibilidade',
            options={'ordering': ['produto__nome', 'ordem', 'peca__nome_generico']},
        ),
        migrations.AddField(
            model_name='compatibilidade',
            name='ordem',
            field=models.PositiveIntegerField(default=0, verbose_name='Ordem'),
        ),
        migrations.RunPython(preencher_ordem_alfabetica, migrations.RunPython.noop),
    ]
