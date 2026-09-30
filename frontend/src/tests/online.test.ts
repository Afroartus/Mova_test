import { describe, it, expect, vi } from 'vitest';
import { get } from 'svelte/store';

describe('online store', () => {
	it('reflects navigator.onLine initial value', async () => {
		vi.stubGlobal('navigator', { onLine: true });
		vi.stubGlobal('window', {
			addEventListener: vi.fn(),
			removeEventListener: vi.fn()
		});

		const { online } = await import('../lib/stores/online');
		expect(get(online)).toBe(true);
	});

	it('updates when online/offline events fire', async () => {
		const listeners: Record<string, EventListener> = {};

		vi.stubGlobal('navigator', { onLine: true });
		vi.stubGlobal('window', {
			addEventListener: (event: string, fn: EventListener) => { listeners[event] = fn; },
			removeEventListener: vi.fn()
		});

		// Re-import to get fresh store with our mock
		vi.resetModules();
		const { online } = await import('../lib/stores/online');

		expect(get(online)).toBe(true);

		// Simulate going offline
		listeners['offline']?.(new Event('offline'));
		expect(get(online)).toBe(false);

		// Simulate going online
		listeners['online']?.(new Event('online'));
		expect(get(online)).toBe(true);
	});
});
