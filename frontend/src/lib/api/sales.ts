import { api } from './client';

/** Estado persistido. `approved` y `declined` son terminales. */
export type SaleStatus = 'created' | 'approved' | 'declined';

/**
 * Lo que se reporta en `/pay`. `timeout` (y `created`) no se persisten: la
 * venta se queda en `created`, es decir, "pago sin resolver".
 */
export type PayOutcome = 'approved' | 'declined' | 'timeout';

/**
 * Una línea por producto (el backend rechaza productos repetidos); las
 * unidades van en `quantity`. `price` es el precio unitario y es opcional:
 * sin él el servidor congela el precio vigente del producto.
 */
export interface SaleLineInput {
	product_id: string;
	quantity: number;
	price?: string;
}

export interface CreateSaleInput {
	products: SaleLineInput[];
}

/** `SaleOut` del backend. Montos como string decimal. */
export interface RemoteSale {
	id: string;
	status: SaleStatus;
	total: string;
	lines: Array<{ product_id: string; price: string; quantity: number }>;
	created_at: string;
	/** false si el estado no cambió (terminal previo, `timeout` o `created`). */
	applied: boolean;
}

export function createSale(input: CreateSaleInput): Promise<RemoteSale> {
	return api.post<RemoteSale>('/v1/sales', input);
}

export function getSale(id: string): Promise<RemoteSale> {
	return api.get<RemoteSale>(`/v1/sales/${id}`);
}

export function listSales(limit = 50): Promise<RemoteSale[]> {
	return api.get<RemoteSale[]>(`/v1/sales?limit=${limit}`);
}

export function paySale(saleId: string, outcome: PayOutcome): Promise<RemoteSale> {
	return api.post<RemoteSale>(`/v1/sales/${saleId}/pay`, { outcome });
}
