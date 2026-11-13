# Histórico de versões

A versão do MUSIX fica em [`version.txt`](version.txt) (fonte única). É o número que aparece em **Settings > About** e no rodapé do menu. Cada entrega publicada sobe a versão e ganha uma seção neste arquivo, com a data e um resumo curto.

O cliente web (`musix-webclient`) não tem número próprio: ele é empacotado junto com o servidor na imagem Docker.

## Regra de versões

Formato MAIOR.MENOR.CORREÇÃO, lido de `version.txt`:

- **MENOR sobe** (e a CORREÇÃO volta a 0) quando a entrega traz um recurso novo que o usuário percebe e que não existia, ou muda um comportamento de forma relevante.
- **CORREÇÃO sobe** em bug, ajuste visual, de ícone ou de texto, responsividade, refatoração e mudança só de cliente sem recurso novo.
- **MAIOR** só em mudança grande ou incompatível (formato do banco, quebra de API, migração manual) ou ao acompanhar um MAIOR do upstream. Quem decide é o Rodrigo.
- **Toda entrega publicada sobe a versão**, uma por prompt, na ordem em que é publicada (o app mostra a versão que está rodando).

## 3.30.0 (2026-11-13)

SidePanel que recolhe, o movimento do protótipo ("Ease in and out back", 300 ms) em todos os painéis que abrem e fecham, e três mudanças pedidas junto (contador de plays nas faixas do álbum e das playlists, miniaturas sem botão de play, Home que quebra de linha).

- **SidePanel recolhido (Figma `Closed`, nó 12546:5413):** clicar no cabeçalho do painel aberto o recolhe para uma faixa de 52 px; clicar na nota musical do fechado o abre. Os componentes são os mesmos (`LeftSidebar`, `Logo`, `SidePanelNav`, `PinnedPlaylists`) com a classe `collapsed`, então o que existe nos dois estados muda de tamanho e o que existe só em um some com fade. Fechado: o botão do cabeçalho tem 36 de largura e a nota de 27 x 32 (`figma/music.svg`, ícone novo); os botões de navegação têm 36 x 34 e só o ícone de 20 (Home ativo em neutral-700, Favorites com o coração vermelho cheio); o divisor tem 36 x 1; as playlists têm 36 x 34 com a capa de 18. O estado fica salvo entre sessões (`settings.side_panel_collapsed`, como `queue_panel_open`) e a coluna da página ganha os 172 px. A barra de rolagem some no estado recolhido, para não tirar largura dos 36 px.
- **O movimento do protótipo (`--panel-toggle-*`, três tokens novos):** `cubic-bezier(0.7, -0.4, 0.4, 1.4)` em 300 ms. A grade do app (SidePanel e PlayingPanel) passou a ter uma única classe `panels-animating`, ligada por 400 ms quando qualquer um dos dois abre ou fecha, e só nesse tempo (a transição permanente ficaria atrasada ao redimensionar a janela, porque as larguras são uma fração da janela). O PlayingPanel, o Now Playing do celular (subir ao abrir e descer pelo chevron) e a gaveta do hambúrguer usam os mesmos tokens. `prefers-reduced-motion: reduce` desliga todos. Não mudaram: menus de contexto, dropdowns, modais, notificações e a capa ampliada do álbum (que tem protótipo próprio).
- **Extra a: contador de plays na linha da faixa.** Faltava o dado: o servidor só mandava `help_text` ("12 plays", "unplayed") na página do artista. Agora o álbum (`POST /album` e `GET /album/<hash>/tracks`) e a playlist mandam também (`serialize_tracks_with_plays`, mesma regra do artista). Na página do álbum a linha mostra "N plays" no lugar dos botões ao passar o mouse, igual à do artista (e um play contado com a página aberta atualiza o número). **A página da playlist ainda usa as linhas antigas (não as do painel)**: lá o número aparece como o texto laranja em maiúsculas que as linhas antigas já usavam em outras listas, no lugar do tempo; refazer essa página no desenho do Figma não fazia parte disto.
- **Extra b: miniaturas sem botão de play.** `AlbumThumb` e `ArtistThumb` não têm mais o botão de play nem a sombra do hover, em todo lugar (Home, "View history", página do álbum, página do artista): só abrem o álbum ou o artista ao clicar; o menu do botão direito continua. Como a opção ficaria sempre ligada, o código (`PlayBtn`, sombra, CSS do hover, prop `noPlay` do `ArtistThumb`) saiu dos dois componentes, junto com os tokens `--feedpanel-play-*` que ninguém mais usava.
- **Extra c: Home que quebra de linha em vez de encolher as miniaturas.** `.feed-row-cards` virou uma grade `auto-fill`: até 8 por linha e, quando os 8 ficariam menores que o mínimo, os cartões quebram para menos colunas, sem passar de 2 por linha para baixo (nunca 1), e os 8 itens aparecem sempre (até 4 linhas). Tokens novos `--feedpanel-card-min-width` e `--feedpanel-card-columns-min`.
- **Decisões minhas (o Rodrigo pode mudar):**
  - O cabeçalho do painel **não leva mais à Home** (é o botão de recolher, como no protótipo); a Home é o primeiro botão de navegação. Na tela de login o `Logo` continua o mesmo, sem botão.
  - **Dica e rótulo (`title` e `aria-label`) nos ícones do painel recolhido** (o Figma não tem tooltip). O botão do cabeçalho tem `aria-expanded` e o texto "Collapse sidebar" / "Expand sidebar" (chaves novas em `en_US.json`).
  - O botão do cabeçalho fechado mede 36 x 48 (nota de 32 mais 8 de padding em cima e embaixo; o Figma só dá a largura) e a capa das playlists fechadas fica com 9 px de cada lado (centralizada nos 36, alinhada com os ícones de cima; o Figma diz padding 8).
  - **Soltar o dedo depois de arrastar o Now Playing** (voltar ao lugar ou sair) **mantém o easing de antes** (`--nowplaying-release-easing`): o dedo já começou o movimento e um passo para trás ali pareceria defeito. Só abrir e fechar pelo chevron usam o do protótipo.
  - **Sombras que cobrem o excesso do easing** (ele passa uns 10% do destino): a folha do Now Playing ganhou `box-shadow: 0 20vh 0 0` na cor do fundo (a página não aparece embaixo dela) e a gaveta do hambúrguer `box-shadow: -40px 0 0 0` (cobre a folga à esquerda, que chega a uns 14 px).
  - **Largura mínima do cartão da Home: 111 px**, a largura dele a 1600 x 900 com os dois painéis abertos (111,3 px), o caso mais estreito com 8 por linha. Com o SidePanel recolhido o cartão ali fica com 133 px e, sem os dois painéis, com 169 px. Os pontos de quebra saem da conta (não há media query): 8 colunas a partir de uns 1060 px de página, 7 abaixo disso e assim por diante.
  - O PlayingPanel passou a preencher a coluna (`min-width` em vez de largura fixa), para não aparecer uma faixa vazia no excesso do movimento.
- **Conferido no navegador (API simulada):** painel aberto igual ao de antes (224 de largura, linhas, logo); recolhido com 52 px, botão do cabeçalho 36 x 48 com a nota de 27 x 32, botões 36 x 34, playlists 36 x 34 com a capa de 18, divisor 36 x 1, Home ativo e favorito com a cor certa, página 172 px maior; clicar no cabeçalho e Enter alternam; o estado sobrevive ao recarregar; a largura da coluna durante a animação (amostrada a cada quadro): 300 ms, vai a 42 px ao recolher e a 234 ao abrir antes de assentar, sem barra horizontal e sem salto no fim; os dois painéis alternados em sequência não quebram a grade; o PlayingPanel sem faixa vazia no excesso; 700 px (painel de 25vw) recolhe e abre; a Home em 1600, 1203, 900 e 700 px com o PlayingPanel aberto e fechado e o SidePanel nos dois estados: nenhum cartão abaixo de 111 px, sem barra horizontal, 8 itens em cada linha (a 1203 px com o PlayingPanel fechado e o SidePanel aberto são 7 colunas e sobra 1 na linha de baixo); celular 412 x 780: o Now Playing sobe passando uns 45 px do topo e fecha pelo chevron com o mesmo movimento, sem mostrar a página embaixo, e a gaveta abre e fecha com o movimento e sem folga na borda; o easing do soltar do dedo confirmado pelo CSS calculado; o contador de plays no álbum (mouse em cima da linha) e na playlist; nenhuma miniatura com botão de play na Home, no histórico e na página do álbum. Servidor: 358 testes passam (um novo para o texto dos plays; os dois testes da playlist passaram a trocar `serialize_tracks_with_plays`). `vite build` e ESLint dos arquivos mudados sem erro novo.
- **Não conferido:** celular de verdade (toque, soltar o dedo depois de arrastar o Now Playing — só o CSS calculado foi lido, não houve gesto real —, área segura); o hover real das dicas dos ícones (só o `title` no DOM); o contador de plays com o servidor de verdade (a API era simulada; o servidor foi coberto só pelo teste da serialização).

## 3.29.0 (2026-11-13)

Celular (600 px ou menos): o bloco fixo de baixo e a tela Now Playing passam a ser os do Figma. **Acima de 600 px nada mudou** (PlayerBar, PlayingPanel e a letra em `/nowplaying/lyrics` conferidos em 1600 x 900). Só o cliente mudou; o servidor só sobe a versão.

- **FixedControls (novo bloco de baixo):** dois blocos de neutral-900 com 4 px em volta e 8 px entre eles, mais a área segura do iPhone embaixo (`viewport-fit=cover` no `index.html`).
  - **PlayerBar mobile:** play/pause de 40 px (o mesmo da barra do desktop), o botão add (abre o menu de adicionar para cima), nome e artistas alinhados à direita (uma linha, com reticências) e a capa de 56 px com o chevron de 24 px para cima por cima; tocar na capa abre o Now Playing (um `push`, então voltar retorna à página anterior). A linha de 2 px no pé do bloco mostra o progresso, só de exibição.
  - **NavBarMobile:** Home, Albums, Artists e Playlists (botões de 48 px; o da página aberta tem o ícone cheio num círculo neutral-700). Favorites ficou de fora, como no Figma, e continua no menu do hambúrguer (conferido: está na lista do `NavSidenav`).
- **Now Playing mobile** (`/nowplaying/:tab`, abas `home`, `lyrics` e `queue`; a troca de aba usa `replace`): tela por cima de tudo (até do FixedControls), sobe ao abrir. Fecha pelo chevron, pelo botão voltar (é uma rota) e deslizando para baixo (sem histórico, por exemplo num link direto, vai para a Home).
  - **Cabeçalho e aba principal:** o nome da origem (álbum, playlist...) com o ícone disc; nas abas Lyrics e Queue, as barrinhas verdes e o nome da faixa. Capa quadrada, nome da faixa, artista (leva à página do artista), favorite e add. Se a tela for baixa demais para a capa de largura inteira, a aba principal rola (o tamanho do Figma não muda).
  - **PlayingControls (iguais em todas as abas):** barra de progresso e os dois tempos, shuffle/anterior/play/próxima/repeat, volume (o alto-falante liga e desliga o mudo), as abas Now playing, Lyrics e Queue (a aberta com fundo redondo) e o botão de opções, que abre o menu da faixa para cima.
  - **Lyrics:** passadas em branco, as seguintes em neutral-500 e a atual preenchida da esquerda para a direita (degradê `#dbdbdb`, com a borda suave de 8%). **O preenchimento é uma estimativa**: a letra só tem o tempo em que cada linha começa, então ele anda de 0 a 100% entre o início da linha e o da próxima (na última, até o fim da faixa); numa linha que quebra em duas o degradê corre as duas ao mesmo tempo. Tocar numa linha vai para o tempo dela. Letra sem tempo: tudo em branco, sem preenchimento e sem rolagem automática. Sem letra: o texto de sempre e o botão de procurar online.
  - **Queue:** a mesma lista do PlayingPanel (extraída para `PlayingPanel/QueueList.vue`, usada pelo painel do desktop e por esta aba), em tamanho de toque: faixa de 48 px com capa de 40, ícones de 20 px. Tocar na faixa toca; repeat, remover e arrastar (segurar a alça) funcionam como no desktop.
