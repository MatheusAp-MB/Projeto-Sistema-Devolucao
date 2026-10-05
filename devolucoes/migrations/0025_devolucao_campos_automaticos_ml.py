from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('devolucoes', '0024_travachatmediacao'),
    ]

    operations = [
        migrations.AddField(
            model_name='devolucao',
            name='campos_automaticos_ml',
            field=models.JSONField(blank=True, default=None, help_text='Quais campos vieram sozinhos da API do Mercado Livre quando a devolução foi criada, com o valor que o ML trouxe — usado só pelos selos (ícone de nuvem) da tela Editar devolução. Vazio (None) = devolução criada antes desse controle; {} = criada à mão.', null=True, verbose_name='Campos preenchidos sozinhos pelo ML ao criar'),
        ),
    ]
