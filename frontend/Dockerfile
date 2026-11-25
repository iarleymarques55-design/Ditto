# Painel do Ditto: o Vite gera os arquivos estáticos e o nginx serve.
# O contexto do build é a raiz do repositório, porque a imagem também empacota a pasta
# extension/ para o download da página "Extensão":
#   docker build -f frontend/Dockerfile .
FROM node:24-alpine AS build
WORKDIR /app

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund --loglevel=error

COPY frontend/ .
# As variáveis VITE_ entram no código na hora do build: mudar o endereço da API pede um build novo
ARG VITE_API_URL
ARG VITE_GOOGLE_CLIENT_ID
RUN npm run build

# A extensão já configurada para este painel, num .zip. Sem as três variáveis, o build continua
# sem o arquivo e a página "Extensão" avisa que o download não está disponível
FROM node:24-alpine AS extensao
RUN apk add --no-cache zip
WORKDIR /pacote
COPY extension/ /fonte/extension/
COPY frontend/scripts/empacotar-extensao.mjs ./
ARG VITE_API_URL
ARG VITE_RELE_URL
ARG PAINEL_URL
RUN mkdir -p /saida/downloads \
    && node empacotar-extensao.mjs /fonte/extension /pacote \
    && if [ -d /pacote/ditto-extensao ]; then \
        cd /pacote && zip -qr /saida/downloads/ditto-extensao.zip ditto-extensao; \
    fi

FROM nginx:1.27-alpine
# O endereço da API também entra na política de segurança (CSP): o painel só conversa com ela
ARG VITE_API_URL
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY frontend/nginx-seguranca.conf /etc/nginx/snippets/seguranca.conf
RUN case "$VITE_API_URL" in \
        http://*|https://*) origem=$(printf '%s' "$VITE_API_URL" | sed -E 's#^(https?://[^/]+).*#\1#') ;; \
        *) origem="" ;; \
    esac \
    && sed -i "s#__ORIGEM_DA_API__#${origem}#" /etc/nginx/snippets/seguranca.conf \
    && nginx -t
COPY --from=build /app/dist /usr/share/nginx/html
COPY --from=extensao /saida/ /usr/share/nginx/html/
EXPOSE 80
