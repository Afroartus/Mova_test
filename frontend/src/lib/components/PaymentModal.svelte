<script lang="ts">
	import { createSale, paySale, type PayOutcome, type SaleStatus } from '$lib/api/sales';
	import type { CartItem } from '$lib/stores/cart';
	import { formatMoney } from '$lib/money';

	export let items: CartItem[];
	export let total: number;
	export let onClose: (result: 'paid' | 'declined' | 'pending' | 'error' | 'cancelled') => void;

	type Step = 'confirm' | 'processing' | 'result';

	let outcome: PayOutcome = 'approved';
	let step: Step = 'confirm';
	let resultStatus: SaleStatus | '' = '';
	let errorMsg = '';
	// La orden se crea una sola vez. Si el pago queda sin resolver (`created`),
	// el reintento reporta el pago sobre la MISMA venta, no crea otra.
	let saleId: string | null = null;

	const outcomeLabels: Record<PayOutcome, string> = {
		approved: 'Aprobado',
		declined: 'Rechazado',
		timeout: 'Timeout (queda sin resolver)'
	};

	async function confirm() {
		step = 'processing';
		errorMsg = '';
		try {
			if (!saleId) {
				const sale = await createSale({
					products: items.map((i) => ({ product_id: i.product_id, quantity: i.qty }))
				});
				saleId = sale.id;
			}
			const result = await paySale(saleId, outcome);
			resultStatus = result.status;
		} catch (e: unknown) {
			errorMsg = e instanceof Error ? e.message : 'Error al procesar el pago';
			// Si la venta ya existe, un fallo de red en /pay la deja en `created`.
			if (saleId) resultStatus = 'created';
		}
		step = 'result';
	}

	function retry() {
		errorMsg = '';
		resultStatus = '';
		step = 'confirm';
	}

	function close() {
		if (resultStatus === 'approved') onClose('paid');
		else if (resultStatus === 'declined') onClose('declined');
		else if (resultStatus === 'created') onClose('pending');
		else onClose('error');
	}
</script>

<!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions -->
<div class="modal-overlay" on:click|self={() => step === 'confirm' && !saleId && onClose('cancelled')}>
	<div class="modal-card">
		{#if step === 'confirm'}
			<h3>{saleId ? 'Reintentar cobro' : 'Confirmar pago'}</h3>
			<p class="modal-total">Total: <strong>{formatMoney(total)}</strong></p>

			<div class="field">
				<label for="outcome">Resultado del pago (simulación)</label>
				<select id="outcome" bind:value={outcome}>
					{#each Object.entries(outcomeLabels) as [val, label]}
						<option value={val}>{label}</option>
					{/each}
				</select>
			</div>

			<div class="modal-actions">
				{#if saleId}
					<button on:click={() => onClose('pending')}>Dejar pendiente</button>
				{:else}
					<button on:click={() => onClose('cancelled')}>Cancelar</button>
				{/if}
				<button class="primary" on:click={confirm}>Cobrar</button>
			</div>

		{:else if step === 'processing'}
			<p class="modal-loading">Procesando pago…</p>

		{:else}
			{#if resultStatus === 'approved'}
				<div class="result success">
					<span class="result-icon">✓</span>
					<p>Pago aprobado</p>
				</div>
			{:else if resultStatus === 'declined'}
				<div class="result declined">
					<span class="result-icon">✕</span>
					<p>Pago rechazado</p>
				</div>
			{:else if resultStatus === 'created'}
				<div class="result unknown">
					<span class="result-icon">?</span>
					<p>Pago sin resolver</p>
					<small>
						{errorMsg || 'El pago no se confirmó.'} La orden quedó registrada; puedes
						reintentar el cobro sobre la misma venta.
					</small>
				</div>
			{:else}
				<div class="result error">
					<span class="result-icon">✕</span>
					<p>{errorMsg}</p>
				</div>
			{/if}

			{#if resultStatus === 'created'}
				<div class="modal-actions">
					<button on:click={close}>Cerrar</button>
					<button class="primary" on:click={retry}>Reintentar cobro</button>
				</div>
			{:else}
				<button class="primary" style="width:100%;margin-top:1rem" on:click={close}>
					{resultStatus === 'approved' ? 'Nueva venta' : 'Cerrar'}
				</button>
			{/if}
		{/if}
	</div>
</div>

<style>
	.modal-overlay {
		position: fixed; inset: 0;
		background: rgba(0,0,0,0.5);
		display: flex; align-items: center; justify-content: center;
		z-index: 100;
	}
	.modal-card {
		background: var(--card);
		border-radius: var(--radius);
		padding: 1.5rem;
		width: min(400px, 90vw);
		box-shadow: 0 8px 32px rgba(0,0,0,0.2);
	}
	h3 { margin: 0 0 1rem; }
	.modal-total { font-size: 1.1rem; margin-bottom: 1rem; }
	.modal-loading { text-align: center; padding: 2rem 0; color: var(--text-muted); }
	.field { margin-bottom: 0.75rem; }
	.field label { display: block; font-size: 0.8rem; color: var(--text-muted); margin-bottom: 0.25rem; }
	.field select { width: 100%; }
	.modal-actions { display: flex; gap: 0.5rem; margin-top: 1rem; justify-content: flex-end; }
	.result { text-align: center; padding: 1rem; border-radius: var(--radius); }
	.result-icon { font-size: 2rem; display: block; margin-bottom: 0.5rem; }
	.result.success  { background: #d1fae5; color: var(--success); }
	.result.declined { background: #fee2e2; color: var(--danger); }
	.result.unknown  { background: #fef3c7; color: var(--warn); }
	.result.error    { background: #fee2e2; color: var(--danger); }
	.result small { display: block; font-size: 0.8rem; margin-top: 0.5rem; opacity: 0.8; }
</style>
