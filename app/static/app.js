const state = {
  token: localStorage.getItem("erp_token") || null,
  user: null,
  products: [],
  orders: [],
};

const $ = (id) => document.getElementById(id);

function showMessage(el, msg, isError = true) {
  el.textContent = msg;
  el.classList.remove("hidden");
  if (el.id === "dashboard-alert") {
    el.className = isError
      ? "p-3.5 rounded-lg border text-sm font-medium bg-rose-500/15 border-rose-500/40 text-rose-300"
      : "p-3.5 rounded-lg border text-sm font-medium bg-emerald-500/15 border-emerald-500/40 text-emerald-300";
  }
}

function hideEl(el) {
  el.classList.add("hidden");
  el.textContent = "";
}

async function apiRequest(path, options = {}) {
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  if (state.token) {
    headers["Authorization"] = `Bearer ${state.token}`;
  }
  const resp = await fetch(path, { ...options, headers });
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    const detail = Array.isArray(data.detail)
      ? data.detail.map((d) => d.msg).join(", ")
      : data.detail || `Error HTTP ${resp.status}`;
    throw new Error(detail);
  }
  return data;
}

function switchAuthTab(mode) {
  hideEl($("auth-error"));
  hideEl($("auth-success"));
  if (mode === "login") {
    $("login-form").classList.remove("hidden");
    $("register-form").classList.add("hidden");
    $("tab-login").className = "flex-1 py-2.5 text-sm font-medium border-b-2 border-indigo-500 text-indigo-400";
    $("tab-register").className = "flex-1 py-2.5 text-sm font-medium border-b-2 border-transparent text-slate-400 hover:text-slate-200";
  } else {
    $("login-form").classList.add("hidden");
    $("register-form").classList.remove("hidden");
    $("tab-register").className = "flex-1 py-2.5 text-sm font-medium border-b-2 border-indigo-500 text-indigo-400";
    $("tab-login").className = "flex-1 py-2.5 text-sm font-medium border-b-2 border-transparent text-slate-400 hover:text-slate-200";
  }
}

function renderProducts() {
  const tbody = $("products-tbody");
  tbody.innerHTML = "";
  const select = $("order-product-select");
  select.innerHTML = "";

  if (state.products.length === 0) {
    tbody.innerHTML = `<tr><td colspan="7" class="px-4 py-6 text-center text-slate-500">No se encontraron productos</td></tr>`;
    return;
  }

  for (const p of state.products) {
    const opt = document.createElement("option");
    opt.value = p.id;
    opt.textContent = `${p.sku} — ${p.name} (Stock: ${p.stock})`;
    select.appendChild(opt);

    const tr = document.createElement("tr");
    tr.setAttribute("data-testid", `product-row-${p.sku}`);
    tr.className = "hover:bg-slate-800/40";

    const stockBadge = p.low_stock
      ? `<span class="px-2 py-0.5 rounded text-xs font-semibold bg-amber-500/20 text-amber-300">Bajo (${p.stock}/${p.min_stock})</span>`
      : `<span class="text-slate-200 font-medium">${p.stock}</span>`;

    const statusBadge = p.is_active
      ? `<span class="px-2 py-0.5 rounded text-xs bg-emerald-500/20 text-emerald-300">Activo</span>`
      : `<span class="px-2 py-0.5 rounded text-xs bg-slate-700 text-slate-400">Inactivo</span>`;

    const canEdit = state.user && (state.user.role === "admin" || state.user.role === "operador");
    const canDelete = state.user && state.user.role === "admin";

    tr.innerHTML = `
      <td class="px-4 py-3 font-mono text-xs text-indigo-300">${p.sku}</td>
      <td class="px-4 py-3 font-medium text-white">${p.name}</td>
      <td class="px-4 py-3 capitalize text-slate-300">${p.category}</td>
      <td class="px-4 py-3 text-slate-200">$${p.price.toFixed(2)}</td>
      <td class="px-4 py-3">${stockBadge}</td>
      <td class="px-4 py-3">${statusBadge}</td>
      <td class="px-4 py-3 text-right space-x-1">
        ${canEdit ? `<button data-testid="order-product-${p.sku}" class="px-2 py-1 text-xs rounded bg-emerald-600/20 text-emerald-300 hover:bg-emerald-600/30">Mover</button>` : ""}
        ${canEdit ? `<button data-testid="edit-product-${p.sku}" class="px-2 py-1 text-xs rounded bg-indigo-600/20 text-indigo-300 hover:bg-indigo-600/30">Editar</button>` : ""}
        ${canDelete ? `<button data-testid="delete-product-${p.sku}" class="px-2 py-1 text-xs rounded bg-rose-600/20 text-rose-300 hover:bg-rose-600/30">Eliminar</button>` : ""}
      </td>
    `;

    if (canEdit) {
      tr.querySelector(`[data-testid="edit-product-${p.sku}"]`).addEventListener("click", () => openProductModal(p));
      tr.querySelector(`[data-testid="order-product-${p.sku}"]`).addEventListener("click", () => openOrderModal(p.id));
    }
    if (canDelete) {
      tr.querySelector(`[data-testid="delete-product-${p.sku}"]`).addEventListener("click", () => deleteProduct(p.id));
    }

    tbody.appendChild(tr);
  }
}

