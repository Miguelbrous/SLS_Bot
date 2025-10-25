import React from "react";

export default function Card({
  title,
  children,
}: {
  title?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="card">
      {title ? <h2>{title}</h2> : null}
      {children}
    </div>
  );
}
