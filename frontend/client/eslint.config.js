import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'

export default [
  {
    ignores: ['dist'],
  },
  {
    files: ['**/*.{js,jsx}'],
    ...js.configs.recommended,
    languageOptions: {
      ecmaVersion: 2020,
      globals: {
        ...globals.browser,
        ...globals.node,
      },
      parserOptions: {
        ecmaVersion: 'latest',
        ecmaFeatures: { jsx: true },
        sourceType: 'module',
      },
    },
    plugins: {
      'react-hooks': reactHooks,
      'react-refresh': reactRefresh,
    },
    rules: {
      // Phase 1: Relaxed rules for CI/CD infrastructure validation
      // TODO: Gradually tighten these rules in Phase 2
      'no-unused-vars': ['warn', { argsIgnorePattern: '^_', varsIgnorePattern: '^_' }],
      'no-prototype-builtins': 'warn',
      'no-undef': 'warn',
      'no-use-before-define': 'warn',
      // Convert all react-hooks rules to warnings for Phase 1
      ...Object.keys(reactHooks.configs.recommended.rules || {}).reduce((acc, key) => {
        acc[key] = 'warn';
        return acc;
      }, {}),
    },
  },
]
