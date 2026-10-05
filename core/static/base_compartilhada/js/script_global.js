// * [RESUMO] → Script global do sistema — menu lateral (sidebar) e
//              fechamento dos avisos globais (messages do Django, ver
//              estrutura_base_global.html).

// * [EXPLICAÇÃO] → O botão de menu (hamburguer) na toolbar faz DUAS coisas,
//                  conforme o tamanho da tela (o mesmo corte do CSS, 900px):
//
//                  - COMPUTADOR (acima de 900px): adiciona ou remove a classe
//                    'sidebar-oculta' no body e GRAVA a escolha no
//                    localStorage — sem isso, a escolha se perdia a cada
//                    recarregamento de página de verdade. A leitura desse
//                    valor já acontece antes, no <script> inline logo no
//                    início do <body> (evita flash visual). NADA mudou aqui.
//
//                  - CELULAR (até 900px): o menu é uma "gaveta" que abre por
//                    cima da tela. Liga/desliga a classe 'menu-aberto' no
//                    body. Começa sempre FECHADO e NÃO grava nada no
//                    localStorage (a escolha do computador não pode ser
//                    mexida pelo celular, e o menu aberto a cada página
//                    comeria a tela inteira). Fecha ao tocar no fundo
//                    escurecido, no X, em qualquer item do menu ou na tecla
//                    Esc.
(function () {
    var botaoMenu = document.getElementById('btn-toggle-sidebar');
    var botaoFechar = document.getElementById('btn-fechar-sidebar');
    var fundo = document.getElementById('sidebar-fundo');
    var sidebar = document.getElementById('sidebar-menu');
    var emCelular = window.matchMedia('(max-width: 900px)');

    function menuEstaAberto() {
        return document.body.classList.contains('menu-aberto');
    }

    function abrirMenu() {
        document.body.classList.add('menu-aberto');
        botaoMenu.setAttribute('aria-expanded', 'true');
        if (botaoFechar) botaoFechar.focus({ preventScroll: true });
    }

    function fecharMenu(devolverFoco) {
        document.body.classList.remove('menu-aberto');
        botaoMenu.setAttribute('aria-expanded', 'false');
        if (devolverFoco) botaoMenu.focus({ preventScroll: true });
    }

    botaoMenu.addEventListener('click', function() {
        if (emCelular.matches) {
            if (menuEstaAberto()) fecharMenu(false);
            else abrirMenu();
            return;
        }
        document.body.classList.toggle('sidebar-oculta');
        const estaOculta = document.body.classList.contains('sidebar-oculta');
        localStorage.setItem('sidebar_oculta', estaOculta);
    });

    if (fundo) fundo.addEventListener('click', function () { fecharMenu(true); });
    if (botaoFechar) botaoFechar.addEventListener('click', function () { fecharMenu(true); });

    // Tocar num item do menu fecha a gaveta ANTES de trocar de página: se a pessoa
    // voltar pelo botão "voltar" do navegador, a página não reaparece com o menu aberto.
    if (sidebar) {
        sidebar.addEventListener('click', function (evento) {
            if (evento.target.closest && evento.target.closest('a')) fecharMenu(false);
        });
    }

    document.addEventListener('keydown', function (evento) {
        if (evento.key === 'Escape' && menuEstaAberto()) fecharMenu(true);
    });

    // Girou o celular / esticou a janela até virar "computador": a gaveta não faz sentido lá.
    function aoMudarTamanho() {
        if (!emCelular.matches && menuEstaAberto()) fecharMenu(false);
    }
    if (emCelular.addEventListener) emCelular.addEventListener('change', aoMudarTamanho);
    else if (emCelular.addListener) emCelular.addListener(aoMudarTamanho);
})();

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

// * [EXPLICAÇÃO] → "Voltar" de verdade (pedido de Matheus, 05/10/2026): "esse deveria
//   ser o comportamento padrão de todos os botões de voltar — voltar ao estado anterior
//   sem perder dados". Todo link de Voltar/Cancelar que só leva "pra tela de antes"
//   ganha o atributo data-voltar. Se a pessoa veio justamente da tela pra onde o link
//   aponta (o endereço de onde veio é o do link), o clique faz o MESMO que o botão
//   voltar do navegador: a tela de antes reaparece como estava (filtros, busca, posição
//   da rolagem — cada tela guarda o que precisa guardar) e o histórico não cresce à toa.
//   Se não veio de lá (abriu a tela direto, veio de outra tela, ou acabou de salvar um
//   formulário), o link funciona normal e leva à tela que ele diz. Sem JS, vale o link.
(function () {
    function veioDaTelaDoLink(link) {
        if (!document.referrer || window.history.length < 2) return false;
        try {
            var origem = new URL(document.referrer);
            var destino = new URL(link.href, window.location.href);
            return origem.origin === window.location.origin && origem.origin === destino.origin &&
                origem.pathname === destino.pathname && origem.pathname !== window.location.pathname;
        } catch (erro) {
            return false;
        }
    }

    document.addEventListener('click', function (evento) {
        if (evento.defaultPrevented || evento.button || evento.ctrlKey || evento.metaKey || evento.shiftKey || evento.altKey) return;
        var link = evento.target.closest ? evento.target.closest('a[data-voltar]') : null;
        if (!link || !veioDaTelaDoLink(link)) return;
        evento.preventDefault();
        window.history.back();
    });
})();

