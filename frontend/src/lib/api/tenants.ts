import { api } from './client';

export interface Tenant {
	id: string;
	name: string;
	created_at: string;
	update_at: string | null;
}

/** Único endpoint sin `X-Tenant-Id`: crea el tenant. */
export function createTenant(name: string): Promise<Tenant> {
	return api.post<Tenant>('/v1/tenants', { name });
}

export function listTenants(): Promise<Tenant[]> {
	return api.get<Tenant[]>('/v1/tenants?limit=200');
}

export function getTenant(id: string): Promise<Tenant> {
	return api.get<Tenant>(`/v1/tenants/${id}`);
}
