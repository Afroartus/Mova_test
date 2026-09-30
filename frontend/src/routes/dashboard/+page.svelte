<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { get } from 'svelte/store';
	import { auth } from '$lib/stores/auth';
	import { online } from '$lib/stores/online';
	import { dashboardStore } from '$lib/stores/dashboard';
	import DashboardMetrics from '$lib/components/DashboardMetrics.svelte';
	import { formatMoney, toCents } from '$lib/money';

	const statusLabels: Record<string, string> = {
		created: 'Pendiente',
		approved: 'Aprobada',
		declined: 'Rechazada'
	};

	let abortController: AbortController | null = null;

	function startSSE() {
		if (!$online || !$auth) return;
		abortController?.abort();
		abortController = new AbortController();
		dashboardStore.connect(get(auth), abortController.signal);
	}

	onMount(() => {
		dashboardStore.loadToday();
		startSSE();
	});

	onDestroy(() => abortController?.abort());

	$: if ($online) startSSE();
	$: if (!$online) abortController?.abort();
</script>

<div class="dash-header">
	<h2>Dashboard — Hoy</h2>
	<span class="sse-dot sse-{$dashboardStore.sseStatus}" title="Estado SSE: {$dashboardStore.sseStatus}">⬤</span>
</div>

{#if $dashboardStore.loading}
	<div class="loading-row"><span>Cargando…</span></div>
{:else if $dashboardStore.loadError}
	<div class="card error-card">{$dashboardStore.loadError}</div>
{:else if $dashboardStore.report}
	<DashboardMetrics report={$dashboardStore.report} />
{/if}

{#if !$online}
	<div class="badge offline" style="margin-top:1rem">Sin conexión — datos del último refresco</div>
{/if}

{#if $dashboardStore.events.length > 0}
	<section style="margin-top:1.5rem">
		<h3>Eventos en tiempo real</h3>
		<div class="event-feed">
			{#each $dashboardStore.events as ev}
				<div class="event-item">
					<span class="event-time">{ev.time}</span>
					<span class="event-status status-{ev.sale.status}">
						{statusLabels[ev.sale.status] ?? ev.sale.status}
					</span>
					<span class="event-total">{formatMoney(toCents(ev.sale.total))}</span>
					<code class="event-id" title={ev.sale.id}>#{ev.sale.id.slice(0, 8)}</code>
				</div>
			{/each}
		</div>
	</section>
{/if}

<style>
	.dash-header { display: flex; align-items: center; gap: 0.75rem; margin-bottom: 1rem; }
	h2 { margin: 0; }
	h3 { margin: 0 0 0.75rem; font-size: 1rem; color: var(--text-muted); }
	.sse-dot { font-size: 0.7rem; }
	.sse-connected    { color: var(--success); }
	.sse-connecting   { color: var(--warn); animation: pulse 1s infinite; }
	.sse-reconnecting { color: var(--warn); }
	.sse-offline      { color: var(--text-muted); }
	@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.3} }
	.loading-row { color: var(--text-muted); padding: 1rem 0; }
	.error-card { color: var(--danger); }
	.event-feed { display: flex; flex-direction: column; gap: 0.5rem; }
	.event-item { display: flex; gap: 0.75rem; align-items: center; background: var(--card); border: 1px solid var(--border); border-radius: var(--radius); padding: 0.5rem 0.75rem; }
	.event-time { font-size: 0.75rem; color: var(--text-muted); white-space: nowrap; }
	.event-status { font-size: 0.8rem; font-weight: 600; }
	.status-created  { color: var(--warn); }
	.status-approved { color: var(--success); }
	.status-declined { color: var(--danger); }
	.event-total { flex: 1; text-align: right; font-weight: 600; }
	.event-id { font-size: 0.75rem; color: var(--text-muted); background: none; }
</style>
