from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('devolucoes', '0004_peca_nome_generico_nome_tecnico_codigo_fabricante'),
    ]

    operations = [
        migrations.AlterField(
            model_name='peca',
            name='imagem',
            field=models.ImageField(upload_to='catalogo_pecas/'),
        ),
    ]