from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('devolucoes', '0025_devolucao_campos_automaticos_ml'),
    ]

    operations = [
        migrations.CreateModel(
            name='PreferenciaTela',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('chave', models.CharField(max_length=40, unique=True, verbose_name='Aba / tela')),
                ('configuracao', models.JSONField(default=dict, verbose_name='Ordem e filtros salvos')),
                ('atualizado_em', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Padrão salvo de tela',
                'verbose_name_plural': 'Padrões salvos de tela',
            },
        ),
    ]
