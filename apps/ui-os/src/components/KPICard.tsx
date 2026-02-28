export function KPICard({ title, value }: { title: string; value: string | number }): JSX.Element {
  return (
    <article className="card">
      <h3>{title}</h3>
      <strong>{value}</strong>
    </article>
  );
}
