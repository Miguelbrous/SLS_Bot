import "./globals.css";

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
