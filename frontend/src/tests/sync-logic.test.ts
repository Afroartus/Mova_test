import { describe, it, expect, vi, beforeEach } from 'vitest';
import 'fake-indexeddb/auto';
import { MovaPayDB } from '../lib/db';
import { syncPendingSales } from '../lib/sync/sync-logic';

function makeDB() {
	return new MovaPayDB();
}

// Returns a fetch mock that responds ok to both create and pay calls.
// createId is the sale id returned in the create response body.
function okFetch(createId = 'sale-remote') {
	return vi.fn().mockResolvedValue({
		ok: true,
		status: 201,
		json: async () => ({ id: createId })
	});
}

describe('syncPendingSales', () => {
	let testDB: MovaPayDB;

	beforeEach(async () => {
		testDB = makeDB();
		await testDB.pending_sales.clear();
		await testDB.products.clear();
	});

	it('returns zero when queue is empty', async () => {
		const mockFetch = vi.fn();
		const result = await syncPendingSales(
			{ db: testDB, apiFetch: mockFetch, apiBase: 'http://api' },
			'tenant-A'
		);
		expect(result.synced).toBe(0);
		expect(result.failed).toBe(0);
		expect(mockFetch).not.toHaveBeenCalled();
	});

	it('syncs pending sales successfully (create + pay per sale)', async () => {
		await testDB.pending_sales.bulkAdd([
			{
				local_id: 'local-1', tenant_id: 'tenant-A',
				items: [{ product_id: 'p1', product_name: 'Café', unit_price_cents: 350, quantity: 2 }],
				total_cents: 700, created_at: '', synced: 0
			},
			{
				local_id: 'local-2', tenant_id: 'tenant-A',
				items: [{ product_id: 'p2', product_name: 'Agua', unit_price_cents: 100, quantity: 1 }],
				total_cents: 100, created_at: '', synced: 0
			}
		]);

		const mockFetch = okFetch();
		const result = await syncPendingSales(
			{ db: testDB, apiFetch: mockFetch, apiBase: 'http://api' },
			'tenant-A'
		);

		expect(result.synced).toBe(2);
		expect(result.failed).toBe(0);
		// 2 sales × 2 calls (create + pay) = 4 total
		expect(mockFetch).toHaveBeenCalledTimes(4);

		const remaining = await testDB.pending_sales.count();
		expect(remaining).toBe(0);
	});

	it('skips already-synced sales', async () => {
		await testDB.pending_sales.add({
			local_id: 'already-done', tenant_id: 'tenant-A',
			items: [], total_cents: 0, created_at: '', synced: 1
		});

		const mockFetch = vi.fn();
		const result = await syncPendingSales(
			{ db: testDB, apiFetch: mockFetch, apiBase: 'http://api' },
			'tenant-A'
		);

		expect(result.synced).toBe(0);
		expect(mockFetch).not.toHaveBeenCalled();
	});

	it('records failure when create step returns error', async () => {
		await testDB.pending_sales.add({
			local_id: 'local-fail', tenant_id: 'tenant-A',
			items: [{ product_id: 'ghost', product_name: 'X', unit_price_cents: 100, quantity: 1 }],
			total_cents: 100, created_at: '', synced: 0
		});

		const mockFetch = vi.fn().mockResolvedValue({ ok: false, status: 422, json: async () => ({}) });
		const result = await syncPendingSales(
			{ db: testDB, apiFetch: mockFetch, apiBase: 'http://api' },
			'tenant-A'
		);

		expect(result.synced).toBe(0);
		expect(result.failed).toBe(1);
		expect(result.errors[0]).toContain('422');

		const unsynced = await testDB.pending_sales.where('synced').equals(0).count();
		expect(unsynced).toBe(1);
	});

	it('records failure when pay step returns error', async () => {
		await testDB.pending_sales.add({
			local_id: 'local-payfail', tenant_id: 'tenant-A',
			items: [], total_cents: 0, created_at: '', synced: 0
		});

		const mockFetch = vi.fn()
			.mockResolvedValueOnce({ ok: true, status: 201, json: async () => ({ id: 'sale-x' }) })
			.mockResolvedValueOnce({ ok: false, status: 500, json: async () => ({}) });

		const result = await syncPendingSales(
			{ db: testDB, apiFetch: mockFetch, apiBase: 'http://api' },
			'tenant-A'
		);

		expect(result.synced).toBe(0);
		expect(result.failed).toBe(1);
		expect(result.errors[0]).toContain('pay HTTP 500');

		const unsynced = await testDB.pending_sales.where('synced').equals(0).count();
		expect(unsynced).toBe(1);
	});

	it('records failure on network error', async () => {
		await testDB.pending_sales.add({
			local_id: 'local-net', tenant_id: 'tenant-A',
			items: [], total_cents: 0, created_at: '', synced: 0
		});

		const mockFetch = vi.fn().mockRejectedValue(new TypeError('Network error'));
		const result = await syncPendingSales(
			{ db: testDB, apiFetch: mockFetch, apiBase: 'http://api' },
			'tenant-A'
		);

		expect(result.failed).toBe(1);
		expect(result.errors[0]).toContain('Network error');
	});

	it('sends X-Tenant-Id header on create and pay', async () => {
		await testDB.pending_sales.add({
			local_id: 'local-auth', tenant_id: 'tenant-B',
			items: [], total_cents: 0, created_at: '', synced: 0
		});

		const mockFetch = okFetch();
		await syncPendingSales(
			{ db: testDB, apiFetch: mockFetch, apiBase: 'http://api' },
			'tenant-B'
		);

		for (const [, init] of mockFetch.mock.calls as [string, RequestInit][]) {
			const headers = init.headers as Record<string, string>;
			expect(headers['X-Tenant-Id']).toBe('tenant-B');
			expect(headers['Authorization']).toBeUndefined();
		}
	});

	it('only syncs sales of the given tenant', async () => {
		await testDB.pending_sales.bulkAdd([
			{ local_id: 'mine', tenant_id: 'tenant-A', items: [], total_cents: 0, created_at: '', synced: 0 },
			{ local_id: 'other', tenant_id: 'tenant-B', items: [], total_cents: 0, created_at: '', synced: 0 }
		]);

		const mockFetch = okFetch();
		const result = await syncPendingSales(
			{ db: testDB, apiFetch: mockFetch, apiBase: 'http://api' },
			'tenant-A'
		);

		expect(result.synced).toBe(1);
		const left = await testDB.pending_sales.toArray();
		expect(left.map((s) => s.local_id)).toEqual(['other']);
	});

	it('sends one line per product with quantity and the offline unit price', async () => {
		await testDB.pending_sales.add({
			local_id: 'local-body', tenant_id: 'tenant-A',
			items: [{ product_id: 'p1', product_name: 'Café', unit_price_cents: 350, quantity: 2 }],
			total_cents: 700, created_at: '', synced: 0
		});

		const mockFetch = okFetch();
		await syncPendingSales(
			{ db: testDB, apiFetch: mockFetch, apiBase: 'http://api' },
			'tenant-A'
		);

		const [createUrl, createInit] = mockFetch.mock.calls[0] as [string, RequestInit];
		expect(createUrl).toBe('http://api/v1/sales');
		expect(JSON.parse(createInit.body as string)).toEqual({
			products: [{ product_id: 'p1', quantity: 2, price: '3.50' }]
		});
	});

	it('calls pay endpoint with correct URL and approved outcome', async () => {
		await testDB.pending_sales.add({
			local_id: 'local-url', tenant_id: 'tenant-A',
			items: [], total_cents: 0, created_at: '', synced: 0
		});

		const mockFetch = okFetch('sale-abc');
		await syncPendingSales(
			{ db: testDB, apiFetch: mockFetch, apiBase: 'http://api' },
			'tenant-A'
		);

		const [payUrl, payInit] = mockFetch.mock.calls[1] as [string, RequestInit];
		expect(payUrl).toBe('http://api/v1/sales/sale-abc/pay');
		expect(JSON.parse(payInit.body as string)).toEqual({ outcome: 'approved' });
	});

	it('does not create the sale twice when pay failed on a previous run', async () => {
		await testDB.pending_sales.add({
			local_id: 'local-retry', tenant_id: 'tenant-A',
			items: [], total_cents: 0, created_at: '', synced: 0
		});

		const failingPay = vi.fn()
			.mockResolvedValueOnce({ ok: true, status: 201, json: async () => ({ id: 'sale-1' }) })
			.mockResolvedValueOnce({ ok: false, status: 503, json: async () => ({}) });
		await syncPendingSales({ db: testDB, apiFetch: failingPay, apiBase: 'http://api' }, 'tenant-A');

		const retryFetch = okFetch();
		const result = await syncPendingSales(
			{ db: testDB, apiFetch: retryFetch, apiBase: 'http://api' },
			'tenant-A'
		);

		expect(result.synced).toBe(1);
		expect(retryFetch).toHaveBeenCalledTimes(1);
		expect(retryFetch.mock.calls[0][0]).toBe('http://api/v1/sales/sale-1/pay');
	});
});
