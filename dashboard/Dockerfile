FROM node:24-alpine
WORKDIR /app
COPY dashboard/package*.json ./
RUN npm ci
COPY dashboard/ ./
ARG LAB_API_URL=http://api:8810
ENV LAB_API_URL=$LAB_API_URL NEXT_TELEMETRY_DISABLED=1
RUN npm run build
CMD ["npx","next","start","--hostname","0.0.0.0","--port","3310"]
