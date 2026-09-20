// * [RESUMO] → Script global do sistema — toggle da sidebar (ocultar/
//              exibir) e fechamento dos avisos globais (messages do
//              Django, ver estrutura_base_global.html).

// * [EXPLICAÇÃO] → Ao clicar no botão de menu (hamburguer) na toolbar,
//                  adiciona ou remove a classe 'sidebar-oculta' no body,
//                  e GRAVA a escolha no localStorage — sem isso, a escolha
//                  se perdia a cada recarregamento de página de verdade.
//                  A leitura desse valor já acontece antes, no <script>
//                  inline logo no início do <body> (evita flash visual).
document.getElementById('btn-toggle-sidebar').addEventListener('click', function() {
    document.body.classList.toggle('sidebar-oculta');
    const estaOculta = document.body.classList.contains('sidebar-oculta');
    localStorage.setItem('sidebar_oculta', estaOculta);
});

// * [EXPLICAÇÃO] → Avisos globais (mensagens do Django messages
//   framework, ex: "Prazo de resposta salvo.") ficavam presos na tela
//   pra sempre -- incômodo real quando a ação (ex: salvar prazo) manda
//   de volta pra MESMA tela, em vez de sair dela. Sucesso/info somem
//   sozinhos depois de alguns segundos; warning/error ficam até serem
//   fechados manualmente, porque merecem mais atenção. O X sempre
//   funciona, em qualquer tipo. Decisão de Matheus, 20/09/2026.
(function () {
    var DURACAO_TRANSICAO_MS = 300;
    var TEMPO_AUTO_DISMISS_MS = 4000;

    function fecharAviso(aviso) {
        if (!aviso || aviso.classList.contains('aviso-global--saindo')) return;
        aviso.classList.add('aviso-global--saindo');
        setTimeout(function () { aviso.remove(); }, DURACAO_TRANSICAO_MS);
    }

    document.querySelectorAll('.aviso-global').forEach(function (aviso) {
        var botaoFechar = aviso.querySelector('.aviso-global-fechar');
        if (botaoFechar) {
            botaoFechar.addEventListener('click', function () { fecharAviso(aviso); });
        }
        if (aviso.getAttribute('data-auto-dismiss') === 'true') {
            setTimeout(function () { fecharAviso(aviso); }, TEMPO_AUTO_DISMISS_MS);
        }
    });
})();