- **Decisões minhas (o Rodrigo pode mudar):** área de toque de 44 px no chevron de fechar (o ícone tem 14) e de 32 px nos ícones da fila (o ícone tem 20); o gesto de fechar só começa no cabeçalho, na aba principal ou numa lista que está no topo, e fecha acima de 120 px ou num arremesso rápido (senão volta); o círculo de toque do botão de opções é de 34 px com o layout de 12; o texto da letra fica alinhado à esquerda (o Figma não diz); a barra de progresso mostra a bolinha o tempo todo (no celular não existe hover); o alto-falante tem caixa de 32 px com o ícone de 20 (o Figma só diz 32); nome e artistas da barra de baixo são texto simples (sem link, para não abrir sem querer); no FixedControls há no mínimo 14 px entre o play, o add e a música; os links do Now Playing (artista, origem) trocam a tela pela página (`replace`), então o voltar dela vai para a página que estava aberta antes.
- **Chevron da capa (abre e fecha o PlayingPanel no desktop; no celular fica sempre sobre a capa e abre o Now Playing):** o círculo de 24 px agora é neutral-300 a 25% de opacidade e o chevron é branco, sem opacidade (antes o círculo era sólido e o chevron a 25%). O celular usa o mesmo badge.
- **Ícones novos do Figma:** `now-playing`, `queue` e `playing` (README dos ícones atualizado).
- **Saiu o código antigo do celular:** a barra antiga (`BottomBar/Left.vue`, `Right.vue`, `LeftSidebar/NavButtons.vue`, `NP/HotKeys.vue`, `scss/BottomBar`), a página antiga do Now Playing (`components/NowPlaying/*`), a fila antiga (`RightSideBar/Queue.vue` e `QueueActions.vue`), o volume em popover (`Volume.vue` agora só tem o horizontal) e as chaves de texto `NowPlaying.*` que ninguém usava.
- Conferido no navegador (412 x 780 e, as medidas de encaixe, 375 x 812; API simulada com letra sincronizada, sem tempo e ausente): tamanhos e cores medidos pelo CSS calculado contra o Figma (FixedControls 412 x 176, PlayerBar 72 e NavBar 88 de altura, capa 372 x 372, PlayingControls 182 de altura, botões de 34 e play de 52), menu de adicionar e de opções, favorite, mudo, volume, repeat, troca de abas, preenchimento da linha atual andando, tocar na faixa da fila, remover, repeat e arrastar para reordenar, fechar pelo chevron e pelo gesto (arrastar com o mouse e eventos de toque simulados: numa lista rolada ou subindo não fecha), link direto indo para a Home; PlayerBar, PlayingPanel (lista e capa) e a letra do desktop em 1600 x 900. `vite build` e o ESLint dos arquivos novos sem erro. **Não conferido:** celular de verdade (toque, área segura, PWA instalado, volume no iPhone, que o iOS ignora); as animações de subir e descer (o painel do navegador ficou escondido e congelou as animações; o CSS foi só lido).

## 3.28.4 (2026-11-13)

- **Página do álbum:** o espaço entre o título (com as infos), os botões, os gêneros e os artistas passou de 8 para 12 px.
- **Tela de letras:** o título "Now Playing" saiu da barra do topo (ele aparecia e sumia conforme a largura).
- **QueuePanel agora é PlayingPanel:** a pasta, o componente, as classes (`.playing-panel`) e os tokens (`--playingpanel-*`) foram renomeados; a chave de texto também (`PlayingPanel.*`). O título "Queue" virou "Now playing", centralizado, e o texto "Clear queue" virou o ícone delete de 14 x 14 px (o vetor tem 9,33 x 12) à direita da mesma linha, em error/300; o texto continua como dica e rótulo do botão. A área de clique é de 24 px (decisão minha). O estado salvo do painel aberto/fechado (`queue_panel_open`) não mudou de nome, para não resetar a escolha de quem já usa. Só o cliente mudou; o servidor só sobe a versão.

## 3.28.3 (2026-11-12)

- **Página do álbum:** os artistas do álbum não mostram mais o botão de play (nem o escurecido que vinha com ele) ao passar o mouse; o clique só abre a página do artista. Na Home e nas páginas de histórico o card continua como antes (novo `no-play` no `ArtistThumb`). Só o cliente mudou; o servidor só sobe a versão.

## 3.28.2 (2026-11-12)

- **Página do álbum (AlbumPanel):** o padding do painel passa a ser 8 px nas laterais, 8 px em cima e 20 px embaixo (era 20 em volta). As duas colunas dividem a largura como no Figma (as duas "fill"): a coluna "album" tem no máximo 400 px e a capa (`album-cover`) enche a coluna mantendo 1:1, então em janelas menores a capa encolhe e a lista de faixas continua ao lado do álbum. A coluna única (álbum em cima, faixas embaixo) agora só entra quando o painel tem 600 px ou menos (antes 900; decisão minha).
- **Grupos da coluna "album":** o título com o ano e a linha de faixas e tempo ficam juntos num grupo `top`, sem espaço entre eles; o grupo dos gêneros perde o padding de cima e de baixo; o grupo `functions` (top, botões, gêneros e artistas) passa a ter 8 px entre os itens (era 4) e todos preenchem a largura.
- **Barras de rolagem:** o conteúdo de cada coluna fica a 2 px da sua barra, e a barra das faixas fica a 2 px da borda do painel (a barra tem 6 px: traço de 4 px mais 2 px até a borda). Os 20 px entre a capa e as faixas continuam; a barra da coluna "album" fica dentro deles. A margem da barra passou a ser a variável `--scrollbar-edge` (3 px para as outras páginas, 2 px na do álbum).
- **Linha de faixa (artista e álbum):** o coração sem favorito agora é neutral-300 e tem traço de 1,5 px (o contorno do ícone é 2 px, desenhado como forma). O traço usa o contorno externo do próprio coração, reduzido para o coração manter o tamanho de 20 de 24 do ícone.
- Conferido no navegador em 1203 px (capa 400 x 400, faixas a 20 px da capa, linha 2 px antes da barra, barra a 2 px da borda), em 900 px (as duas colunas de 315 px, capa 307 x 307 em 1:1) e em 760 px (uma coluna). Só o cliente mudou; o servidor só sobe a versão.

## 3.28.1 (2026-11-12)

- **Home, "Most played artists" e "Most played albums" não atualizavam.** As listas só eram pedidas ao abrir a Home, e até a 3.27 o play só era registrado quando a próxima faixa começava; com a Home aberta nada mudava. Agora a Home pede as listas de novo sempre que um play é contado (30 s ou metade da faixa).
  - **Servidor:** as listas por período (`/logger/top-artists`, `/top-albums`, `/top-tracks` e as estatísticas) passam a usar a mesma regra de play da 3.28.0: faixa pulada soma tempo mas não conta, e quem só foi pulado não entra na lista por contagem. Empate na contagem vai para quem tem mais tempo ouvido. A soma por álbum fazia uma cópia do álbum a cada registro do histórico; agora faz uma por álbum (mais rápido com histórico longo).
- **Página do álbum, capa:** a capa tem sempre 400 x 400 px. Antes ela encolhia em janela baixa (até 120 px) para o lado esquerdo caber sem rolar; agora, quando não cabe, o lado esquerdo rola. O espaço da barra de rolagem fica fora dos 400 px, e as faixas continuam a 20 px da capa.
- **Decisão minha:** o painel do álbum vira uma coluna só (álbum em cima, faixas embaixo) abaixo de 900 px de largura (era 760), porque a coluna do álbum agora é fixa em 400 px e as faixas ficariam espremidas.
- Conferido: testes do servidor (um novo para as listas da Home; a suíte toda passa, 357) e, no navegador com uma API simulada, as duas listas apareceram na Home aberta assim que o play foi contado; capa de 400,00 x 400,00 px em 1600 x 620, 1600 x 1100 e no painel de 850 px, com 20 px até as faixas. **Não conferido com o servidor real nem com o histórico real.**

## 3.28.0 (2026-11-12)

- **"Most played" corrigido (servidor e cliente).** O Rodrigo notou que o contador no hover não mudava ao tocar uma faixa e que as faixas do topo de alguns artistas não eram as mais ouvidas.
  - **O que conta como play:** uma faixa conta quando foi ouvida por **30 segundos ou metade da duração, o que for menor** (`musix/lib/playcount.py`). Antes, qualquer execução de 5 segundos contava, então faixa pulada pesava igual a faixa ouvida inteira. A regra vale também para o histórico: ao carregar, o servidor só conta como play os registros que passam nela (nada é apagado do banco; o tempo ouvido continua somando). **Os números vão cair** nas faixas que eram muito puladas.
  - **O play é registrado durante a faixa:** o cliente envia o play assim que ele conta e, quando a faixa termina ou é trocada, envia o resto do tempo ouvido como extensão do mesmo registro (`extend` em `POST /logger/track/log`). Antes o play só era enviado quando a PRÓXIMA faixa começava, então a última faixa da fila não era registrada até lá. Faixa pulada não envia nada.
  - **Contador ao vivo:** a resposta do registro traz a contagem nova e a página do artista atualiza o "12 plays" da faixa na hora, sem mudar a ordem da lista (a ordem se refaz ao abrir a página de novo).
  - **Tempo ouvido medido pelo áudio:** o cliente soma o avanço da posição do áudio, não o relógio; seek, pausa e aba em segundo plano não somam nem perdem tempo. Saíram o Worker criado a cada registro (nunca era encerrado) e os listeners que se acumulavam nos elementos de áudio.
  - **Ao iniciar, o servidor carrega os plays de todos os usuários.** Antes carregava só os do usuário de id 1 (o mapeamento roda fora de uma requisição), mas somava ao vivo os de qualquer usuário: os números mudavam a cada reinício.
  - **Desempate:** com a mesma contagem, vem primeiro quem tem mais tempo ouvido e depois a ordem alfabética (A a Z). Antes o empate saía de Z a A.
- **Página do álbum, artistas:** primeiro os artistas do álbum, depois todos os que participam de alguma faixa (na ordem das faixas), cada um uma vez.
- **Decisão minha (o Rodrigo pode mudar):** o limite de 30 segundos ou metade da faixa.
- **Não feito:** o play continua creditado ao álbum e aos artistas do primeiro arquivo de um grupo de faixas duplicadas, não necessariamente o arquivo tocado.
- Conferido: testes novos do servidor (`tests/test_play_count.py`, 9; a suíte toda passa, 356) e, no navegador com uma API simulada e áudio de verdade, uma faixa de 20 s contou aos 11 s com o hover passando de "unplayed" para "1 play", a troca de faixa enviou a extensão de 25 s, e uma faixa pulada aos 7 s não enviou nada; artistas do álbum na ordem certa. **Não conferido com o servidor real nem com o histórico real.**

## 3.27.2 (2026-11-11)

- **AlbumThumb e ArtistThumb:** a imagem não tem mais a borda de 1 px por dentro (era `neutral-900`), em todos os lugares onde os dois cartões aparecem (Home, página do artista, página do álbum, "View history").
- Conferido no navegador (API simulada): cartões de álbum na página do artista e artistas na página do álbum sem a borda. Só o cliente mudou; o servidor só sobe a versão.

## 3.27.1 (2026-11-11)

- **Página do álbum, título e ano:** o ano fica ao lado da última palavra do título, a 12 px (era 10), e desce de linha junto com o texto quando o título é grande. Antes, um título de mais de uma linha jogava o ano sozinho para a linha de baixo.
- Conferido no navegador (API simulada) em 1600 x 900: 12,00 px com título de 1 linha e de 4 linhas, o ano na mesma linha da última palavra. Só o cliente mudou; o servidor só sobe a versão.

## 3.27.0 (2026-11-11)

