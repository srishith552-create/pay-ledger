import { useState } from "react";
import { api } from "../api";
import PagedTable from "../components/PagedTable";

const deliveryColumns = [
    {
        key: "created_at",
        label: "Time",
        render: (r) => new Date(r.created_at).toLocaleString(),
    },
    { key: "transfer_id", label: "Transfer", render: (r) => (r.transfer_id ? `${String(r.transfer_id).slice(0, 8)}…` : "-") },
    { key: "attempt_number", label: "Attempt" },
    {
        key: "delivery_status",
        label: "Status",
        render: (r) => <span className={`badge ${r.delivery_status}`}>{r.delivery_status}</span>,
    },
    { key: "http_status_code", label: "HTTP" },
    { key: "latency_ms", label: "Latency (ms)" },
    { key: "error_message", label: "Error" },
];

export default function Deliveries() {
    const [url, setUrl] = useState("");
    const [secret, setSecret] = useState("");
    const [message, setMessage] = useState(null);
    const [saving, setSaving] = useState(false);
    const [refreshKey, setRefreshKey] = useState(0);

    async function registerEndpoint(e) {
        e.preventDefault();
        setSaving(true);
        setMessage(null);
        const body = { url: url.trim() };
        if (secret.trim()) body.secret = secret.trim();
        try {
            await api("/api/webhooks/endpoints/", { method: "POST", body });
            setMessage({ type: "success", text: "Endpoint registered." });
            setUrl("");
            setSecret("");
            setRefreshKey((k) => k + 1); // re-mount the endpoints table to reload it
        } catch (err) {
            setMessage({ type: "error", text: err.message });
        } finally {
            setSaving(false);
        }
    }

    return (
        <>
            <section className="panel">
                <h2>Register a webhook endpoint</h2>
                <p className="hint">
                    After a transfer completes, PayLedger sends a signed (HMAC-SHA256) POST to each
                    registered URL. Tip: use a free test URL from webhook.site.
                </p>
                <form onSubmit={registerEndpoint}>
                    <label>
                        Endpoint URL
                        <input
                            type="url"
                            value={url}
                            onChange={(e) => setUrl(e.target.value)}
                            placeholder="https://webhook.site/your-id"
                            required
                        />
                    </label>
                    <label>
                        Signing secret (optional)
                        <input value={secret} onChange={(e) => setSecret(e.target.value)} />
                    </label>
                    {message && <p className={message.type === "error" ? "error" : "success"}>{message.text}</p>}
                    <button type="submit" disabled={saving}>
                        {saving ? "Saving..." : "Register endpoint"}
                    </button>
                </form>
            </section>

            <section className="panel">
                <h2>Your endpoints</h2>
                <PagedTable
                    key={refreshKey}
                    path="/api/webhooks/endpoints/"
                    emptyText="No endpoints registered yet."
                />
            </section>

            <section className="panel">
                <h2>Delivery log</h2>
                <PagedTable
                    path="/api/webhooks/deliveries/"
                    columns={deliveryColumns}
                    emptyText="No deliveries yet. Register an endpoint, then send a transfer."
                />
            </section>
        </>
    );
}