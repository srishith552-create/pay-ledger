import PagedTable from "../components/PagedTable";

export default function Deliveries() {
    return (
        <section className="panel">
            <h2>Webhook deliveries</h2>
            <PagedTable
                path="/api/webhooks/deliveries/"
                emptyText="No webhook deliveries yet. Register a webhook endpoint and make a transfer."
            />
        </section>
    );
}