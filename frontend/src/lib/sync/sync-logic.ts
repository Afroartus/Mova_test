import type { MovaPayDB, PendingSale } from '$lib/db';
import { TENANT_HEADER } from '$lib/api/client';
import { toDecimal } from '$lib/money';

export interface SyncDeps {
	db: MovaPayDB;
	apiFetch: (url: string, init: RequestInit) => Promise<Response>;
	apiBase: string;
}

export interface SyncResult {
	synced: number;
	failed: number;
	errors: string[];
}

/**
 * Sube las ventas hechas offline: `POST /v1/sales` y luego `/pay` con
 * `approved` (una venta offline es efectivo ya cobrado).
 *
 * El backend no tiene idempotency key, así que el id remoto se guarda en
 * cuanto la venta se crea: si el `/pay` falla, el siguiente intento reutiliza
 * esa venta en vez de duplicarla. `/pay` sí es seguro de reintentar, porque
 * `approved` es terminal y un segundo reporte es un no-op.
 */
export async function syncPendingSales(deps: SyncDeps, tenantId: string): Promise<SyncResult> {
	const unsynced: PendingSale[] = await deps.db.pending_sales
		.where('synced')
		.equals(0)
		.filter((sale) => sale.tenant_id === tenantId)
		.toArray();

	let synced = 0;
	let failed = 0;
	const errors: string[] = [];

	const headers = {
		'Content-Type': 'application/json',
		[TENANT_HEADER]: tenantId
	};

	for (const sale of unsynced) {
		try {
			let remoteId = sale.remote_id;

			if (!remoteId) {
				const createRes = await deps.apiFetch(`${deps.apiBase}/v1/sales`, {
					method: 'POST',
					headers,
					body: JSON.stringify({
						// Se manda el precio que vio el cliente al vender offline,
						// no el vigente al sincronizar.
						products: sale.items.map((i) => ({
							product_id: i.product_id,
							quantity: i.quantity,
							price: toDecimal(i.unit_price_cents)
						}))
					})
				});

				if (!createRes.ok) {
					failed++;
					errors.push(`Sale ${sale.local_id}: create HTTP ${createRes.status}`);
					continue;
				}

				const created = (await createRes.json()) as { id: string };
				remoteId = created.id;
				await deps.db.pending_sales.update(sale.id!, { remote_id: remoteId });
			}

			const payRes = await deps.apiFetch(`${deps.apiBase}/v1/sales/${remoteId}/pay`, {
				method: 'POST',
				headers,
				body: JSON.stringify({ outcome: 'approved' })
			});

			if (payRes.ok) {
				await deps.db.pending_sales.delete(sale.id!);
				synced++;
			} else {
				failed++;
				errors.push(`Sale ${sale.local_id}: pay HTTP ${payRes.status}`);
			}
		} catch (err) {
			failed++;
			errors.push(`Sale ${sale.local_id}: ${String(err)}`);
		}
	}

	return { synced, failed, errors };
}
