import { api } from './client';
import { db, type Product } from '$lib/db';
import { toCents, toDecimal } from '$lib/money';

/** `ProductOut` del backend. `price` es un decimal serializado como string. */
export interface RemoteProduct {
	id: string;
	name: string;
	price: string;
	created_at: string;
	update_at: string | null;
}

export interface CreateProductInput {
	name: string;
	price_cents: number;
}

export function toLocalProduct(remote: RemoteProduct, tenantId: string): Product {
	return {
		id: remote.id,
		tenant_id: tenantId,
		name: remote.name,
		price_cents: toCents(remote.price),
		created_at: remote.created_at
	};
}

export async function createProduct(
	tenantId: string,
	input: CreateProductInput
): Promise<Product> {
	const remote = await api.post<RemoteProduct>('/v1/products', {
		name: input.name,
		price: toDecimal(input.price_cents)
	});
	const product = toLocalProduct(remote, tenantId);
	await db.products.put(product);
	return product;
}

/**
 * Trae el catálogo del tenant y reemplaza la copia local, para que los
 * productos que ya no existen en el servidor desaparezcan también offline.
 */
export async function fetchProducts(tenantId: string): Promise<Product[]> {
	const remote = await api.get<RemoteProduct[]>('/v1/products?limit=200');
	const products = remote.map((p) => toLocalProduct(p, tenantId));
	await db.transaction('rw', db.products, async () => {
		await db.products.where('tenant_id').equals(tenantId).delete();
		await db.products.bulkPut(products);
	});
	return products;
}

export function getLocalProducts(tenantId: string) {
	return db.products.where('tenant_id').equals(tenantId).toArray();
}
