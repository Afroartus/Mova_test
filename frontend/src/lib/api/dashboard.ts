import { api } from './client';
import type { SaleStatus } from './sales';

/** `TodayAggregate` del backend: día UTC, montos como string decimal. */
export interface DashboardReport {
	date: string;
	timezone: string;
	/** Siempre igual a created + approved + declined. */
	total_sales: number;
	counts: Record<SaleStatus, number>;
	amounts: Record<SaleStatus, string>;
	approved_amount: string;
}

/** Frame `sale` del SSE: snapshot de la venta en el momento del cambio. */
export interface SaleEvent {
	id: string;
	status: SaleStatus;
	total: string;
	lines: Array<{ product_id: string; price: string; quantity: number }>;
	created_at: string;
}

export function fetchTodayReport(): Promise<DashboardReport> {
	return api.get<DashboardReport>('/v1/dashboard/today');
}
