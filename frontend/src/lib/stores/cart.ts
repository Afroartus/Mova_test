import { writable, derived } from 'svelte/store';
import type { Product } from '$lib/db';

export interface CartItem {
	product_id: string;
	name: string;
	price_cents: number;
	qty: number;
}

export function createCartStore() {
	const { subscribe, update, set } = writable<CartItem[]>([]);

	return {
		subscribe,
		add(product: Pick<Product, 'id' | 'name' | 'price_cents'>) {
			update((items) => {
				const existing = items.find((i) => i.product_id === product.id);
				if (existing) {
					return items.map((i) =>
						i.product_id === product.id ? { ...i, qty: i.qty + 1 } : i
					);
				}
				return [
					...items,
					{ product_id: product.id, name: product.name, price_cents: product.price_cents, qty: 1 }
				];
			});
		},
		remove(product_id: string) {
			update((items) => items.filter((i) => i.product_id !== product_id));
		},
		clear() {
			set([]);
		}
	};
}

export const cartStore = createCartStore();

export const cartTotal = derived(cartStore, ($cart) =>
	$cart.reduce((sum, item) => sum + item.price_cents * item.qty, 0)
);
