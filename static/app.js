// ============================================================================
// Theme Management
// ============================================================================

const THEME_KEY = "sql-assistant-theme";
const themeToggle = document.getElementById("theme-toggle");
const html = document.documentElement;

function initTheme() {
  const saved = localStorage.getItem(THEME_KEY);
  const isDark = saved === "dark" || (!saved && window.matchMedia("(prefers-color-scheme: dark)").matches);
  setTheme(isDark ? "dark" : "light");
}

function setTheme(theme) {
  html.setAttribute("data-theme", theme);
  localStorage.setItem(THEME_KEY, theme);
  themeToggle.querySelector(".theme-icon").textContent = theme === "dark" ? "☀️" : "🌙";
}

themeToggle.addEventListener("click", () => {
  const current = html.getAttribute("data-theme");
  setTheme(current === "dark" ? "light" : "dark");
});

initTheme();

// ============================================================================
// Database Management
// ============================================================================

const uploadTrigger = document.getElementById("upload-trigger");
const dbUpload = document.getElementById("db-upload");
const dbList = document.getElementById("db-list");

async function loadDatabases() {
  try {
    const res = await fetch("/api/databases");
    const data = await res.json();
    renderDatabaseList(data.databases);
  } catch (err) {
    console.error("Failed to load databases:", err);
  }
}

function renderDatabaseList(databases) {
  dbList.innerHTML = "";
  
  databases.forEach((db) => {
    const item = document.createElement("div");
    item.className = `db-item ${db.active ? "active" : ""}`;
    
    const typeIcon = db.type === "sqlite" ? "🗄️" : db.type === "csv" ? "📄" : "📊";
    const typeName = db.type.charAt(0).toUpperCase() + db.type.slice(1);
    
    item.innerHTML = `
      <div class="db-item-info">
        <div class="db-item-name">${db.name}</div>
        <div class="db-item-type">${typeIcon} ${typeName}</div>
      </div>
      ${db.active ? '<div class="db-item-badge">✓ Active</div>' : ""}
      <div class="db-item-actions">
        ${db.name !== "Sample Database" ? `<button class="btn btn-icon db-delete-btn" title="Delete">🗑️</button>` : ""}
      </div>
    `;
    
    item.addEventListener("click", (e) => {
      if (!e.target.closest(".db-delete-btn")) {
        switchDatabase(db.name);
      }
    });
    
    item.querySelector(".db-delete-btn")?.addEventListener("click", (e) => {
      e.stopPropagation();
      deleteDatabase(db.name);
    });
    
    dbList.appendChild(item);
  });
}

function updateSchema(schema) {
  const schemaEl = document.getElementById("schema-content");
  if (schemaEl) schemaEl.textContent = schema;
}

async function switchDatabase(name) {
  try {
    const res = await fetch("/api/databases/switch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    });
    
    if (!res.ok) {
      const err = await res.json();
      showNotification(err.error, "error");
      return;
    }
    
    const data = await res.json();
    await loadDatabases();
    updateSchema(data.schema);
    showNotification(`Switched to "${name}"`, "success");
  } catch (err) {
    console.error("Failed to switch database:", err);
  }
}

async function deleteDatabase(name) {
  if (!confirm(`Delete database "${name}"? This cannot be undone.`)) return;
  
  try {
    const res = await fetch(`/api/databases/${encodeURIComponent(name)}`, {
      method: "DELETE",
    });
    
    if (!res.ok) {
      const err = await res.json();
      showNotification(err.error, "error");
      return;
    }
    
    const data = await res.json();
    renderDatabaseList(data.databases);
    showNotification(`Database "${name}" deleted`, "success");
  } catch (err) {
    console.error("Failed to delete database:", err);
  }
}

uploadTrigger.addEventListener("click", () => {
  dbUpload.click();
});

dbUpload.addEventListener("change", async (e) => {
  const file = e.target.files?.[0];
  if (!file) return;

  const formData = new FormData();
  formData.append("file", file);

  try {
    uploadTrigger.disabled = true;
    uploadTrigger.querySelector("span").textContent = "Uploading...";

    const res = await fetch("/api/upload-db", {
      method: "POST",
      body: formData,
    });

    const data = await res.json();

    if (!res.ok) {
      throw new Error(data.error || "Upload failed");
    }

    renderDatabaseList(data.databases);
    updateSchema(data.schema);
    showNotification(`Database "${file.name}" loaded successfully!`, "success");
  } catch (err) {
    showNotification(err.message, "error");
  } finally {
    uploadTrigger.disabled = false;
    uploadTrigger.querySelector("span").textContent = "+ Add Database";
    dbUpload.value = "";
  }
});

// Load databases on page load
loadDatabases();

// ============================================================================
// Query Execution
// ============================================================================

const form = document.getElementById("ask-form");
const input = document.getElementById("question");
const askBtn = document.getElementById("ask-btn");
const output = document.getElementById("output");
const sqlEl = document.getElementById("sql");
const resultWrap = document.getElementById("result-wrap");
const resultCount = document.getElementById("result-count");
const errorEl = document.getElementById("error");
const copySqlBtn = document.getElementById("copy-sql");

function buildTable(columns, rows) {
  if (!rows.length) return "<p style='text-align: center; color: var(--text-muted); padding: 20px;'>No rows returned.</p>";
  const head = columns.map((c) => `<th>${escapeHtml(c)}</th>`).join("");
  const body = rows
    .map((r) => `<tr>${r.map((v) => `<td>${escapeHtml(v ?? "")}</td>`).join("")}</tr>`)
    .join("");
  return `<table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
}

function escapeHtml(text) {
  const map = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" };
  return String(text).replace(/[&<>"']/g, (m) => map[m]);
}

function showNotification(message, type = "info") {
  console.log(`[${type}] ${message}`);
}

async function ask(question) {
  errorEl.classList.add("hidden");
  output.classList.add("hidden");
  askBtn.disabled = true;
  askBtn.querySelector(".btn-text").textContent = "Generating...";

  try {
    const res = await fetch("/api/query", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });
    const data = await res.json();

    if (!res.ok) {
      if (data.sql) sqlEl.textContent = data.sql;
      throw new Error(data.error || "Something went wrong.");
    }

    sqlEl.textContent = data.sql;
    const table = buildTable(data.columns, data.rows);
    resultWrap.innerHTML = table;
    resultCount.textContent = `${data.rows.length} row${data.rows.length !== 1 ? "s" : ""}`;
    output.classList.remove("hidden");
  } catch (err) {
    errorEl.textContent = err.message;
    errorEl.classList.remove("hidden");
  } finally {
    askBtn.disabled = false;
    askBtn.querySelector(".btn-text").textContent = "Generate SQL";
  }
}

form.addEventListener("submit", (e) => {
  e.preventDefault();
  const q = input.value.trim();
  if (q) ask(q);
});

document.querySelectorAll(".example-chip").forEach((chip) => {
  chip.addEventListener("click", () => {
    input.value = chip.textContent.trim();
    input.focus();
    ask(chip.textContent.trim());
  });
});

// ============================================================================
// Copy SQL
// ============================================================================

copySqlBtn.addEventListener("click", async () => {
  const sql = sqlEl.textContent;
  try {
    await navigator.clipboard.writeText(sql);
    copySqlBtn.textContent = "✓ Copied";
    setTimeout(() => {
      copySqlBtn.textContent = "📋";
    }, 2000);
  } catch (err) {
    console.error("Failed to copy:", err);
  }
});
