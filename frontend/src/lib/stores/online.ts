import { readable } from 'svelte/store';

export const online = readable<boolean>(
	typeof navigator !== 'undefined' ? navigator.onLine : true,
	(set) => {
		if (typeof window === 'undefined') return;

		const handleOnline  = () => set(true);
		const handleOffline = () => set(false);

		window.addEventListener('online',  handleOnline);
		window.addEventListener('offline', handleOffline);

		return () => {
			window.removeEventListener('online',  handleOnline);
			window.removeEventListener('offline', handleOffline);
		};
	}
);