- **Nova página do álbum (AlbumPanel do Figma, nó 12506:4909), acima de 600 px.** Duas colunas com rolagem própria. À esquerda, o álbum: capa (400 px), título e ano, a linha "14 tracks • 52 minutes" (a mesma da página do artista, agora o componente `InfoLine`; as palavras em minúsculas nas duas páginas, antes "Tracks" e "Albums"), os botões play/pause, favorito, adicionar (menu "Add to queue" / "Add to Playlist") e options (o menu do álbum de sempre), os gêneros em pílulas e os artistas do álbum (`ArtistThumb`, o clique abre a página do artista). À direita, as faixas: as mesmas linhas da página do artista, sem a coluna do álbum. Até 600 px o celular continua com a página antiga (outras versões, "More from", álbuns parecidos e estatísticas seguem só lá).
  - **A coluna do álbum cabe na janela:** em janela baixa a capa encolhe (até 120 px) para o lado esquerdo não precisar rolar; só abaixo disso ele rola. Mínimo de 120 px: decisão minha.
  - **Capa em tela cheia:** clicar na capa abre a imagem original centralizada (até 796 px), sobre fundo `#000000` a 35%, com dissolve de 150 ms ease-out; clique fora ou Esc fecha (protótipo do Figma, nó 12508:5721).
  - **Decisões minhas (o Figma só tem o painel largo):** painel com menos de 760 px vira uma coluna só (álbum em cima, faixas embaixo); "Disc 2" só aparece em álbum com mais de um disco; gêneros não são clicáveis (não existe página de gênero); a contagem de plays no hover não entra (o servidor não manda esse número no álbum).
- **SidePanel:** todo botão tem cantos de 4 px (logo, itens de navegação, Playlists e playlists fixadas; antes pílulas). A playlist fixada passa a ter 8 px de padding em cima e embaixo (linha de 44 px), hover em `neutral-700` e a playlist aberta fica marcada em `neutral-700` (antes não havia estado selecionado).
- **Barras de rolagem dos painéis:** aparecem enquanto a lista rola e somem com um fade de 0,3 s cerca de 0,8 s depois (SidePanel, páginas, fila, página do artista e do álbum). Com o ponteiro sobre a barra ela aparece, para poder ser arrastada.
- **Código compartilhado:** os botões redondos e as linhas de faixa dos painéis saíram dos componentes do artista para `assets/scss/Global/panels.scss`, usados pelas duas páginas.
- Conferido no navegador com uma API simulada, em 1600 x 900, 1600 x 620, 950 x 900 e 375 x 812: página do álbum (1 e 2 discos, título longo, sem gêneros), capa aberta (fundo a 35%, 740 px em janela de 900, Esc e clique fora), menus de adicionar e de options, tocar pela linha, SidePanel (44 px, raio 4, `neutral-700`), barras de rolagem (aparecem e somem), página do artista igual à de antes, celular com a página antiga. **Não conferido com o servidor real:** imagens dos artistas do álbum e o estado selecionado da playlist em uma playlist aberta (a API simulada não tem a página de playlist). Só o cliente mudou; o servidor só sobe a versão.

## 3.26.5 (2026-11-10)

- **Linha de faixa da página do artista:** o número de ordem fica sempre a 20 px da miniatura do álbum e do nome da faixa. Antes a coluna reservava a largura de 3 dígitos de 12 px e o número ficava à esquerda, então a distância passava de 50 px. Agora a coluna tem só a largura dos dígitos (8 px cada, tabulares) e o número fica alinhado à direita, de modo que o espaço é 20 px em qualquer número e as miniaturas continuam alinhadas. O Figma reserva 12 px para 1 dígito; seguiu-se o pedido de 20 px.
- **Texto da linha:** nome da faixa, nome do artista e nome do álbum passam a usar `paragraph-16px` (Medium 16); antes eram `track-title-18px` (Bold 18). O número (`paragraph-12px`) e o tempo (`paragraph-14px`) não mudaram.
- Conferido no navegador em 1203 px: distância de 20,00 px nos números de 1 e 2 dígitos e os três textos medindo 16 px, peso 500. Só o cliente mudou; o servidor só sobe a versão.

## 3.26.4 (2026-11-10)

- **Layout antigo do desktop removido:** de 601 px para cima o app agora é sempre o layout de painéis (SidePanel, TopBar, página, QueuePanel e PlayerBar), em qualquer largura e em qualquer navegador. Antes, quem tinha o layout "alternate" salvo (o padrão de um navegador novo) via a versão antiga em telas acima de 900 px, como no notebook de 1203 x 603. Até 600 px o celular continua exatamente como era.
- **Saíram do projeto:** o layout alternativo (links no topo), a barra lateral direita antiga (Ctrl+B, abas de início, busca e fila), as opções de Configurações "Usar layout sem barra lateral", "Alternar barra lateral direita", "Largura total" (já não fazia nada nos painéis) e "Ocultar a capa do painel esquerdo", e o código da barra de player antiga do desktop. O que o celular usa (barra de baixo, páginas antigas, fila do Now Playing) ficou.
- Conferido no navegador: o CSS computado de 8 telas em 1857, 1203 (x 603), 960, 900 e 700 px, com o layout antigo salvo, é idêntico ao dos painéis de antes; em 375 e 600 px é idêntico ao do celular de antes. A única diferença é a lupa da busca (sem efeito visual).
- Só o cliente mudou; o servidor só sobe a versão. As telas que ainda não foram redesenhadas (Álbum, Playlist, Pasta, Busca, Configurações) seguem como estavam, agora dentro dos painéis.

## 3.26.3 (2026-11-09)

- **Busca da TopBar:** o ícone da lupa passa a ter o glifo de 18 x 18 px (era 20), o texto usa o novo estilo `paragraph-16px` (Medium 16) e o espaço entre a lupa e o texto é de 12 px (era 24). O peso Medium do `paragraph-16px` segue o dos outros `paragraph`: não foi informado, decisão minha.
- Só o cliente mudou; o servidor só sobe a versão.

## 3.26.2 (2026-11-09)

- **TopBar:** a busca não passa de **500 px** de largura. O que sobra fica antes do avatar, que continua na borda direita (com o título de uma página, é o título que vai para a direita).
- **Página do artista:** o hero agora vai até a borda do painel, sem a faixa de 7 px da barra de rolagem. A barra de rolagem passou a ser desenhada **sobre** a página (e sobre o hero): 4 px, redonda, `neutral-700`, a 3 px da borda, como a fina dos outros painéis; arrasta com o mouse e some quando a página cabe.
- **Linha de faixa:** o tempo passa para `paragraph-14px` em `neutral-300` e o ícone de options também em `neutral-300` (o coração continua branco).
- Só o cliente mudou; o servidor só sobe a versão.

## 3.26.1 (2026-11-09)

- **Página do artista, lista de faixas:** o número de ordem passa para `paragraph-12px` em `neutral-300`. E volta a função de ver **quantas vezes a faixa foi tocada**: ao passar o mouse sobre a linha, "12 plays" (ou "unplayed") aparece no fim, no lugar do coração, do tempo e das opções (`paragraph-14px`, `neutral-300`; estilo e cor são decisão minha). Com o mouse sobre esses botões eles voltam, para não ficarem invisíveis e clicáveis ao mesmo tempo.
- Só o cliente mudou; o servidor só sobe a versão.

## 3.26.0 (2026-11-09)

- **Nova página do artista, etapa D: hero com imagem, thumbnail com ponto de foco e o menu do artista novo.**
  - **Hero (servidor e cliente):** o artista passa a ter, além da foto redonda (thumbnail), uma imagem larga escolhida à mão. Nada é baixado sozinho. O servidor guarda a imagem **sem cortar** (no máximo 2560 px de largura, mais uma versão de 1280 px para telas estreitas) numa pasta própria (`images/artists/hero`) e o **ponto de foco** (x e y, em %) num arquivo JSON com o nome do artista, ao lado da imagem; a "marca de que existe hero" é a própria imagem. Rotas novas, só para admin: `POST /artist/<hash>/hero` (envia a imagem e o foco), `POST /artist/<hash>/hero/position` (só o foco) e `DELETE /artist/<hash>/hero`; as imagens saem em `/img/artist/hero/<arquivo>` e `/img/artist/hero/small/<arquivo>`. `GET /artist/<hash>` traz o `hero` (arquivo, foco e uma versão para furar o cache) ou `null`. O hero da página usa `object-fit: cover` com esse foco: nunca estica nem deforma e o mesmo pedaço fica à vista em qualquer largura. Sem hero, o quadriculado de antes.
  - **Reposicionar:** o botão **Reposition** (transparente, borda de 1 px e texto brancos, raio 8) aparece no hover do hero, só para admin e só quando há hero. Arrastar a imagem (mouse ou dedo) move o foco, com o enquadramento real à mostra; **Save**, **Cancel** e, com um hero já salvo, **Remove**. Uma linha explica que o enquadramento se adapta a outras larguras.
  - **Thumbnail:** o envio da foto redonda aceita o ponto de foco (`x` e `y`, opcionais; sem eles, o centro como antes) e o quadrado é cortado em volta dele. No cliente, **Update artist's thumbnail** abre uma janela com a foto, o quadrado para arrastar (com o círculo que vira a foto redonda), Save, a escolha de outro arquivo e o **Refetch photo** que já existia. A imagem nova aparece na hora.
  - **Menu do artista**, em todo lugar onde ele abre (cartões, busca, página, hero): Play next, Add to queue, Add to Playlist, Add to Collection; separador; Update artist's thumbnail e Update artist's hero (só admin; o do hero só no layout em painéis, e de fora da página do artista leva até ela); separador; Open in files (a pasta em comum das faixas do artista; se for a raiz da biblioteca, a pasta do primeiro álbum, com aviso); separador; Rename (só admin, a janela que já existia); separador; Search on. O "Search on" do artista passa a buscar o nome do artista do menu, não o da página aberta.
  - Testes do servidor: `tests/test_artist_hero.py` (novo) e o foco da thumbnail em `tests/test_artist_image.py`.
- Servidor **e** cliente mudaram: depois de atualizar, o hero e o foco só passam a existir quando o admin enviar a primeira imagem.

## 3.25.0 (2026-11-09)

- **Nova página do artista, etapa C: abas de lançamentos e cartão de álbum com duas variantes.**
  - **Abas Albums, EPs & Singles, Lives, Appearances, Compilations (e Soundtracks, quando houver):** todos os álbuns do artista, do mais novo ao mais antigo, em grade (até 8 colunas, 20 px entre colunas e linhas, padding `40 8 20 8`), no lugar do carrossel que rolava de lado. A lista completa vem do servidor quando a aba abre. Uma aba sem nada mostra a linha "Nothing here yet". Em painéis mais estreitos a grade perde colunas (cartão de no mínimo 120 px). As rotas "ver tudo" continuam no app, só a página não as usa mais.
  - **Cartão de álbum (`AlbumThumb`) com duas variantes:** `home` (nome, artista e ano: Home, "View history" e a aba Appearances) e `artist` (nome e ano: as outras abas). Novo estilo de texto `album-title-16px` para o nome (cor `neutral-100`), artista e ano em `paragraph-14px` `neutral-300`, sem gaps entre a capa e as linhas. A Home passa a mostrar o ano. O servidor já mandava o ano em todos os cartões; sem data, o ano some.
- Só o cliente mudou; o servidor só sobe a versão.

## 3.24.1 (2026-11-09)

- **Página do artista: sem ícone de arrastar na lista de faixas.** No hover da linha o número agora fica onde está, sem virar o ícone de arrastar (não há para onde soltar a faixa: arrastar fica só nas playlists, por enquanto).
- Só o cliente mudou; o servidor só sobe a versão.

## 3.24.0 (2026-11-09)

