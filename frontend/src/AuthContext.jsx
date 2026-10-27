import { createContext, useContext, useEffect, useState } from "react";
import { api, getToken, setToken, setUnauthorizedHandler } from "./api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
    const [token, setTokenState] = useState(getToken());

    useEffect(() => {
        setUnauthorizedHandler(() => setTokenState(null));
    }, []);

    async function login(username, password) {
        const data = await api("/api/auth/token/", {
            method: "POST",
            body: { username, password },
        });
        setToken(data.access);
        setTokenState(data.access);
    }

    async function register(username, email, password) {
        await api("/api/auth/register/", {
            method: "POST",
            body: { username, email, password },
        });
        await login(username, password);
    }

    function logout() {
        setToken(null);
        setTokenState(null);
    }

    return (
        <AuthContext.Provider value={{ token, login, register, logout }}>
            {children}
        </AuthContext.Provider>
    );
}

export function useAuth() {
    return useContext(AuthContext);
}