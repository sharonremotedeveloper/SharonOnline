import nextCoreWebVitals from "eslint-config-next/core-web-vitals";

const config = [
  ...nextCoreWebVitals,
  {
    rules: {
      "@next/next/no-img-element": "off",
      "react/no-unescaped-entities": "off",
      // New in eslint-plugin-react-hooks 7 (React Compiler heuristics). The flagged "reset state when an input changes"
      // effects are long-standing, working patterns (data loaders, timers); refactoring 16 screens is not part of the
      // framework upgrade. Revisit if/when the React Compiler is adopted.
      "react-hooks/set-state-in-effect": "off",
      // Deliberate hard navigations: on session end / logout we want a full reload so no in-memory user state survives.
      "@next/next/no-location-assign-relative-destination": "off",
    },
  },
  { ignores: [".next/**", ".test-build/**", "node_modules/**", "scripts/**", "next-env.d.ts", "src/types/api.generated.ts"] },
];

export default config;