- **Nova página do artista, etapa B: hero, abas e "Most played tracks".** No desktop (a partir de 601 px, layout padrão) a página do artista vira um painel com borda que rola por dentro, no lugar do cabeçalho antigo:
  - **Hero:** 400 px de altura (280 a 400 px conforme a largura do painel, proporção 1319 x 400), padding `20 12`, o nome do artista em `screen-title-48px` (uma linha, com reticências), os números (`203 Tracks • 14 Albums • 17 hrs, 52 minutes`, `paragraph-14px`) e os botões: play (40 px, vira pause quando a fila é a deste artista e está tocando; toca "Most played tracks" em ordem), favoritar (32 px, coração em `error/300`) e opções (14 x 32, abre o menu do artista). Enquanto não há imagem de capa (vem na etapa D) o fundo é o quadriculado de 16 px (`neutral-900` e `neutral-700`) com o degradê até `#070707` (sem estilo no Figma, a confirmar).
  - **Barra de abas:** 44 px, fixa no topo ao rolar. Abas: Most played tracks, Albums, EPs & Singles, Lives, Appearances, Compilations (e Soundtracks só se houver). A aba aberta vai na URL (`?tab=albums`, o botão voltar volta à aba anterior) e as setas esquerda e direita movem entre as abas. Novo estilo de texto `action-button-16px` (Bold 16).
  - **Aba "Most played tracks":** todas as faixas do artista por reproduções, em uma lista virtual. A linha segue o Figma (64 px, número, capa de 48, título, artista, álbum, coração, tempo, opções; hover em `neutral-700`; no hover o número vira o ícone de arrastar). Um clique toca a partir da faixa, o clique direito abre o menu da faixa. Em painéis estreitos a coluna do álbum, depois a do artista e por fim o número e o coração saem.
  - As abas de lançamentos (Albums, EPs & Singles, Lives, Appearances, Compilations) ainda não têm conteúdo (etapa C): ficam em branco, e a linha "Nothing here yet" aparece quando não há nada.
  - O cabeçalho antigo (foto ao lado, botão de editar foto e de renomear), os gêneros, as estatísticas e os artistas parecidos não aparecem mais nesse layout (o código continua). Celular (até 600 px) e layout alternativo seguem com a página antiga.
- Só o cliente mudou; o servidor só sobe a versão.

## 3.23.0 (2026-11-09)

- **Formato e bitrate no QueuePanel** (nova página do artista, etapa A). A etiqueta que o cartão antigo do painel da esquerda mostrava (por exemplo `FLAC • 3200`) volta **sobre a capa do álbum** da Queue, no canto inferior esquerdo, a 8 px das bordas e sem tapar o disco. É o mesmo componente de antes (`Bitrate.vue`), com os tokens de etiqueta do app: fundo `neutral-700`, raio 4, padding `1 4`, texto `paragraph-12px` em `neutral-100`. Some quando a faixa não tem bitrate; o `title` explicativo continua. O Figma não tem desenho para ela: medidas e cores são uma decisão provisória.
- Só o cliente mudou; o servidor só sobe a versão.

## 3.22.1 (2026-11-07)

- **Largura máxima dos painéis laterais:** 224 px o painel da esquerda e 280 px a Queue (os tamanhos do Figma). Abaixo disso continuam com 25% da largura da janela; a 1400 px ou mais ficam nos tamanhos de antes.
- Só o cliente mudou; o servidor só sobe a versão.

## 3.22.0 (2026-11-07)

- **Painéis laterais com 25% da largura da janela** (o painel da esquerda era 224 px e a Queue 280 px). O que há dentro escala com o painel e os paddings e gaps continuam em px.
  - **Queue:** a capa é um quadrado da largura do painel e o disco aparece acima dela por 55/264 da largura (os números do Figma a 280 px), então o conjunto escala inteiro: o disco girando fica proporcional em qualquer largura.
  - **A grade em painéis agora vale a partir de 601 px** (antes de 901 px): no que era o tablet (601 a 900 px) a Home tem o painel da esquerda, a TopBar, o conteúdo e a Queue. A PlayerBar fica em duas linhas até 900 px (as ações e a música na segunda) e em uma linha acima disso; a barra de navegação do tablet some. Até 600 px (celular) nada muda.
  - **Layout alternativo:** de 601 a 900 px ele mostra o layout padrão (a barra de links não cabe); acima de 900 px continua como era.
  - A coluna da Queue só anima ao abrir e fechar o painel (com a largura em `vw`, redimensionar a janela disparava a transição e as colunas ficavam atrasadas).
- Só o cliente mudou; o servidor só sobe a versão.

## 3.21.4 (2026-11-07)

- **Play e pause da PlayerBar com 40 x 40 px** (eram 48). O ícone e o spinner acompanham a escala. Só o play tem `padding-left` de 4 px (o triângulo fica mais centrado); o pause não tem padding.
- **TopBar com 52 px de altura** (era 64). **A busca não tem mais fundo nem traço**: ficam a lupa e o texto, e ela cresce até 12 px do botão do perfil. Em páginas com título na barra (pasta) o título continua entre a busca e o perfil, com o espaço de antes.
- **O play que aparece sobre a miniatura na Home (álbuns e artistas) agora é um círculo de 40 x 40 px** (raio de 400 px). Antes ficava oval: o `height` global do botão anulava a proporção. A cor azul não mudou.
- Só o cliente mudou; o servidor só sobe a versão.

## 3.21.3 (2026-11-07)

- **Cores do play e do pause da PlayerBar** (nó `12385:255` do Figma): o play tem fundo `neutral-700`, ícone `neutral-100` e hover `neutral-500`; o pause tem fundo `neutral-500`, ícone `neutral-100` e hover `neutral-700`. A troca entre os dois segue com a transição de 400 ms.
- Só o cliente mudou; o servidor só sobe a versão.

## 3.21.2 (2026-11-07)

- **PlayerBar nova também no tablet.**
  - **De 661 a 900 px** (qualquer layout) a PlayerBar do Figma substitui a barra antiga, em duas linhas: os controles com a linha do tempo em cima; embaixo, as ações (volume, letra, favorito e add) à esquerda e a música com a capa à direita. Os botões de navegação continuam embaixo dela. Até 660 px (celular) a barra continua a de antes, e o layout alternativo acima de 900 px também.
  - **O chevron** sobre a capa da PlayerBar (abre e fecha a fila) fica com 25% de opacidade, como no Figma.
  - **Gaps:** FeedPanel de 32 para 40 px (entre o título e as linhas); QueuePanel de 12 para 20 px (entre o título, a lista e a miniatura).
- Só o cliente mudou; o servidor só sobe a versão.

## 3.21.1 (2026-11-07)

- **Correções do redesign da Home (desktop, layout padrão).**
  - **A música que toca nunca sai da fila:** "Clear queue" do QueuePanel apaga tudo menos a faixa que toca (a música continua e a PlayerBar não fica vazia); o `delete` de um grupo também deixa a faixa que toca.
  - **SidePanel sem a capa do álbum** (o cartão da música embaixo das playlists) e **a página Now Playing sai do desktop**: o endereço volta para a Home. A letra (lyrics, que é uma aba dela) continua funcionando. Telas de até 900 px e layout alternativo não mudam.
  - **A capa do QueuePanel leva à página do álbum** (a que está tocando).
  - **O disco e a capa do QueuePanel têm 8 px de cada lado** (antes 4 à direita: o painel guarda 4 para a barra de rolagem da lista, e a miniatura devolve).
  - **Cabeçalho do grupo com 4 px de padding em cima** (o nó `12408:1963` do Figma), para não ficar colado na faixa de cima.
  - **A barra de rolagem das páginas** começa a 4 px da borda de cima do painel e termina a 4 px da borda de baixo.
  - **O chevron do hover na miniatura da PlayerBar** passa a aparecer por cima da capa.
- Só o cliente mudou; o servidor só sobe a versão.

## 3.21.0 (2026-11-07)

- **Redesign da Home, etapa 6: os botões da fila (QueuePanel, desktop, layout padrão).** Os botões do cabeçalho de cada grupo (álbum ou playlist) agora funcionam e afetam **só as faixas daquele grupo**: `shuffle` embaralha a ordem dentro do grupo, uma vez, sem parar a música (a faixa que toca continua tocando); `repeat` liga e desliga a repetição do grupo (quando a última faixa do grupo termina, volta para a primeira dele); `delete` tira todas as faixas do grupo (se a que toca é dele, passa para a seguinte, como a remoção de uma faixa); `drag` arrasta o grupo inteiro, com o cabeçalho, para outra posição da fila. Na linha de cada faixa o `repeat` repete aquela faixa. Os de liga e desliga ficam em `neutral-100` quando ligados (o Figma não tem o estado ligado; é a cor do hover), com `aria-pressed` e `aria-label`, e todos são alcançáveis pelo Tab.
- **Prioridade das repetições:** repetir a faixa vale mais que repetir o grupo, que vale mais que o `repeat` geral da PlayerBar (todos, uma, nenhum). A faixa que repete volta para si mesma; no fim do grupo que repete a fila volta ao começo do grupo; nas demais, vale o repeat da PlayerBar. O `shuffle` e o `repeat` da PlayerBar continuam para a fila toda. A repetição vale mesmo com o repeat geral desligado (a fila não para no fim do grupo ou da faixa). O estado da repetição é salvo com a fila.
- **Arrastar uma faixa de um grupo:** ela pode mudar de lugar dentro do grupo; arrastada para fora vira faixa solta; solta entre duas faixas de um grupo, entra nele (decisão minha: se preferir travar dentro do grupo, é só pedir).
- Não mudam: o layout alternativo e as telas de até 900 px. O servidor só sobe a versão.

## 3.20.0 (2026-11-07)

- **Redesign da Home, etapa 5: o QueuePanel (desktop, acima de 900 px, layout padrão).** A fila vira um painel de 280 px à direita, entre a TopBar e a PlayerBar (a TopBar passa a ocupar a largura toda), com borda de 1 px `neutral-700` e cantos de 8. Abre e fecha pela miniatura da PlayerBar com uma animação de largura de 300 ms (`ease-in-out`) e o estado fica salvo. Ele **substitui a barra lateral direita antiga** nesse layout: a opção "Use sidebar" não tem mais efeito no desktop de layout padrão (continua valendo no layout alternativo e nas telas de até 900 px, onde a barra já não aparecia).
- **Título e lista:** "Queue" em `paragraph-18px` e, na direita, "Clear queue" (`action-button-14px`, `error/300`, sublinha no hover) que apaga a fila toda. A lista usa o `DynamicScroller`, com 4 px entre os itens, barra de rolagem fina de 4 px (`neutral-700`) e um degradê (máscara de 24 px) embaixo quando há mais para baixo e em cima quando já rolou. Fila vazia: a mensagem de sempre, sem "Clear queue" e sem o disco.
- **Faixas:** 36 px de altura, capa de 28, nome em `paragraph-14px` com reticências e os botões repeat, delete e drag (12 px, `neutral-500`, `neutral-100` no hover, área de clique de 24). Tocar a faixa, remover e arrastar para mudar a ordem funcionam (a faixa que toca acompanha o arrasto); a faixa que toca e o hover da linha usam `neutral-700`; o botão direito abre o menu de faixas de sempre. O repeat da faixa aparece desabilitado (etapa 6).
- **Grupos:** quando um álbum ou uma playlist inteiros entram na fila (tocar, "Add to queue" e "Play next"), as faixas ganham um cabeçalho com o ícone (`soundtrack`, que gira 180° em 2 s, ou `add-to-playlist`), o nome em `paragraph-12px` (nome longo corre em letreiro a cerca de 30 px/s, com 1 s de pausa; parado com reticências se o sistema pede menos movimento) e os botões shuffle, repeat, delete e drag, desabilitados até a etapa 6. Um divisor de 1 px marca o fim do grupo. Faixas de pasta, artista, busca ou favoritos ficam soltas. O grupo é salvo junto com a fila; filas salvas antes continuam funcionando (soltas).
- **Miniatura do disco:** a capa do álbum que toca (267 x 267) com um vinil atrás (a imagem do Figma, guardada no cliente), 55 px acima da capa, que gira 360° em 8 s enquanto a música toca e para quando pausa.
- Não mudam: o layout alternativo e as telas de até 900 px. O servidor só sobe a versão.

## 3.19.0 (2026-11-07)

