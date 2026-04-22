import { handleUpload } from "@vercel/blob/client";

const MAX_FILE_SIZE = 50 * 1024 * 1024;

const ALLOWED_CONTENT_TYPES = [
  "application/pdf",
  "application/msword",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "application/vnd.ms-powerpoint",
  "application/vnd.openxmlformats-officedocument.presentationml.presentation",
  "application/vnd.ms-excel",
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  "application/zip",
  "application/x-zip-compressed",
  "application/octet-stream",
  "image/*",
  "text/*",
];

function jsonError(message, status = 400) {
  return Response.json({ error: message }, { status });
}

export default async function handler(request) {
  if (request.method !== "POST") {
    return jsonError("Method not allowed.", 405);
  }

  try {
    const body = await request.json();

    const jsonResponse = await handleUpload({
      body,
      request,
      onBeforeGenerateToken: async (pathname, clientPayload) => {
        if (!pathname || !pathname.startsWith("documents/")) {
          throw new Error("Invalid upload destination.");
        }

        let metadata = {};
        try {
          metadata = clientPayload ? JSON.parse(clientPayload) : {};
        } catch {
          throw new Error("Invalid upload metadata.");
        }

        if (!metadata.title || !metadata.filename) {
          throw new Error("Document title and filename are required.");
        }

        return {
          allowedContentTypes: ALLOWED_CONTENT_TYPES,
          maximumSizeInBytes: MAX_FILE_SIZE,
          addRandomSuffix: true,
          tokenPayload: JSON.stringify({
            title: metadata.title,
            category: metadata.category || "Other",
            notes: metadata.notes || "",
            filename: metadata.filename,
            size: metadata.size || 0,
          }),
        };
      },
      onUploadCompleted: async () => {
        return;
      },
    });

    return Response.json(jsonResponse);
  } catch (error) {
    return jsonError(error.message || "Upload could not be authorized.");
  }
}
