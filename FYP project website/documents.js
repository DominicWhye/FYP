const uploadForm = document.querySelector("#uploadForm");
const dropZone = document.querySelector("#dropZone");
const fileInput = document.querySelector("#file");
const formMessage = document.querySelector("#formMessage");
const documentList = document.querySelector("#documentList");
const searchInput = document.querySelector("#searchInput");
const documentCount = document.querySelector("#documentCount");

let documents = [];

async function readJsonResponse(response) {
  const contentType = response.headers.get("content-type") || "";
  const text = await response.text();

  if (!contentType.includes("application/json")) {
    const serverUrl = "http://127.0.0.1:8000/documents.html";
    throw new Error(
      `The document database API did not respond with JSON. Open the vault through ${serverUrl} and make sure python server.py is running.`
    );
  }

  try {
    return text ? JSON.parse(text) : null;
  } catch {
    throw new Error("The server returned an unreadable response. Please restart python server.py and try again.");
  }
}

function formatBytes(bytes) {
  if (!bytes) return "0 KB";
  const units = ["B", "KB", "MB", "GB"];
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  return `${(bytes / 1024 ** index).toFixed(index === 0 ? 0 : 1)} ${units[index]}`;
}

function formatDate(value) {
  return new Intl.DateTimeFormat("en-SG", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function setMessage(message, type = "") {
  formMessage.textContent = message;
  formMessage.className = `form-message ${type ? `is-${type}` : ""}`;
}

function updateDropLabel() {
  const file = fileInput.files[0];
  const title = dropZone.querySelector("strong");
  const hint = dropZone.querySelector("small");

  if (!file) {
    title.textContent = "Drop your file here or click to browse";
    hint.textContent = "PDF, DOCX, PPTX, images, ZIP files, and other project materials";
    return;
  }

  title.textContent = file.name;
  hint.textContent = `${formatBytes(file.size)} selected`;
}

function renderDocuments() {
  const searchTerm = searchInput.value.trim().toLowerCase();
  const filtered = documents.filter((item) => {
    return [item.title, item.category, item.notes, item.original_name]
      .join(" ")
      .toLowerCase()
      .includes(searchTerm);
  });

  documentCount.textContent = `${documents.length} ${documents.length === 1 ? "document" : "documents"}`;

  if (!filtered.length) {
    documentList.innerHTML = `
      <div class="empty-state">
        <strong>${documents.length ? "No matching documents" : "No documents yet"}</strong>
        <span>${documents.length ? "Try another search term." : "Upload your first project file to start building the vault."}</span>
      </div>
    `;
    return;
  }

  documentList.innerHTML = filtered
    .map(
      (item) => `
        <article class="document-item">
          <div class="document-meta">
            <strong>${item.title}</strong>
            <p>${item.notes || "No notes added."}</p>
            <div class="document-tags">
              <span>${item.category}</span>
              <span>${item.original_name}</span>
              <span>${formatBytes(item.size)}</span>
              <span>${formatDate(item.uploaded_at)}</span>
            </div>
          </div>
          <div class="document-actions">
            <a class="small-button" href="/api/documents/${item.id}/download">Download</a>
            <button class="small-button delete" type="button" data-delete="${item.id}">Delete</button>
          </div>
        </article>
      `
    )
    .join("");
}

async function loadDocuments() {
  const response = await fetch("/api/documents");
  const result = await readJsonResponse(response);

  if (!response.ok) {
    throw new Error(result?.error || "Could not load documents.");
  }

  documents = result;
  renderDocuments();
}

dropZone.addEventListener("dragover", (event) => {
  event.preventDefault();
  dropZone.classList.add("is-dragging");
});

dropZone.addEventListener("dragleave", () => {
  dropZone.classList.remove("is-dragging");
});

dropZone.addEventListener("drop", (event) => {
  event.preventDefault();
  dropZone.classList.remove("is-dragging");

  if (event.dataTransfer.files.length) {
    fileInput.files = event.dataTransfer.files;
    updateDropLabel();
  }
});

fileInput.addEventListener("change", updateDropLabel);
searchInput.addEventListener("input", renderDocuments);

documentList.addEventListener("click", async (event) => {
  const deleteButton = event.target.closest("[data-delete]");
  if (!deleteButton) return;

  const id = deleteButton.dataset.delete;
  const confirmed = window.confirm("Delete this document from the vault?");
  if (!confirmed) return;

  deleteButton.disabled = true;
  const response = await fetch(`/api/documents/${id}`, { method: "DELETE" });
  const result = await readJsonResponse(response);

  if (!response.ok) {
    deleteButton.disabled = false;
    window.alert(result?.error || "Could not delete the document.");
    return;
  }

  await loadDocuments();
});

uploadForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  setMessage("");

  const submitButton = uploadForm.querySelector("button[type='submit']");
  submitButton.disabled = true;
  submitButton.textContent = "Uploading...";

  try {
    const response = await fetch("/api/documents", {
      method: "POST",
      body: new FormData(uploadForm),
    });

    const result = await readJsonResponse(response);

    if (!response.ok) {
      throw new Error(result?.error || "Upload failed.");
    }

    uploadForm.reset();
    updateDropLabel();
    setMessage("Document uploaded successfully.", "success");
    await loadDocuments();
  } catch (error) {
    setMessage(error.message, "error");
  } finally {
    submitButton.disabled = false;
    submitButton.textContent = "Upload Document";
  }
});

loadDocuments().catch((error) => {
  documentList.innerHTML = `
    <div class="empty-state">
      <strong>Server not connected</strong>
      <span>${error.message} Start the Python server to use the document database.</span>
    </div>
  `;
});
