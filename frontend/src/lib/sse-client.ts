import { tenantHeaders } from '$lib/api/client';

export interface SSEEvent {
	type: string;
	data: string;
}

/**
 * Async generator that reads an SSE stream from a fetch response.
 * Uses fetch instead of native EventSource because the backend needs the
 * `X-Tenant-Id` header, which EventSource cannot send.
 */
export async function* createSSEStream(
	url: string,
	tenantId: string,
	signal: AbortSignal
): AsyncGenerator<SSEEvent> {
	const response = await fetch(url, {
		headers: { Accept: 'text/event-stream', ...tenantHeaders(tenantId) },
		signal
	});

	if (!response.ok || !response.body) {
		throw new Error(`SSE HTTP ${response.status}`);
	}

	const reader = response.body.getReader();
	const decoder = new TextDecoder();
	let buffer = '';
	let eventType = 'message';
	let data: string[] = [];

	try {
		while (true) {
			const { done, value } = await reader.read();
			if (done) break;

			buffer += decoder.decode(value, { stream: true });

			let idx: number;
			while ((idx = buffer.indexOf('\n')) !== -1) {
				const line = buffer.slice(0, idx).replace(/\r$/, '');
				buffer = buffer.slice(idx + 1);

				if (line === '') {
					if (data.length > 0) {
						yield { type: eventType, data: data.join('\n') };
					}
					eventType = 'message';
					data = [];
				} else if (line.startsWith(':')) {
					// Comentario SSE (heartbeat `: ping`): solo mantiene viva la conexión.
				} else if (line.startsWith('event:')) {
					eventType = line.slice(6).trim();
				} else if (line.startsWith('data:')) {
					data.push(line.slice(5).replace(/^ /, ''));
				}
				// `id:` y `retry:` no se usan: al reconectar llega un snapshot nuevo.
			}
		}
	} finally {
		reader.releaseLock();
	}
}

export interface ReconnectHooks {
	/** Se llama antes de esperar para reconectar (stream cerrado o caído). */
	onRetry?: (delayMs: number) => void;
}

/**
 * Connects to an SSE endpoint and calls onEvent for each event.
 * Auto-reconnects with exponential backoff until signal is aborted — also when
 * the server closes the stream cleanly, so a restart of the API is recovered.
 */
export async function streamWithReconnect(
	url: string,
	tenantId: string,
	onEvent: (event: SSEEvent) => void,
	signal: AbortSignal,
	hooks: ReconnectHooks = {}
): Promise<void> {
	let delay = 1000;

	while (!signal.aborted) {
		try {
			for await (const event of createSSEStream(url, tenantId, signal)) {
				onEvent(event);
				delay = 1000; // reset backoff on successful message
			}
		} catch {
			// red caída o HTTP no-ok: se reintenta abajo
		}
		if (signal.aborted) break;
		hooks.onRetry?.(delay);
		await new Promise<void>((resolve) => {
			const t = setTimeout(resolve, delay);
			signal.addEventListener('abort', () => { clearTimeout(t); resolve(); }, { once: true });
		});
		delay = Math.min(delay * 2, 30_000);
	}
}
