/**
 * Ids after `currentId` in queue order, without `exclude` and `currentId`, at most `count`.
 * With `wrap`, the ids before `currentId` follow (from the top of the queue).
 * Returns `null` when `currentId` is not in `queue` (e.g. the reviewer already decided it).
 */
export function idsAfter(
  queue: number[],
  currentId: number,
  count: number,
  opts: { exclude?: Set<number>; wrap?: boolean } = {}
): number[] | null {
  const i = queue.indexOf(currentId)
  if (i === -1) return null
  const order = opts.wrap ? [...queue.slice(i + 1), ...queue.slice(0, i)] : queue.slice(i + 1)
  return order.filter((id) => id !== currentId && !opts.exclude?.has(id)).slice(0, count)
}
