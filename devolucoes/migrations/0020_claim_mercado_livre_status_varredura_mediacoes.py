from django.db import migrations, models


def semear_status_varredura(apps, schema_editor):
    StatusVarreduraMediacoes = apps.get_model('devolucoes', 'StatusVarreduraMediacoes')
    StatusVarreduraMediacoes.objects.get_or_create(pk=1)


def remover_status_varredura(apps, schema_editor):
    StatusVarreduraMediacoes = apps.get_model('devolucoes', 'StatusVarreduraMediacoes')
    StatusVarreduraMediacoes.objects.filter(pk=1).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('devolucoes', '0019_devolucao_claim_id_mediacaoavulsa_claim_id'),
    ]

    operations = [
        migrations.CreateModel(
            name='ClaimMercadoLivre',
            fields=[
                ('claim_id', models.CharField(max_length=50, primary_key=True, serialize=False, verbose_name='ID da reclamação/mediação no ML')),
                ('numero_pedido', models.CharField(db_index=True, help_text='Chave de casamento com Devolucao.numero_pedido — não é única aqui (mais de 1 claim pode existir pro mesmo pedido ao longo do tempo).', max_length=100, verbose_name='Número do pedido')),
                ('meu_papel', models.CharField(help_text='"respondent" ou "complainant" — vem de qual busca (players.role) encontrou o claim.', max_length=20, verbose_name='Nosso papel nesta reclamação')),
                ('dados_brutos', models.JSONField(help_text='Resposta bruta da API (stage, type, date_created, players...) — usada pra recalcular a combinação Reclamação/Mediação/Devolução via categoria_slug().', verbose_name='Dados brutos do claim')),
                ('tem_devolucao_fisica', models.BooleanField(help_text='True/False confirmado via GET /post-purchase/v2/claims/{id}/returns — None quando não deu pra confirmar (erro que não foi um 404 limpo).', null=True, verbose_name='Tem devolução física associada?')),
                ('mensagens', models.JSONField(blank=True, null=True, verbose_name='Mensagens da reclamação')),
                ('esta_acompanhando', models.BooleanField(default=False, help_text='Liga automaticamente (casa com Devolucao pelo numero_pedido) ou manualmente ("Acompanhar") — só desliga por ação explícita ("Deixar de acompanhar"), nunca reativa sozinha numa varredura futura.', verbose_name='Está em acompanhamento?')),
                ('ultima_busca_em', models.DateTimeField(verbose_name='Última busca em')),
                ('criado_em', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'ordering': ['-ultima_busca_em'],
            },
        ),
        migrations.CreateModel(
            name='StatusVarreduraMediacoes',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('rodando', models.BooleanField(default=False, verbose_name='Rodando agora?')),
                ('tipo_execucao', models.CharField(blank=True, choices=[('completa', 'Varredura completa'), ('acompanhados', 'Atualização de itens em acompanhamento')], max_length=20, null=True, verbose_name='Tipo de execução')),
                ('fase_atual', models.CharField(blank=True, max_length=100, null=True, verbose_name='Fase atual')),
                ('processados', models.IntegerField(default=0, verbose_name='Processados')),
                ('total', models.IntegerField(default=0, verbose_name='Total')),
                ('itens_nao_confirmados', models.IntegerField(default=0, help_text='Soma de erros pontuais (devolução física e/ou mensagens) que não pararam o loop — mesmo padrão do script de exploração.', verbose_name='Itens não confirmados')),
                ('iniciado_em', models.DateTimeField(blank=True, null=True, verbose_name='Iniciado em')),
                ('finalizado_em', models.DateTimeField(blank=True, null=True, verbose_name='Finalizado em')),
                ('erro', models.TextField(blank=True, help_text='Mensagem técnica crua da falha, só pra debug do Matheus (banco/logs) — NUNCA exibida pra Ana. A tela mostra sempre o mesmo texto fixo e amigável quando este campo não está vazio.', verbose_name='Erro técnico (debug)')),
            ],
        ),
        migrations.RunPython(semear_status_varredura, remover_status_varredura),
    ]
