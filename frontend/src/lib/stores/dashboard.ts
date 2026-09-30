import { writable } from 'svelte/store';
import { API_BASE } from '$lib/api/client';
import { fetchTodayReport, type DashboardReport, type SaleEvent } from '$lib/api/dashboard';
import { streamWithReconnect, type SSEEvent } from '$lib/sse-client';

export interface DashboardState {
	report: DashboardReport | null;
	loading: boolean;
	loadError: string;
	events: { time: string; sale: SaleEvent }[];
	sseStatus: 'connecting' | 'connected' | 'reconnecting' | 'offline';
}

const initial: DashboardState = {
	report: null,
	loading: false,
	loadError: '',
	events: [],
	sseStatus: 'offline'
};

export function createDashboardStore() {
	const { subscribe, update, set } = writable<DashboardState>({ ...initial });

	/** `silent` refresca sin mostrar el estado de carga (tras un evento SSE). */
	async function loadToday(silent = false) {
		if (!silent) update((s) => ({ ...s, loading: true, loadError: '' }));
		try {
			const report = await fetchTodayReport();
			update((s) => ({ ...s, report, loading: false, loadError: '' }));
		} catch {
			update((s) => ({
				...s,
				loading: false,
				loadError: s.report ? '' : 'No se pudo cargar el dashboard'
			}));
		}
	}

	function handleEvent(ev: SSEEvent) {
		// `snapshot`: agregado del día que el backend manda al conectar.
		if (ev.type === 'snapshot') {
			try {
				const report = JSON.parse(ev.data) as DashboardReport;
				update((s) => ({ ...s, report, loading: false, loadError: '', sseStatus: 'connected' }));
			} catch {
				update((s) => ({ ...s, sseStatus: 'connected' }));
			}
			return;
		}
		// `sale`: una venta se creó o cambió de estado.
		if (ev.type === 'sale') {
			let sale: SaleEvent;
			try {
				sale = JSON.parse(ev.data) as SaleEvent;
			} catch {
				return; // frame malformado
			}
			update((s) => ({
				...s,
				events: [{ time: new Date().toLocaleTimeString(), sale }, ...s.events].slice(0, 20)
			}));
			// El worker actualiza la caché del agregado antes de publicar el
			// frame, así que el `/today` que sigue ya refleja esta venta.
			void loadToday(true);
		}
	}

	function connect(tenantId: string, signal: AbortSignal) {
		update((s) => ({ ...s, sseStatus: 'connecting' }));
		signal.addEventListener('abort', () => {
			update((s) => ({ ...s, sseStatus: 'offline' }));
		}, { once: true });
		streamWithReconnect(`${API_BASE}/v1/dashboard/stream`, tenantId, handleEvent, signal, {
			onRetry: () => update((s) => ({ ...s, sseStatus: 'reconnecting' }))
		}).catch(() => {
			if (!signal.aborted) {
				update((s) => ({ ...s, sseStatus: 'reconnecting' }));
			}
		});
	}

	function reset() {
		set({ ...initial });
	}

	return { subscribe, loadToday, handleEvent, connect, reset };
}

export const dashboardStore = createDashboardStore();
