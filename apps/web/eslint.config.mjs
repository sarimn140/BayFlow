// ESLint 9 flat config (spec 12 §1.2). Next 16 removed `next lint`; the script is
// `eslint . --max-warnings 0` (D80).
import { defineConfig, globalIgnores } from 'eslint/config'
import nextVitals from 'eslint-config-next/core-web-vitals'
import nextTs from 'eslint-config-next/typescript'
import prettier from 'eslint-config-prettier/flat'

const eslintConfig = defineConfig([
  ...nextVitals, // Next + React + React Hooks + jsx-a11y
  ...nextTs, // typescript-eslint recommended
  prettier, // turn off rules that fight Prettier
  {
    rules: {
      '@typescript-eslint/no-explicit-any': 'error',
      'no-console': ['error', { allow: ['warn', 'error'] }],
      'no-restricted-syntax': [
        'error',
        {
          selector: "CallExpression[callee.name='fetch']",
          message: 'Use the typed API client in src/lib/api (D50).',
        },
      ],
    },
  },
  // The API client module is the only code that talks to /api/* (D50).
  { files: ['src/lib/api/**'], rules: { 'no-restricted-syntax': 'off' } },
  globalIgnores([
    '.next/**',
    'out/**',
    'build/**',
    'coverage/**',
    'next-env.d.ts',
    // Generated from the API's OpenAPI document (D76) — never edited by hand.
    'src/lib/api/schema.d.ts',
  ]),
])

export default eslintConfig
