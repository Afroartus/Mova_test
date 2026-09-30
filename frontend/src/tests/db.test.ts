import { describe, it, expect, beforeEach } from 'vitest';
import 'fake-indexeddb/auto';
import { db, type Product, type PendingSale } from '../lib/db';

describe('MovaPayDB', () => {
	beforeEach(async () => {
		await db.products.clear();
		await db.pending_sales.clear();
	});

	it('stores and retrieves a product', async () => {
		const product: Product = {
			id: 'prod-1',
			tenant_id: 'tenant-A',
			name: 'Café',
			price_cents: 350,
			created_at: new Date().toISOString()
		};
		await db.products.put(product);

		const retrieved = await db.products.get('prod-1');
		expect(retrieved?.name).toBe('Café');
		expect(retrieved?.price_cents).toBe(350);
	});

	it('filters products by tenant_id', async () => {
		await db.products.bulkPut([
			{ id: 'p1', tenant_id: 'tenant-A', name: 'Café', price_cents: 350, created_at: '' },
			{ id: 'p2', tenant_id: 'tenant-B', name: 'Agua', price_cents: 100, created_at: '' }
		]);

		const forA = await db.products.where('tenant_id').equals('tenant-A').toArray();
		expect(forA).toHaveLength(1);
		expect(forA[0].id).toBe('p1');
	});

	it('stores a pending sale and marks it synced', async () => {
		const sale: PendingSale = {
			local_id: 'local-123',
			tenant_id: 'tenant-A',
			items: [{ product_id: 'p1', product_name: 'Café', unit_price_cents: 350, quantity: 2 }],
			total_cents: 700,
			created_at: new Date().toISOString(),
			synced: 0
		};
		const id = await db.pending_sales.add(sale);
		expect(id).toBeDefined();

		await db.pending_sales.update(id, { synced: 1 });
		const updated = await db.pending_sales.get(id);
		expect(updated?.synced).toBe(1);
	});

	it('queries unsynced sales via index (synced=0)', async () => {
		await db.pending_sales.bulkAdd([
			{ local_id: 'a', tenant_id: 'tenant-A', items: [], total_cents: 100, created_at: '', synced: 0 },
			{ local_id: 'b', tenant_id: 'tenant-A', items: [], total_cents: 200, created_at: '', synced: 1 }
		]);

		const unsynced = await db.pending_sales.where('synced').equals(0).toArray();
		expect(unsynced).toHaveLength(1);
		expect(unsynced[0].local_id).toBe('a');
	});
});
