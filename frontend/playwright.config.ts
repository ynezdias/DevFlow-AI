import {defineConfig} from '@playwright/test'
export default defineConfig({testDir:'./tests', workers:1, use:{baseURL:process.env.DASHBOARD_URL || 'http://host.docker.internal:5173', launchOptions:{executablePath:'/usr/bin/chromium',args:['--no-sandbox']}}})
