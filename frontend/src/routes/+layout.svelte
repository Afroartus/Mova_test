<script lang="ts">
	import '../app.css';
	import { page } from '$app/stores';
	import { auth, isTenantId } from '$lib/stores/auth';
	import { online } from '$lib/stores/online';
	import { cartStore } from '$lib/stores/cart';
	import { dashboardStore } from '$lib/stores/dashboard';
	import { ApiError } from '$lib/api/client';
	import { createTenant, getTenant, listTenants, type Tenant } from '$lib/api/tenants';

	let tenants: Tenant[] = [];
	let tenantsLoaded = false;
	let selectedId = '';
	let manualId = '';
	let newName = '';
	let busy = false;
	let loginError = '';
	let tenantName = '';

	// El carrito y el dashboard son del tenant: no pueden pasar al siguiente.
	function logout() {
		cartStore.clear();
		dashboardStore.reset();
		tenantName = '';
		auth.logout();
	}

	async function loadTenants() {
		try {
			tenants = await listTenants();
			selectedId = tenants[0]?.id ?? '';
		} catch {
			tenants = [];
		} finally {
			tenantsLoaded = true;
		}
	}

	async function enter(id: string) {
		const tenantId = id.trim();
		if (!isTenantId(tenantId)) {
			loginError = 'El Tenant ID debe ser un UUID válido';
			return;
		}
		busy = true;
		loginError = '';
		try {
			await getTenant(tenantId);
			auth.login(tenantId);
		} catch (e) {
			if (e instanceof ApiError && e.status === 404) {
				loginError = 'Ese tenant no existe';
			} else if (e instanceof ApiError) {
				loginError = e.message;
			} else {
				// Sin red: se permite entrar con el catálogo local (modo offline).
				auth.login(tenantId);
			}
		} finally {
			busy = false;
		}
	}

	async function createAndEnter() {
		if (!newName.trim()) return;
		busy = true;
		loginError = '';
		try {
			const tenant = await createTenant(newName.trim());
			newName = '';
			auth.login(tenant.id);
		} catch (e) {
			loginError = e instanceof Error ? e.message : 'No se pudo crear el tenant';
		} finally {
			busy = false;
		}
	}

	// Al salir se vuelve a pedir la lista, que puede traer tenants nuevos.
	$: if (!$auth && !tenantsLoaded) loadTenants();
	$: if ($auth) {
		tenantsLoaded = false;
		getTenant($auth)
			.then((t) => (tenantName = t.name))
			.catch(() => (tenantName = ''));
	}
</script>

{#if !$auth}
	<div class="login-screen">
		<div class="card login-card">
			<h1>MovaPay</h1>
			<p>Elige el comercio (tenant) con el que vas a trabajar</p>

			{#if tenants.length > 0}
				<form on:submit|preventDefault={() => enter(selectedId)}>
					<select bind:value={selectedId} style="width:100%">
						{#each tenants as t}
							<option value={t.id}>{t.name}</option>
						{/each}
					</select>
					<button type="submit" class="primary" style="margin-top:0.75rem;width:100%" disabled={busy}>
						Entrar
					</button>
				</form>
				<div class="divider">o</div>
			{/if}

			<form on:submit|preventDefault={createAndEnter}>
				<input bind:value={newName} placeholder="Nombre del nuevo comercio" autocomplete="off" />
				<button type="submit" class="primary" style="margin-top:0.75rem;width:100%" disabled={busy || !newName.trim()}>
					Crear comercio y entrar
				</button>
			</form>

			<details class="manual">
				<summary>Tengo un Tenant ID</summary>
				<form on:submit|preventDefault={() => enter(manualId)}>
					<input
						bind:value={manualId}
						placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
						autocomplete="off"
					/>
					<button type="submit" style="margin-top:0.5rem;width:100%" disabled={busy}>Entrar</button>
				</form>
			</details>

			{#if loginError}<p class="login-error">{loginError}</p>{/if}
		</div>
	</div>
{:else}
<div class="app-shell">
		<header class="topbar">
			<span class="brand">MovaPay{#if tenantName}<small> · {tenantName}</small>{/if}</span>
			<div class="topbar-right">
				<span class="badge {$online ? 'online' : 'offline'}">
					{$online ? 'En línea' : 'Sin conexión'}
				</span>
				<button on:click={logout} style="background:transparent;color:#fff;padding:0.25rem 0.5rem;font-size:0.8rem">
					Salir
				</button>
			</div>
		</header>

		<nav class="bottom-nav">
			<a href="/pos"       class:active={$page.url.pathname.startsWith('/pos')}>
				🛒 POS
			</a>
			<a href="/dashboard" class:active={$page.url.pathname.startsWith('/dashboard')}>
				📊 Dashboard
			</a>
		</nav>

		<main class="content">
			<slot />
		</main>
	</div>
{/if}

<style>
	.login-screen {
		min-height: 100dvh;
		display: flex;
		align-items: center;
		justify-content: center;
		padding: 1rem;
	}
	.login-card {
		width: 100%;
		max-width: 400px;
		text-align: center;
	}
	.login-card h1 { margin: 0 0 0.5rem; font-size: 2rem; color: var(--brand); }
	.login-card p  { color: var(--text-muted); margin: 0 0 1.5rem; }
	.divider { color: var(--text-muted); font-size: 0.8rem; margin: 1rem 0; }
	.manual { margin-top: 1rem; text-align: left; font-size: 0.85rem; color: var(--text-muted); }
	.manual summary { cursor: pointer; }
	.manual form { margin-top: 0.5rem; }
	.login-error { color: var(--danger) !important; font-size: 0.85rem; margin: 1rem 0 0 !important; }
	.brand small { font-weight: 400; opacity: 0.85; }

	.app-shell {
		display: flex;
		flex-direction: column;
		min-height: 100dvh;
	}
	.topbar {
		background: var(--brand);
		color: #fff;
		padding: 0.75rem 1rem;
		display: flex;
		align-items: center;
		justify-content: space-between;
		position: sticky;
		top: 0;
		z-index: 10;
	}
	.topbar-right {
		display: flex;
		align-items: center;
		gap: 0.5rem;
	}
	.brand { font-weight: 700; font-size: 1.1rem; }

	.content {
		flex: 1;
		padding: 1rem;
		padding-bottom: 5rem;
		max-width: 640px;
		width: 100%;
		margin: 0 auto;
	}

	.bottom-nav {
		position: fixed;
		bottom: 0;
		left: 0;
		right: 0;
		background: var(--card);
		border-top: 1px solid var(--border);
		display: flex;
		z-index: 10;
	}
	.bottom-nav a {
		flex: 1;
		text-align: center;
		padding: 0.75rem 0.5rem;
		text-decoration: none;
		color: var(--text-muted);
		font-size: 0.875rem;
		font-weight: 500;
		transition: color 0.15s;
	}
	.bottom-nav a.active {
		color: var(--brand);
		font-weight: 700;
	}
</style>
