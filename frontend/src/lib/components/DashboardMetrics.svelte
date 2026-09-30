<script lang="ts">
	import type { DashboardReport } from '$lib/api/dashboard';
	import { formatMoney, toCents } from '$lib/money';
	export let report: DashboardReport;
</script>

<div class="stats-grid">
	<div class="card stat">
		<div class="stat-label">Ventas totales</div>
		<div class="stat-value">{report.total_sales}</div>
	</div>
	<div class="card stat">
		<div class="stat-label">Aprobadas</div>
		<div class="stat-value">{report.counts.approved}</div>
	</div>
	<div class="card stat">
		<div class="stat-label">Ingresos aprobados</div>
		<div class="stat-value">{formatMoney(toCents(report.approved_amount))}</div>
	</div>
	<div class="card stat declined">
		<div class="stat-label">Rechazadas</div>
		<div class="stat-value">{report.counts.declined}</div>
		<div class="stat-note">{formatMoney(toCents(report.amounts.declined))}</div>
	</div>
	{#if report.counts.created > 0}
		<div class="card stat pending">
			<div class="stat-label">Pago sin resolver</div>
			<div class="stat-value">{report.counts.created}</div>
			<div class="stat-note">{formatMoney(toCents(report.amounts.created))} · verificar con cliente</div>
		</div>
	{/if}
</div>
<p class="date-label">Fecha: {report.date} ({report.timezone})</p>

<style>
	.stats-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); gap: 0.75rem; }
	.stat { text-align: center; padding: 1rem; }
	.stat-label { font-size: 0.8rem; color: var(--text-muted); margin-bottom: 0.25rem; }
	.stat-value { font-size: 1.75rem; font-weight: 700; color: var(--brand); }
	.stat.declined .stat-value { color: var(--danger); }
	.stat.pending .stat-value { color: var(--warn); }
	.stat-note { font-size: 0.75rem; color: var(--text-muted); margin-top: 0.25rem; }
	.stat.pending .stat-note { color: var(--warn); }
	.date-label { font-size: 0.8rem; color: var(--text-muted); margin-top: 0.5rem; }
</style>
