import "./globals.css";

export const metadata = { title: "SLS Panel" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es">
      <body>
        <div className="container">
          <nav className="top-nav">
            <a href="/dashboard">Dashboard</a>
            <a href="/arena">Arena</a>
          </nav>
          {children}
        </div>
      </body>
    </html>
  );
}

export const metadata = { title: "SLS Panel" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es">
      <body>
        <div className="container">{children}</div>
      </body>
    </html>
  );
}
