import { defineConfig } from 'vitest/config';
import { svelte } from '@sveltejs/vite-plugin-svelte';
import path from 'path';

export default defineConfig({
	plugins: [svelte({ hot: false })],
	resolve: {
		alias: {
			$lib: path.resolve('./src/lib'),
			'$app/stores': path.resolve('./src/tests/__mocks__/app-stores.ts'),
			'$app/navigation': path.resolve('./src/tests/__mocks__/app-navigation.ts')
		}
	},
	test: {
		environment: 'jsdom',
		include: ['src/tests/**/*.test.ts'],
		globals: true
	}
});
