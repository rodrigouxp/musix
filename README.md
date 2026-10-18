<div align="center" style="display: flex; justify-content: center; align-items: center;">
  <img src='.github/images/logo-fill.light.svg' style="height: 4rem">
</div>
<div align="center" style="font-size: 2rem"><b>MUSIX</b></div>

##

MUSIX é um servidor de streaming de música para rodar em casa. Como um Spotify mais simples, mas com a sua própria música: aponte para as pastas, abra no navegador e ouça.

## Recursos

- **Normalização de metadados** - uma biblioteca limpa e consistente
- **Versões de álbum** - álbuns normalizados e associados a rótulos de versão (Deluxe, Remaster etc.)
- **Artistas e álbuns relacionados**
- **Visão por pastas** - navegue pela biblioteca pelas pastas
- **Interface web**
- **Detecção de silêncio** - combina crossfade com detecção de silêncio
- **Coleções** - agrupe álbuns e artistas
- **Estatísticas** - dados sobre o que você ouve
- **Vários usuários**
- **Classificação manual de álbuns** - marque à mão EPs & Singles, trilhas sonoras e álbuns ao vivo (nada é adivinhado pelo título)
- **Foto do artista** - envie uma do computador ou busque a automática de novo
- **Editar arquivos com segurança** - renomear faixa (tag e nome do arquivo iguais) e gravar a capa nas músicas; toda escrita usa arquivo temporário e conferência, e o original só é trocado se tudo bater
- **Capas** - a capa vem da imagem da pasta (`cover.jpg`, `folder.jpg`...) ou da arte embutida, e pode ser atualizada pelo menu do álbum ou em Settings > Library > Albums

## Instalação

### Docker Compose

```yaml
services:
  musix:
    image: ghcr.io/rodrigouxp/musix:dev
    container_name: musix
    ports:
      - "1970:1970"
    volumes:
      - /caminho/da/musica:/music
      - /caminho/da/config:/config
    restart: unless-stopped
```

A interface abre em <http://localhost:1970>. Para outra porta, troque o mapeamento em `ports`.

No ZimaOS há um arquivo pronto em [`deploy/zimaos-compose.yml`](deploy/zimaos-compose.yml).

### Docker CLI

```sh
docker pull ghcr.io/rodrigouxp/musix:dev
docker run --name musix -p 1970:1970 -v /caminho/da/musica:/music -v /caminho/da/config:/config --restart unless-stopped ghcr.io/rodrigouxp/musix:dev
```

### Atualização automática (opcional)

Para não precisar de `sudo docker pull` a cada versão, instale o Watchtower como um app a parte: cole [`deploy/watchtower-compose.yml`](deploy/watchtower-compose.yml) em ZimaOS > Install Custom App. Ele confere a cada 15 minutos se há imagem nova do MUSIX e recria só o container `musix` (portas e pastas continuam as mesmas). O MUSIX não faz isso sozinho porque dentro do container ele não tem acesso ao Docker.

### Opções

Flags podem ser passadas ao iniciar o app no terminal (`python -m musix -h` lista todas). As principais variáveis de ambiente são `MUSIX_PORT`, `MUSIX_CONFIG_DIR` e `MUSIX_CLIENT_DIR`.

Quando o cliente web é informado com `--client` (ou `MUSIX_CLIENT_DIR`), o servidor usa a pasta como está: não compara versões e não baixa nada.

### Dados de versões anteriores

Na primeira execução, uma pasta de dados criada com o nome antigo (`swingmusic` ou `.swingmusic`) é renomeada para `musix` (ou `.musix`), junto com o banco (`swingmusic.db` vira `musix.db`). Nada é apagado.

## Versões

O histórico de cada versão está em [`CHANGELOG.md`](CHANGELOG.md). O número fica em `version.txt` e aparece em Settings > About.

## Origem

MUSIX é baseado no [Swing Music](https://github.com/swingmx/swingmusic), com modificações. O código do servidor segue a licença **AGPL-3.0**; o texto completo está no arquivo [`LICENSE`](LICENSE), com o aviso de copyright original. O cliente web, também baseado no projeto original, tem a própria licença (MIT) no repositório [musix-webclient](https://github.com/rodrigouxp/musix-webclient).

O histórico do git preserva a autoria do projeto original e de seus colaboradores.

## Desenvolvimento

O servidor é Python (Flask); o cliente fica em outro repositório ([musix-webclient](https://github.com/rodrigouxp/musix-webclient)). Veja [`.github/contributing.md`](.github/contributing.md).
