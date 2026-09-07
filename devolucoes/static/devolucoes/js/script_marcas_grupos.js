// devolucoes/static/devolucoes/js/script_marcas_grupos.js

// Função Objetivo: comportamentos da tela de Marcas e Grupos Fornecedores
// — mostrar/esconder os formulários de "+ Novo grupo"/"+ Nova marca", e
// confirmação antes de excluir (o vínculo com produtos/marcas some, mas
// o objeto marca/produto em si continua existindo — a ação não tem
// volta, então confirma antes).

(function () {
    var botaoNovoGrupo = document.getElementById('botao-nova-linha-grupo');
    var formNovoGrupo = document.getElementById('form-novo-grupo');
    if (botaoNovoGrupo && formNovoGrupo) {
        botaoNovoGrupo.addEventListener('click', function () {
            formNovoGrupo.hidden = !formNovoGrupo.hidden;
        });
    }

    var botaoNovaMarca = document.getElementById('botao-nova-linha-marca');
    var formNovaMarca = document.getElementById('form-nova-marca');
    if (botaoNovaMarca && formNovaMarca) {
        botaoNovaMarca.addEventListener('click', function () {
            formNovaMarca.hidden = !formNovaMarca.hidden;
        });
    }
})();

(function () {
    document.addEventListener('submit', function (evento) {
        var form = evento.target;
        if (!form.classList) return;

        if (form.classList.contains('marcas-form-excluir-grupo')) {
            var botaoG = form.querySelector('.marcas-botao-excluir');
            var nomeG = botaoG ? botaoG.getAttribute('data-nome') : 'este grupo';
            if (!window.confirm('Excluir o grupo "' + nomeG + '"? As marcas vinculadas continuam existindo, só ficam sem grupo.')) {
                evento.preventDefault();
            }
            return;
        }

        if (form.classList.contains('marcas-form-excluir-marca')) {
            var botaoM = form.querySelector('.marcas-botao-excluir');
            var nomeM = botaoM ? botaoM.getAttribute('data-nome') : 'esta marca';
            if (!window.confirm('Excluir a marca "' + nomeM + '"? Os produtos vinculados continuam existindo, só ficam sem marca.')) {
                evento.preventDefault();
            }
        }
    });
})();