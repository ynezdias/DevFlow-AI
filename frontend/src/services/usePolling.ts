import {useEffect, useState} from 'react'
export function usePolling<T>(load: (signal: AbortSignal) => Promise<T>) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState('')
  useEffect(() => {
    const controller = new AbortController()
    let timer: ReturnType<typeof setTimeout>
    async function refresh() {
      try { const value = await load(controller.signal); if (!controller.signal.aborted) {setData(value); setError('')} }
      catch (e) {if (!controller.signal.aborted) setError(e instanceof Error ? e.message : 'Unable to load reviews.')}
      if (!controller.signal.aborted) timer = setTimeout(refresh, 5000)
    }
    void refresh()
    return () => {controller.abort(); clearTimeout(timer)}
  }, [load])
  return {data, error}
}
