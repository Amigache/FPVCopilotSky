import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.js'],
    testTimeout: 60000,
    hookTimeout: 60000,
    teardownTimeout: 10000,
    coverage: {
      provider: 'v8',
      reporter: ['text', 'json', 'html', 'lcov'],
      exclude: ['node_modules/', 'src/test/', '**/*.config.js', '**/dist/**'],
      // Progressive baseline (measured ~41.3/74.4/51.7). Raise as coverage grows.
      thresholds: {
        statements: 40,
        branches: 70,
        functions: 49,
        lines: 40,
      },
    },
    // Reduce memory usage for embedded systems
    pool: 'threads',
    poolOptions: {
      threads: {
        singleThread: false,
      },
    },
    maxConcurrency: 2,
    minWorkers: 1,
    maxWorkers: 2,
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
})
