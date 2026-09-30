/**
 * El backend maneja dinero como `Numeric(12,2)` y lo serializa como string
 * decimal (`"10.50"`), nunca como número. En el front se opera en centavos
 * enteros para no arrastrar errores de coma flotante.
 */

export function toCents(decimal: string | number): number {
	return Math.round(Number(decimal) * 100);
}

export function toDecimal(cents: number): string {
	return (cents / 100).toFixed(2);
}

export function formatMoney(cents: number): string {
	return `$ ${(cents / 100).toLocaleString('es-CO', {
		minimumFractionDigits: 0,
		maximumFractionDigits: 2
	})}`;
}
