<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { liveQuery } from 'dexie';
	import { get } from 'svelte/store';
	import { v4 as uuidv4 } from 'uuid';
	import { auth } from '$lib/stores/auth';
	import { online } from '$lib/stores/online';
	import { syncStore } from '$lib/stores/sync';
	import { cartStore, cartTotal } from '$lib/stores/cart';
	import { db } from '$lib/db';
	import { formatMoney, toCents } from '$lib/money';
	import ProductCard from '$lib/components/ProductCard.svelte';
	import Cart from '$lib/components/Cart.svelte';
	import PaymentModal from '$lib/components/PaymentModal.svelte';

	const products = liveQuery(() =>
		db.products.where('tenant_id').equals(get(auth)).sortBy('name')
	);

	let showModal = false;
	let checkoutStatus: 'idle' | 'loading' | 'success' | 'offline-saved' | 'error' = 'idle';
	let checkoutMsg = '';

	// --- add-product panel ---
	let newName = '';
	let newPrice = '';
	let addingProduct = false;
	let addProductError = '';

	async function addProduct() {
		addingProduct = true;
		addProductError = '';
		try {
			const { createProduct } = await import('$lib/api/products');
			await createProduct(get(auth), {
				name: newName.trim(),
				price_cents: toCents(newPrice)
			});
			newName = ''; newPrice = '';
		} catch (e: unknown) {
			addProductError = e instanceof Error ? e.message : 'Error';
		} finally {
			addingProduct = false;
		}
	}

	// --- checkout ---
	function handleCheckout() {
		if ($online) {
			showModal = true;
		} else {
			saveOffline();
		}
	}

	async function saveOffline() {
		checkoutStatus = 'loading';
		const tenantId = get(auth);
		const total = get(cartTotal);
		await db.pending_sales.add({
			local_id: uuidv4(),
			tenant_id: tenantId,
			items: $cartStore.map((c) => ({
				product_id: c.product_id,
				product_name: c.name,
				unit_price_cents: c.price_cents,
				quantity: c.qty
			})),
			total_cents: total,
			created_at: new Date().toISOString(),
			synced: 0
		});
		await syncStore.refresh(tenantId);
		checkoutStatus = 'offline-saved';
		checkoutMsg = `Guardada offline (${formatMoney(total)}). Se enviará cuando haya conexión.`;
		cartStore.clear();
	}

	function handleModalClose(result: 'paid' | 'declined' | 'pending' | 'error' | 'cancelled') {
		showModal = false;
		if (result === 'paid') {
			const total = get(cartTotal);
			cartStore.clear();
			checkoutStatus = 'success';
			checkoutMsg = `Venta pagada por ${formatMoney(total)}`;
		} else if (result === 'declined') {
			checkoutStatus = 'error';
			checkoutMsg = 'Pago rechazado. Intenta con otro método o limpia el carrito.';
		} else if (result === 'pending') {
			checkoutStatus = 'error';
			checkoutMsg = 'Pago sin resolver: la orden quedó registrada como pendiente. Verifica con el cliente antes de cobrar de nuevo.';
		} else if (result === 'error') {
			checkoutStatus = 'error';
			checkoutMsg = 'Error al procesar el pago. Verifica e intenta de nuevo.';
		}
		// 'cancelled': no cambia el estado, el carrito sigue listo para cobrar
	}

	function clearCheckout() {
		checkoutStatus = 'idle';
		checkoutMsg = '';
		cartStore.clear();
	}

	// --- sync worker ---
	let worker: Worker | null = null;
	let unsubOnline: (() => void) | null = null;

	function triggerSync() {
		if (!worker) return;
		syncStore.setSyncing(true);
		worker.postMessage({ type: 'sync', tenantId: get(auth) });
	}

	async function refreshProducts() {
		try {
			const { fetchProducts } = await import('$lib/api/products');
			await fetchProducts(get(auth));
		} catch {
			// silently ignore — catálogo local queda como está
		}
	}

	onMount(async () => {
		await syncStore.refresh(get(auth));
		if (typeof Worker !== 'undefined') {
			const SyncWorker = (await import('$lib/sync/sync.worker.ts?worker')).default;
			const w: Worker = new SyncWorker();
			worker = w;
			w.addEventListener('message', (e: MessageEvent) => {
				if (e.data.type === 'sync_done') {
					const { synced, failed, errors } = e.data;
					console.log('[sync] done — synced:', synced, 'failed:', failed, 'errors:', errors);
					syncStore.onSyncDone(synced ?? 0);
					syncStore.refresh(get(auth));
				} else if (e.data.type === 'sync_error') {
					console.error('[sync] worker error:', e.data.error);
					syncStore.onSyncError(e.data.error);
				}
			});

			// Fires immediately with current value AND on every future change.
			// Worker is guaranteed to exist here, so triggerSync is safe to call.
			unsubOnline = online.subscribe((isOnline) => {
				if (!isOnline) return;
				refreshProducts();
				triggerSync();
			});
		}
	});

	onDestroy(() => {
		worker?.terminate();
		unsubOnline?.();
	});
</script>

<div class="pos-header">
	<h2>Punto de Venta</h2>
	{#if $syncStore.pending > 0}
		<span class="badge offline" title="Ventas pendientes de sincronizar">
			{$syncStore.pending} pendiente{$syncStore.pending > 1 ? 's' : ''}
			{#if $syncStore.syncing}— sincronizando…{/if}
		</span>
	{/if}
</div>

{#if $online}
	<details class="card add-product" style="margin-bottom:1rem">
		<summary style="cursor:pointer;font-weight:600;font-size:0.9rem;color:var(--text-muted)">
			+ Agregar producto al catálogo
		</summary>
		<form on:submit|preventDefault={addProduct} style="margin-top:0.75rem;display:flex;gap:0.5rem;flex-wrap:wrap">
			<input bind:value={newName} placeholder="Nombre" style="flex:2;min-width:120px" required />
			<input bind:value={newPrice} placeholder="Precio (ej: 3500)" type="number" step="0.01" min="0" style="flex:1;min-width:90px" required />
			<button type="submit" class="primary" disabled={addingProduct} style="white-space:nowrap">
				{addingProduct ? '…' : 'Agregar'}
			</button>
		</form>
		{#if addProductError}<p style="color:var(--danger);font-size:0.8rem;margin-top:0.5rem">{addProductError}</p>{/if}
	</details>
{/if}

<section class="catalog">
	<h3>Catálogo</h3>
	{#if $products && $products.length > 0}
		<div class="product-grid">
			{#each $products as p}
				<ProductCard product={p} onAdd={(prod) => cartStore.add(prod)} />
			{/each}
		</div>
	{:else}
		<p class="empty">No hay productos. {$online ? 'Agrégalos arriba.' : 'Sin conexión para cargar catálogo.'}</p>
	{/if}
</section>

<Cart
	online={$online}
	{checkoutStatus}
	{checkoutMsg}
	onCheckout={handleCheckout}
	onClear={clearCheckout}
/>

{#if showModal}
	<PaymentModal
		items={$cartStore}
		total={get(cartTotal)}
		onClose={handleModalClose}
	/>
{/if}

<style>
	.pos-header { display: flex; align-items: center; gap: 0.75rem; margin-bottom: 1rem; }
	h2 { margin: 0; }
	h3 { margin: 0 0 0.75rem; font-size: 1rem; color: var(--text-muted); }
	.empty { color: var(--text-muted); font-size: 0.9rem; }
	.add-product { padding: 0.75rem 1rem; }
	.product-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); gap: 0.75rem; }
</style>
