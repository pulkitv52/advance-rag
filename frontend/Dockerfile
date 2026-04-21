# Use the official Node.js 20 image
FROM node:20-slim AS base

# Install pnpm
RUN npm install -g pnpm

WORKDIR /app

# Copy package files
COPY package.json pnpm-lock.yaml* ./

# Install dependencies
RUN pnpm install

# Copy the rest of the application
COPY . .

# Expose the Vite port
EXPOSE 5173

# Set environment variables
ENV NODE_ENV=development

# Start Vite with the --host flag to allow external connections
CMD ["pnpm", "dev", "--host", "0.0.0.0"]
