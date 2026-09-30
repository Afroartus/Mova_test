import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig, loadEnv } from 'vite';
import { VitePWA } from 'vite-plugin-pwa';

export default defineConfig(({ mode }) => {
	const env = loadEnv(mode, '.', '');
	// Backend FastAPI. El front llama rutas relativas (`/v1/...`) y Vite las
	// reenvía aquí: mismo origen para el navegador, sin CORS, y el SSE pasa
	// tal cual porque el proxy no bufferiza.
	const apiTarget = env.API_PROXY_TARGET || 'http://localhost:8000';
	const proxy = {
		'/v1': { target: apiTarget, changeOrigin: true },
		'/health': { target: apiTarget, changeOrigin: true }
	};

	return {
		server: { proxy },
		preview: { proxy },
		plugins: [
			sveltekit(),
			VitePWA({
				registerType: 'autoUpdate',
				workbox: {
					globPatterns: ['**/*.{js,css,html,ico,png,svg,webp,woff2}'],
					// Sin runtimeCaching de la API: el cache del SW indexa por URL e
					// ignora `X-Tenant-Id`, así que serviría datos de un tenant a otro.
					// El modo offline usa IndexedDB (Dexie), que sí separa por tenant.
					navigateFallbackDenylist: [/^\/v1\//, /^\/health/]
				},
				manifest: {
					name: 'MovaPay POS',
					short_name: 'MovaPay',
					description: 'Punto de venta offline-first',
					theme_color: '#1a56db',
					background_color: '#ffffff',
					display: 'standalone',
					start_url: '/pos',
					icons: [
						{ src: '/icons/icon-192.png', sizes: '192x192', type: 'image/png' },
						{ src: '/icons/icon-512.png', sizes: '512x512', type: 'image/png', purpose: 'any maskable' }
					]
				}
			})
		]
	};
});
