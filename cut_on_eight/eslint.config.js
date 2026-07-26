import js from '@eslint/js';
import globals from 'globals';
import tseslint from 'typescript-eslint';

export default tseslint.config(
  {
    ignores: [
      '**/.aspire/**',
      '**/dist/**',
      '**/coverage/**',
      '**/node_modules/**',
    ],
  },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ['apps/web/**/*.ts'],
    languageOptions: { globals: globals.browser },
  },
  {
    files: [
      'apps/server/**/*.ts',
      'packages/**/*.ts',
      'aspire-apphost/**/*.mts',
    ],
    languageOptions: { globals: globals.node },
  },
);
