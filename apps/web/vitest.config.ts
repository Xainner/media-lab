import { defineConfig } from 'vitest/config'
import web from './vite.config'
export default defineConfig({
 ...web,
 test: {environment:'jsdom', environmentOptions:{jsdom:{url:'http://localhost/'}},include:['src/**/*.test.tsx','src/**/*.test.ts'],maxWorkers:1,setupFiles:['src/test-setup.ts']},
})
