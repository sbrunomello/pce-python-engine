import { useQuery } from '@tanstack/react-query';
import { fetchControlState } from '../api/os';

export function TwinPage(): JSX.Element {
  const stateQuery = useQuery({
    queryKey: ['control-state'],
    queryFn: ({ signal }) => fetchControlState(signal),
    refetchInterval: 5000,
  });

  const twin = stateQuery.data?.twin_snapshot;

  return (
    <section>
      <h2>Twin</h2>
      <p>RobotProjectState legível.</p>
      <pre>{JSON.stringify(twin ?? {}, null, 2)}</pre>
    </section>
  );
}