- **Redesign da Home, etapa 4: a PlayerBar nova (desktop, acima de 900 px, layout padrão).** A barra ganha a ordem do Figma (`default-2` pausada e `playing-2` tocando): à esquerda os controles (play/pause de 48 px, anterior e próxima de 34, a linha do tempo com o tempo atual, a barra e o tempo total, e shuffle e repeat), no meio as ações (volume, lyrics, favorite e add, 40 px entre elas) e à direita o nome da música e os artistas alinhados à direita com a miniatura de 56 px na ponta. Barra de 80 px, padding 12 / 16, 40 px entre os três grupos (24 px até 1280 px de janela).
- **Pausado e tocando:** o fundo passa de `neutral-900` para `dynamic-playbar`, o círculo do play de `white` para `neutral-100` (com o ícone em `background` e `dynamic-playbar`), a trilha e as pílulas dos tempos de `neutral-700` para `neutral-500` e o nome dos artistas de `neutral-500` para `neutral-300`, tudo com transição de 400 ms (`ease-in-out`). O trecho carregado da barra passa a `neutral-300` quando toca (decisão minha: o Figma não tem esse trecho).
- **A miniatura abre e fecha a fila:** deixa de levar ao álbum e vira um botão que alterna `queue_panel_open` (salvo entre sessões); no hover aparece um círculo de 24 px `neutral-300` com o chevron (para cima com a fila fechada, para baixo com ela aberta), com `aria-label` "Show queue" / "Hide queue" e `aria-expanded`. O painel da fila entra na etapa 5; por ora só o estado e o chevron mudam. O nome da música vira o link do álbum.
- **Textos:** nome e artistas em `action-button-14px` e os tempos em `paragraph-12px` (o Figma não tem estilo nesses quatro textos; o Rodrigo escolheu). As pílulas dos tempos ficam mais baixas que no Figma (18 px contra 22) porque a altura de linha do estilo é automática.
- Não mudam: as telas de até 900 px e o layout alternativo (continuam com a barra de antes).
- Só o cliente mudou; o servidor só sobe a versão.

## 3.18.0 (2026-11-07)

- **Redesign da Home, etapa 3: o FeedPanel (desktop, acima de 900 px, layout padrão).** A Home vira o título "Good morning, nome" (a saudação que já existia, no estilo `screen-title-48px`, no lugar do cabeçalho "Home") e **três linhas de 8 cartões**, nesta ordem: Most played artists (8 artistas mais tocados de sempre, por número de reproduções), Most played albums (8 álbuns, igual) e Recently added (8 álbuns adicionados há pouco). As outras linhas (Recently played, Top artists this week e this month, coleções) saem da Home neste layout (o código continua, só não é chamado). Linha vazia não aparece. Sempre 8 cartões por linha, cada um com 1/8 da largura, 20 px entre eles; 32 px entre os blocos, 20 px entre o título da linha e os cartões, padding do painel 8 / 16 / 12 / 16. O título da linha usa `section-title-28px` e o "View history" (nas duas primeiras) `paragraph-18px` em `neutral-300`. Tokens `--feedpanel-*`.
- **Cartões novos:** `ArtistThumb` (imagem redonda quadrada com traço de 1 px `neutral-900` por dentro, nome centralizado 4 px abaixo em `paragraph-18px` `neutral-100`) e `AlbumThumb` (capa quadrada de cantos 8 com traço de 1 px por dentro, com uma "placa" `neutral-500` aparecendo atrás, em cima; título em `paragraph-18px` e artista em `paragraph-14px` `neutral-300`, com 4 px de margem dos lados; proporção 164 x 172). Mantêm o que os cartões antigos faziam: clique abre o artista ou o álbum, o nome do artista dentro do cartão do álbum abre o artista, clique direito abre o menu, o botão de tocar aparece ao passar o mouse.
- **Páginas "View history":** `/history/artists` e `/history/albums` (o link "View history" de cada linha): todos os artistas ou álbuns mais tocados de sempre, por reproduções, até 500 (sem paginação), com os mesmos cartões e o número de reproduções embaixo. O Figma não tem desenho delas: o painel e os cartões são os da Home, em colunas de pelo menos 10,75rem (a largura mínima das outras grades do app). Sem reproduções aparece "Nothing played yet.".
- **A largura máxima do app (1760 px) sai** no layout padrão acima de 900 px: o painel ocupa a janela toda, como no Figma (1857 px). Vale para todas as páginas.
- Não mudam: as telas de até 900 px e o layout alternativo (continuam com a Home de antes) e o servidor (só sobe a versão).
- Só o cliente mudou; o servidor só sobe a versão.

## 3.17.0 (2026-11-07)

- **Redesign da Home, etapa 2: a TopBar (desktop, acima de 900 px, layout padrão).** Voltar e avançar viram dois círculos de 36 px com borda de 1 px `neutral-700`, 16 px entre eles e sem a linha separadora, com o ícone `chevron` do Figma (o de voltar é o mesmo girado 180°; o arquivo `chevron-right.svg` virou `chevron.svg`). A busca passa a 380 x 48 px, redonda, com fundo `neutral-700` a 50%, borda de 1 px, lupa de 20 px em `neutral-500`, 24 px até o texto e placeholder "Start typing to search..." no estilo `paragraph-18px` (o texto digitado é `neutral-100`, o Figma não mostra). O avatar tem 36 px na ponta direita. 64 px entre os botões e a busca. Nas larguras pequenas a busca encolhe até 14rem e os espaços caem para 24 px. Tokens `--topbar-*`.
- **O título da página fica:** o Figma não tem o título, mas ele não foi apagado: o caminho da pasta (com o menu de ordenação) e os títulos de Configurações, Playlists, Faixas do artista e Now Playing continuam entre a busca e o avatar e cedem espaço primeiro.
- Não mudam: o layout alternativo, as telas de até 900 px e a busca da barra lateral direita.
- Só o cliente mudou; o servidor só sobe a versão.

## 3.16.0 (2026-11-07)

- **Redesign da Home, etapa 1: a grade em painéis e o SidePanel (desktop, acima de 900 px, layout padrão).** O app vira um conjunto de blocos soltos sobre o fundo `background`, com 8 px em volta de tudo e 8 px entre os painéis, cantos de 8: SidePanel (224), TopBar (64), conteúdo da página (o FeedPanel, ocupa o resto) e PlayerBar (80) embaixo, na largura toda. As bordas laterais do app e a borda de cima da barra de baixo saem; a TopBar, o conteúdo e a barra lateral direita têm borda de 1 px `neutral-700` por dentro. Vale para todas as páginas (a moldura é a mesma em toda página). Tokens novos `--layout-panel-gap`, `--layout-panel-radius`, `--layout-panel-border` e `--topbar-height`. A barra de rolagem das páginas fica fina (4 px, redonda, `neutral-700`, sem trilho). Telas de até 900 px e o layout alternativo não mudam.
- **SidePanel como no Figma:** fundo `neutral-900`, cantos de 8, sem a borda direita, padding 8, cabeçalho de 60 sem fundo (a logo é a mesma do Figma), divisor `neutral-700`; os itens usam o estilo de texto `action-button-14px` (Bold 14, antes peso 600), a pílula do item ativo é `neutral-700` e o coração de Favorites é sempre cheio e vermelho (`error/300`), mesmo com outra página ativa. Os textos do painel passam a usar o token de texto, sem tamanho nem peso soltos. O cartão da música do pé do painel (opção "use_np_img") não está no Figma e ficou como estava.
- **PlayerBar:** sem a borda de cima, cantos de 8 e fundo `neutral-900` (a PlayerBar nova inteira vem na etapa 4).
- **Menu de contexto:** a seta do submenu passa a 14 x 14 px e `neutral-100`, como o Rodrigo atualizou no Figma (o ícone `chevron`).
- Só o cliente mudou; o servidor só sobe a versão.

## 3.15.0 (2026-11-07)

- **Redesign da Home, etapa 0: tokens do Figma.** Os cinco cinzas mudaram de valor no Figma e o app segue pelo nome do token: `neutral-300` `#b8b8b8` para `#707070`, `neutral-500` `#606060` para `#333333`, `neutral-700` `#323232` para `#222222`, `neutral-900` `#222222` para `#111111`. Nova cor `--color-dynamic-playbar` (`#1f1e1f`, ainda sem uso). O hover padrão (`--hover-bg`) passa a `neutral-700`, então continua `#222222`.
- **O que muda na tela:** o fundo do menu de contexto e do menu do usuário passa a `#111111`, o divisor e o hover do item a `#222222`, os ícones do menu a branco (como no Figma) e a seta do submenu a `#707070` (token novo `--menu-item-arrow`); a borda de cima da barra do player passa a `#111111` e o nome do artista nela a `#333333` (contraste baixo, fica assim até a PlayerBar nova); a trilha e as pílulas dos tempos seguem `#222222` (agora por `neutral-700`) e o trecho carregado `#333333`.
- **Sem desenho no Figma:** o fundo da página de playlist (mistura a 15%) e o fundo padrão do cabeçalho da playlist mantêm os valores antigos pelos tokens `--color-legacy-neutral-500` (`#606060`) e `--color-legacy-neutral-900` (`#222222`), até o Rodrigo decidir.
- **Tokens de texto:** os nove estilos de texto do Figma (screen-title-48px, section-title-28px, panel-title-20px, action-button-14px, album-title-24px, track-title-18px e paragraph-18px, -14px e -12px) viram tokens `--text-<nome>-size`, `-weight` e `-line-height` (a altura automática do Figma é `normal`) e o mixin `@include text('<nome>')`. Ainda ninguém usa: os painéis novos da Home aplicam nas próximas etapas.
- Só o cliente mudou; o servidor só sobe a versão.

## 3.14.0 (2026-11-03)

- **Fonte do app inteiro: Satoshi Variable** (pesos 300 a 900, um arquivo só, `Satoshi-Variable.ttf`, 127 KB, dentro do próprio cliente, sem CDN). Vale para o texto do app, os botões, os campos, o painel da esquerda e a PlayerBar. Antes: SF Compact Display no app e Roboto no painel e na PlayerBar. Os arquivos do SF Compact Display e o `import` da Roboto saíram do cliente (o pacote da Roboto continua no `package.json`, sem uso; o SF Mono dos campos de código e das chaves continua). O `:root` tem um token só, `--font-sans`, no lugar do `--font-roboto`. Os caracteres que a Satoshi não tem (japonês, coreano, emoji) caem na fonte do sistema.
- Só o cliente mudou; o servidor só sobe a versão.

## 3.13.1 (2026-11-03)

- **PlayerBar:** 24 px entre o botão de lyrics e o do volume (antes 40, o valor do Figma). É a distância entre as caixas dos dois botões (28 px); entre os ícones ficam 32 px, e os círculos de hover de 34 px não se tocam.
- Só o cliente mudou; o servidor só sobe a versão.

## 3.13.0 (2026-11-02)

- **"Mark as Compilation" no menu do álbum.** Marca o álbum como coletânea para ele entrar na seção Compilations da página do artista (em Albums), como já era com "Mark as EPs & Singles", "Soundtrack" e "Live album". O servidor aceita `compilation` em `POST /album/<hash>/type` (a marca fica no banco e vale depois de reiniciar). Para um álbum que o servidor já toma por coletânea sozinho (Various Artists, "Greatest Hits"...), "Remove from Compilations" grava a marca `album` ("álbum comum"), que vence a detecção pelo título. Sem marca, tudo funciona como antes.
- **Menu da música sem "Go to Folder"** (o "Open in files" continua).
- **Menu de contexto como no Figma:** ícones em 20 px (antes 18), divisor em `neutral/700` (antes branco a 15%) e o ícone novo `files` no "Open in files" (o arquivo `menu/go-to-folder.svg` foi apagado). `compilation` e `files` são as duas variantes novas do Icon (43 SVGs); os 23 estilos de cor continuam iguais aos tokens e os outros ícones não mudaram.
- **Página do álbum (e do artista e da playlist):** o botão de três pontinhos com o menu aberto usa a cor do hover (`neutral/900`, antes azul); o botão de favorito não tem mais o preenchimento de fundo e o hover é o padrão; o botão Play é sempre branco (texto em `background`), qualquer que seja a cor do álbum.
- **PlayerBar:** 32 px entre a música, o favorite e o add (antes 40).

## 3.12.1 (2026-11-01)

- **Hover da barra do player igual em todos os botões.** Favorite, add, lyrics e speaker passam a ter o mesmo círculo de hover de 34 px dos cinco botões do centro (antes 28 px). Os ícones continuam no mesmo lugar (20 px, com as mesmas distâncias do Figma): só o círculo cresceu, em volta do ícone.
- **Hover padrão do app em `neutral/900` (`#222222`).** O hover de todo `button` era azul (`$darkestblue`): os botões de editar o nome e a foto do artista, do álbum e da playlist, os botões do menu de foto e os demais. Agora usam o token novo `--hover-bg` (`neutral/900`), o mesmo círculo dos botões do centro da barra.
- **Menu de contexto:** o hover do item deixa de ser azul. Como o fundo do menu já é `neutral/900`, o hover usa `neutral/700` (`#323232`, token novo `--menu-item-bg-hover`; decisão do Rodrigo), para continuar visível.
- Não mudaram: os estados "ativo" em azul (`.btn-active`, a linha tocando na fila, a opção ativa dos seletores e o cartão do resultado da busca com o menu aberto).
- Só o cliente mudou; o servidor só sobe a versão.

