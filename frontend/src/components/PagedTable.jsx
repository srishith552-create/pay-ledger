import { useEffect, useState } from "react";
import { api } from "../api";

function renderValue(value) {
    if (value === null || value === undefined || value === "") return "-";
    if (typeof value === "object") return JSON.stringify(value);
    return String(value);
}

export default function PagedTable({ path, columns, emptyText }) {
    const [url, setUrl] = useState(path);
    const [rows, setRows] = useState([]);
    const [next, setNext] = useState(null);
    const [previous, setPrevious] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState("");

    useEffect(() => {
        let cancelled = false;
        setLoading(true);
        setError("");
        api(url)
            .then((data) => {
                if (cancelled) return;
                setRows(Array.isArray(data) ? data : data.results || []);
                setNext(data.next || null);
                setPrevious(data.previous || null);
            })
            .catch((err) => {
                if (!cancelled) setError(err.message);
            })
            .finally(() => {
                if (!cancelled) setLoading(false);
            });
        return () => {
            cancelled = true;
        };
    }, [url]);

    // If no columns are given, build them from the first row's keys.
    const cols =
        columns ||
        (rows[0] ? Object.keys(rows[0]).map((key) => ({ key, label: key })) : []);

    return (
        <div>
            {loading && <p>Loading...</p>}
            {error && <p className="error">{error}</p>}
            {!loading && !error && rows.length === 0 && <p>{emptyText || "Nothing here yet."}</p>}
            {rows.length > 0 && (
                <div className="table-wrap">
                    <table>
                        <thead>
                            <tr>
                                {cols.map((c) => (
                                    <th key={c.key}>{c.label}</th>
                                ))}
                            </tr>
                        </thead>
                        <tbody>
                            {rows.map((row, i) => (
                                <tr key={row.id || i}>
                                    {cols.map((c) => (
                                        <td key={c.key} title={renderValue(row[c.key])}>
                                            {c.render ? c.render(row) : renderValue(row[c.key])}
                                        </td>
                                    ))}
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}
            <div className="pager">
                <button disabled={!previous || loading} onClick={() => setUrl(previous)}>
                    Previous
                </button>
                <button disabled={!next || loading} onClick={() => setUrl(next)}>
                    Next
                </button>
            </div>
        </div>
    );
}