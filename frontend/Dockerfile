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
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