## 3.12.0 (2026-10-27)

- **Barra do player (acima de 900 px) igual ao PlayerBar do Figma** (nó `12355:646`). A barra de baixo ganha o fundo `background` (`#0d0d0d`) e a borda de cima de 2 px em `neutral/900`, com 80 px de altura útil e padding de 12 e 20 px. Os tokens vivem no bloco novo `--playerbar-*` de `_musix-tokens.scss`; nenhuma cor do Figma mudou (os 23 estilos já eram iguais).
- **Controles:** os cinco botões do centro (shuffle, anterior, play, próximo e repeat) são círculos de 34 px, com 28 px entre eles, e o play tem o mesmo tamanho dos outros. Todos os ícones têm a mesma caixa de 20 px (o glifo de 20 no viewBox de 24), então a proporção entre o ícone e o círculo do hover é a mesma em todos. O hover é o círculo cheio em `neutral/900` (antes `#1a1919`).
- **Esquerda:** capa de 56 px (raio 4, sombra do Figma), texto em Roboto Bold 14/20 (título `neutral/100`, artistas `neutral/500`), 14 px entre a capa e o texto e 40 px entre a música, o favorite e o add. Os dois ícones têm 20 px e o hover é um círculo de 28 px (no Figma eles não têm círculo: decisão minha).
- **Linha do tempo:** 502 px (tempo, barra de 400 x 4 e tempo, com 12 px entre eles), colada nos botões. Os tempos viram "pílulas" em `neutral/900` (raio 4, padding 1 e 4, Roboto Bold 12/20 branco). O trecho já carregado da barra usa `neutral/700` (decisão minha: não existe no Figma). A bolinha da barra tem 14 px e continua aparecendo só com o mouse na barra.
- **Direita:** `lyrics` e `speaker` em círculos de 28 px com ícone de 20 px, 40 px entre os dois grupos e 8 px entre o speaker e a barra do volume (94 x 4, bolinha de 14).
- **Ícones novos:** `shuffle` e `repeat` do Figma (nós `12355:544` e `12355:550`, 41 SVGs na pasta `figma/`); a barra usa também o `play` e o `pause` do Figma (o `transform` que consertava o `pause.svg` antigo saiu). O Figma ainda não tem o "repetir uma": o estado usa o `repeat-one.svg` antigo.
- **Telas até 900 px:** o layout não mudou; só o desenho dos botões shuffle, repeat, play e pause, que agora são os do Figma (o glifo do play passou de 13,8 x 15,4 para 18 x 20 px e o do pause de 8,1 x 14,8 para 16 x 20 px).
- Só o cliente mudou; o servidor só sobe a versão.

## 3.11.3 (2026-10-27)

- **Controles do player com hover em círculo perfeito.** Cada botão da barra de baixo (shuffle, anterior, play, próximo e repeat) passa de 48 x 40 px (a "pílula") para 28 x 28 px, com o hover redondo igual nos cinco, e o espaço entre eles passa a 12 px. Todos os glifos cabem em 14 x 14 px (o lado maior vale 14): anterior e próximo ficam em 14 x 14, o play em 12,5 x 14 e o shuffle e o repeat, mais largos que altos, em 14 x 11,1 e 14 x 11,9. O pause segue a mesma medida (escala do desenho de 14,82 px para 14 px; conferido só pela conta, porque o app de teste fica carregando e não mostra o pause). Antes os glifos tinham tamanhos diferentes entre si (o anterior e o próximo eram maiores que os outros).
- Só o cliente mudou; o servidor só sobe a versão.

## 3.11.2 (2026-10-27)

- **Ícones do menu de configurações na mesma proporção.** Os ícones antigos (viewBox de 28 ou 30, com margens próprias) apareciam de 11 a 20 px dentro da mesma caixa de 20 px, enquanto os do Figma ficam com 16,7 px. Albums, Artists e Tracks agora usam os ícones do Figma (`disc`, `user` e `mic`, os mesmos do menu principal, em contorno), e Appearance, Accounts, Folders, Backup e About (que não existem no Figma) ganharam um viewBox só nas configurações (`fitIcon`, em `settings/utils.ts`) que deixa o glifo com a proporção dos do Figma, sem mexer nos arquivos, que outras telas também usam. Hoje a maior medida de todos os ícones do menu é 16,7 px (alguns são mais estreitos pelo próprio desenho, como o microfone).
- Só o cliente mudou; o servidor só sobe a versão.

## 3.11.1 (2026-10-27)

- **Ícones do menu todos do mesmo tamanho.** Os paddings por ícone (`icon_pad`) do Home, Albums e Favorites compensavam os desenhos antigos e, com os ícones novos (todos com glifo de 20 px na caixa de 24), deixavam o Home, o disco e o coração menores que a silhueta do Artists. Saíram do `navitems.ts` e dos dois componentes que os liam (a barra de baixo e o menu lateral das telas pequenas). Na barra de baixo (caixa de 21,6 px) os quatro botões ficam com glifo de 18 px; no menu lateral (caixa de 24 px), com 20 px. O Playlists é a mesma coisa (o desenho dele é um pouco menor).
- Só o cliente mudou; o servidor só sobe a versão.

## 3.11.0 (2026-10-27)

- **Botão direito no card principal da pesquisa ("Top Result").** O clique direito em qualquer ponto do card (capa, título, etiqueta, play, espaço vazio) abre o menu de contexto do app, o do tipo do resultado: música (o mesmo dos três pontinhos), álbum ou artista. Antes só a música tinha menu, e só no botão dos três pontinhos; o clique direito abria o menu do navegador. Vale na página de pesquisa e na aba de pesquisa da barra da direita.
- **Ícones com dois estados (`data-state`):** `disc` (antes `ep-and-single`: disco cheio com furo e dois anéis), `favorite` (coração cheio e de contorno; a variante `favorited` saiu do Figma e o arquivo foi apagado) e `user` (silhueta cheia e de contorno), na mesma convenção do `home`. Nova classe `.icon-active` (`Global/basic.scss`) mostra o estado cheio em qualquer lugar: o botão de favoritar, a notificação de favorito e o "Playing from" de favoritos a usam, e o coração agora tem um tamanho só nos dois estados.
- **Itens Albums, Artists e Favorites do menu como o Home:** de contorno quando inativos e cheios na página aberta, no painel da esquerda, na barra de baixo e no menu lateral das telas pequenas (que agora também troca o ícone da página aberta, inclusive o Home).
- **Nove ícones reajustados para o vetor de 20 x 20 (Figma):** `add-to-queue`, `attach`, `login`, `logout`, `live-album`, `play-next`, `play-previous`, `play` e `soundtrack`, exportados de novo. Os ícones dos menus de contexto passam a ter todos o mesmo tamanho visual (15 px dos 18 px da caixa). O `chevron-right` não mudou: o Figma exporta o mesmo desenho.
- **Cores do Figma:** `--color-background` agora é `#0d0d0d` (fundo do painel da esquerda), `--color-neutral-500` é `#606060` (a mistura do fundo da página de playlist fica mais escura) e `--color-neutral-700` (`#323232`) foi criado, ainda sem uso.
- **Um ícone de busca só:** o `search-on` saiu do Figma por ser idêntico ao `search`; o item "Search on" dos menus da música e do álbum usa o `search.svg`. O README dos ícones tem as notas e a contagem (39 SVGs).
- Só o cliente mudou; o servidor só sobe a versão.

## 3.10.1 (2026-10-27)

- **Logo do painel da esquerda atualizado (protótipo do Figma).** O cabeçalho agora mostra só a palavra MUSIX (169 x 29 px, `logos/musix.svg`, em `currentColor`) centralizada no bloco de 60 px, no lugar da nota com o texto. Ela mantém a proporção e encolhe sozinha se o painel ficar mais estreito que o do desenho (conferido com `--sidepanel-width` em 160, 200, 224 e 260). A tela de login usa o mesmo logo. A nota (`logos/note.svg`) continua nos outros layouts.
- **Cores do painel atualizadas.** O fundo do painel passou de preto para `#151515` (novo token `--color-background`, o estilo "background" do Figma) e o cabeçalho para `#0a0a0a` (`--sidepanel-header-bg`), sem borda e sem gradiente. O token `--sidepanel-header-border` (`#303030`), que nunca foi usado, saiu porque o cabeçalho do protótipo não tem contorno; saíram também `--sidepanel-header-gap` e `--sidepanel-title-weight`, que só serviam ao texto "MUSIX" que deixou de existir.
- Só o cliente mudou; o servidor só sobe a versão.

## 3.10.0 (2026-10-27)

- **Painel da esquerda redesenhado (SidePanel do Figma).** Medidas do protótipo, todas em tokens `--sidepanel-*` (`_musix-tokens.scss`): painel de 224 px mais a borda de 1 px que o app mantém (o painel principal ganha 15 px: 1200 para 1215 a 1440 px), padding e espaços de 12, cabeçalho de 60 px com padding 10 12 10 18 e cantos 13, itens de 34 px com ícone de 20 px e 12 de espaço, 10 entre os botões, divisor de 1 px (`--color-divider`) com 12 acima e abaixo e cartão da música quadrado com cantos 10. Nada tem largura fixa: tudo ocupa a largura do painel menos o padding (conferido trocando `--sidepanel-width` para 200 e 260). O cabeçalho continua com o gradiente, a borda e a nota de hoje; o fundo cinza do item ativo também.
- **Fonte Roboto no painel.** A Roboto variável (`@fontsource-variable/roboto`, instalada no cliente: nada de CDN) cobre o 500 e o 600 de verdade. Todos os rótulos de navegação (ativos ou não) e o "MUSIX" do cabeçalho em SemiBold 600 de 14 px, as playlists fixadas em Medium 500 de 14 px (linha de 20). Só o painel usa a Roboto (token `--font-roboto`); a fonte do resto do app continua no `body` (`Global/index.scss`). A Roboto acrescenta cerca de 250 KB ao build (o navegador só baixa os trechos usados).
- **Botões reorganizados:** Home, Albums, Artists, Favorites, divisor, Playlists. Ícones do Figma: Artists com `user` e Playlists com `add-to-playlist`. A barra de baixo das telas pequenas segue a mesma ordem, com os mesmos tamanhos.
- **Ícone Home com dois estados:** `home.svg` traz a casa cheia (`data-state="active"`) e o contorno (`inactive`), e o CSS mostra um de cada vez (cheia no item ativo, contorno nos outros). A convenção vale para qualquer ícone com `data-state` (ver o README dos ícones).
- **Playlists fixadas no painel**, abaixo de "Playlists": capa de 28 px, nome cortado com reticências, clique abre a playlist e o clique direito abre o mesmo menu do card (Unpin, Rename, Add to queue, Delete). Elas aparecem sem abrir a página Playlists e acompanham na hora fixar, desafixar, renomear e excluir. "Rename" pelo painel abre a playlist já com o nome em edição (o campo agora também preenche quando a página abre renomeando).
- **Open in files no menu do álbum**, em todos os menus do álbum (página, cards, artista, coleção), antes de "Update album cover". A pasta vem das faixas (a pasta pai comum quando o álbum tem CD1 e CD2 em subpastas) e a aba abre no clique, como na música. A tradução do rótulo virou comum (`Menus.Common.OpenInFiles`).
- Só o cliente mudou; o servidor só sobe a versão.

## 3.9.1 (2026-10-24)

- **"Clear queue" mantém a música que está tocando.** Antes ele esvaziava a fila inteira: a faixa continuava tocando, mas sumia da fila, do Now Playing e das informações da barra do player. Agora a fila fica só com a faixa atual (destacada, a origem "Album ..." continua), a música não para e o player segue mostrando título, artista e capa. Sem nada tocando, ele esvazia tudo como antes. Só o cliente mudou; adicionar a fila a uma playlist continua igual.

## 3.9.0 (2026-10-24)

