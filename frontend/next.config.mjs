// Mock/fixture mode is a local-development convenience. A production build (or `next start`) with it enabled would
// ship fabricated data and fake logins to real users, so refuse outright.
if (process.env.NODE_ENV === 'production' && process.env.NEXT_PUBLIC_USE_MOCKS === 'true') {
  throw new Error(
    'NEXT_PUBLIC_USE_MOCKS=true is not allowed in a production build. Unset it (it only exists for `npm run dev`).'
  );
}

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  images: {
    remotePatterns: [
      {
        protocol: 'https',
        hostname: 'images.unsplash.com',
      },
      {
        protocol: 'https',
        hostname: 'assets.sharonesl.com',
      },
      {
        protocol: 'https',
        hostname: 'cloudflarestream.com',
      },
      {
        protocol: 'https',
        hostname: '**.r2.dev',
      },
      {
        protocol: 'https',
        hostname: '**.r2.cloudflarestorage.com',
      }
    ],
  },
};

export default nextConfig;
