// Mock/fixture mode is a local-development convenience. A production build (or `next start`) with it enabled would
// ship fabricated data and fake logins to real users, so refuse outright.
if (process.env.NODE_ENV === 'production' && process.env.NEXT_PUBLIC_USE_MOCKS === 'true') {
  throw new Error(
    'NEXT_PUBLIC_USE_MOCKS=true is not allowed in a production build. Unset it (it only exists for `npm run dev`).'
  );
}

/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  reactStrictMode: true,
  // Do not advertise the framework to every visitor.
  poweredByHeader: false,
  async headers() {
    // One-time reset / verification links carry their credential in the URL: never leak it through the Referer header.
    const noReferrer = [{ key: 'Referrer-Policy', value: 'no-referrer' }, { key: 'Cache-Control', value: 'no-store' }];
    // Baseline hardening for every page. A Content-Security-Policy is deliberately not set here yet: it needs a
    // nonce and a test pass against Daily, PayPal and PayFast first.
    // Camera/microphone: this header is the ceiling for every iframe, and the classroom runs inside Daily's iframe on
    // https://<domain>.daily.co. With only `(self)` the browser refused Daily the devices and the join hung on
    // "Connecting to Live Stage" (2026-10-16). Name Daily's origins explicitly; the wildcard covers other Daily domains.
    const dailyOrigins = '"https://topscholaracademy.daily.co" "https://*.daily.co"';
    const baseline = [
      { key: 'X-Content-Type-Options', value: 'nosniff' },
      { key: 'X-Frame-Options', value: 'DENY' },
      { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
      {
        key: 'Permissions-Policy',
        value: `camera=(self ${dailyOrigins}), microphone=(self ${dailyOrigins}), display-capture=(self ${dailyOrigins}), `
          + 'geolocation=(), payment=(self)',
      },
      ...(process.env.NODE_ENV === 'production'
        ? [{ key: 'Strict-Transport-Security', value: 'max-age=31536000; includeSubDomains' }]
        : []),
    ];
    return [
      { source: '/:path*', headers: baseline },
      { source: '/reset-password', headers: noReferrer },
      { source: '/verify-email', headers: noReferrer },
    ];
  },
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