// * [EXPLICAÇÃO] → EstadoDaTela: telas com filtro/busca feitos por JavaScript (que o
//   navegador não consegue devolver sozinho) registram aqui "como ler" e "como aplicar"
//   o que a pessoa escolheu. Ao sair da tela, uma "foto" (o que foi lido + a posição da
//   rolagem) é guardada na própria entrada do histórico (history.state, então cada
//   entrada tem a sua). Quando a tela abre pelo voltar do navegador — ou por um botão
//   data-voltar, que faz a mesma coisa — a foto é aplicada e a rolagem volta ao ponto.
//   Abrir a tela de outro jeito (menu, link) nunca aplica nada. (A lista de Devoluções
//   tem a sua própria versão disso, mais completa: ver script_devolucoes_pendentes.js.)
window.EstadoDaTela = (function () {
    var CHAVE = 'dpTela';

    function tipoDaNavegacao() {
        try {
            var entrada = window.performance.getEntriesByType('navigation')[0];
            if (entrada && entrada.type) return entrada.type;
        } catch (erro) { /* tenta o jeito antigo abaixo */ }
        try {
            if (window.performance.navigation && window.performance.navigation.type === 2) return 'back_forward';
        } catch (erro) { /* desconhecido: trata como abertura normal */ }
        return 'navigate';
    }

    // Só enquanto a pessoa ainda não mexeu na tela: refaz a posição quando as fontes e
    // as imagens terminam de carregar (o tamanho final das coisas só fica certo aí).
    function restaurarRolagem(y) {
        var mexeu = false;
        var marcar = function () { mexeu = true; };
        ['wheel', 'touchstart', 'mousedown', 'keydown'].forEach(function (nomeEvento) {
            window.addEventListener(nomeEvento, marcar, { passive: true, once: true });
        });
        var aplicar = function () { if (!mexeu) window.scrollTo({ top: Math.max(0, y), left: 0, behavior: 'instant' }); };
        var devolverAoNavegador = function () {
            window.setTimeout(function () {
                try { window.history.scrollRestoration = 'auto'; } catch (erro) { /* ignora */ }
            }, 400);
        };
        aplicar();
        if (document.fonts && document.fonts.ready) document.fonts.ready.then(aplicar);
        if (document.readyState === 'complete') {
            devolverAoNavegador();
        } else {
            window.addEventListener('load', function () { aplicar(); devolverAoNavegador(); });
        }
    }

    function registrar(ler, aplicar) {
        var guardado = null;
        if (tipoDaNavegacao() === 'back_forward') {
            try { guardado = window.history.state && window.history.state[CHAVE]; } catch (erro) { guardado = null; }
        }
        if (guardado && typeof guardado === 'object') {
            try { window.history.scrollRestoration = 'manual'; } catch (erro) { /* ignora */ }
            try { aplicar(guardado.dados || {}); } catch (erro) { /* foto estragada: a tela abre normal */ }
            restaurarRolagem(typeof guardado.y === 'number' ? guardado.y : 0);
        }
        window.addEventListener('pagehide', function () {
            try {
                var atual = window.history.state;
                var novo = (atual && typeof atual === 'object') ? Object.assign({}, atual) : {};
                novo[CHAVE] = { dados: ler(), y: Math.round(window.pageYOffset || 0) };
                window.history.replaceState(novo, '');
            } catch (erro) { /* sem histórico: segue sem guardar */ }
        });
    }

    return { registrar: registrar };
})();


// * [EXPLICAÇÃO] → pedido de Matheus (05/10/2026): onde há envio de foto, a pessoa escolhe "Tirar foto" (câmera
//   na hora) ou "Anexar arquivo". Nos campos de UMA foto só (Produto, Peça, janelinha de Peça) o "Tirar foto" é
//   um segundo <input type="file" capture="environment" data-foto-camera="<id do campo principal>">: quando a
//   foto é tirada, ela passa pro campo principal e o campo da câmera é esvaziado. Como o campo principal ganha
//   a foto e dispara o 'change' dele, a prévia e a regra "foto obrigatória" de cada tela funcionam sem mudar
//   nada nelas. Sem DataTransfer (navegador muito antigo) o campo da câmera continua valendo sozinho: os 2
//   têm o mesmo name e só um deles leva arquivo.
document.addEventListener('change', function (evento) {
    var camera = evento.target;
    if (!camera || !camera.matches || !camera.matches('input[type="file"][data-foto-camera]')) return;
    if (typeof DataTransfer === 'undefined' || !camera.files || !camera.files.length) return;

    var principal = document.getElementById(camera.getAttribute('data-foto-camera'));
    if (!principal) return;

    var transferencia = new DataTransfer();
    transferencia.items.add(camera.files[0]);
    principal.files = transferencia.files;
    camera.value = '';
    principal.dispatchEvent(new Event('change', { bubbles: true }));
});
