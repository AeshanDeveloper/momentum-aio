const mongodbUri = process.env.MONGODB_URI?.trim();

export default {
  development: {
    client: "mongodb",
    connection: {
      url: mongodbUri,
      database: process.env.MONGODB_DB?.trim() || undefined,
    },
  },
  production: {
    client: "mongodb",
    connection: {
      url: mongodbUri,
      database: process.env.MONGODB_DB?.trim() || undefined,
    },
  },
};
