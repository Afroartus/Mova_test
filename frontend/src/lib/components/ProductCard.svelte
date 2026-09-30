<script lang="ts">
	import type { Product } from '$lib/db';
	import { formatMoney } from '$lib/money';
	export let product: Product;
	export let onAdd: (p: Product) => void;
</script>

<button class="product-card" on:click={() => onAdd(product)}>
	<span class="product-name">{product.name}</span>
	<span class="product-price">{formatMoney(product.price_cents)}</span>
</button>

<style>
	.product-card {
		background: var(--card);
		border: 1px solid var(--border);
		border-radius: var(--radius);
		padding: 0.75rem;
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
		text-align: left;
		font-weight: 400;
		width: 100%;
	}
	.product-name { font-weight: 600; }
	.product-price { color: var(--brand); font-size: 0.9rem; }
</style>
