from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('devolucoes', '0005_alter_peca_imagem'),
    ]

    operations = [
        migrations.AddField(
            model_name='peca',
            name='marca',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='pecas', to='devolucoes.marca'),
        ),
    ]