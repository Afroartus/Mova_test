import { writable } from 'svelte/store';
import { db } from '$lib/db';

export interface SyncState {
	pending: number;
	syncing: boolean;
	lastSyncAt: Date | null;
	error: string | null;
}

const initial: SyncState = { pending: 0, syncing: false, lastSyncAt: null, error: null };
const { subscribe, update, set } = writable<SyncState>(initial);

export const syncStore = {
	subscribe,
	async refresh(tenantId: string) {
		const count = await db.pending_sales
			.where('synced')
			.equals(0)
			.filter((sale) => sale.tenant_id === tenantId)
			.count();
		update((s) => ({ ...s, pending: count }));
	},
	setSyncing(b: boolean) {
		update((s) => ({ ...s, syncing: b, error: null }));
	},
	onSyncDone(synced: number) {
		update((s) => ({
			...s,
			syncing: false,
			lastSyncAt: new Date(),
			pending: Math.max(0, s.pending - synced)
		}));
	},
	onSyncError(msg: string) {
		update((s) => ({ ...s, syncing: false, error: msg }));
	},
	reset() {
		set(initial);
	}
};
