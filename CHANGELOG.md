# Histórico de versões

A versão do MUSIX fica em [`version.txt`](version.txt) (fonte única). É o número que aparece em **Settings > About** e no rodapé do menu. Cada entrega publicada sobe a versão e ganha uma seção neste arquivo, com a data e um resumo curto.

O cliente web (`musix-webclient`) não tem número próprio: ele é empacotado junto com o servidor na imagem Docker.

## Regra de versões

Formato MAIOR.MENOR.CORREÇÃO, lido de `version.txt`:

- **MENOR sobe** (e a CORREÇÃO volta a 0) quando a entrega traz um recurso novo que o usuário percebe e que não existia, ou muda um comportamento de forma relevante.
- **CORREÇÃO sobe** em bug, ajuste visual, de ícone ou de texto, responsividade, refatoração e mudança só de cliente sem recurso novo.
- **MAIOR** só em mudança grande ou incompatível (formato do banco, quebra de API, migração manual) ou ao acompanhar um MAIOR do upstream. Quem decide é o Rodrigo.
- **Toda entrega publicada sobe a versão**, uma por prompt, na ordem em que é publicada (o app mostra a versão que está rodando).

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
