import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('devolucoes', '0003_alter_produto_codigo_fabricante_alter_produto_marca_and_more'),
    ]

    operations = [
        migrations.RenameField(
            model_name='peca',
            old_name='nome',
            new_name='nome_generico',
        ),
        migrations.AddField(
            model_name='peca',
            name='nome_tecnico',
            field=models.CharField(blank=True, max_length=200, verbose_name='Nome técnico'),
        ),
        migrations.AddField(
            model_name='peca',
            name='codigo_fabricante',
            field=models.CharField(blank=True, max_length=100, null=True, unique=True, verbose_name='Código do fabricante'),
        ),
        migrations.AlterModelOptions(
            name='peca',
            options={'ordering': ['nome_generico']},
        ),
        migrations.AlterField(
            model_name='compatibilidade',
            name='quantidade_esperada',
            field=models.PositiveIntegerField(default=1, validators=[django.core.validators.MinValueValidator(1)]),
        ),
    ]