- **Letras pelo LRCLIB.** A busca online agora pergunta primeiro ao [LRCLIB](https://lrclib.net/) (aberto, sem chave) e só depois ao Musixmatch. Ela tenta o título como a faixa tem, depois o título sem enfeites de versão ("(feat. X)", "(Remix)", "- Remastered 2011", "(Radio Edit)"...) com o primeiro artista, e por fim uma busca em que só vale a letra de duração parecida (até 3 s de diferença: letra de outra versão sai do tempo). **Letra simples (sem marcas de tempo) também é aceita** e salva como `.lrc`; a sincronizada é preferida. Instrumental é reconhecido. O arquivo é gravado como veio (UTF-8, com quebra de linha no fim), de forma atômica, só dentro das pastas raiz, e **nunca sobrescreve um `.lrc` que já tenha texto** (um `.lrc` vazio conta como inexistente; a única troca permitida é uma letra simples por uma sincronizada quando "Override unsynced lyrics" está ligado).
- **"Não achei" guardado.** Quem não tem letra online não é procurado de novo por 30 dias (instrumental, 365). Falha de rede, 429 e erro de gravação não são guardados. O botão "Search online" ignora essa memória.
- **O botão "Search online" diz o motivo:** "No lyrics found online", "This track is instrumental", "Couldn't reach the lyrics sites", "Turn on the lyrics plugin in Settings" ou "Found the lyrics but couldn't save the file" (antes era sempre "No lyrics found!"). Achou, ele recarrega a letra salva pelo caminho normal, então a letra simples também aparece. O servidor tenta mais uma vez quando o LRCLIB responde 503 ("servidor ocupado").
- **Auto download em qualquer tela.** Com o plugin e o "Auto download lyrics" ligados, a busca roda quando a faixa começa a tocar, em qualquer tela e uma vez por faixa (pausar e voltar ou trocar de aba não repete). Falhas ficam só no console.
- **Find missing lyrics (Settings > Plugins > Lyrics, só admin).** Procura, em segundo plano no servidor, a letra de todas as faixas que não têm (sem `.lrc` com texto, sem letra na tag e sem `.lrc` de duplicata), com progresso, cancelar e resumo ao fim (achadas, sincronizadas, não achadas, erros com o arquivo). No máximo 2 consultas por segundo; espera e tenta de novo em 429 e 5xx; 3 falhas de rede seguidas abortam. Reiniciar o servidor zera o progresso; o que já foi salvo e a memória de "não achei" ficam.
- **Leitor de letras (`lib/lyrics.py`), três defeitos:** (1) `meta` e `is_synced` eram da classe, então o `[offset:+500]` ou `[ar:...]` de uma letra vazava para as seguintes até reiniciar o servidor; (2) linhas de seção como `[Chorus]` ou `[Verse 1]` quebravam o leitor (`ValueError`); agora são texto da letra; (3) a fração dos segundos era lida como milissegundos: `[00:03.50]` virava 3050 ms em vez de 3500 ms, e as linhas acendiam adiantadas em até quase 1 s. **Isso muda o tempo dos `.lrc` que já existiam** (para o certo). Também: colchetes dentro do texto de uma linha sincronizada não apagam mais o texto, `[offset:abc]` vale 0 e um BOM no início é ignorado.
- Precisa da internet e de permissão de escrita na pasta de músicas, com o plugin de letras ligado em Settings.

## 3.8.2 (2026-10-23)

- O `check` do submenu "Add to playlist" ficou com 18 x 18 (a medida dos ícones do menu) e foi para o canto direito do item: o nome fica de um lado e o ícone do outro (`space-between`), com o mesmo espaço à esquerda do nome e à direita do ícone. Nome comprido continua cortando com reticências, sem empurrar o check. Só o cliente mudou.

## 3.8.1 (2026-10-23)

- O YAML de exemplo do ZimaOS (`deploy/zimaos-compose.yml`) publica o MUSIX na porta **1972** (era 1971). Só o modelo mudou; o app não.

## 3.8.0 (2026-10-23)

- **"Add to playlist" mostra onde a música já está.** No submenu (menu da música e botão `add` da barra do player), as playlists que já têm a faixa ganham o ícone `check` (Figma `type=check`, 16 x 16, na cor do ícone do menu) logo depois do nome. Nome comprido continua cortando com reticências e o check fica fixo. Clicar numa playlist que já tem a música continua dando o aviso de "já está na playlist". Menus de álbum, artista, pasta e fila não mudaram. O servidor aceita `GET /playlists?trackhash=a,b` e devolve `has_track` em cada playlist (verdadeiro quando todas as faixas pedidas estão nela); sem a query a resposta é a mesma de antes.
- **"Open in files" abre o Files do ZimaOS.** Antes o servidor tentava abrir um gerenciador de arquivos dentro do container, onde não existe nenhum, e nada acontecia. Agora o servidor devolve o modelo da URL e a pasta (no caminho que o Files mostra) e o navegador de quem usa abre uma aba nova no Files, na pasta da música. O endereço usa o mesmo host por onde você abriu o MUSIX (IP de casa, IP da VPN ou domínio, sem a porta), então funciona em qualquer endereço em que o Files responda. Sem configuração, ou com pasta que não está no mapeamento, o app avisa em vez de ficar mudo.
- **Precisa configurar no ZimaOS:** as variáveis `MUSIX_HOST_PATHS` e `MUSIX_FILES_URL` no YAML do app (modelo em `deploy/zimaos-compose.yml`); o Watchtower recria o container com o YAML antigo, então o passo é manual.

## 3.7.0 (2026-10-23)

- **Playlist no celular: o número da faixa voltou, e é a alça para ordenar.** Nas telas pequenas a linha mostra o número (cabe até 4 dígitos). Ao **segurar o número por cerca de 350 ms** (com uma vibração curta, onde o aparelho permite) ele vira o ícone `drag` e a linha passa a seguir o dedo; ao soltar, a faixa fica na nova posição. Um toque, ou rolar a lista, continua funcionando como antes: mover mais de 8 px antes dos 350 ms cancela a espera e a lista rola. No Android o menu da faixa não abre mais com o toque longo no número. No desktop nada mudou (passar o mouse troca o número pelo ícone).
- O servidor aceita mover a faixa dizendo **depois de qual faixa ela vai** (`after_trackhash`), além da posição (`to_index`, que continua valendo). O cliente passou a usar a faixa de cima: uma playlist pode ter faixas que saíram da biblioteca, que a página não mostra, e a posição da página não é a da lista do servidor (a faixa ia parar no lugar errado).
- Ao ordenar, o cliente carrega a playlist inteira de uma vez (antes pedia "o resto" pela quantidade de linhas e, em playlists com faixa fora da biblioteca, repetia a última).
- "11 tracks" com espaço (era "11tracks") no cabeçalho da playlist e no card.
- **Ainda não entraram** (esperando o que só o Rodrigo pode dar): o ícone de check (`check.svg`) no submenu "Add to playlist" e o "Open in files" (falta o endereço do Files do ZimaOS).

## 3.6.2 (2026-10-21)

- **Albums e Artists não trocavam de lista.** As duas telas são o mesmo componente e, ao ir de uma para a outra pelo menu, ele era reaproveitado: o título mudava, mas a lista continuava a da tela anterior (e só carregava de verdade depois de rolar). Agora cada rota começa do zero. O mesmo vale para ir de uma playlist para outra (a página ficava na primeira) e para "Recently added" e "Recently played".
- Menu da faixa dentro de uma playlist: o item agora é "Remove From *nome da playlist*".
- Arrastar faixas: a linha de destino usa `neutral/500` a 15% e o ícone `drag` ficou com 16 px, com o mesmo espaço dos dois lados quando ele aparece no lugar do número.
- **A Home não quebra mais sem dados.** O servidor dava erro 500 na Home quando não havia nada tocado nem adicionado, e em "Recently played" quando nada tinha sido tocado; o cliente ficava com a Home em branco se a API falhasse. Agora a Home abre (vazia) e a lista de tocadas recentemente abre vazia.
- Só o cliente mudou de forma visível; o servidor só trata os dois casos de lista vazia.

## 3.6.1 (2026-10-21)

- O menu de contexto (botão direito) do card da playlist ganhou o **Delete**, em vermelho e por último, separado dos outros três itens por um divisor. Ele abre a mesma confirmação de excluir do menu dos três pontinhos.
- Só o cliente mudou: a versão sobe para disparar a build da imagem.

## 3.6.0 (2026-10-21)

- **Bug: a foto da playlist sumia.** Depois de enviar uma foto, a miniatura na página Playlists ficava quebrada e, ao reabrir a playlist, a foto não estava lá. A limpeza de imagens que roda depois de cada atualização estava com a comparação invertida: apagava a imagem e a miniatura das playlists e deixava os órfãos. Agora só apaga o que nenhuma playlist (de nenhum usuário) usa, e só dentro da pasta `playlist-img`, sem mexer em subpastas. **Uma playlist que já perdeu a imagem não volta** (o arquivo foi apagado): é preciso enviar a foto de novo. Imagens órfãs que já estão na pasta saem na próxima vez que alguma playlist for atualizada ou excluída.
- **Capa sempre quadrada.** A foto enviada é cortada no centro (GIF quadro a quadro) e a miniatura é de 250 x 250. A opção "Show square cover image" e o ajuste de posição saíram. Enviar um GIF não dá mais erro.
- **Página da playlist sem modal**, como a do álbum: o lápis ao lado do título troca o título por um campo (Enter salva, Esc ou sair do campo cancela; nome repetido avisa e o campo continua aberto); a foto se troca (ou se remove) no botão sobre a capa, como na foto do artista. Playlist nova, sem faixas e sem foto, mostra o placeholder dos artistas e as cores do design system, e não a tela preta. O "Edit | lixeira" do canto saiu (a lixeira foi para o menu).
- **Banner da playlist** com play, favoritar e três pontinhos (Play next, Add to queue, Pin/Unpin, Rename, Delete). Favoritar playlist é novo (fica nas configurações da própria playlist; ainda não aparece na página Favorites). O pin saiu do canto do banner e vive nos menus, com o ícone do Figma.
- **Menu de contexto no card da playlist** (botão direito): Pin/Unpin, Rename (no próprio card) e Add to queue.
- **Ordenar as faixas arrastando**: o número da faixa vira o ícone `drag` no hover (nas telas pequenas o ícone fica fixo no começo da linha, arraste por toque). A fila de reprodução segue a nova ordem sem parar a música. Fica desligado nas playlists especiais e com o filtro ativo.
- Servidor: `PUT /playlists/<id>/update` aceita `name`, `image` e `settings` opcionais (409 para nome repetido do mesmo usuário, 400 para nome vazio ou imagem inválida); novos `POST /playlists/<id>/favorite` e `POST /playlists/<id>/move-track`; `GET /playlists/<id>?limit=-1` passa a devolver todas as faixas (a última ficava de fora). `square_img` deixou de existir (o que já está no banco fica lá).
- Sem dependência nova; `vue-virtual-draglist`, que não era usada, saiu do cliente.

## 3.5.2 (2026-10-21)

- O ícone `ep-and-single` (Albums no menu lateral, "Go to album" e "Mark as EPs & Singles" nos menus) aparecia só como um círculo: a exportação SVG do Figma perdeu o anel interno. O SVG foi refeito a partir dos vetores do Figma (anel externo e anel interno, como um disco) e conferido pixel a pixel contra o screenshot do Figma. Os outros 39 ícones da pasta foram conferidos do mesmo jeito e batem.
- Só o cliente mudou: a versão sobe para disparar a build da imagem.

## 3.5.1 (2026-10-20)

- A seta dos itens com submenu, em todos os menus de contexto, passa a ser o `chevron-right` do Figma, em 10 x 10 px (a seta antiga tinha 8 x 12). O X de apagar o texto da busca ficou com 10 x 10 px (era 14 x 14).
- Só o cliente mudou: a versão sobe para disparar a build da imagem.

## 3.5.0 (2026-10-20)

- **Ícones do Figma em todo o app.** Os ícones do componente Icon (`src/assets/icons/figma/`) passam a ser os do app: Home, Quick scan (refresh), Settings, Delete (sempre em `error/300`), Add to Collection, Lyrics, Update album cover, volume (mudo, baixo e alto), lupa e Search on, favoritar (e favoritado em `error/300`), Logout, o menu do celular e o X da busca (14 x 14 px). Os ícones dos menus de contexto que existem no Figma (adicionar à fila, à playlist, tocar a seguir, renomear, marcar EPs/Soundtrack/Live) também. Os ícones antigos que ficaram sem uso saíram. Ícones que o Figma não tem (shuffle, repeat, play, pause e outros) continuam os do repositório.
- **Um vermelho só no app**: `error/300` do Figma (`#F7635C`). O token `--color-error-300` estava errado (`#ff7676`) e foi corrigido; `$red` e `$danger` leem o token, e os outros vermelhos soltos (`$pink`, o do aviso de erro e o da tela de contas) viraram o mesmo.
- **Menu do usuário** (foto no canto superior direito) no padrão dos menus de contexto: ícone à esquerda, texto depois, mesmas medidas e cores (tokens `--menu-*`). Mesmas funções e ordem: saudação, Quick scan, Settings e Log out.
- **Barra do player** (acima de 900 px): a miniatura do álbum fica sempre à esquerda e leva à página do álbum que está tocando; depois vêm o nome da música, o favoritar e o novo botão de adicionar (menu com "Add to queue" e "Add to playlist"), com 14 px entre cada um. O grupo da direita ficou letras e volume. O hover dos botões da barra é só o preenchimento, sem borda. Até 900 px nada muda de lugar.
- "Remove from queue" (menu da música na tela Now Playing) com ícone `delete` do Figma e o texto com q minúsculo.
- O item "Settings" saiu do painel lateral esquerdo (continua no menu do usuário).
- Só o cliente mudou: a versão sobe para disparar a build da imagem.

## 3.4.2 (2026-10-20)

- **Controles do player** (acima de 900 px) mais discretos: shuffle, anterior, play/pause, próxima e repeat com glifo de 18 px de altura (anterior e próxima 18 x 18). A escala de 1,2 da linha de botões saiu e o play/pause não é mais maior que os outros.
- **Botões da barra inferior** com hover redondo (raio de 400 px, círculo ou pílula). O favoritar do grupo da direita perdeu a borda retangular: só o ícone, como o microfone e o volume. O espaço entre microfone, favoritar e volume é de 4 px.
- Só o cliente mudou: a versão sobe para disparar a build da imagem.

## 3.4.1 (2026-10-20)

- **Margem lateral única de 16 px** no painel principal, dos dois lados e em todas as larguras: a mesma do painel da esquerda e da barra inferior. Um token só (`--layout-gutter`, em `_musix-tokens.scss`) alimenta o topo, as páginas e o painel da esquerda; o `clamp` de porcentagem que dava 32 px ou 80 px sumiu. Em telas largas o conteúdo ganha 128 px e o número de cards por linha pode subir. O layout alternativo e as telas de até 900 px não mudam.
- **Controles do player** (acima de 900 px): shuffle, anterior, play/pause, próxima e repeat no centro, com o tempo atual, a barra de progresso e o tempo total embaixo; o grupo da direita ficou letras, favorito e volume. O volume virou um controle horizontal sempre aberto ao lado do alto-falante (até 900 px continua o popover). Anterior e próxima usam os ícones `play-previous` e `play-next` do Figma. O microfone das letras ficou 6,5% menor. Nas telas de até 900 px nada mudou de lugar.
- Registro do que foi publicado **sem subir a versão** (só cliente), antes da 3.4.0: menu lateral com Albums e Artists, Home sem Browse Library, busca do topo centralizada e ícone de letras trocado (`d1f2800`); e a busca do topo sem sobrepor as abas da busca, com os menus de contexto responsivos no toque (`841ffc1`).
- Só o cliente mudou: a versão sobe para disparar a build da imagem.

## 3.4.0 (2026-10-19)

- **Renomear o álbum**, na página do álbum (só admin): o lápis ao lado do título abre o diálogo com prévia, e o título novo é gravado na tag `ALBUM` de todos os arquivos do álbum, de forma segura (cópia temporária, conferência depois de escrever, só a tag do álbum muda). O hash do álbum e os das faixas mudam junto, e favoritos, plays, playlists, coleções, tipo do álbum, cores e miniaturas acompanham. Se o título novo é o de outro álbum dos mesmos artistas, os dois viram um. Trocar só maiúsculas ou espaços muda a tag e não muda o hash. Arquivos sem a tag `ALBUM` não são tocados (a tag nunca é criada).
- Servidor: `POST /album/<albumhash>/rename/preview`, `POST /album/<albumhash>/rename` e `GET /album/rename/status`. Só um renomear (de artista ou de álbum) roda por vez no app inteiro. Cada arquivo gravado entra em `rename-journal.jsonl` com `"action": "rename-album"`.
- O que o renomear artista e o renomear álbum dividem foi para `lib/renamecommon.py` (estado do job e trava, atualização dos hashes e recarga dos stores); o renomear artista continua igual. O diálogo do cliente também é um só (`RenameDialog.vue`), usado pelo artista e pelo álbum.
- Não há dependência nova.

## 3.3.5

- Menu das músicas: "Play next" passa para o mesmo grupo de "Add to queue" e "Add to Playlist" (sem divisor entre eles). Só o cliente mudou: a versão sobe para disparar a build da imagem.

## 3.3.4

- Menu de contexto das músicas no desenho do protótipo (Figma): 232 px de largura, ícones novos (álbum, pasta e artista incluídos), itens em grupos separados por divisores finos (Play next; fila e playlist; ir para álbum, pasta e artista; abrir nos arquivos; Rename só para admin; Search on). "Remove from playlist" e "Remove from queue" continuam vermelhos e no topo, num grupo próprio. O menu de artista e o de playlist não mudam. Só o cliente mudou: a versão sobe para disparar a build da imagem.

## 3.3.3

- Lápis do Rename (menu da faixa) e dos botões de editar o nome e a foto do artista trocado pelo lápis de contorno do Figma, em 18 x 18. No menu da faixa só o item Rename muda de tamanho; o texto fica no mesmo ponto e os outros ícones não mudam. O lápis da página de coleção continua o antigo. Só o cliente mudou: a versão sobe para disparar a build da imagem.

## 3.3.2

- Menu de contexto (todos os menus) com as cores e medidas do design system do Figma (`src/assets/scss/_musix-tokens.scss`): fundo `#222222`, texto `#ECECEC`, item selecionado azul `#1267B7` com texto branco e ícone cinza, raio e sombra do protótipo. Menu do álbum com 10 px de espaço acima e abaixo de cada divisor, para o hover não encostar na linha. Larguras e disposição dos menus de faixa, artista e playlist não mudam; itens críticos continuam no vermelho do app. Só o cliente mudou: a versão sobe para disparar a build da imagem.

## 3.3.1

- Menu do álbum no desenho do protótipo (Figma): ícones novos, itens em grupos separados por divisores finos (reprodução e listas; capa; marcação; "Search on") e seta de submenu nova em todos os menus. O menu do álbum fica com 232 px de largura; os menus de faixa, artista e playlist mantêm tamanho, ícones e ordem. Só o cliente mudou: a versão sobe para disparar a build da imagem.

## 3.3.0

Renomear um artista em todos os arquivos, e atualização automática opcional.

- **Rename artist** (lápis ao lado do nome, na página do artista, só admin): digite o nome novo, veja a **prévia** (quantas faixas e álbuns, faixas em que o artista só participa de álbum de outro, arquivos que serão renomeados, formatos sem suporte, conflitos de nome, arquivos sem permissão, se o nome novo já existe e os dois serão juntados) e confirme. Roda em segundo plano, arquivo por arquivo, com barra de progresso; um arquivo que falha não derruba os outros e fica com o nome antigo.
- Regra das tags com vários artistas: a troca é **por elemento** (nunca por texto: renomear "Stones" não mexe em "Rolling Stones"), os outros nomes, a ordem e o separador ficam como estavam, e `ALBUMARTIST` só muda nos arquivos cujo `ALBUMARTIST` tem o artista. Tag que o arquivo não tinha nunca é criada. Cada arquivo é conferido depois de gravado; se algo não bate, o original fica intacto. Se o nome novo já estava na mesma tag, os dois viram um só (aparece destacado na prévia).
- Participação só no título ("(feat. X)" ou "[ft. X]"): o título muda e o arquivo é renomeado, como no Rename de faixa.
- Hashes do artista, dos álbuns e das faixas são trocados em favoritos, reproduções, playlists, coleções, cores, artistas parecidos, marcações de álbum, fotos do artista (inclusive a marca de foto manual) e miniaturas de capa. O artista só muda de hash se **todos** os arquivos foram gravados; se algum falhou, ele continua existindo com o nome antigo.
- Cada arquivo gravado acrescenta uma linha em `rename-journal.jsonl` (mesmo arquivo do Rename de faixa).
- `deploy/watchtower-compose.yml`: app opcional para o ZimaOS que atualiza o MUSIX sozinho quando sai imagem nova.
- 3.2.1 (correção): `mutagen` faltava no `requirements.txt` e a imagem não abria.

## 3.2.0

Primeira versão que **escreve nos arquivos de música**. Toda escrita passa por um helper único (`src/musix/lib/tagwriter.py`): copia o arquivo para um temporário na mesma pasta, altera a cópia, relê com mutagen e com o leitor do app (tinytag), confere que só o pedido mudou e só então troca o original (`os.replace`). Qualquer falha apaga o temporário e deixa o original intacto. Formatos: MP3, FLAC, M4A/MP4, OGG/Opus; outros dão "unsupported format" sem tocar no arquivo.

- **Save cover to files** (menu do álbum, só admin): grava a capa da pasta (`cover.jpg`, `folder.jpg`...) como capa embutida em todas as músicas do álbum. Falha numa faixa não impede as outras. Nada é criado ou renomeado na pasta.
- **Rename** (menu da faixa, só admin): o título da tela, o da tag e o nome do arquivo passam a ser o mesmo texto. Caracteres que o Windows não aceita viram `_` só no nome do arquivo (a tag guarda o texto digitado); nome já existente na pasta dá erro 409 e nada muda. Um "(feat. X)" do título antigo vai para a tag de artista. Favoritos, reproduções, playlists e coleções acompanham a faixa para o hash novo (`rekey_hash`).
- Cada renomeação acrescenta uma linha em `rename-journal.jsonl` na pasta de configuração, para desfazer à mão se precisar (não é backup do áudio).
- Se `ALBUMARTIST` não existe e o artista da faixa cresce (por causa do "(feat. X)"), o `ALBUMARTIST` é gravado com o artista antigo, para o álbum não mudar de dono (o app deduz o dono do álbum pelo artista).

## 3.1.0

Limpeza, classificação manual de álbuns e foto do artista. Nada nesta versão escreve nos arquivos de música.

- Só inglês: o seletor de idioma e as traduções (italiano, coreano, chinês) saíram.
- Removido o pareamento com o celular (`/auth/getpaircode`, `/auth/pair`).
- Removida a conexão do Last.fm com a conta (rotas de sessão, envio de scrobble, tela de configuração). O registro local de reproduções, usado pela página de Stats, continua. Chaves antigas no `settings.json` (como `lastfmSessionKeys` e `showAlbumsAsSingles`) são ignoradas sem erro.
- Álbuns **não são mais classificados sozinhos** como single, EP, trilha sonora ou ao vivo (a regra errava, por exemplo, "Heaven and Hell"). A detecção de compilação continua automática. A opção "Mark albums with one track as singles" saiu.
- Marcação manual no menu (...) do álbum: *Mark as EPs & Singles*, *Mark as Soundtrack*, *Mark as Live album* (e *Remove from ...*). Vale uma marca por álbum, guardada na tabela nova `album_type_override`. A página do artista e a discografia ganharam as seções **Soundtracks** e **Live**, que só aparecem quando há álbuns marcados.
  - Atenção: a marca fica ligada ao `albumhash`, que depende do título e do artista da tag. Se esses campos mudarem, a marca se perde.
- Foto do artista: lápis na página do artista (só admin) para enviar uma foto do computador (JPEG, PNG ou WEBP, até 10 MB) ou buscar a automática de novo. Foto enviada é marcada como manual e a busca automática nunca a substitui.
- Ícones nos itens do menu do álbum.

## 3.0.0

Versão base do MUSIX: renomeação a partir do Swing Music, ícone provisório e botões para atualizar a capa dos álbuns.
