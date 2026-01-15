/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  reactStrictMode: true,
  typescript: {
    // Allow production builds to complete even with type errors
    ignoreBuildErrors: false,
  },
  eslint: {
    // Allow production builds to complete even with lint errors
    ignoreDuringBuilds: false,
  },
}

module.exports = nextConfig
