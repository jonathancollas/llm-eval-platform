FROM node:20-alpine AS base

WORKDIR /app
COPY package.json ./
RUN npm install
COPY . .

ARG NEXT_PUBLIC_API_URL=https://llm-eval-backend-kqlh.onrender.com/api
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
ENV NEXT_TELEMETRY_DISABLED=1

RUN npm run build

EXPOSE 3000
CMD ["npm", "start"]
