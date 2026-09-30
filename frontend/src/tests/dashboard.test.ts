import { describe, it, expect, vi, beforeEach } from 'vitest';
import { get } from 'svelte/store';
import { createDashboardStore } from '../lib/stores/dashboard';
import { fetchTodayReport, type DashboardReport } from '../lib/api/dashboard';
import { streamWithReconnect } from '../lib/sse-client';

vi.mock('../lib/api/dashboard', () => ({
	fetchTodayReport: vi.fn()
}));

vi.mock('../lib/sse-client', () => ({
	streamWithReconnect: vi.fn()
}));

function report(overrides: Partial<DashboardReport> = {}): DashboardReport {
	return {
		date: '2026-09-30',
		timezone: 'UTC',
		total_sales: 0,
		counts: { created: 0, approved: 0, declined: 0 },
		amounts: { created: '0.00', approved: '0.00', declined: '0.00' },
		approved_amount: '0.00',
		...overrides
	};
}

describe('dashboardStore', () => {
	let store: ReturnType<typeof createDashboardStore>;

	beforeEach(() => {
		vi.clearAllMocks();
		vi.mocked(fetchTodayReport).mockResolvedValue(report());
		vi.mocked(streamWithReconnect).mockResolvedValue(undefined);
		store = createDashboardStore();
	});

	it('loads today report and updates state', async () => {
		vi.mocked(fetchTodayReport).mockResolvedValue(
			report({
				total_sales: 10,
				counts: { created: 1, approved: 8, declined: 1 },
				approved_amount: '50.00'
			})
		);

		await store.loadToday();

		const state = get(store);
		expect(state.report?.total_sales).toBe(10);
		expect(state.report?.counts.approved).toBe(8);
		expect(state.loading).toBe(false);
		expect(state.loadError).toBe('');
	});

	it('snapshot frame sets the report and marks the stream connected', () => {
		store.handleEvent({ type: 'snapshot', data: JSON.stringify(report({ total_sales: 3 })) });

		const state = get(store);
		expect(state.report?.total_sales).toBe(3);
		expect(state.sseStatus).toBe('connected');
	});

	it('sale frames feed the event list and refresh the aggregate', () => {
		store.handleEvent({ type: 'sale', data: '{"id":"s1","status":"created","total":"7.00"}' });
		store.handleEvent({ type: 'sale', data: '{"id":"s1","status":"approved","total":"7.00"}' });
		store.handleEvent({ type: 'sale', data: 'not json' });

		const state = get(store);
		expect(state.events).toHaveLength(2);
		expect(state.events[0].sale.status).toBe('approved');
		expect(fetchTodayReport).toHaveBeenCalledTimes(2);
	});

	it('connects to the stream with the tenant id', () => {
		const ac = new AbortController();
		store.connect('tenant-1', ac.signal);

		const [url, tenantId] = vi.mocked(streamWithReconnect).mock.calls[0];
		expect(url).toBe('/v1/dashboard/stream');
		expect(tenantId).toBe('tenant-1');
	});

	it('sets sseStatus to offline when signal is aborted', () => {
		const ac = new AbortController();
		store.connect('token', ac.signal);
		expect(get(store).sseStatus).toBe('connecting');

		ac.abort();
		expect(get(store).sseStatus).toBe('offline');
	});
});
