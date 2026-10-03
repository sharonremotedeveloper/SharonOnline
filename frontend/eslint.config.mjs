import nextCoreWebVitals from "eslint-config-next/core-web-vitals";

const config = [
  ...nextCoreWebVitals,
  {
    rules: {
      "@next/next/no-img-element": "off",
      "react/no-unescaped-entities": "off",
    },
  },
  { ignores: [".next/**", ".test-build/**", "node_modules/**", "scripts/**", "next-env.d.ts", "src/types/api.generated.ts"] },
];

export default config;
