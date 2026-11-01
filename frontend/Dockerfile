FROM node:20-alpine

WORKDIR /app

COPY package.json .npmrc ./
RUN npm install

COPY . .

EXPOSE 5178

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
