"use client";

import React, { useEffect, useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8880";
const STORAGE_KEY = "sls-control-auth";
const CONTROL_AUTH_MODE = process.env.NEXT_PUBLIC_CONTROL_AUTH_MODE || "browser";
const PROXY_TOKEN = "__proxy__";

type Props = { service: string; label?: string };

export default function Controls({ service, label }: Props) {
  const [resp, setResp] = useState<string>("");
  const useProxyAuth = CONTROL_AUTH_MODE === "proxy";
  const [authToken, setAuthToken] = useState<string | null>(useProxyAuth ? PROXY_TOKEN : null);

  useEffect(() => {
    if (typeof window === "undefined" || useProxyAuth) return;
    setAuthToken(localStorage.getItem(STORAGE_KEY));
  }, [useProxyAuth]);

  function configureAuth(): string | null {
    if (useProxyAuth) {
      return PROXY_TOKEN;
    }
    if (typeof window === "undefined") return null;
    const user = window.prompt("Usuario para /control");
    if (!user) {
      return null;
    }
    const pass = window.prompt("Password para /control");
    if (pass === null) {
      return null;
    }
    const token = window.btoa(`${user}:${pass}`);
    localStorage.setItem(STORAGE_KEY, token);
    setAuthToken(token);
    return token;
  }

  function clearAuth() {
    if (useProxyAuth) {
      return;
    }
    if (typeof window === "undefined") return;
    localStorage.removeItem(STORAGE_KEY);
    setAuthToken(null);
  }

  async function call(action: "start" | "stop" | "restart" | "status") {
    setResp("...");
    let token = authToken;
    if (!token && !useProxyAuth) {
      token = configureAuth();
      if (!token) {
        setResp("Acción cancelada: se requieren credenciales.");
        return;
      }
    }
    try {
      const headers: HeadersInit = {};
      if (!useProxyAuth && token) {
        headers.Authorization = `Basic ${token}`;
      }
      const r = await fetch(`${API_BASE}/control/${service}/${action}`, { method: "POST", headers });
      if (r.status === 401) {
        clearAuth();
        setResp("No autorizado: credenciales inválidas. Configura de nuevo.");
        return;
      }
      if (r.status === 503) {
        setResp("Backend sin credenciales configuradas (CONTROL_USER/PASSWORD).");
        return;
      }
      const j = await r.json();
      setResp(JSON.stringify(j, null, 2));
    } catch (e: any) {
      setResp(String(e?.message || e));
    }
  }

  return (
    <div>
      <div className="badges">
        <span className="badge">{label ?? service}</span>
        <span className={`badge ${authToken ? "ok" : "fail"}`}>
          {useProxyAuth ? "Proxy" : authToken ? "Auth lista" : "Auth requerida"}
        </span>
        {!useProxyAuth ? (
          <>
            <button onClick={configureAuth}>Credenciales</button>
            {authToken ? <button onClick={clearAuth}>Salir</button> : null}
          </>
        ) : null}
        <button onClick={() => call("start")}>Start</button>
        <button onClick={() => call("stop")}>Stop</button>
        <button onClick={() => call("restart")}>Restart</button>
        <button onClick={() => call("status")}>Status</button>
      </div>
      {resp ? <pre className="mono">{resp}</pre> : null}
    </div>
  );
}
