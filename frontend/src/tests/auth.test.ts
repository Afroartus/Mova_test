import { describe, it, expect, beforeEach, vi } from 'vitest';
import { get } from 'svelte/store';

// Mock localStorage before importing the store
const store: Record<string, string> = {};
vi.stubGlobal('localStorage', {
	getItem: (k: string) => store[k] ?? null,
	setItem: (k: string, v: string) => { store[k] = v; },
	removeItem: (k: string) => { delete store[k]; }
});

// Dynamic import so the mock is in place first
const { auth, isTenantId } = await import('../lib/stores/auth');

describe('auth store', () => {
	beforeEach(() => {
		auth.logout();
	});

	it('starts empty when localStorage is empty', () => {
		expect(get(auth)).toBe('');
	});

	it('login sets merchantId in store and localStorage', () => {
		auth.login('merchant-123');
		expect(get(auth)).toBe('merchant-123');
		expect(localStorage.getItem('movapay_tenant_id')).toBe('merchant-123');
	});

	it('logout clears store and localStorage', () => {
		auth.login('merchant-abc');
		auth.logout();
		expect(get(auth)).toBe('');
		expect(localStorage.getItem('movapay_tenant_id')).toBeNull();
	});

	it('login with trimmed id', () => {
		auth.login('  merchant-xyz  ');
		expect(get(auth)).toBe('merchant-xyz');
	});

	it('isTenantId accepts UUIDs only', () => {
		expect(isTenantId('11111111-1111-4111-8111-111111111111')).toBe(true);
		expect(isTenantId('  11111111-1111-4111-8111-111111111111  ')).toBe(true);
		expect(isTenantId('merchant-123')).toBe(false);
		expect(isTenantId('')).toBe(false);
	});
});
