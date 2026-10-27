import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import TransferForm from "../components/TransferForm";

function formatBalance(account) {
    if (account.balance_display) return account.balance_display;
    return (Number(account.balance) / 100).toFixed(2);
}

export default function Dashboard() {
    const [accounts, setAccounts] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState("");
    const [name, setName] = useState("");
    const [currency, setCurrency] = useState("USD");
    const [creating, setCreating] = useState(false);

    const loadAccounts = useCallback(async () => {
        setError("");
        try {
            const data = await api("/api/accounts/");
            setAccounts(Array.isArray(data) ? data : data.results || []);
        } catch (err) {
            setError(err.message);
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        loadAccounts();
    }, [loadAccounts]);

    async function createAccount(e) {
        e.preventDefault();
        setCreating(true);
        setError("");
        try {
            await api("/api/accounts/", { method: "POST", body: { name, currency } });
            setName("");
            await loadAccounts();
        } catch (err) {
            setError(err.message);
        } finally {
            setCreating(false);
        }
    }

    return (
        <>
            <section className="panel">
                <h2>Your accounts</h2>
                {loading && <p>Loading...</p>}
                {error && <p className="error">{error}</p>}
                {!loading && accounts.length === 0 && <p>No accounts yet. Create one below.</p>}
                {accounts.length > 0 && (
                    <table>
                        <thead>
                            <tr>
                                <th>Name</th>
                                <th>Currency</th>
                                <th>Balance</th>
                                <th>Account ID</th>
                            </tr>
                        </thead>
                        <tbody>
                            {accounts.map((a) => (
                                <tr key={a.id}>
                                    <td>{a.name}</td>
                                    <td>{a.currency}</td>
                                    <td>{formatBalance(a)}</td>
                                    <td className="mono">{a.id}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                )}
            </section>

            <section className="panel">
                <h2>Create account</h2>
                <form onSubmit={createAccount} className="row">
                    <input
                        value={name}
                        onChange={(e) => setName(e.target.value)}
                        placeholder="Account name"
                        required
                    />
                    <input
                        value={currency}
                        onChange={(e) => setCurrency(e.target.value.toUpperCase())}
                        maxLength={3}
                        style={{ width: 80 }}
                        required
                    />
                    <button type="submit" disabled={creating}>
                        {creating ? "Creating..." : "Create"}
                    </button>
                </form>
            </section>

            <section className="panel">
                <h2>New transfer</h2>
                <TransferForm accounts={accounts} onDone={loadAccounts} />
            </section>
        </>
    );
}