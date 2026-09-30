import { get } from 'svelte/store';
import { auth } from '$lib/stores/auth';

/**
 * Base de la API. Vacía por defecto: en dev el proxy de Vite reenvía `/v1` y
 * `/health` al backend (mismo origen, sin CORS). Si el front se sirve desde
 * otro origen, definir `VITE_API_BASE_URL` (p. ej. `http://localhost:8000`).
 */
export const API_BASE: string = import.meta.env.VITE_API_BASE_URL ?? '';

/** Header de aislamiento multi-tenant que exige el backend. */
export const TENANT_HEADER = 'X-Tenant-Id';

export function tenantHeaders(tenantId: string): Record<string, string> {
	return tenantId ? { [TENANT_HEADER]: tenantId } : {};
}

export class ApiError extends Error {
	constructor(
		public readonly status: number,
		message: string
	) {
		super(message);
		this.name = 'ApiError';
	}
}

/** FastAPI responde `{"detail": "..."}` o `{"detail": [{msg, loc}, ...]}` en 422. */
function errorMessage(status: number, text: string): string {
	try {
		const body = JSON.parse(text) as { detail?: unknown };
		if (typeof body.detail === 'string') return body.detail;
		if (Array.isArray(body.detail)) {
			return body.detail
				.map((d: { msg?: string; loc?: unknown[] }) =>
					d.loc ? `${d.loc.slice(1).join('.')}: ${d.msg}` : String(d.msg)
				)
				.join('; ');
		}
	} catch {
		/* no es JSON */
	}
	return text || `HTTP ${status}`;
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
	const headers: Record<string, string> = {
		'Content-Type': 'application/json',
		...tenantHeaders(get(auth))
	};

	const res = await fetch(`${API_BASE}${path}`, {
		method,
		headers,
		body: body !== undefined ? JSON.stringify(body) : undefined
	});

	if (!res.ok) {
		const text = await res.text().catch(() => '');
		throw new ApiError(res.status, errorMessage(res.status, text));
	}

	if (res.status === 204) return undefined as T;
	return res.json();
}

export const api = {
	get: <T>(path: string) => request<T>('GET', path),
	post: <T>(path: string, body: unknown) => request<T>('POST', path, body),
	patch: <T>(path: string, body: unknown) => request<T>('PATCH', path, body)
};
