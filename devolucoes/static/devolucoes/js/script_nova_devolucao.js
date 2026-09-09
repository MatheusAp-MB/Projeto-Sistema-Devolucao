// devolucoes/static/devolucoes/js/script_nova_devolucao.js

// Função Objetivo: 2 blocos independentes da tela de Nova Devolução —
// (1) busca/seleção de produto e (2) "colar linha do ERP", que
// preenche sozinho os campos que dá pra reconhecer numa linha copiada
// da grade do ERP.

(function () {
    // ===== Busca/seleção de produto =====
    // Aceita digitação livre (nome/SKU/cód. fabricante/marca, com
    // debounce) e bipagem direta de código de barras no mesmo campo —
    // um leitor de código de barras digita tudo muito rápido e manda
    // um Enter no final, então o Enter dispara a busca na hora (sem
    // esperar o debounce) e, se vier match_exato, seleciona sozinho
    // sem precisar clicar. Clique num resultado também seleciona.
    // "Trocar" desfaz a seleção e volta pra busca.

    var buscaInput = document.getElementById('nd_produto_busca');
    if (!buscaInput) return;

    var buscaBloco = document.getElementById('nd_produto_busca_bloco');
    var resultadosDiv = document.getElementById('nd_produto_resultados');
    var produtoIdInput = document.getElementById('nd_produto_id');
    var produtoCard = document.getElementById('nd_produto_card');
    var urlBusca = buscaInput.getAttribute('data-url-busca');

    var DEBOUNCE_MS = 300;
    var timerDebounce = null;
    var proximoIdRequisicao = 0;
    var ultimoIdRespondido = -1;

    function escapeHtml(texto) {
        var div = document.createElement('div');
        div.textContent = texto == null ? '' : texto;
        return div.innerHTML;
    }

    function esconderResultados() {
        resultadosDiv.hidden = true;
        resultadosDiv.innerHTML = '';
    }

    function renderizarResultados(resultados) {
        if (!resultados.length) {
            resultadosDiv.innerHTML = '<div class="nd-produto-resultado-vazio">Nenhum produto encontrado.</div>';
            resultadosDiv.hidden = false;
            return;
        }

        resultadosDiv.innerHTML = resultados.map(function (produto) {
            var foto = produto.foto_url
                ? '<img class="nd-produto-resultado-foto" src="' + escapeHtml(produto.foto_url) + '" alt="">'
                : '<div class="nd-produto-resultado-sem-foto"><i class="fas fa-box"></i></div>';

            return (
                '<div class="nd-produto-resultado-item" data-produto-id="' + produto.id + '" ' +
                'data-produto-nome="' + escapeHtml(produto.nome) + '" ' +
                'data-produto-marca="' + escapeHtml(produto.marca_nome) + '" ' +
                'data-produto-foto="' + escapeHtml(produto.foto_url || '') + '">' +
                    foto +
                    '<div>' +
                        '<p class="nd-produto-resultado-nome">' + escapeHtml(produto.nome) + '</p>' +
                        '<p class="nd-produto-resultado-marca">' + escapeHtml(produto.marca_nome) + '</p>' +
                    '</div>' +
                '</div>'
            );
        }).join('');

        resultadosDiv.hidden = false;
    }

    function selecionarProduto(dados) {
        produtoIdInput.value = dados.id;

        var foto = dados.foto
            ? '<img src="' + escapeHtml(dados.foto) + '" alt="' + escapeHtml(dados.nome) + '">'
            : '<div class="nd-produto-sem-foto"><i class="fas fa-box"></i></div>';

        produtoCard.innerHTML = (
            foto +
            '<div class="nd-produto-textos">' +
                '<p class="nd-produto-nome">' + escapeHtml(dados.nome) + '</p>' +
                '<p class="nd-produto-marca">' + escapeHtml(dados.marca) + '</p>' +
            '</div>' +
            '<button type="button" class="nd-produto-trocar" id="nd_produto_trocar"><i class="fas fa-rotate"></i> Trocar</button>'
        );

        produtoCard.hidden = false;
        buscaBloco.hidden = true;
        esconderResultados();
        buscaInput.value = '';
    }

    function trocarProduto() {
        produtoIdInput.value = '';
        produtoCard.hidden = true;
        produtoCard.innerHTML = '<button type="button" class="nd-produto-trocar" id="nd_produto_trocar"><i class="fas fa-rotate"></i> Trocar</button>';
        buscaBloco.hidden = false;
        buscaInput.value = '';
        buscaInput.focus();
    }

    function executarBusca(termo, callback) {
        var idDestaRequisicao = ++proximoIdRequisicao;

        fetch(urlBusca + '?q=' + encodeURIComponent(termo), {
            headers: { 'X-Requested-With': 'XMLHttpRequest' },
        })
            .then(function (resposta) { return resposta.json(); })
            .then(function (dados) {
                if (idDestaRequisicao < ultimoIdRespondido) return; // resposta antiga, chegou fora de ordem
                ultimoIdRespondido = idDestaRequisicao;
                callback(dados);
            })
            .catch(function () {
                if (idDestaRequisicao < ultimoIdRespondido) return;
                ultimoIdRespondido = idDestaRequisicao;
                resultadosDiv.innerHTML = '<div class="nd-produto-resultado-vazio">Erro ao buscar — tente de novo.</div>';
                resultadosDiv.hidden = false;
            });
    }

    function aoReceberResultado(dados) {
        var resultados = dados.resultados || [];

        if (dados.match_exato && resultados.length === 1) {
            var produto = resultados[0];
            selecionarProduto({
                id: produto.id, nome: produto.nome,
                marca: produto.marca_nome, foto: produto.foto_url,
            });
            return;
        }

        renderizarResultados(resultados);
    }

    buscaInput.addEventListener('input', function () {
        var termo = buscaInput.value.trim();

        if (timerDebounce) clearTimeout(timerDebounce);

        if (termo.length < 2) {
            esconderResultados();
            return;
        }

        timerDebounce = setTimeout(function () {
            executarBusca(termo, aoReceberResultado);
        }, DEBOUNCE_MS);
    });

    buscaInput.addEventListener('keydown', function (evento) {
        if (evento.key !== 'Enter') return;
        evento.preventDefault(); // não deixa o Enter (do leitor de código de barras) submeter o formulário inteiro

        var termo = buscaInput.value.trim();
        if (!termo) return;

        if (timerDebounce) clearTimeout(timerDebounce);
        executarBusca(termo, aoReceberResultado);
    });

    resultadosDiv.addEventListener('click', function (evento) {
        var item = evento.target.closest('.nd-produto-resultado-item');
        if (!item) return;

        selecionarProduto({
            id: item.getAttribute('data-produto-id'),
            nome: item.getAttribute('data-produto-nome'),
            marca: item.getAttribute('data-produto-marca'),
            foto: item.getAttribute('data-produto-foto'),
        });
    });

    // "Trocar" recria o botão toda vez que a seleção muda (innerHTML novo),
    // então a única forma segura de ouvir o clique é delegando no card.
    produtoCard.addEventListener('click', function (evento) {
        if (evento.target.closest('#nd_produto_trocar')) trocarProduto();
    });

    document.addEventListener('click', function (evento) {
        if (!evento.target.closest('.nd-produto-busca-wrap')) esconderResultados();
    });
})();


