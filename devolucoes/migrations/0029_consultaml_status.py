from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('devolucoes', '0028_consultaml'),
    ]

    operations = [
        migrations.AddField(
            model_name='consultaml',
            name='status',
            field=models.CharField(
                choices=[('aberta', 'Aberta'), ('encerrada', 'Encerrada')],
                default='aberta', max_length=10, verbose_name='Situação',
            ),
        ),
    ]
