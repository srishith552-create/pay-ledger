import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../AuthContext";

export default function Login() {
    const { login, register } = useAuth();
    const navigate = useNavigate();
    const [mode, setMode] = useState("login");
    const [username, setUsername] = useState("");
    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");
    const [error, setError] = useState("");
    const [loading, setLoading] = useState(false);

    async function handleSubmit(e) {
        e.preventDefault();
        setError("");
        setLoading(true);
        try {
            if (mode === "login") await login(username, password);
            else await register(username, email, password);
            navigate("/");
        } catch (err) {
            setError(err.message);
        } finally {
            setLoading(false);
        }
    }

    return (
        <div className="card">
            <h1>PayLedger</h1>
            <h2>{mode === "login" ? "Sign in" : "Create account"}</h2>
            <form onSubmit={handleSubmit}>
                <label>
                    Username
                    <input value={username} onChange={(e) => setUsername(e.target.value)} required />
                </label>
                {mode === "register" && (
                    <label>
                        Email
                        <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
                    </label>
                )}
                <label>
                    Password
                    <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required />
                </label>
                {error && <p className="error">{error}</p>}
                <button type="submit" disabled={loading}>
                    {loading ? "Please wait..." : mode === "login" ? "Sign in" : "Register"}
                </button>
            </form>
            <button className="link" onClick={() => setMode(mode === "login" ? "register" : "login")}>
                {mode === "login" ? "Need an account? Register" : "Have an account? Sign in"}
            </button>
        </div>
    );
}