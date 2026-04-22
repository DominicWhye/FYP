from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import unquote
import cgi
import json
import mimetypes
import os
import re
import shutil
import sqlite3
import sys
import uuid


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
DB_PATH = DATA_DIR / "documents.db"
MAX_UPLOAD_SIZE = 50 * 1024 * 1024


def init_database():
    DATA_DIR.mkdir(exist_ok=True)
    UPLOAD_DIR.mkdir(exist_ok=True)

    with sqlite3.connect(DB_PATH) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                category TEXT NOT NULL,
                notes TEXT,
                original_name TEXT NOT NULL,
                stored_name TEXT NOT NULL,
                content_type TEXT,
                size INTEGER NOT NULL,
                uploaded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.commit()


def row_to_dict(row):
    return {
        "id": row[0],
        "title": row[1],
        "category": row[2],
        "notes": row[3],
        "original_name": row[4],
        "stored_name": row[5],
        "content_type": row[6],
        "size": row[7],
        "uploaded_at": row[8],
    }


def clean_filename(filename):
    name = Path(filename or "document").name
    name = re.sub(r"[^A-Za-z0-9._ -]", "_", name).strip()
    return name or "document"


def json_response(handler, status, payload):
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


class DocumentVaultHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def log_message(self, format, *args):
        sys.stdout.write("%s - - [%s] %s\n" % (self.client_address[0], self.log_date_time_string(), format % args))

    def do_GET(self):
        if self.path == "/api/documents":
            self.list_documents()
            return

        match = re.fullmatch(r"/api/documents/(\d+)/download", unquote(self.path))
        if match:
            self.download_document(int(match.group(1)))
            return

        if self.path == "/":
            self.path = "/index.html"

        super().do_GET()

    def do_POST(self):
        if self.path == "/api/documents":
            self.upload_document()
            return

        json_response(self, 404, {"error": "Route not found."})

    def do_DELETE(self):
        match = re.fullmatch(r"/api/documents/(\d+)", unquote(self.path))
        if match:
            self.delete_document(int(match.group(1)))
            return

        json_response(self, 404, {"error": "Route not found."})

    def list_documents(self):
        with sqlite3.connect(DB_PATH) as connection:
            rows = connection.execute(
                """
                SELECT id, title, category, notes, original_name, stored_name, content_type, size, uploaded_at
                FROM documents
                ORDER BY datetime(uploaded_at) DESC, id DESC
                """
            ).fetchall()

        json_response(self, 200, [row_to_dict(row) for row in rows])

    def upload_document(self):
        content_length = int(self.headers.get("Content-Length", "0"))
        if content_length <= 0:
            json_response(self, 400, {"error": "No upload data received."})
            return

        if content_length > MAX_UPLOAD_SIZE:
            json_response(self, 413, {"error": "File is too large. Maximum upload size is 50 MB."})
            return

        form = cgi.FieldStorage(
            fp=self.rfile,
            headers=self.headers,
            environ={
                "REQUEST_METHOD": "POST",
                "CONTENT_TYPE": self.headers.get("Content-Type"),
                "CONTENT_LENGTH": str(content_length),
            },
        )

        title = (form.getfirst("title") or "").strip()
        category = (form.getfirst("category") or "Other").strip()
        notes = (form.getfirst("notes") or "").strip()
        file_item = form["file"] if "file" in form else None

        if not title:
            json_response(self, 400, {"error": "Document title is required."})
            return

        if file_item is None or not getattr(file_item, "filename", ""):
            json_response(self, 400, {"error": "Please choose a file to upload."})
            return

        original_name = clean_filename(file_item.filename)
        extension = Path(original_name).suffix
        stored_name = f"{uuid.uuid4().hex}{extension}"
        stored_path = UPLOAD_DIR / stored_name

        with stored_path.open("wb") as output_file:
            shutil.copyfileobj(file_item.file, output_file)

        size = stored_path.stat().st_size
        content_type = file_item.type or mimetypes.guess_type(original_name)[0] or "application/octet-stream"

        with sqlite3.connect(DB_PATH) as connection:
            cursor = connection.execute(
                """
                INSERT INTO documents (title, category, notes, original_name, stored_name, content_type, size)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (title, category, notes, original_name, stored_name, content_type, size),
            )
            connection.commit()
            document_id = cursor.lastrowid

        json_response(self, 201, {"id": document_id, "message": "Document uploaded successfully."})

    def download_document(self, document_id):
        with sqlite3.connect(DB_PATH) as connection:
            row = connection.execute(
                """
                SELECT id, title, category, notes, original_name, stored_name, content_type, size, uploaded_at
                FROM documents
                WHERE id = ?
                """,
                (document_id,),
            ).fetchone()

        if not row:
            json_response(self, 404, {"error": "Document not found."})
            return

        document = row_to_dict(row)
        stored_path = UPLOAD_DIR / document["stored_name"]

        if not stored_path.exists():
            json_response(self, 404, {"error": "Stored file is missing."})
            return

        self.send_response(200)
        self.send_header("Content-Type", document["content_type"] or "application/octet-stream")
        self.send_header("Content-Length", str(stored_path.stat().st_size))
        self.send_header("Content-Disposition", f'attachment; filename="{document["original_name"]}"')
        self.end_headers()

        with stored_path.open("rb") as source:
            shutil.copyfileobj(source, self.wfile)

    def delete_document(self, document_id):
        with sqlite3.connect(DB_PATH) as connection:
            row = connection.execute("SELECT stored_name FROM documents WHERE id = ?", (document_id,)).fetchone()
            if not row:
                json_response(self, 404, {"error": "Document not found."})
                return

            connection.execute("DELETE FROM documents WHERE id = ?", (document_id,))
            connection.commit()

        stored_path = UPLOAD_DIR / row[0]
        if stored_path.exists():
            os.remove(stored_path)

        json_response(self, 200, {"message": "Document deleted."})


def run():
    init_database()
    port = int(os.environ.get("PORT", "8000"))
    server = ThreadingHTTPServer(("127.0.0.1", port), DocumentVaultHandler)
    print(f"Document vault running at http://127.0.0.1:{port}/documents.html")
    server.serve_forever()


if __name__ == "__main__":
    run()
