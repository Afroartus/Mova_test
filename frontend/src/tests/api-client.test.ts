import { describe, it, expect, vi, beforeEach } from 'vitest';

// Setup stores mock before importing api client
const store: Record<string, string> = { movapay_tenant_id: '11111111-1111-4111-8111-111111111111' };
vi.stubGlobal('localStorage', {
	getItem: (k: string) => store[k] ?? null,
	setItem: (k: string, v: string) => { store[k] = v; },
	removeItem: (k: string) => { delete store[k]; }
});

vi.resetModules();
const { auth } = await import('../lib/stores/auth');
const { api, ApiError } = await import('../lib/api/client');

describe('api client', () => {
	beforeEach(() => {
		vi.restoreAllMocks();
	});

	it('includes X-Tenant-Id header from auth store', async () => {
		auth.login('22222222-2222-4222-8222-222222222222');

		const mockFetch = vi.fn().mockResolvedValue({
			ok: true,
			status: 200,
			json: async () => ({ id: '1' })
		});
		vi.stubGlobal('fetch', mockFetch);

		await api.get('/v1/products');

		const [, options] = mockFetch.mock.calls[0] as [string, RequestInit];
		const headers = options.headers as Record<string, string>;
		expect(headers['X-Tenant-Id']).toBe('22222222-2222-4222-8222-222222222222');
		expect(headers['Authorization']).toBeUndefined();
	});

	it('throws ApiError on non-ok response', async () => {
		vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
			ok: false,
			status: 422,
			text: async () => '{"detail":"productos no encontrados: [\'p1\']"}'
		}));

		await expect(api.post('/v1/sales', {})).rejects.toMatchObject({
			status: 422,
			name: 'ApiError',
			message: "productos no encontrados: ['p1']"
		});
	});

	it('POST includes JSON body', async () => {
		const mockFetch = vi.fn().mockResolvedValue({
			ok: true,
			status: 201,
			json: async () => ({ id: 'sale-1' })
		});
		vi.stubGlobal('fetch', mockFetch);

		await api.post('/v1/sales', { products: [{ product_id: 'p1', quantity: 2 }] });

		const [, options] = mockFetch.mock.calls[0] as [string, RequestInit];
		expect(options.method).toBe('POST');
		expect(options.body).toContain('"product_id":"p1"');
	});

	it('flattens FastAPI validation errors into the message', async () => {
		vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
			ok: false,
			status: 422,
			text: async () =>
				'{"detail":[{"loc":["body","products"],"msg":"List should have at least 1 item"}]}'
		}));

		await expect(api.post('/v1/sales', { products: [] })).rejects.toMatchObject({
			status: 422,
			message: 'products: List should have at least 1 item'
		});
	});

	it('uses relative URLs by default (Vite proxy)', async () => {
		const mockFetch = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => [] });
		vi.stubGlobal('fetch', mockFetch);

		await api.get('/v1/products');

		expect(mockFetch.mock.calls[0][0]).toBe('/v1/products');
	});
});
