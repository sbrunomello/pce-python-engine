export function JsonViewer({ value }: { value: unknown }): JSX.Element {
  return <pre className="json-viewer">{JSON.stringify(value, null, 2)}</pre>;
}
