import { useEffect, useRef, useState } from 'react';

export type Resource<T> = { data: T | null; error: string; loading: boolean };
type Snapshot<T> = { key: string | null; revision: number; resource: Resource<T> };

// The key and revision identify the request; the loader may safely change on each render.
export function useResource<T>(key: string | null, load: (signal: AbortSignal) => Promise<T>, revision = 0): Resource<T> {
  const loader = useRef(load);
  loader.current = load;
  const [snapshot, setSnapshot] = useState<Snapshot<T>>({
    key, revision, resource: { data: null, error: '', loading: key !== null },
  });

  useEffect(() => {
    if (key === null) {
      setSnapshot({ key, revision, resource: { data: null, error: '', loading: false } });
      return;
    }
    const controller = new AbortController();
    setSnapshot({ key, revision, resource: { data: null, error: '', loading: true } });
    Promise.resolve().then(() => loader.current(controller.signal)).then(data => {
      if (!controller.signal.aborted) setSnapshot({ key, revision, resource: { data, error: '', loading: false } });
    }).catch(error => {
      if (!controller.signal.aborted) setSnapshot({ key, revision, resource: {
        data: null, error: error instanceof Error ? error.message : 'Request failed.', loading: false,
      } });
    });
    return () => controller.abort();
  }, [key, revision]);

  // Never expose an earlier selection while the new effect is waiting to run.
  if (snapshot.key !== key || snapshot.revision !== revision)
    return { data: null, error: '', loading: key !== null };
  return snapshot.resource;
}
