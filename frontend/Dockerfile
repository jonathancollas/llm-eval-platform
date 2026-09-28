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

# server.js only serves client files that sit next to it. `next build`
# leaves those chunks in .next/static, so the standalone process 404s
# every /_next/static/* request and the UI never hydrates.
RUN mkdir -p .next/standalone/.next \
 && cp -a .next/static .next/standalone/.next/static \
 && if [ -d public ]; then cp -a public .next/standalone/public; fi

RUN addgroup -S appgroup && adduser -S appuser -G appgroup

USER appuser

EXPOSE 3000
CMD ["node", ".next/standalone/server.js"]
