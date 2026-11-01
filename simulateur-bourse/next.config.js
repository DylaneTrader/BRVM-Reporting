/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Ne pas bundler xlsx côté serveur (lecture de fichiers natifs)
  serverExternalPackages: ["xlsx"],
};

module.exports = nextConfig;
