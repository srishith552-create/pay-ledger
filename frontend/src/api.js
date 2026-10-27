const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

let accessToken = localStorage.getItem("access") || null;
let onUnauthorized = () => { };

export function setToken(token) {
    accessToken = token;
    if (token) localStorage.setItem("access", token);
    else localStorage.removeItem("access");
}

export function getToken() {
    return accessToken;
}

export function setUnauthorizedHandler(fn) {
    onUnauthorized = fn;
}

function formatError(status, data) {
    if (status === 429) return "Too many requests, retry shortly.";
    if (data && typeof data === "object") {
        if (data.detail) return String(data.detail);
        return Object.entries(data)
            .map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(", ") : v}`)
            .join(" | ");
    }
    return `Request failed (${status})`;
}

export async function api(path, { method = "GET", body, headers = {} } = {}) {
    const finalHeaders = { "Content-Type": "application/json", ...headers };
    if (accessToken) finalHeaders.Authorization = `Bearer ${accessToken}`;

    // Cursor pagination returns absolute "next"/"previous" URLs; accept both forms.
    const url = path.startsWith("http") ? path : `${API_URL}${path}`;

    const response = await fetch(url, {
        method,
        headers: finalHeaders,
        body: body ? JSON.stringify(body) : undefined,
    });

    let data = null;
    const text = await response.text();
    if (text) {
        try {
            data = JSON.parse(text);
        } catch {
            data = null;
        }
    }

    if (response.status === 401 && accessToken) {
        setToken(null);
        onUnauthorized();
    }

    if (!response.ok) {
        const error = new Error(formatError(response.status, data));
        error.status = response.status;
        error.data = data;
        throw error;
    }
    return data;
}