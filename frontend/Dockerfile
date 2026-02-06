# # Frontend Dockerfile for Production Build

# # Stage 1: Build Angular application
# FROM node:20-alpine AS build

# WORKDIR /app

# # Copy package files
# COPY package*.json ./

# # Install dependencies
# RUN npm ci --only=production

# # Copy source code
# COPY . .

# # Build production bundle
# RUN npm run build:prod

# # Stage 2: Serve with nginx
# FROM nginx:alpine

# # Copy nginx configuration
# COPY nginx.conf /etc/nginx/nginx.conf

# # Copy built application from build stage
# COPY --from=build /app/dist/chatbot-frontend /usr/share/nginx/html

# # Expose port 80
# EXPOSE 80

# # Start nginx
# CMD ["nginx", "-g", "daemon off;"]


# Frontend Dockerfile for Production Build

# Stage 1: Build Angular application
FROM node:20-alpine AS build

WORKDIR /app

# Copy package files
COPY package*.json ./

# Install all dependencies (including devDependencies needed for build)
# Use npm install if package-lock.json doesn't exist, otherwise use npm ci
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi

# Copy source code
COPY . .

# Build production bundle
RUN npm run build:prod

# Stage 2: Serve with nginx
FROM nginx:alpine

# Copy nginx configuration
COPY nginx.conf /etc/nginx/nginx.conf

# Copy built application from build stage
COPY --from=build /app/dist/chatbot-frontend /usr/share/nginx/html

# Expose port 80
EXPOSE 80

# Start nginx
CMD ["nginx", "-g", "daemon off;"]