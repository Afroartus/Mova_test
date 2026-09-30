import { db } from '$lib/db';
import { API_BASE } from '$lib/api/client';
import { syncPendingSales } from './sync-logic';

interface SyncRequest {
	type: 'sync';
	tenantId: string;
}

// Un worker dedicado resuelve `fetch` relativo contra su propia URL, que es
// del mismo origen que la app, así que `API_BASE` vacío también pasa por el
// proxy de Vite.
self.addEventListener('message', async (event: MessageEvent<SyncRequest>) => {
	if (event.data.type !== 'sync') return;

	const { tenantId } = event.data;
	try {
		const result = await syncPendingSales(
			{ db, apiFetch: (url, init) => fetch(url, init), apiBase: API_BASE },
			tenantId
		);
		self.postMessage({ type: 'sync_done', ...result });
	} catch (err) {
		self.postMessage({ type: 'sync_error', error: String(err) });
	}
});