function renderOrders() {
  const tbody = $("orders-tbody");
  tbody.innerHTML = "";
  if (state.orders.length === 0) {
    tbody.innerHTML = `<tr><td colspan="8" class="px-4 py-6 text-center text-slate-500">Sin movimientos registrados</td></tr>`;
    return;
  }
  for (const o of state.orders) {
    const tr = document.createElement("tr");
    tr.setAttribute("data-testid", `order-row-${o.id}`);
    const typeBadge = o.order_type === "entrada"
      ? `<span class="px-2 py-0.5 rounded text-xs bg-emerald-500/20 text-emerald-300">Entrada</span>`
      : `<span class="px-2 py-0.5 rounded text-xs bg-rose-500/20 text-rose-300">Salida</span>`;
    tr.innerHTML = `
      <td class="px-4 py-3 text-slate-400">#${o.id}</td>
      <td class="px-4 py-3">${typeBadge}</td>
      <td class="px-4 py-3 text-white">${o.product_sku} — ${o.product_name}</td>
      <td class="px-4 py-3">${o.quantity}</td>
      <td class="px-4 py-3">$${o.subtotal.toFixed(2)}</td>
      <td class="px-4 py-3 text-emerald-300">-$${o.discount_amount.toFixed(2)} (${(o.discount_rate * 100).toFixed(0)}%)</td>
      <td class="px-4 py-3">$${o.tax_amount.toFixed(2)}</td>
      <td class="px-4 py-3 font-semibold text-white">$${o.total.toFixed(2)}</td>
    `;
    tbody.appendChild(tr);
  }
}

async function loadDashboardData() {
  const params = new URLSearchParams();
  const search = $("filter-search").value.trim();
  const category = $("filter-category").value;
  const minPrice = $("filter-min-price").value;
  const maxPrice = $("filter-max-price").value;
  const lowStock = $("filter-low-stock").checked;

  if (search) params.set("search", search);
  if (category) params.set("category", category);
  if (minPrice) params.set("min_price", minPrice);
  if (maxPrice) params.set("max_price", maxPrice);
  if (lowStock) params.set("low_stock_only", "true");

  const qs = params.toString() ? `?${params.toString()}` : "";
  const [products, alerts, orders] = await Promise.all([
    apiRequest(`/api/products${qs}`),
    apiRequest("/api/products/alerts/low-stock"),
    apiRequest("/api/orders"),
  ]);
  state.products = products;
  state.orders = orders;
  $("low-stock-badge").textContent = `Alertas Stock Bajo: ${alerts.length}`;
  renderProducts();
  renderOrders();
}

function openProductModal(product = null) {
  hideEl($("product-modal-error"));
  if (product) {
    $("product-modal-title").textContent = `Editar ${product.sku}`;
    $("product-edit-id").value = product.id;
    $("product-sku").value = product.sku;
    $("product-name").value = product.name;
    $("product-description").value = product.description || "";
    $("product-category").value = product.category;
    $("product-price").value = product.price;
    $("product-stock").value = product.stock;
    $("product-min-stock").value = product.min_stock;
    $("product-active").checked = product.is_active;
  } else {
    $("product-modal-title").textContent = "Nuevo Producto";
    $("product-form").reset();
    $("product-edit-id").value = "";
    $("product-active").checked = true;
    $("product-min-stock").value = "5";
    $("product-stock").value = "0";
  }
  $("product-modal").classList.remove("hidden");
}

function openOrderModal(productId = null) {
  hideEl($("order-modal-error"));
  $("order-form").reset();
  $("order-quantity").value = "1";
  if (productId) {
    $("order-product-select").value = String(productId);
  }
  $("order-modal").classList.remove("hidden");
}

