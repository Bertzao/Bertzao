# Rocinha Cousins

Site do [@rocinhacousins](https://instagram.com/rocinhacousins) — tour privado
pela Rocinha guiado por dois primos nascidos e criados na comunidade.

O trabalho do site é um só: transformar quem chega de um Reels do Instagram em
uma conversa no WhatsApp pedindo reserva.

## Estrutura

```
index.html    o site inteiro, em um arquivo
fotos/        as fotos usadas na página, em WebP
share.jpg     imagem de preview quando o link circula no WhatsApp
originais/    os JPEG originais, preservados (não são carregados pelo site)
```

É um site estático: sem servidor, sem banco, sem build. Abrir o `index.html`
no navegador já mostra a página.

## Publicar

Arrastar a pasta (menos `originais/`) para o Netlify, Cloudflare Pages, Vercel
ou GitHub Pages. Não separar o `index.html` da pasta `fotos`.

## Idiomas

A página é traduzida em inglês, espanhol, francês e português, e detecta o
idioma do navegador. As traduções ficam no objeto `T`, no final do arquivo.

O tour em si é guiado em inglês, espanhol e português — a versão em francês
existe para leitura, e a página diz isso.
