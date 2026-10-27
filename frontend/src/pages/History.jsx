import PagedTable from "../components/PagedTable";

const short = (id) => (id ? `${String(id).slice(0, 8)}…` : "-");

const columns = [
    {
        key: "created_at",
        label: "Date",
        render: (r) => new Date(r.created_at).toLocaleString(),
    },
    { key: "source_account", label: "From", render: (r) => short(r.source_account) },
    { key: "destination_account", label: "To", render: (r) => short(r.destination_account) },
    {
        key: "amount",
        label: "Amount",
        render: (r) => r.amount_display || (Number(r.amount) / 100).toFixed(2),
    },
    { key: "currency", label: "Currency" },
    {
        key: "status",
        label: "Status",
        render: (r) => <span className={`badge ${r.status}`}>{r.status}</span>,
    },
    { key: "description", label: "Description" },
];

export default function History() {
    return (
        <section className="panel">
            <h2>Transaction history</h2>
            <PagedTable
                path="/api/transfers/list/"
                columns={columns}
                emptyText="No transfers yet."
            />
        </section>
    );
}