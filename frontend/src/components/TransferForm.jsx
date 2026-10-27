import { useRef, useState } from "react";
import { api } from "../api";

export default function TransferForm({ accounts, onDone }) {
    const [source, setSource] = useState("");
    const [destination, setDestination] = useState("");
    const [amount, setAmount] = useState("");
    const [description, setDescription] = useState("");
    const [message, setMessage] = useState(null); // {type, text}
    const [loading, setLoading] = useState(false);

    // One Idempotency-Key per distinct payload. If the same payload is sent again
    // (double-click, retry after a network error) the same key is reused, so the
    // backend returns the original result instead of creating a second transfer.
    const keyRef = useRef({ signature: "", key: "" });

    function getKey(payload) {
        const signature = JSON.stringify(payload);
        if (keyRef.current.signature !== signature) {
            keyRef.current = { signature, key: crypto.randomUUID() };
        }
        return keyRef.current.key;
    }

    async function handleSubmit(e) {
        e.preventDefault();
        if (loading) return;
        setMessage(null);

        const minorUnits = Math.round(parseFloat(amount) * 100);
        if (!source || !destination || !Number.isFinite(minorUnits) || minorUnits <= 0) {
            setMessage({ type: "error", text: "Choose accounts and enter a positive amount." });
            return;
        }

        const payload = {
            source_account: source,
            destination_account: destination.trim(),
            amount: minorUnits,
            description,
        };

        setLoading(true);
        try {
            await api("/api/transfers/", {
                method: "POST",
                body: payload,
                headers: { "Idempotency-Key": getKey(payload) },
            });
            setMessage({ type: "success", text: "Transfer completed." });
            setAmount("");
            setDescription("");
            keyRef.current = { signature: "", key: "" }; // fresh key for the next transfer
            onDone();
        } catch (err) {
            setMessage({ type: "error", text: err.message });
        } finally {
            setLoading(false);
        }
    }

    return (
        <form onSubmit={handleSubmit}>
            <label>
                From account
                <select value={source} onChange={(e) => setSource(e.target.value)} required>
                    <option value="">Select an account</option>
                    {accounts.map((a) => (
                        <option key={a.id} value={a.id}>
                            {a.name} ({a.currency})
                        </option>
                    ))}
                </select>
            </label>
            <label>
                Destination account ID
                <input
                    value={destination}
                    onChange={(e) => setDestination(e.target.value)}
                    placeholder="UUID of the receiving account"
                    required
                />
            </label>
            <label>
                Amount
                <input
                    type="number"
                    step="0.01"
                    min="0.01"
                    value={amount}
                    onChange={(e) => setAmount(e.target.value)}
                    required
                />
            </label>
            <label>
                Description
                <input value={description} onChange={(e) => setDescription(e.target.value)} />
            </label>
            {message && <p className={message.type === "error" ? "error" : "success"}>{message.text}</p>}
            <button type="submit" disabled={loading}>
                {loading ? "Sending..." : "Send transfer"}
            </button>
        </form>
    );
}