(function () {
    // ===== Colar linha do ERP =====
    // Ela seleciona a linha do CABEÇALHO junto com a linha de DADOS na
    // grade do ERP e cola aqui (2 linhas). O casamento é feito pelo
    // NOME da coluna, nunca pela posição — assim, mesmo que sobre uma
    // coluna vazia no meio (ex: "Impressa"), nada desalinha.
    //
    // * [ATENÇÃO] → só funciona se a colagem preservar Tab de verdade
    //   entre as colunas (é o que o Ctrl+C de uma grade normalmente
    //   gera). Se não vier Tab nenhum, a tela avisa e não tenta
    //   adivinhar por espaço — coluna vazia faria tudo desalinhar
    //   silenciosamente, e um valor errado no campo errado é pior do
    //   que não preencher nada.

    var toggleBtn = document.getElementById('nd_colar_toggle');
    var bloco = document.getElementById('nd_colar_bloco');
    var textarea = document.getElementById('nd_colar_textarea');
    var statusEl = document.getElementById('nd_colar_status');
    if (!toggleBtn || !textarea) return;

    var MAPEAMENTOS = [
        { coluna: 'Pedido Marketplace', campoId: 'id_numero_pedido', rotulo: 'Número do pedido' },
        { coluna: 'Nota Fiscal', campoId: 'id_numero_nota_fiscal', rotulo: 'Nota fiscal' },
        { coluna: 'Parceiro de Negócio', campoId: 'id_nome_cliente', rotulo: 'Cliente' },
    ];

    // "Plataforma" virou <select> com uma lista fechada de marketplaces —
    // não dá mais pra jogar o texto cru da coluna "Canal de Vendas" direto
    // nela (ex: vem "MAGAZINE MAGALU", não bate com nenhuma <option>). Por
    // isso essa aqui não entra no MAPEAMENTOS genérico: procura uma palavra-
    // chave conhecida dentro do texto e só marca a opção se achar uma —
    // sem match, o campo fica em branco (não tenta adivinhar).
    var DETECCAO_PLATAFORMA = [
        { rotulo: 'Shopee', chave: 'SHOPEE' },
        { rotulo: 'Magalu', chave: 'MAGALU' },
        { rotulo: 'Tiktok Shop', chave: 'TIKTOK' },
        { rotulo: 'Raia', chave: 'RAIA' },
        // "MERCADO LIVRE" cobre quando o ERP escreve o nome por extenso;
        // "MELI" (sigla que o ERP usa em vendas FULL, ex.: "MAGAZINE MELI
        // FULL") cobre a abreviação — achado real em 09/09/2026: um exemplo
        // colado direto do ERP não tinha "MERCADO LIVRE" escrito em lugar
        // nenhum, só "MELI FULL", e a detecção antiga nunca batia.
        { rotulo: 'Mercado Livre', chave: 'MERCADO LIVRE' },
        { rotulo: 'Mercado Livre', chave: 'MELI' },
        { rotulo: 'Amazon', chave: 'AMAZON' },
        { rotulo: 'Mais correios', chave: 'CORREIOS' },
    ];

    function detectarPlataforma(textoErp) {
        var textoNormalizado = textoErp.toUpperCase();
        for (var i = 0; i < DETECCAO_PLATAFORMA.length; i++) {
            if (textoNormalizado.indexOf(DETECCAO_PLATAFORMA[i].chave) !== -1) {
                return DETECCAO_PLATAFORMA[i].rotulo;
            }
        }
        return null;
    }

    // "Data da venda" vem da coluna "Emissão" do ERP (data de emissão da
    // nota fiscal) — mas o ERP mostra ela como dd/mm/aaaa (às vezes com
    // hora junto, "dd/mm/aaaa hh:mm:ss"), e o <input type="date"> só
    // aceita aaaa-mm-dd. Só preenche se reconhecer esse formato exato —
    // sem bater o padrão, não adivinha e deixa o campo em branco.
    function converterDataErpParaIso(valorErp) {
        var match = valorErp.trim().match(/^(\d{2})\/(\d{2})\/(\d{4})/);
        if (!match) return null;

        var dia = match[1], mes = match[2], ano = match[3];
        return ano + '-' + mes + '-' + dia;
    }

    // Achado real em 09/09/2026: o nome da coluna não é o mesmo nos dois
    // ERPs — o ERP MAGAZINE manda "Canal de Vendas" (plural) e o ERP
    // SAMVALE manda "Canal de Venda" (singular). Buscar só um nome fixo
    // funcionava pra um e falhava silenciosamente pro outro (a coluna
    // simplesmente não era encontrada, então a Plataforma ficava sempre
    // em branco). Essa função tenta uma lista de nomes possíveis, na
    // ordem, e usa o primeiro que existir no cabeçalho colado.
    function buscarValorPorAliases(valorPorColuna, nomesPossiveis) {
        for (var i = 0; i < nomesPossiveis.length; i++) {
            var valor = valorPorColuna[nomesPossiveis[i]];
            if (valor) return valor;
        }
        return undefined;
    }

    toggleBtn.addEventListener('click', function () {
        bloco.hidden = !bloco.hidden;
        if (!bloco.hidden) textarea.focus();
    });

    function mostrarStatus(mensagem, ok) {
        statusEl.textContent = mensagem;
        statusEl.hidden = false;
        statusEl.classList.toggle('nd-colar-status--ok', ok);
        statusEl.classList.toggle('nd-colar-status--erro', !ok);
    }

    function limparNomeProduto(nome) {
        // tira o "(1)" de quantidade que a grade do ERP deixa no final do nome
        return nome.replace(/\s*\(\d+\)\s*$/, '').trim();
    }

    function processarColagem(texto) {
        var linhas = texto
            .split(/\r\n|\r|\n/)
            .map(function (linha) { return linha.trim(); })
            .filter(function (linha) { return linha.length > 0; });

        if (linhas.length < 2) {
            mostrarStatus('Cole a linha do cabeçalho junto com a linha de dados (as 2 linhas).', false);
            return;
        }

        var cabecalho = linhas[0].split('\t');
        var valores = linhas[1].split('\t');

        if (cabecalho.length < 2 || valores.length < 2) {
            mostrarStatus('Não consegui separar as colunas — copie direto da grade do ERP (com Tab entre as colunas).', false);
            return;
        }

        var valorPorColuna = {};
        cabecalho.forEach(function (nomeColuna, indice) {
            valorPorColuna[nomeColuna.trim()] = (valores[indice] || '').trim();
        });

        var preenchidos = [];

        MAPEAMENTOS.forEach(function (mapeamento) {
            var valor = valorPorColuna[mapeamento.coluna];
            if (!valor) return;

            var campo = document.getElementById(mapeamento.campoId);
            if (!campo) return;

            campo.value = valor;
            preenchidos.push(mapeamento.rotulo);
        });

        var canalVendas = buscarValorPorAliases(valorPorColuna, ['Canal de Vendas', 'Canal de Venda']);
        if (canalVendas) {
            var plataformaDetectada = detectarPlataforma(canalVendas);
            var campoPlataforma = document.getElementById('id_nome_plataforma');
            if (plataformaDetectada && campoPlataforma) {
                campoPlataforma.value = plataformaDetectada;
                preenchidos.push('Plataforma');
            }
        }

        var emissao = valorPorColuna['Emissão'];
        if (emissao) {
            var dataVendaIso = converterDataErpParaIso(emissao);
            var campoDataVenda = document.getElementById('id_data_venda');
            if (dataVendaIso && campoDataVenda) {
                campoDataVenda.value = dataVendaIso;
                preenchidos.push('Data da venda');
            }
        }

        var nomeProduto = valorPorColuna['Produto'];
        var buscaBloco = document.getElementById('nd_produto_busca_bloco');
        var buscaInputProduto = document.getElementById('nd_produto_busca');

        if (nomeProduto && buscaInputProduto && buscaBloco && !buscaBloco.hidden) {
            buscaInputProduto.value = limparNomeProduto(nomeProduto);
            buscaInputProduto.dispatchEvent(new Event('input')); // já dispara a busca de produto sozinha
            preenchidos.push('Busca de produto (confirme clicando no resultado certo)');
        }

        if (preenchidos.length) {
            mostrarStatus('Preenchido: ' + preenchidos.join(', ') + '.', true);
        } else {
            mostrarStatus('Não encontrei nenhuma coluna reconhecida nessa linha.', false);
        }
    }

    textarea.addEventListener('paste', function (evento) {
        var texto = (evento.clipboardData || window.clipboardData).getData('text');
        evento.preventDefault();
        processarColagem(texto);
        textarea.value = '';
    });
})();