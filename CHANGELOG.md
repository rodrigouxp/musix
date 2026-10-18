# Histórico de versões

A versão do MUSIX fica em [`version.txt`](version.txt) (fonte única). É o número que aparece em **Settings > About** e no rodapé do menu. A cada conjunto de mudanças:

1. sobe o número em `version.txt` (mudança com recurso novo sobe o do meio: 3.1.0 → 3.2.0; só correção sobe o último: 3.1.0 → 3.1.1);
2. acrescenta uma seção neste arquivo, com o que mudou;
3. o commit que sobe a versão diz isso na mensagem (`chore: versão 3.2.0`).

O cliente web (`musix-webclient`) não tem número próprio: ele é empacotado junto com o servidor na imagem Docker.

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
