export default {
  port: 3000,
  api_port: 3000,
  protocol: process.env.SECURE === "true" ? "https" : "http",
  host: process.env.HOST || '0.0.0.0',
  api_host: process.env.API_HOST || '0.0.0.0',
  environment: process.env.NODE_ENV || 'development',
  env: process.env.NODE_ENV || 'development',
  isDevelopment: () => process.env.NODE_ENV === 'development',
  isProduction: () => process.env.NODE_ENV === 'production'
};