async function deleteProduct(id) {
  try {
    await apiRequest(`/api/products/${id}`, { method: "DELETE" });
    showMessage($("dashboard-alert"), "Producto eliminado correctamente", false);
    await loadDashboardData();
  } catch (err) {
    showMessage($("dashboard-alert"), err.message, true);
  }
}

async function enterDashboard() {
  try {
    state.user = await apiRequest("/api/auth/me");
    $("user-badge").textContent = `${state.user.username} (${state.user.role})`;
    $("auth-section").classList.add("hidden");
    $("dashboard-section").classList.remove("hidden");

    const isAuditor = state.user.role === "auditor";
    $("open-create-product-btn").classList.toggle("hidden", isAuditor);
    $("open-order-modal-btn").classList.toggle("hidden", isAuditor);

    await loadDashboardData();
  } catch {
    logout();
  }
}

function logout() {
  state.token = null;
  state.user = null;
  localStorage.removeItem("erp_token");
  $("dashboard-section").classList.add("hidden");
  $("auth-section").classList.remove("hidden");
}

// Event listeners
$("tab-login").addEventListener("click", () => switchAuthTab("login"));
$("tab-register").addEventListener("click", () => switchAuthTab("register"));
$("logout-btn").addEventListener("click", logout);

$("login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  hideEl($("auth-error"));
  try {
    const res = await apiRequest("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({
        username: $("login-username").value,
        password: $("login-password").value,
      }),
    });
    state.token = res.access_token;
    localStorage.setItem("erp_token", res.access_token);
    await enterDashboard();
  } catch (err) {
    showMessage($("auth-error"), err.message, true);
  }
});

$("register-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  hideEl($("auth-error"));
  hideEl($("auth-success"));
  try {
    await apiRequest("/api/auth/register", {
      method: "POST",
      body: JSON.stringify({
        username: $("register-username").value,
        email: $("register-email").value,
        password: $("register-password").value,
        role: $("register-role").value,
      }),
    });
    switchAuthTab("login");
    showMessage($("auth-success"), "Cuenta creada. Ahora puedes iniciar sesión.", false);
  } catch (err) {
    showMessage($("auth-error"), err.message, true);
  }
});

$("open-create-product-btn").addEventListener("click", () => openProductModal(null));
$("product-cancel").addEventListener("click", () => $("product-modal").classList.add("hidden"));
$("open-order-modal-btn").addEventListener("click", () => openOrderModal(null));
$("order-cancel").addEventListener("click", () => $("order-modal").classList.add("hidden"));

$("filter-apply-btn").addEventListener("click", () => loadDashboardData());
$("filter-reset-btn").addEventListener("click", () => {
  $("filter-search").value = "";
  $("filter-category").value = "";
  $("filter-min-price").value = "";
  $("filter-max-price").value = "";
  $("filter-low-stock").checked = false;
  loadDashboardData();
});

$("product-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  hideEl($("product-modal-error"));
  const editId = $("product-edit-id").value;
  const payload = {
    sku: $("product-sku").value,
    name: $("product-name").value,
    description: $("product-description").value,
    category: $("product-category").value,
    price: parseFloat($("product-price").value),
    stock: parseInt($("product-stock").value, 10),
    min_stock: parseInt($("product-min-stock").value, 10),
    is_active: $("product-active").checked,
  };
  try {
    if (editId) {
      await apiRequest(`/api/products/${editId}`, { method: "PUT", body: JSON.stringify(payload) });
      showMessage($("dashboard-alert"), "Producto actualizado correctamente", false);
    } else {
      await apiRequest("/api/products", { method: "POST", body: JSON.stringify(payload) });
      showMessage($("dashboard-alert"), "Producto creado correctamente", false);
    }
    $("product-modal").classList.add("hidden");
    await loadDashboardData();
  } catch (err) {
    showMessage($("product-modal-error"), err.message, true);
  }
});

$("order-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  hideEl($("order-modal-error"));
  const payload = {
    product_id: parseInt($("order-product-select").value, 10),
    order_type: $("order-type").value,
    quantity: parseInt($("order-quantity").value, 10),
    notes: $("order-notes").value,
  };
  try {
    await apiRequest("/api/orders", { method: "POST", body: JSON.stringify(payload) });
    $("order-modal").classList.add("hidden");
    showMessage($("dashboard-alert"), "Movimiento registrado exitosamente", false);
    await loadDashboardData();
  } catch (err) {
    showMessage($("order-modal-error"), err.message, true);
  }
});

if (state.token) {
  enterDashboard();
}
