FROM node:20-alpine AS base
WORKDIR /app

# Install dependencies
COPY package*.json ./
RUN npm ci

# Build
COPY . .
ARG NEXT_PUBLIC_API_URL=http://localhost:8000/api
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build
RUN mkdir -p .next/standalone/.next && cp -r .next/static .next/standalone/.next/static

RUN addgroup -S appgroup && adduser -S appuser -G appgroup

USER appuser

EXPOSE 3000
CMD ["sh", "-c", "HOSTNAME=0.0.0.0 PORT=${PORT:-3000} node .next/standalone/server.js"]
