<script lang="ts">
	import { cartStore, cartTotal } from '$lib/stores/cart';
	import { formatMoney } from '$lib/money';
	export let online: boolean;
	export let checkoutStatus: 'idle' | 'loading' | 'success' | 'offline-saved' | 'error' = 'idle';
	export let checkoutMsg = '';
	export let onCheckout: () => void;
	export let onClear: () => void;
</script>

<section class="card" style="margin-top:1rem">
	<h3>Carrito {$cartStore.length > 0 ? `(${$cartStore.length})` : ''}</h3>

	{#if checkoutStatus === 'success'}
		<div class="feedback success">{checkoutMsg}</div>
		<button on:click={onClear} class="primary" style="width:100%;margin-top:0.5rem">Nueva venta</button>
	{:else if checkoutStatus === 'offline-saved'}
		<div class="feedback warn">{checkoutMsg}</div>
		<button on:click={onClear} class="primary" style="width:100%;margin-top:0.5rem">Nueva venta</button>
	{:else if checkoutStatus === 'error'}
		<div class="feedback danger">{checkoutMsg}</div>
		<button on:click={onClear} style="width:100%;margin-top:0.5rem">Reintentar</button>
	{:else if $cartStore.length === 0}
		<p class="empty">Carrito vacío</p>
	{:else}
		{#each $cartStore as item}
			<div class="cart-row">
				<span class="cart-item-name">{item.name}</span>
				<span class="cart-item-qty">×{item.qty}</span>
				<span class="cart-item-price">{formatMoney(item.price_cents * item.qty)}</span>
				<button class="danger remove-btn" on:click={() => cartStore.remove(item.product_id)}>✕</button>
			</div>
		{/each}

		<div class="cart-total">Total: <strong>{formatMoney($cartTotal)}</strong></div>

		<button
			class="primary"
			style="width:100%;margin-top:0.75rem"
			disabled={checkoutStatus === 'loading'}
			on:click={onCheckout}
		>
			{#if checkoutStatus === 'loading'}
				Procesando…
			{:else if online}
				Cobrar — {formatMoney($cartTotal)}
			{:else}
				Guardar offline — {formatMoney($cartTotal)}
			{/if}
		</button>
	{/if}
</section>

<style>
	h3 { margin: 0 0 0.75rem; font-size: 1rem; color: var(--text-muted); }
	.empty { color: var(--text-muted); font-size: 0.9rem; }
	.cart-row { display: flex; align-items: center; gap: 0.5rem; padding: 0.375rem 0; border-bottom: 1px solid var(--border); }
	.cart-item-name { flex: 1; }
	.cart-item-qty  { color: var(--text-muted); font-size: 0.875rem; }
	.cart-item-price { font-weight: 600; }
	.remove-btn { padding: 0.125rem 0.5rem; font-size: 0.75rem; background: transparent; border: 1px solid var(--danger); color: var(--danger); }
	.cart-total { text-align: right; padding: 0.5rem 0; font-size: 1.1rem; }
	.feedback { border-radius: var(--radius); padding: 0.75rem 1rem; font-size: 0.9rem; }
	.feedback.success { background: #d1fae5; color: var(--success); }
	.feedback.warn    { background: #fef3c7; color: var(--warn); }
	.feedback.danger  { background: #fee2e2; color: var(--danger); }
</style>
