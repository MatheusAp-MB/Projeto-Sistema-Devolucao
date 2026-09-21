from django.db import migrations, models


def semear_trava_chat_mediacao(apps, schema_editor):
    TravaChatMediacao = apps.get_model('devolucoes', 'TravaChatMediacao')
    TravaChatMediacao.objects.get_or_create(pk=1)


def remover_trava_chat_mediacao(apps, schema_editor):
    TravaChatMediacao = apps.get_model('devolucoes', 'TravaChatMediacao')
    TravaChatMediacao.objects.filter(pk=1).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('devolucoes', '0023_claimmercadolivre_ultima_mensagem_de_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='TravaChatMediacao',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('liberado', models.BooleanField(default=False, verbose_name='Chat de resposta liberado?')),
            ],
        ),
        migrations.RunPython(semear_trava_chat_mediacao, remover_trava_chat_mediacao),
    ]
