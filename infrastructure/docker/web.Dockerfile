FROM node:22-alpine
WORKDIR /app
COPY packages ./packages
COPY apps/web ./apps/web
WORKDIR /app/apps/web
RUN npm install
EXPOSE 5173
CMD ["npm", "run", "dev"]
