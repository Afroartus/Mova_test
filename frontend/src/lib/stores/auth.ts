import { writable } from 'svelte/store';

/**
 * Tenant activo. El backend no tiene usuarios ni sesiones: el tenant viaja en
 * cada request en el header `X-Tenant-Id`, así que "iniciar sesión" es solo
 * elegir con qué tenant trabajar.
 */
const STORAGE_KEY = 'movapay_tenant_id';

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function isTenantId(value: string): boolean {
	return UUID_RE.test(value.trim());
}

function createAuthStore() {
	const stored = typeof localStorage !== 'undefined'
		? (localStorage.getItem(STORAGE_KEY) ?? '')
		: '';

	const { subscribe, set } = writable<string>(stored);

	return {
		subscribe,
		login(tenantId: string) {
			const trimmed = tenantId.trim();
			if (typeof localStorage !== 'undefined') {
				localStorage.setItem(STORAGE_KEY, trimmed);
			}
			set(trimmed);
		},
		logout() {
			if (typeof localStorage !== 'undefined') {
				localStorage.removeItem(STORAGE_KEY);
			}
			set('');
		}
	};
}

export const auth = createAuthStore();
