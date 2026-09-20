// core/static/base_compartilhada/js/script_modal_fotos.js
//
// [RESUMO] -> Modal de fotos unico e reutilizavel pro sistema inteiro.
// Qualquer elemento com a classe "card-fotos-item" fica clicavel
// automaticamente, sem precisar de nenhum JS especifico por tela e sem
// precisar de nenhuma estrutura de dados montada no backend. Ao clicar,
// o script pega esse elemento e todos os outros na pagina com o MESMO
// data-fotos-id (na ordem em que aparecem no HTML) e monta uma galeria
// navegavel entre eles. Atributos lidos de cada elemento:
//   data-fotos-id   -> obrigatorio, agrupa as fotos que navegam juntas
//   data-titulo     -> obrigatorio, mostrado no topo do modal
//   data-subtitulo  -> opcional
//   data-legenda    -> opcional, mostrado embaixo da foto
// A URL da foto e lida do <img> de dentro do elemento (ou do atributo
// data-url, se o elemento nao tiver <img> dentro).
//
// Baseado no Hub de Fotos do Sistema Interno V2 (mercado_livre/), com 2
// diferencas de proposito: nao depende de json_script/dados vindos do
// backend (tudo vem dos atributos data-* que o proprio HTML ja tem), e
// titulo/subtitulo/legenda mudam por FOTO (nao por galeria) — util pra
// telas como a Evidência para a mediação, onde uma mesma galeria junta
// fotos de peças diferentes.

(function () {
    var overlay = document.getElementById('modal-fotos');
    if (!overlay) return;

    var elTitulo = document.getElementById('modal-fotos-titulo');
    var elSubtitulo = document.getElementById('modal-fotos-subtitulo');
    var elContador = document.getElementById('modal-fotos-contador');
    var elLegenda = document.getElementById('modal-fotos-legenda');
    var elImagem = document.getElementById('modal-fotos-imagem');
    var btnFechar = document.getElementById('modal-fotos-fechar');
    var btnAnterior = document.getElementById('modal-fotos-anterior');
    var btnProxima = document.getElementById('modal-fotos-proxima');

    var estado = { fotos: [], indice: 0 };
    var precarregadas = {};

    function precarregar(url) {
        if (!url || precarregadas[url]) return;
        precarregadas[url] = true;
        var img = new Image();
        img.src = url;
    }

    function dadosDoElemento(elemento) {
        // O elemento com "card-fotos-item" às vezes É o próprio <img>
        // (ex.: Resumo geral da conferência) e às vezes é uma <div>/<a>
        // que só CONTÉM um <img> lá dentro (a maioria das telas). Nos
        // dois casos precisa achar a imagem certa.
        var img = elemento.tagName === 'IMG' ? elemento : elemento.querySelector('img');
        var url = (img && img.src) || elemento.getAttribute('data-url') || '';
        return {
            url: url,
            titulo: elemento.getAttribute('data-titulo') || '',
            subtitulo: elemento.getAttribute('data-subtitulo') || '',
            legenda: elemento.getAttribute('data-legenda') || '',
        };
    }

    function grupoDoElemento(elemento) {
        var fotosId = elemento.getAttribute('data-fotos-id');
        if (!fotosId) return null;
        var elementos = Array.prototype.slice.call(
            document.querySelectorAll('.card-fotos-item[data-fotos-id="' + CSS.escape(fotosId) + '"]')
        );
        return {
            fotos: elementos.map(dadosDoElemento),
            indice: elementos.indexOf(elemento),
        };
    }

    function renderizar() {
        var foto = estado.fotos[estado.indice];
        if (!foto) return;
        var multiplas = estado.fotos.length > 1;

        elImagem.src = foto.url;
        elImagem.alt = foto.titulo || '';

        elTitulo.textContent = foto.titulo;

        if (foto.subtitulo) {
            elSubtitulo.textContent = foto.subtitulo;
            elSubtitulo.hidden = false;
        } else {
            elSubtitulo.hidden = true;
        }

        elContador.hidden = !multiplas;
        elContador.textContent = multiplas ? ('Foto ' + (estado.indice + 1) + ' de ' + estado.fotos.length) : '';

        btnAnterior.hidden = !multiplas;
        btnProxima.hidden = !multiplas;

        if (foto.legenda) {
            elLegenda.textContent = foto.legenda;
            elLegenda.hidden = false;
        } else {
            elLegenda.hidden = true;
        }

        if (multiplas) {
            var proximo = estado.fotos[(estado.indice + 1) % estado.fotos.length];
            var anterior = estado.fotos[(estado.indice - 1 + estado.fotos.length) % estado.fotos.length];
            precarregar(proximo.url);
            precarregar(anterior.url);
        }
    }

    function abrir(fotos, indice) {
        if (!fotos || !fotos.length) return;
        estado.fotos = fotos;
        estado.indice = indice || 0;
        renderizar();
        overlay.hidden = false;
        document.body.style.overflow = 'hidden';
    }

    function fechar() {
        overlay.hidden = true;
        document.body.style.overflow = '';
    }

    function irParaAnterior() {
        if (estado.fotos.length <= 1) return;
        estado.indice = (estado.indice - 1 + estado.fotos.length) % estado.fotos.length;
        renderizar();
    }

    function irParaProxima() {
        if (estado.fotos.length <= 1) return;
        estado.indice = (estado.indice + 1) % estado.fotos.length;
        renderizar();
    }

    // Pré-carrega a foto assim que o mouse passa por cima do card, pra
    // já estar pronta no cache do navegador quando o clique acontecer.
    document.addEventListener('mouseover', function (evento) {
        var item = evento.target.closest('.card-fotos-item');
        if (item) precarregar(dadosDoElemento(item).url);
    });

    document.addEventListener('click', function (evento) {
        var item = evento.target.closest('.card-fotos-item');
        if (!item) return;

        // Se o clique foi num controle de verdade dentro do card (botão
        // de excluir foto, botão de remover prévia, etc.), deixa esse
        // controle agir normalmente e não abre o modal.
        var controle = evento.target.closest('button, a, input, label');
        if (controle && controle !== item && item.contains(controle)) return;

        var grupo = grupoDoElemento(item);
        if (!grupo) return;

        evento.preventDefault();
        abrir(grupo.fotos, grupo.indice);
    });

    btnFechar.addEventListener('click', fechar);
    btnAnterior.addEventListener('click', irParaAnterior);
    btnProxima.addEventListener('click', irParaProxima);

    overlay.addEventListener('click', function (evento) {
        if (evento.target === overlay) fechar();
    });

    document.addEventListener('keydown', function (evento) {
        if (overlay.hidden) return;
        if (evento.key === 'Escape') fechar();
        else if (evento.key === 'ArrowLeft') irParaAnterior();
        else if (evento.key === 'ArrowRight') irParaProxima();
    });
})();
