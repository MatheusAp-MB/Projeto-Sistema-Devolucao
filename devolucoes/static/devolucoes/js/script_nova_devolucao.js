// devolucoes/static/devolucoes/js/script_nova_devolucao.js

// Função Objetivo: calcula e mostra, em tempo real, a situação de cada
// peça na tela de Nova Devolução — completa, parcial (com déficit),
// não recebida, ou completa mas com anotação — conforme o usuário marca
// o checkbox (peça de quantidade 1) ou digita quantos vieram (peça de
// quantidade maior que 1). É só feedback visual; o cálculo de verdade
// pra gerar o PDF é refeito no servidor a partir dos mesmos campos.

(function () {
    var listaPecas = document.getElementById('lista-pecas');
    if (!listaPecas) return;

    function atualizarLinha(pecaDiv) {
        var esperado = parseInt(pecaDiv.getAttribute('data-esperado'), 10);
        var status = pecaDiv.querySelector('.devolucao-peca-status');
        var anotacao = pecaDiv.querySelector('.devolucao-peca-anotacao');
        var recebido = 0;

        var checkUnica = pecaDiv.querySelector('.check-unica');
        var qtdMultipla = pecaDiv.querySelector('.qtd-multipla');

        if (checkUnica) {
            recebido = checkUnica.checked ? 1 : 0;
        } else if (qtdMultipla) {
            var valor = parseInt(qtdMultipla.value, 10);
            if (isNaN(valor) || valor < 0) valor = 0;
            if (valor > esperado) valor = esperado;
            qtdMultipla.value = valor;
            recebido = valor;
        }

        var temAnotacao = anotacao.value.trim().length > 0;

        status.classList.remove('status-completa', 'status-parcial', 'status-nao-recebida', 'status-atencao');

        if (recebido === 0) {
            status.textContent = 'Não recebida';
            status.classList.add('status-nao-recebida');
            anotacao.disabled = true;
        } else if (recebido < esperado) {
            status.textContent = 'Parcial — faltam ' + (esperado - recebido);
            status.classList.add('status-parcial');
            anotacao.disabled = false;
        } else if (temAnotacao) {
            status.textContent = 'Completa (ver anotação)';
            status.classList.add('status-atencao');
            anotacao.disabled = false;
        } else {
            status.textContent = 'Completa';
            status.classList.add('status-completa');
            anotacao.disabled = false;
        }
    }

    listaPecas.addEventListener('input', function (evento) {
        var pecaDiv = evento.target.closest('.devolucao-peca');
        if (pecaDiv) atualizarLinha(pecaDiv);
    });
    listaPecas.addEventListener('change', function (evento) {
        var pecaDiv = evento.target.closest('.devolucao-peca');
        if (pecaDiv) atualizarLinha(pecaDiv);
    });

    document.querySelectorAll('#lista-pecas .devolucao-peca').forEach(atualizarLinha);
})();