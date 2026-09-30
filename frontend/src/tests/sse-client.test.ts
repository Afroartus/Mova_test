import { describe, it, expect, vi } from 'vitest';
import { createSSEStream, type SSEEvent } from '../lib/sse-client';

function makeReadableStream(chunks: string[]): ReadableStream<Uint8Array> {
	const encoder = new TextEncoder();
	return new ReadableStream({
		start(controller) {
			for (const chunk of chunks) {
				controller.enqueue(encoder.encode(chunk));
			}
			controller.close();
		}
	});
}

function makeFetchResponse(body: ReadableStream<Uint8Array>) {
	return Promise.resolve({
		ok: true,
		status: 200,
		body
	} as unknown as Response);
}

describe('createSSEStream', () => {
	it('parses a single event', async () => {
		const stream = makeReadableStream(['event: sale_paid\ndata: {"status":"PAID"}\n\n']);
		vi.stubGlobal('fetch', vi.fn().mockReturnValue(makeFetchResponse(stream)));

		const controller = new AbortController();
		const events = [];
		for await (const ev of createSSEStream('http://api/stream', 'token', controller.signal)) {
			events.push(ev);
		}

		expect(events).toHaveLength(1);
		expect(events[0].type).toBe('sale_paid');
		expect(events[0].data).toBe('{"status":"PAID"}');
	});

	it('parses multiple events', async () => {
		const sseText = [
			'event: connected\ndata: {}\n\n',
			'event: sale_paid\ndata: {"id":"s1"}\n\n',
			'event: sale_paid\ndata: {"id":"s2"}\n\n'
		];
		const stream = makeReadableStream(sseText);
		vi.stubGlobal('fetch', vi.fn().mockReturnValue(makeFetchResponse(stream)));

		const controller = new AbortController();
		const events = [];
		for await (const ev of createSSEStream('http://api/stream', 'token', controller.signal)) {
			events.push(ev);
		}

		expect(events).toHaveLength(3);
		expect(events[0].type).toBe('connected');
		expect(events[1].type).toBe('sale_paid');
		expect(events[1].data).toBe('{"id":"s1"}');
		expect(events[2].data).toBe('{"id":"s2"}');
	});

	it('handles chunked delivery (split across chunks)', async () => {
		// SSE data split across two network chunks
		const stream = makeReadableStream([
			'event: sale_paid\ndata',
			': {"amount":500}\n\n'
		]);
		vi.stubGlobal('fetch', vi.fn().mockReturnValue(makeFetchResponse(stream)));

		const controller = new AbortController();
		const events = [];
		for await (const ev of createSSEStream('http://api/stream', 'token', controller.signal)) {
			events.push(ev);
		}

		expect(events).toHaveLength(1);
		expect(events[0].data).toBe('{"amount":500}');
	});

	it('sends X-Tenant-Id header', async () => {
		const stream = makeReadableStream([]);
		const mockFetch = vi.fn().mockReturnValue(makeFetchResponse(stream));
		vi.stubGlobal('fetch', mockFetch);

		const controller = new AbortController();
		// eslint-disable-next-line @typescript-eslint/no-unused-vars
		for await (const _ of createSSEStream('http://api/stream', 'my-token', controller.signal)) {
			// empty
		}

		const [, init] = mockFetch.mock.calls[0] as [string, RequestInit];
		const headers = init.headers as Record<string, string>;
		expect(headers['X-Tenant-Id']).toBe('my-token');
	});

	it('stops immediately on abort signal', async () => {
		const controller = new AbortController();
		controller.abort(); // Already aborted

		vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new DOMException('Aborted', 'AbortError')));

		const events = [];
		try {
			for await (const ev of createSSEStream('http://api/stream', 'token', controller.signal)) {
				events.push(ev);
			}
		} catch {
			// Expected: fetch throws on abort
		}

		expect(events).toHaveLength(0);
	});

	it('throws on non-ok response so the caller backs off', async () => {
		vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 422, body: null }));

		const controller = new AbortController();
		const events: SSEEvent[] = [];
		await expect(async () => {
			for await (const ev of createSSEStream('http://api/stream', 'bad-tenant', controller.signal)) {
				events.push(ev);
			}
		}).rejects.toThrow('SSE HTTP 422');
		expect(events).toHaveLength(0);
	});

	it('parses the backend frames (id, CRLF, heartbeat comments)', async () => {
		const stream = makeReadableStream([
			'id: 0\r\nevent: snapshot\r\ndata: {"total_sales":1}\r\n\r\n',
			': ping\n\n',
			'id: 7\nevent: sale\ndata: {"id":"s1","status":"approved"}\n\n'
		]);
		vi.stubGlobal('fetch', vi.fn().mockReturnValue(makeFetchResponse(stream)));

		const events: SSEEvent[] = [];
		for await (const ev of createSSEStream('http://api/stream', 't', new AbortController().signal)) {
			events.push(ev);
		}

		expect(events).toEqual([
			{ type: 'snapshot', data: '{"total_sales":1}' },
			{ type: 'sale', data: '{"id":"s1","status":"approved"}' }
		]);
	});
});
