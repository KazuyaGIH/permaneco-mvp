FROM node:20.19.2-alpine

WORKDIR /app
ARG API_ORIGIN
ENV API_ORIGIN=${API_ORIGIN}
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

ENV NODE_ENV=production
EXPOSE 3000
CMD ["sh", "-c", "npm run start -- --hostname 0.0.0.0 --port ${PORT:-3000}"]
