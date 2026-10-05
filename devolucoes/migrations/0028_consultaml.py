from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('devolucoes', '0027_compatibilidade_ordem'),
    ]

    operations = [
        migrations.CreateModel(
            name='ConsultaML',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('numero', models.CharField(max_length=12, verbose_name='N.º da consulta no ML')),
                ('anotacao', models.CharField(blank=True, max_length=300, verbose_name='Anotação')),
                ('criada_em', models.DateTimeField(auto_now_add=True)),
                ('devolucao', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='consultas_ml', to='devolucoes.devolucao')),
            ],
            options={
                'verbose_name': 'Consulta no Mercado Livre',
                'verbose_name_plural': 'Consultas no Mercado Livre',
                'ordering': ['criada_em', 'id'],
            },
        ),
        migrations.AddConstraint(
            model_name='consultaml',
            constraint=models.UniqueConstraint(fields=('devolucao', 'numero'), name='consulta_ml_unica_por_devolucao'),
        ),
    ]
