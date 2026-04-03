FROM node:20-alpine AS base

WORKDIR /app
COPY package.json ./
RUN npm install

COPY . .

ENV NEXT_PUBLIC_API_URL=http://localhost:8000/api
ENV NEXT_TELEMETRY_DISABLED=1

RUN npm run build

EXPOSE 3000
CMD ["npm", "start"]
