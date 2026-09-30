import Dexie, { type EntityTable } from 'dexie';

export interface Product {
	id: string;
	tenant_id: string;
	name: string;
	price_cents: number;
	created_at: string;
}

export interface PendingSaleItem {
	product_id: string;
	product_name: string;
	unit_price_cents: number;
	quantity: number;
}

export interface PendingSale {
	id?: number; // auto-increment local key
	local_id: string; // uuid generated client-side
	tenant_id: string;
	items: PendingSaleItem[];
	total_cents: number;
	created_at: string;
	/**
	 * Id de la venta en el servidor, una vez creada. El backend no tiene
	 * idempotency key: si el `POST /v1/sales` ya se hizo y falló el `/pay`, el
	 * reintento reutiliza este id en vez de crear la venta dos veces.
	 */
	remote_id?: string;
	synced: 0 | 1; // IndexedDB does not support boolean keys; use 0=false, 1=true
}

export class MovaPayDB extends Dexie {
	products!: EntityTable<Product, 'id'>;
	pending_sales!: EntityTable<PendingSale, 'id'>;

	constructor() {
		super('movapay');
		this.version(1).stores({
			products: 'id, merchant_id',
			pending_sales: '++id, local_id, merchant_id, synced'
		});
		// v2: el backend es multi-tenant por `X-Tenant-Id`, no por merchant, y
		// los precios cambiaron de formato. Los datos de v1 no son migrables.
		this.version(2)
			.stores({
				products: 'id, tenant_id',
				pending_sales: '++id, local_id, tenant_id, synced'
			})
			.upgrade(async (tx) => {
				await tx.table('products').clear();
				await tx.table('pending_sales').clear();
			});
	}
}

export const db = new MovaPayDB();
