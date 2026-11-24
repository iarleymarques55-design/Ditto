# Painel do Ditto: o Vite gera os arquivos estáticos e o nginx serve.
FROM node:24-alpine AS build
WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund --loglevel=error

COPY . .
# As variáveis VITE_ entram no código na hora do build: mudar o endereço da API pede um build novo
ARG VITE_API_URL
ARG VITE_GOOGLE_CLIENT_ID
RUN npm run build

FROM nginx:1.27-alpine
# O endereço da API também entra na política de segurança (CSP): o painel só conversa com ela
ARG VITE_API_URL
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY nginx-seguranca.conf /etc/nginx/snippets/seguranca.conf
RUN case "$VITE_API_URL" in \
        http://*|https://*) origem=$(printf '%s' "$VITE_API_URL" | sed -E 's#^(https?://[^/]+).*#\1#') ;; \
        *) origem="" ;; \
    esac \
    && sed -i "s#__ORIGEM_DA_API__#${origem}#" /etc/nginx/snippets/seguranca.conf \
    && nginx -t
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
