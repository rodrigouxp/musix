# Histórico de versões

A versão do MUSIX fica em [`version.txt`](version.txt) (fonte única). É o número que aparece em **Settings > About** e no rodapé do menu. Cada entrega publicada sobe a versão e ganha uma seção neste arquivo, com a data e um resumo curto.

O cliente web (`musix-webclient`) não tem número próprio: ele é empacotado junto com o servidor na imagem Docker.

## Regra de versões

Formato MAIOR.MENOR.CORREÇÃO, lido de `version.txt`:

- **MENOR sobe** (e a CORREÇÃO volta a 0) quando a entrega traz um recurso novo que o usuário percebe e que não existia, ou muda um comportamento de forma relevante.
- **CORREÇÃO sobe** em bug, ajuste visual, de ícone ou de texto, responsividade, refatoração e mudança só de cliente sem recurso novo.
- **MAIOR** só em mudança grande ou incompatível (formato do banco, quebra de API, migração manual) ou ao acompanhar um MAIOR do upstream. Quem decide é o Rodrigo.
- **Toda entrega publicada sobe a versão**, uma por prompt, na ordem em que é publicada (o app mostra a versão que está rodando).

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
